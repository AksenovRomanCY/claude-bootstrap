#!/usr/bin/env python3
"""Claude Code unified hook guard entrypoint."""

from __future__ import annotations

import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
HOOKS_DIR = SCRIPT_DIR.parent
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from guard.context import from_hook_payload  # noqa: E402
from guard.decisions import Decision, DecisionKind, combine  # noqa: E402
from guard.rules import evaluate  # noqa: E402
from guard.secrets import evaluate as evaluate_secrets  # noqa: E402
from guard.shell import parse  # noqa: E402
import large_file_policy  # noqa: E402
import post_write_warnings  # noqa: E402


def decision_output(decision: Decision) -> dict[str, object] | None:
    if decision.kind == DecisionKind.NONE:
        return None

    output: dict[str, object] = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
        }
    }
    hook_output = output["hookSpecificOutput"]
    assert isinstance(hook_output, dict)

    if decision.kind == DecisionKind.DENY:
        hook_output["permissionDecision"] = "deny"
        hook_output["permissionDecisionReason"] = decision.formatted_reason()
        return output

    if decision.kind == DecisionKind.ASK:
        hook_output["permissionDecision"] = "ask"
        hook_output["permissionDecisionReason"] = decision.formatted_reason()
        return output

    if decision.kind == DecisionKind.WARNING:
        hook_output["additionalContext"] = decision.formatted_reason()
        return output

    return None


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
    secret_decision = evaluate_secrets(payload)
    large_file_output = large_file_policy.run(payload)
    large_file_decision = decision_from_hook_output(large_file_output)
    return decision_output(combine([secret_decision, large_file_decision]))


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
    try:
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            return 0

        payload = json.loads(raw_input)
        if not isinstance(payload, dict):
            print("command_guard warning: hook payload must be a JSON object", file=sys.stderr)
            return 0

        output = run(payload)
        if output is not None:
            print(json.dumps(output, separators=(",", ":")))
        return 0
    except Exception as exc:  # noqa: BLE001 - hook must fail open to Claude permission flow.
        print(f"command_guard warning: internal error: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
