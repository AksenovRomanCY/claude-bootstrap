#!/usr/bin/env python3
"""Claude Code unified hook guard entrypoint."""

from __future__ import annotations

import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
HOOKS_DIR = SCRIPT_DIR.parent
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from guard.context import from_hook_payload  # noqa: E402
from guard.decisions import Decision, combine  # noqa: E402
from guard.edit_content import ReconstructedEdit, reconstruct_edit  # noqa: E402
from guard.hook_io import decision_output, run_hook  # noqa: E402
from guard.paths import resolve_file_path  # noqa: E402
from guard.rules import evaluate  # noqa: E402
from guard.secrets import evaluate as evaluate_secrets  # noqa: E402
from guard.shell import parse  # noqa: E402
import large_file_policy  # noqa: E402
import post_write_warnings  # noqa: E402


def run(payload: dict[str, object]) -> dict[str, object] | None:
    hook_event_name = payload.get("hook_event_name")
    tool_name = payload.get("tool_name")

    if hook_event_name == "PreToolUse" and tool_name in {"Write", "Edit"}:
        return run_pre_write_guard(payload)

    if hook_event_name == "PostToolUse" and tool_name in {"Write", "Edit"}:
        return post_write_warnings.run(payload)

    if hook_event_name not in {None, "", "PreToolUse"}:
        return None

    return run_bash_guard(payload)


def run_bash_guard(payload: dict[str, object]) -> dict[str, object] | None:
    context = from_hook_payload(payload)
    if not context.is_bash_pre_tool_use or not context.command:
        return None

    parsed = parse(context.command)
    decision = combine(evaluate(context, parsed))
    return decision_output(decision)


def run_pre_write_guard(payload: dict[str, object]) -> dict[str, object] | None:
    reconstructed = reconstructed_edit(payload)
    secret_decision = evaluate_secrets(payload, reconstructed)
    large_file_output = large_file_policy.run(payload, reconstructed)
    large_file_decision = decision_from_hook_output(large_file_output)
    return decision_output(combine([secret_decision, large_file_decision]))


def reconstructed_edit(payload: dict[str, object]) -> ReconstructedEdit | None:
    """The Edit result, applied once for both rules instead of once each.

    A reconstruction that fails is left to the rules: each already reports it in
    its own terms, and redoing the work on that path costs nothing, because the
    edit is not going to apply either.
    """
    if payload.get("tool_name") != "Edit":
        return None

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None

    raw_file_path = tool_input.get("file_path")
    if not isinstance(raw_file_path, str) or not raw_file_path:
        return None

    cwd = payload.get("cwd")
    cwd_path = Path(cwd) if isinstance(cwd, str) and cwd else Path.cwd()
    try:
        return reconstruct_edit(resolve_file_path(raw_file_path, cwd_path), tool_input)
    except (OSError, ValueError):
        return None


def decision_from_hook_output(output: dict[str, object] | None) -> Decision:
    if output is None:
        return Decision.none()

    hook_output = output.get("hookSpecificOutput")
    if not isinstance(hook_output, dict):
        return Decision.none()

    decision = hook_output.get("permissionDecision")
    if decision == "deny":
        return Decision.deny("", string_value(hook_output.get("permissionDecisionReason")))
    if decision == "ask":
        return Decision.ask("", string_value(hook_output.get("permissionDecisionReason")))

    additional_context = hook_output.get("additionalContext")
    if isinstance(additional_context, str) and additional_context:
        return Decision.warning("", additional_context)

    return Decision.none()


def string_value(value: object) -> str:
    return value if isinstance(value, str) else ""


def main() -> int:
    return run_hook(run, name="command_guard")


if __name__ == "__main__":
    sys.exit(main())
