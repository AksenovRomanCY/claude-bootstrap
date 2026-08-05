#!/usr/bin/env python3
"""Claude Code PreToolUse secret guard entrypoint."""

from __future__ import annotations

import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
HOOKS_DIR = SCRIPT_DIR.parent
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from guard.decisions import Decision, DecisionKind  # noqa: E402
from guard.secrets import evaluate  # noqa: E402


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
    return decision_output(evaluate(payload))


def main() -> int:
    try:
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            return 0

        payload = json.loads(raw_input)
        if not isinstance(payload, dict):
            print("secret_guard warning: hook payload must be a JSON object", file=sys.stderr)
            return 0

        output = run(payload)
        if output is not None:
            print(json.dumps(output, separators=(",", ":")))
        return 0
    except Exception as exc:  # noqa: BLE001 - hook must fail open without exposing content.
        print(f"secret_guard warning: internal error: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
