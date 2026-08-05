"""Filesystem command guard rules."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .context import HookContext
from .decisions import Decision
from .shell import CommandSegment, ShellParseResult


DISK_TOOLS = {"wipefs", "fdisk", "parted"}
GLOB_MARKERS = ("*", "?", "[")


@dataclass(frozen=True)
class PathTarget:
    raw: str
    path: Path | None
    uncertain: bool = False


@dataclass(frozen=True)
class FilesystemContext:
    cwd: Path
    project_root: Path
    home: Path


def evaluate(context: HookContext, parsed: ShellParseResult) -> list[Decision]:
    fs_context = FilesystemContext(
        cwd=normalize_existing_path(context.cwd),
        project_root=find_project_root(context.cwd),
        home=Path.home(),
    )
    decisions: list[Decision] = []

    for segment in parsed.segments:
        decisions.extend(evaluate_segment(segment, fs_context))

    return decisions


def evaluate_segment(segment: CommandSegment, context: FilesystemContext) -> list[Decision]:
    decisions: list[Decision] = []

    if "sudo" in segment.wrappers:
        decisions.append(Decision.ask("FS-SUDO", "Confirm sudo command because it can modify system state."))

    raw_command = segment.command
    if raw_command is None:
        return decisions
    command = Path(raw_command).name

    if is_disk_tool(command):
        decisions.append(Decision.deny("FS-DISK-TOOL", f"Do not run destructive disk utility {command}."))
    elif command == "dd" and dd_writes_device(segment.args):
        decisions.append(Decision.deny("FS-DD-DEVICE", "Do not write directly to /dev devices with dd."))
    elif command == "rm":
        decisions.extend(evaluate_rm(segment, context))
    elif command in {"chmod", "chown"} and has_recursive_flag(segment.args):
        decisions.append(
            Decision.ask(
                f"FS-{command.upper()}-RECURSIVE",
                f"Confirm recursive {command}; it can affect many files.",
            )
        )

    return decisions


def is_disk_tool(command: str) -> bool:
    return command in DISK_TOOLS or command == "mkfs" or command.startswith("mkfs.")


def dd_writes_device(args: list[str]) -> bool:
    index = 0
    while index < len(args):
        token = args[index]
        if token.startswith("of=/dev/") or token == "of=/dev":
            return True
        if token == "of" and index + 1 < len(args) and args[index + 1].startswith("/dev/"):
            return True
        index += 1
    return False


def evaluate_rm(segment: CommandSegment, context: FilesystemContext) -> list[Decision]:
    if not rm_is_recursive_force(segment.args):
        return []

    path_args = positional_args(segment.args, set())
    if not path_args:
        return []

    decisions: list[Decision] = []
    for raw_path in path_args:
        target = normalize_target(raw_path, context)
        if target.uncertain:
            decisions.append(
                Decision.ask(
                    "FS-RM-RF-UNCERTAIN",
                    f"Confirm rm -rf target with unresolved shell syntax: {raw_path}.",
                )
            )
            continue

        if target.path is not None and is_critical_rm_target(target.path, context):
            decisions.append(
                Decision.deny(
                    "FS-RM-RF-CRITICAL",
                    f"Do not recursively delete critical path: {raw_path}.",
                )
            )
            continue

        decisions.append(Decision.ask("FS-RM-RF", f"Confirm recursive deletion of {raw_path}."))

    return decisions


def rm_is_recursive_force(args: list[str]) -> bool:
    recursive = False
    force = False

    for token in args:
        if token == "--":
            break
        if token in {"-r", "-R", "--recursive"}:
            recursive = True
        elif token in {"-f", "--force"}:
            force = True
        elif token.startswith("-") and not token.startswith("--"):
            flags = token[1:]
            recursive = recursive or "r" in flags or "R" in flags
            force = force or "f" in flags

    return recursive and force


def has_recursive_flag(args: list[str]) -> bool:
    for token in args:
        if token == "--":
            break
        if token in {"-R", "-r", "--recursive"}:
            return True
        if token.startswith("-") and not token.startswith("--") and ("R" in token[1:] or "r" in token[1:]):
            return True
    return False


def positional_args(args: list[str], value_options: set[str]) -> list[str]:
    positionals: list[str] = []
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            positionals.extend(args[index + 1 :])
            break
        if token in value_options:
            index += 2
            continue
        if token.startswith("--") and any(token.startswith(f"{option}=") for option in value_options):
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        positionals.append(token)
        index += 1
    return positionals


def normalize_target(raw_path: str, context: FilesystemContext) -> PathTarget:
    if has_uncertain_shell_syntax(raw_path):
        return PathTarget(raw=raw_path, path=None, uncertain=True)

    expanded = raw_path
    if expanded == "~" or expanded.startswith("~/"):
        expanded = str(context.home) + expanded[1:]
    elif expanded == "$HOME" or expanded.startswith("$HOME/"):
        expanded = str(context.home) + expanded[len("$HOME") :]
    elif expanded == "${HOME}" or expanded.startswith("${HOME}/"):
        expanded = str(context.home) + expanded[len("${HOME}") :]

    if "$" in expanded:
        return PathTarget(raw=raw_path, path=None, uncertain=True)

    if os.path.isabs(expanded):
        absolute = expanded
    else:
        absolute = os.path.join(str(context.cwd), expanded)

    normalized = os.path.normpath(absolute)
    return PathTarget(raw=raw_path, path=Path(normalized))


def has_uncertain_shell_syntax(raw_path: str) -> bool:
    if "$(" in raw_path or "`" in raw_path:
        return True
    if any(marker in raw_path for marker in GLOB_MARKERS):
        return True
    if "$" in raw_path and not (
        raw_path == "$HOME"
        or raw_path.startswith("$HOME/")
        or raw_path == "${HOME}"
        or raw_path.startswith("${HOME}/")
    ):
        return True
    return False


def is_critical_rm_target(path: Path, context: FilesystemContext) -> bool:
    critical_paths = {
        Path("/"),
        normalize_existing_path(context.home),
        context.project_root,
        context.project_root.parent,
        context.project_root / ".git",
    }
    return path in critical_paths


def find_project_root(cwd: Path) -> Path:
    current = normalize_existing_path(cwd)
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists() or (candidate / ".claude").exists():
            return candidate
    return current


def normalize_existing_path(path: Path) -> Path:
    return Path(os.path.normpath(os.path.abspath(str(path))))
