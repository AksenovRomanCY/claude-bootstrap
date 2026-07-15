#!/usr/bin/env python3
"""Claude Code PreToolUse large file policy hook."""

from __future__ import annotations

import fnmatch
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
HOOKS_DIR = SCRIPT_DIR.parent
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from guard.edit_content import reconstruct_edit  # noqa: E402


DEFAULT_WARNING_LINES = 800
DEFAULT_ASK_ON_CREATE_LINES = 1200
DEFAULT_ASK_ON_GROWTH_LINES = 100

DEFAULT_EXCLUDED_PATTERNS = [
    "**/generated/**",
    "**/*.generated.*",
    "**/vendor/**",
    "**/schema/**",
    "**/schemas/**",
    "**/*.schema.*",
    "**/migration/**",
    "**/migrations/**",
    "**/snapshot/**",
    "**/snapshots/**",
    "**/*.snap",
    "**/*.snapshot",
    "**/*.min.js",
    "**/*.min.css",
    "package-lock.json",
    "npm-shrinkwrap.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lockb",
    "poetry.lock",
    "Pipfile.lock",
    "Cargo.lock",
    "Gemfile.lock",
    "composer.lock",
    "go.sum",
]


@dataclass(frozen=True)
class LargeFilePolicy:
    warning_lines: int = DEFAULT_WARNING_LINES
    ask_on_create_lines: int = DEFAULT_ASK_ON_CREATE_LINES
    ask_on_growth_lines: int = DEFAULT_ASK_ON_GROWTH_LINES
    excluded_patterns: tuple[str, ...] = tuple(DEFAULT_EXCLUDED_PATTERNS)


@dataclass(frozen=True)
class FileState:
    exists: bool
    current_lines: int | None
    final_lines: int


def output_warning(reason: str) -> dict[str, object]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": f"[LARGE-FILE] {reason}",
        }
    }


def output_ask(reason: str) -> dict[str, object]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": f"[LARGE-FILE] {reason}",
        }
    }


def run(payload: dict[str, Any]) -> dict[str, object] | None:
    if payload.get("hook_event_name") != "PreToolUse":
        return None

    tool_name = payload.get("tool_name")
    if tool_name not in {"Write", "Edit"}:
        return None

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return output_warning("Unable to evaluate file size because tool_input is missing.")

    raw_file_path = tool_input.get("file_path")
    if not isinstance(raw_file_path, str) or not raw_file_path:
        return None

    cwd = payload.get("cwd")
    cwd_path = Path(cwd) if isinstance(cwd, str) and cwd else Path.cwd()
    project_root = find_project_root(cwd_path)
    file_path = resolve_file_path(raw_file_path, cwd_path)
    policy = load_policy(project_root)

    if is_excluded(file_path, project_root, policy):
        return None

    try:
        if tool_name == "Write":
            content = tool_input.get("content")
            if not isinstance(content, str):
                return output_warning("Unable to evaluate file size because Write content is missing.")
            state = write_file_state(file_path, content)
        else:
            state = edit_file_state(file_path, tool_input)
    except OSError as exc:
        return output_warning(f"Unable to evaluate file size: {exc}.")
    except ValueError as exc:
        return output_warning(str(exc))

    return decide(raw_file_path, state, policy)


def find_project_root(cwd: Path) -> Path:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=2,
            check=False,
        )
        if completed.returncode == 0 and completed.stdout.strip():
            return Path(completed.stdout.strip()).resolve()
    except (OSError, subprocess.TimeoutExpired):
        pass

    resolved = cwd.resolve()
    for candidate in [resolved, *resolved.parents]:
        if (candidate / ".git").exists():
            return candidate
    return resolved


def resolve_file_path(raw_file_path: str, cwd: Path) -> Path:
    path = Path(raw_file_path).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (cwd / path).resolve()


