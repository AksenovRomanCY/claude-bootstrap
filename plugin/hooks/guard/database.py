"""Database command guard rules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .context import HookContext
from .decisions import Decision
from .paths import find_project_root
from .policy import load_policy, policy_section
from .shell import CommandSegment, ShellParseResult, normalized_command


SQL_PATTERNS = (
    re.compile(r"\bdrop\s+database\b", re.IGNORECASE),
    re.compile(r"\bdrop\s+schema\b", re.IGNORECASE),
    re.compile(r"\bdrop\s+table\b", re.IGNORECASE),
    re.compile(r"\btruncate(?:\s+table)?\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class DatabasePolicy:
    destructive_operations: str = "ask"
    enabled: bool = False


def evaluate(context: HookContext, parsed: ShellParseResult) -> list[Decision]:
    policy = load_database_policy(find_project_root(context.cwd))
    if not policy.enabled:
        return []

    decisions: list[Decision] = []
    for segment in parsed.segments:
        if is_destructive_database_command(segment):
            if policy.destructive_operations == "deny":
                decisions.append(
                    Decision.deny(
                        "DB-DESTRUCTIVE",
                        "Do not run high-confidence destructive database operations from the shell.",
                    )
                )
            else:
                decisions.append(
                    Decision.ask(
                        "DB-DESTRUCTIVE",
                        "Confirm high-confidence destructive database operation.",
                    )
                )
    return decisions


def is_destructive_database_command(segment: CommandSegment) -> bool:
    command = normalized_command(segment)
    args = segment.args

    if command in {"psql", "mysql"}:
        return any(is_destructive_sql(sql) for sql in command_values(args, {"-c", "--command", "-e", "--execute"}))

    if command == "sqlite3":
        sql_args = [arg for arg in args[1:] if not arg.startswith("-")]
        return any(is_destructive_sql(sql) for sql in sql_args)

    if command == "prisma" and args[:2] == ["migrate", "reset"]:
        return True

    if command == "alembic" and args[:2] == ["downgrade", "base"]:
        return True

    return False


def command_values(args: list[str], options: set[str]) -> list[str]:
    values: list[str] = []
    index = 0
    while index < len(args):
        token = args[index]
        if token in options and index + 1 < len(args):
            values.append(args[index + 1])
            index += 2
            continue
        for option in options:
            if token.startswith(f"{option}="):
                values.append(token.split("=", 1)[1])
                break
        index += 1
    return values


def is_destructive_sql(sql: str) -> bool:
    return any(pattern.search(sql) for pattern in SQL_PATTERNS)


def load_database_policy(project_root: Path) -> DatabasePolicy:
    database = policy_section(load_policy(project_root), "database")
    destructive_operations = database.get("destructiveOperations")
    if destructive_operations not in {"ask", "deny"}:
        return DatabasePolicy()

    return DatabasePolicy(
        destructive_operations=destructive_operations,
        enabled=True,
    )
