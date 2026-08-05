"""Pre-write secret detection rules."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .decisions import Decision, DecisionKind
from .edit_content import EditReconstructionError, reconstruct_edit


GIT_TIMEOUT_SECONDS = 2
PLACEHOLDER_MARKERS = (
    "example",
    "placeholder",
    "dummy",
    "fake",
    "test",
    "changeme",
    "change-me",
    "your-",
    "your_",
    "replace",
)

PRIVATE_KEY_PATTERN = re.compile(
    r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----.*?-----END (?:[A-Z0-9]+ )?PRIVATE KEY-----",
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

    findings = detect_secrets(secret_input.content)
    if not findings:
        return Decision.none()

    project_root = find_project_root(secret_input.cwd)
    file_class = classify_file(secret_input.file_path, project_root)
    decisions = [decision_for_finding(finding, file_class, secret_input.display_path) for finding in findings]
    return strongest(decisions)


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
    if tool_name == "Write":
        content = tool_input.get("content")
        if not isinstance(content, str) or not content:
            return None
    else:
        content = reconstruct_edit(file_path, tool_input).final_content

    return SecretInput(
        tool_name=tool_name,
        file_path=file_path,
        display_path=raw_file_path,
        content=content,
        cwd=cwd_path,
    )


def edit_display_path(payload: dict[str, Any]) -> str:
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        file_path = tool_input.get("file_path")
        if isinstance(file_path, str) and file_path:
            return file_path
    return "the target file"


def resolve_file_path(raw_file_path: str, cwd: Path) -> Path:
    path = Path(raw_file_path).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (cwd / path).resolve()


def detect_secrets(content: str) -> list[SecretFinding]:
    findings: list[SecretFinding] = []

    if any(not is_placeholder(match.group(0)) for match in PRIVATE_KEY_PATTERN.finditer(content)):
        findings.append(SecretFinding("SECRET-PRIVATE-KEY", "private key block", FindingSeverity.HIGH))

    for pattern, rule_id, secret_type in [
        (AWS_ACCESS_KEY_PATTERN, "SECRET-AWS-ACCESS-KEY", "AWS access key"),
        (GITHUB_PAT_PATTERN, "SECRET-GITHUB-PAT", "GitHub personal access token"),
        (GITLAB_PAT_PATTERN, "SECRET-GITLAB-PAT", "GitLab personal access token"),
        (SLACK_TOKEN_PATTERN, "SECRET-SLACK-TOKEN", "Slack token"),
        (CREDENTIAL_URL_PATTERN, "SECRET-CREDENTIAL-URL", "credential URL"),
    ]:
        if any(not is_placeholder(match.group(0)) for match in pattern.finditer(content)):
            findings.append(SecretFinding(rule_id, secret_type, FindingSeverity.HIGH))

    if any(not is_placeholder(match.group(0)) for match in JWT_PATTERN.finditer(content)):
        findings.append(SecretFinding("SECRET-JWT", "JWT-like token", FindingSeverity.JWT))

    if any(
        is_actionable_generic_value(generic_assignment_value(match))
        for match in GENERIC_ASSIGNMENT_PATTERN.finditer(content)
    ):
        findings.append(SecretFinding("SECRET-GENERIC-LITERAL", "generic credential assignment", FindingSeverity.GENERIC))

    return dedupe_findings(findings)


def dedupe_findings(findings: list[SecretFinding]) -> list[SecretFinding]:
    deduped: list[SecretFinding] = []
    seen: set[str] = set()
    for finding in findings:
        if finding.rule_id in seen:
            continue
        seen.add(finding.rule_id)
        deduped.append(finding)
    return deduped


def is_placeholder(value: str) -> bool:
    normalized = value.lower()
    if any(marker in normalized for marker in PLACEHOLDER_MARKERS):
        return True

    compact = re.sub(r"[^a-z0-9]", "", normalized)
    if len(compact) >= 12 and len(set(compact)) <= 2:
        return True
    if re.fullmatch(r"(?:abc|123|xyz|0+|x+|a+|1+){4,}", compact):
        return True
    return False


def is_actionable_generic_value(value: str) -> bool:
    return not is_placeholder(value) and JWT_PATTERN.fullmatch(value) is None


def generic_assignment_value(match: re.Match[str]) -> str:
    return match.group("quoted_value") or match.group("unquoted_value") or ""


def find_project_root(cwd: Path) -> Path:
    resolved = cwd.resolve()
    for candidate in [resolved, *resolved.parents]:
        if (candidate / ".git").exists():
            return candidate
    return resolved


def classify_file(file_path: Path, project_root: Path) -> FileClass:
    relative_path = relative_to_project(file_path, project_root)
    if git_path_matches(project_root, ["ls-files", "--error-unmatch", "--", relative_path]):
        return FileClass.TRACKED_SOURCE
    if git_path_matches(project_root, ["check-ignore", "-q", "--", relative_path]):
        return FileClass.IGNORED
    return FileClass.UNTRACKED_COMMITTABLE


def relative_to_project(file_path: Path, project_root: Path) -> str:
    try:
        return file_path.relative_to(project_root).as_posix()
    except ValueError:
        return file_path.as_posix()


def git_path_matches(project_root: Path, args: list[str]) -> bool:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(project_root),
            text=True,
            capture_output=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


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


def strongest(decisions: list[Decision]) -> Decision:
    if not decisions:
        return Decision.none()
    priority = {
        DecisionKind.NONE: 0,
        DecisionKind.WARNING: 1,
        DecisionKind.ASK: 2,
        DecisionKind.DENY: 3,
    }
    return max(decisions, key=lambda decision: priority[decision.kind])