def load_policy(project_root: Path) -> LargeFilePolicy:
    policy = LargeFilePolicy()
    policy_file = project_root / ".claude" / "security-policy.json"

    try:
        raw_policy = json.loads(policy_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return policy

    if not isinstance(raw_policy, dict):
        return policy

    large_files = raw_policy.get("largeFiles")
    if not isinstance(large_files, dict):
        large_files = {}

    paths = raw_policy.get("paths")
    generated_patterns: list[str] = []
    if isinstance(paths, dict) and isinstance(paths.get("generated"), list):
        generated_patterns = [item for item in paths["generated"] if isinstance(item, str) and item]

    return LargeFilePolicy(
        warning_lines=positive_int(large_files.get("warningLines"), policy.warning_lines),
        ask_on_create_lines=positive_int(large_files.get("askOnCreateLines"), policy.ask_on_create_lines),
        ask_on_growth_lines=positive_int(large_files.get("askOnGrowthLines"), policy.ask_on_growth_lines),
        excluded_patterns=tuple([*policy.excluded_patterns, *generated_patterns]),
    )


def positive_int(value: object, fallback: int) -> int:
    return value if isinstance(value, int) and value >= 0 else fallback


def write_file_state(file_path: Path, content: str) -> FileState:
    current_lines = count_file_lines(file_path) if file_path.exists() else None
    return FileState(
        exists=file_path.exists(),
        current_lines=current_lines,
        final_lines=count_content_lines(content),
    )


def edit_file_state(file_path: Path, tool_input: dict[str, Any]) -> FileState:
    reconstructed = reconstruct_edit(file_path, tool_input)
    return FileState(
        exists=True,
        current_lines=count_content_lines(reconstructed.current_content),
        final_lines=count_content_lines(reconstructed.final_content),
    )


def count_file_lines(file_path: Path) -> int:
    return count_content_lines(file_path.read_text(encoding="utf-8"))


def count_content_lines(content: str) -> int:
    if content == "":
        return 0
    return len(content.splitlines())


def decide(raw_file_path: str, state: FileState, policy: LargeFilePolicy) -> dict[str, object] | None:
    final_lines = state.final_lines
    if final_lines < policy.warning_lines:
        return None

    if not state.exists:
        if final_lines > policy.ask_on_create_lines:
            return output_ask(
                f"{raw_file_path} would create a {final_lines}-line file. Confirm that a generated or split file is not better."
            )
        return output_warning(f"{raw_file_path} would create a {final_lines}-line file.")

    if state.current_lines is None:
        return output_warning(f"Unable to compare previous size for {raw_file_path}.")

    growth = final_lines - state.current_lines
    if growth <= 0:
        return None
    if growth >= policy.ask_on_growth_lines:
        return output_ask(
            f"{raw_file_path} would grow by {growth} lines to {final_lines} lines. Confirm this should stay in one file."
        )
    return output_warning(f"{raw_file_path} would grow by {growth} lines to {final_lines} lines.")


def is_excluded(file_path: Path, project_root: Path, policy: LargeFilePolicy) -> bool:
    relative = relative_to_project(file_path, project_root)
    candidates = {relative, f"./{relative}", file_path.name}
    normalized_parts = {part.lower() for part in Path(relative).parts}
    if normalized_parts.intersection({"generated", "vendor", "schema", "schemas", "migration", "migrations", "snapshot", "snapshots"}):
        return True

    for pattern in policy.excluded_patterns:
        normalized_pattern = pattern.replace("\\", "/")
        for candidate in candidates:
            if fnmatch.fnmatch(candidate, normalized_pattern):
                return True
            if normalized_pattern.startswith("**/") and fnmatch.fnmatch(candidate, normalized_pattern[3:]):
                return True
    return False


def relative_to_project(file_path: Path, project_root: Path) -> str:
    try:
        return file_path.relative_to(project_root).as_posix()
    except ValueError:
        return file_path.as_posix()


def main() -> int:
    try:
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            return 0

        payload = json.loads(raw_input)
        if not isinstance(payload, dict):
            print("large_file_policy warning: hook payload must be a JSON object", file=sys.stderr)
            return 0

        output = run(payload)
        if output is not None:
            print(json.dumps(output, separators=(",", ":")))
        return 0
    except Exception as exc:  # noqa: BLE001 - hooks must fail open.
        print(json.dumps(output_warning(f"Internal error while evaluating file size: {exc}"), separators=(",", ":")))
        return 0


if __name__ == "__main__":
    sys.exit(main())
