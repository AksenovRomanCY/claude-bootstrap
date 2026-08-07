"""Claude Code hook protocol: reading a payload, rendering a decision, failing open.

Every hook entrypoint shares one contract. It reads a JSON payload from stdin,
prints at most one JSON object on stdout, and always exits 0: a non-zero exit
from PreToolUse is itself a denial, so a guard that crashes would block the tool
call it was only meant to describe. Internal errors go to stderr, never to
stdout, because stdout is read as a decision and lands in the model's context.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Optional

from .decisions import Decision, DecisionKind


HookPayload = dict[str, object]
# `Optional[...]` rather than `... | None`: these aliases are evaluated at import
# time, where `from __future__ import annotations` does not reach, and PEP 604
# unions only became a runtime expression in 3.10. The floor is 3.9, the system
# Python on macOS.
HookOutput = Optional[dict[str, object]]
HookHandler = Callable[[HookPayload], HookOutput]


def decision_output(decision: Decision) -> HookOutput:
    """Render a decision as PreToolUse hook output, or nothing when there is none."""
    if decision.kind == DecisionKind.NONE:
        return None

    if decision.kind == DecisionKind.WARNING:
        rendered: dict[str, object] = {"additionalContext": decision.formatted_reason()}
    else:
        rendered = {
            "permissionDecision": decision.kind.value,
            "permissionDecisionReason": decision.formatted_reason(),
        }

    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", **rendered}}


def run_hook(handler: HookHandler, *, name: str) -> int:
    """Drive one hook invocation from stdin to stdout. Never raises, always exits 0."""
    try:
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            return 0

        payload = json.loads(raw_input)
        if not isinstance(payload, dict):
            print(f"{name} warning: hook payload must be a JSON object", file=sys.stderr)
            return 0

        output = handler(payload)
        if output is not None:
            print(json.dumps(output, separators=(",", ":")))
        return 0
    except Exception as exc:  # noqa: BLE001 - a guard must fail open to the permission flow.
        print(f"{name} warning: internal error: {exc}", file=sys.stderr)
        return 0
