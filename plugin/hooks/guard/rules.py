"""Foundation guard rules."""

from __future__ import annotations

from .context import HookContext
from .decisions import Decision
from .shell import ShellParseResult


def evaluate(context: HookContext, parsed: ShellParseResult) -> list[Decision]:
    decisions: list[Decision] = []

    if not context.is_bash_pre_tool_use:
        return decisions

    if parsed.unsupported:
        constructs = ", ".join(parsed.unsupported)
        decisions.append(
            Decision.warning(
                "UNSUPPORTED-SHELL",
                f"Command contains unsupported shell constructs: {constructs}. Standard permission flow should review it.",
            )
        )

    return decisions
