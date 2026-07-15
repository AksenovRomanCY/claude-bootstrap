"""Foundation guard rules."""

from __future__ import annotations

from .context import HookContext
from .decisions import Decision
from .database import evaluate as evaluate_database
from .filesystem import evaluate as evaluate_filesystem
from .git import evaluate as evaluate_git
from .infrastructure import evaluate as evaluate_infrastructure
from .shell import ShellParseResult


def evaluate(context: HookContext, parsed: ShellParseResult) -> list[Decision]:
    decisions: list[Decision] = []

    if not context.is_bash_pre_tool_use:
        return decisions

    decisions.extend(evaluate_git(context, parsed))
    decisions.extend(evaluate_infrastructure(context, parsed))
    decisions.extend(evaluate_database(context, parsed))
    decisions.extend(evaluate_filesystem(context, parsed))

    if parsed.unsupported:
        constructs = ", ".join(parsed.unsupported)
        reason = f"Command contains unsupported shell constructs: {constructs}. Standard permission flow should review it."
        decisions.append(Decision.ask("UNSUPPORTED-SHELL", reason))

    return decisions
