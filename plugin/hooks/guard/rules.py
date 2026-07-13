"""Foundation guard rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .context import HookContext
from .decisions import Decision
from .database import evaluate as evaluate_database
from .filesystem import evaluate as evaluate_filesystem
from .filesystem import find_project_root
from .git import evaluate as evaluate_git
from .infrastructure import evaluate as evaluate_infrastructure
from .shell import ShellParseResult


def evaluate(context: HookContext, parsed: ShellParseResult) -> list[Decision]:
    decisions: list[Decision] = []

    if not context.is_bash_pre_tool_use:
        return decisions

    if parsed.unsupported:
        constructs = ", ".join(parsed.unsupported)
        reason = f"Command contains unsupported shell constructs: {constructs}. Standard permission flow should review it."
        if parser_uncertainty_requires_ask(context.cwd):
            decisions.append(Decision.ask("UNSUPPORTED-SHELL", reason))
        else:
            decisions.append(Decision.warning("UNSUPPORTED-SHELL", reason))

    decisions.extend(evaluate_git(context, parsed))
    decisions.extend(evaluate_infrastructure(context, parsed))
    decisions.extend(evaluate_database(context, parsed))
    decisions.extend(evaluate_filesystem(context, parsed))

    return decisions


def parser_uncertainty_requires_ask(cwd: Path) -> bool:
    policy_file = find_project_root(cwd) / ".claude" / "security-policy.json"
    try:
        raw_policy: Any = json.loads(policy_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False

    command_guard = raw_policy.get("commandGuard") if isinstance(raw_policy, dict) else None
    if not isinstance(command_guard, dict):
        return False
    return command_guard.get("parserUncertainty") == "ask"
