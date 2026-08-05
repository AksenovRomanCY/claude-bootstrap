"""Pre-write secret detection rules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .decisions import Decision, combine, dedupe_by_rule_id
from .edit_content import EditReconstructionError, reconstruct_edit
from .paths import find_project_root, path_matches_patterns, relative_to_project, resolve_file_path
from .policy import load_policy, policy_section, string_list
from .process import command_succeeds


# Matched against delimiter/camelCase-bounded parts of the candidate value,
# never as raw substrings ("latest" must not count as "test").
PLACEHOLDER_MARKERS = frozenset(
    {
        "example",
        "placeholder",
        "dummy",
        "fake",
        "test",
        "changeme",
        "your",
        "replace",
    }
)

PRIVATE_KEY_PATTERN = re.compile(
    r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----(.*?)-----END (?:[A-Z0-9]+ )?PRIVATE KEY-----",
    re.DOTALL,
)
AWS_ACCESS_KEY_PATTERN = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
GITHUB_PAT_PATTERN = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{22,})\b")
GITLAB_PAT_PATTERN = re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b")
SLACK_TOKEN_PATTERN = re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")
CREDENTIAL_URL_PATTERN = re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:([^@\s/]{6,})@[^/\s]+", re.IGNORECASE)
JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{8,}\b")
GENERIC_ASSIGNMENT_PATTERN = re.compile(
    r"""(?ix)
    \b
    (?:[a-z0-9]+[_-])*
    (?:api[_-]?key|api[_-]?secret|secret[_-]?key|access[_-]?token|auth[_-]?token|refresh[_-]?token|
       client[_-]?secret|private[_-]?key|password|passwd|pwd|token|secret)
    (?:[_-][a-z0-9]+)*
    \b
    \s*[:=]\s*
    (?:
        (?P<quote>['"])
        (?P<quoted_value>[A-Za-z0-9_./+=:@$!%-]{16,})
        (?P=quote)
        |
        (?P<unquoted_value>[A-Za-z0-9_./+=:@$!%-]{16,})
    )
    """
)


class FileClass(str, Enum):
    TRACKED_SOURCE = "tracked source"
    IGNORED = "ignored file"
    UNTRACKED_COMMITTABLE = "untracked committable file"


class FindingSeverity(str, Enum):
    HIGH = "high"
    GENERIC = "generic"
    JWT = "jwt"


@dataclass(frozen=True)
class SecretFinding:
    rule_id: str
    secret_type: str
    severity: FindingSeverity


@dataclass(frozen=True)
class SecretInput:
    tool_name: str
    file_path: Path
    display_path: str
    content: str
    cwd: Path
    baseline_content: str | None = None


def evaluate(payload: dict[str, Any]) -> Decision:
    try:
        secret_input = extract_secret_input(payload)
    except (OSError, EditReconstructionError) as exc:
        if payload.get("tool_name") != "Edit":
            raise
        display_path = edit_display_path(payload)
        return Decision.ask(
            "SECRET-EDIT-UNCERTAIN",
            f"Unable to reconstruct Edit result for {display_path}: {exc} Confirm the edit before applying it.",
        )
    if secret_input is None:
        return Decision.none()

    findings = new_findings(secret_input.content, secret_input.baseline_content)
    if not findings:
        return Decision.none()

    project_root = find_project_root(secret_input.cwd)
    if path_matches_patterns(secret_input.file_path, project_root, load_allow_paths(project_root)):
        return Decision.warning(
            "SECRET-ALLOWED-PATH",
            f"Detected {findings[0].secret_type} in {secret_input.display_path}, "
            "allowed by secrets.allowPaths in .claude/security-policy.json.",
        )

    file_class = classify_file(secret_input.file_path, project_root)
    decisions = [decision_for_finding(finding, file_class, secret_input.display_path) for finding in findings]
    return combine(decisions)


def new_findings(content: str, baseline_content: str | None) -> list[SecretFinding]:
    """Findings the write introduces, ignoring what the file already contained.

    Scanning the whole reconstructed file would make every future Edit of a file
    that already holds a secret undeniable, including the edit that removes it.
    """
    findings = detect_secrets(content)
    if baseline_content is None or not findings:
        return findings
    already_present = {finding.rule_id for finding in detect_secrets(baseline_content)}
    return [finding for finding in findings if finding.rule_id not in already_present]


def extract_secret_input(payload: dict[str, Any]) -> SecretInput | None:
    if payload.get("hook_event_name") != "PreToolUse":
        return None

    tool_name = payload.get("tool_name")
    if tool_name not in {"Write", "Edit"}:
        return None

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None

    raw_file_path = tool_input.get("file_path")
    if not isinstance(raw_file_path, str) or not raw_file_path:
        return None

    cwd = payload.get("cwd")
    cwd_path = Path(cwd) if isinstance(cwd, str) and cwd else Path.cwd()
    file_path = resolve_file_path(raw_file_path, cwd_path)
    baseline_content: str | None = None
    if tool_name == "Write":
        content = tool_input.get("content")
        if not isinstance(content, str) or not content:
            return None
    else:
        reconstructed = reconstruct_edit(file_path, tool_input)
        content = reconstructed.final_content
        baseline_content = reconstructed.current_content

    return SecretInput(
        tool_name=tool_name,
        file_path=file_path,
        display_path=raw_file_path,
        content=content,
        cwd=cwd_path,
        baseline_content=baseline_content,
    )


def edit_display_path(payload: dict[str, Any]) -> str:
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        file_path = tool_input.get("file_path")
        if isinstance(file_path, str) and file_path:
            return file_path
    return "the target file"


def detect_secrets(content: str) -> list[SecretFinding]:
    findings: list[SecretFinding] = []

    # Only the key body decides whether a PEM block is a sample; a marker in the
    # armor or in surrounding text must not suppress detection.
    if any(not is_placeholder(match.group(1)) for match in PRIVATE_KEY_PATTERN.finditer(content)):
        findings.append(SecretFinding("SECRET-PRIVATE-KEY", "private key block", FindingSeverity.HIGH))

    # Strict-format patterns are not run through is_placeholder: the format itself
    # proves the value is a key, so "AKIATESTQWERTY123456" must still be denied.
    # Use secrets.allowPaths to exempt fixture and documentation files.
    for pattern, rule_id, secret_type in [
        (AWS_ACCESS_KEY_PATTERN, "SECRET-AWS-ACCESS-KEY", "AWS access key"),
        (GITHUB_PAT_PATTERN, "SECRET-GITHUB-PAT", "GitHub personal access token"),
        (GITLAB_PAT_PATTERN, "SECRET-GITLAB-PAT", "GitLab personal access token"),
        (SLACK_TOKEN_PATTERN, "SECRET-SLACK-TOKEN", "Slack token"),
    ]:
        if pattern.search(content) is not None:
            findings.append(SecretFinding(rule_id, secret_type, FindingSeverity.HIGH))

    # Only the captured password is a placeholder candidate; scheme and host are not.
    if any(not is_placeholder(match.group(1)) for match in CREDENTIAL_URL_PATTERN.finditer(content)):
        findings.append(SecretFinding("SECRET-CREDENTIAL-URL", "credential URL", FindingSeverity.HIGH))

    if JWT_PATTERN.search(content) is not None:
        findings.append(SecretFinding("SECRET-JWT", "JWT-like token", FindingSeverity.JWT))

    if any(
        is_actionable_generic_value(value, quoted=quoted)
        for value, quoted in (generic_assignment_value(match) for match in GENERIC_ASSIGNMENT_PATTERN.finditer(content))
    ):
        findings.append(SecretFinding("SECRET-GENERIC-LITERAL", "generic credential assignment", FindingSeverity.GENERIC))

    return dedupe_by_rule_id(findings)


def is_placeholder(value: str) -> bool:
    parts = placeholder_parts(value)
    if PLACEHOLDER_MARKERS & parts:
        return True
    if {"change", "me"} <= parts:
        return True

    compact = re.sub(r"[^a-z0-9]", "", value.lower())
    if len(compact) >= 12 and len(set(compact)) <= 2:
        return True
    if re.fullmatch(r"(?:abc|123|xyz|0+|x+|a+|1+){4,}", compact):
        return True
    return False


def placeholder_parts(value: str) -> set[str]:
    """Word-like parts of a value, so markers match "my-test-key" but not "latest"."""
    split_camel_case = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", value)
    return {part for part in re.split(r"[^A-Za-z0-9]+", split_camel_case.lower()) if part}


def is_actionable_generic_value(value: str, *, quoted: bool) -> bool:
    if is_placeholder(value) or JWT_PATTERN.fullmatch(value) is not None:
        return False
    return quoted or is_literal_looking_value(value)


def is_literal_looking_value(value: str) -> bool:
    """Reject unquoted references to a secret, which are the recommended pattern.

    `apiKey = process.env.API_KEY` reads a secret safely; flagging it turns every
    later edit of the file into a prompt, which is how hooks end up disabled.
    """
    if value.startswith("$"):
        return False
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+", value):
        return False
    if re.fullmatch(r"[A-Za-z_]+", value):
        return False
    return True


def generic_assignment_value(match: re.Match[str]) -> tuple[str, bool]:
    quoted_value = match.group("quoted_value")
    if quoted_value:
        return quoted_value, True
    return match.group("unquoted_value") or "", False


def load_allow_paths(project_root: Path) -> list[str]:
    return string_list(policy_section(load_policy(project_root), "secrets").get("allowPaths"))


def classify_file(file_path: Path, project_root: Path) -> FileClass:
    relative_path = relative_to_project(file_path, project_root)
    if command_succeeds(project_root, ["git", "ls-files", "--error-unmatch", "--", relative_path]):
        return FileClass.TRACKED_SOURCE
    if command_succeeds(project_root, ["git", "check-ignore", "-q", "--", relative_path]):
        return FileClass.IGNORED
    return FileClass.UNTRACKED_COMMITTABLE


def decision_for_finding(finding: SecretFinding, file_class: FileClass, display_path: str) -> Decision:
    if file_class == FileClass.IGNORED:
        return Decision.ask(
            "SECRET-IGNORED-FILE",
            reason_for(finding.secret_type, display_path, "Confirm this secret belongs only in an ignored local file."),
        )

    if finding.severity == FindingSeverity.HIGH:
        return Decision.deny(
            finding.rule_id,
            reason_for(finding.secret_type, display_path, "Move it to a secret manager or environment variable and rotate it if real."),
        )

    if finding.severity == FindingSeverity.GENERIC:
        return Decision.ask(
            finding.rule_id,
            reason_for(finding.secret_type, display_path, "Confirm this is not a real secret or move it out of source."),
        )

    return Decision.warning(
        finding.rule_id,
        reason_for(finding.secret_type, display_path, "Confirm fixture/example tokens are clearly fake."),
    )


def reason_for(secret_type: str, display_path: str, remediation: str) -> str:
    return f"Detected {secret_type} in {display_path}. {remediation}"
