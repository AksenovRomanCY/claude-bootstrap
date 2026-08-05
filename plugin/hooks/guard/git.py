"""Git command guard rules."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .context import HookContext
from .decisions import Decision
from .options import has_option, has_positional, positional_args
from .policy import load_policy, string_list
from .process import command_output
from .shell import CommandSegment, ShellParseResult


DEFAULT_PROTECTED_BRANCHES = ["main", "master"]

GIT_GLOBAL_OPTIONS_WITH_VALUES = {
    "-C",
    "-c",
    "--config-env",
    "--git-dir",
    "--work-tree",
    "--namespace",
    "--exec-path",
}
GIT_CONFIG_VALUE_OPTIONS = {"-c", "--config-env"}
# Config keys that disable repository hooks outright.
HOOK_BYPASS_CONFIG_KEYS = {"core.hookspath"}
# Config keys whose value git executes as a command.
EXECUTING_CONFIG_KEYS = {
    "core.fsmonitor",
    "core.pager",
    "core.editor",
    "core.sshcommand",
    "diff.external",
    "credential.helper",
    "sequence.editor",
}
COMMIT_OPTIONS_WITH_VALUES = {
    "-m",
    "--message",
    "-F",
    "--file",
    "-C",
    "-c",
    "--reuse-message",
    "--reedit-message",
    "--fixup",
    "--squash",
    "--author",
    "--date",
    "-S",
    "--gpg-sign",
}
PUSH_OPTIONS_WITH_VALUES = {
    "--repo",
    "--receive-pack",
    "--exec",
    "--signed",
    "--push-option",
    "-o",
}
RESTORE_OPTIONS_WITH_VALUES = {
    "-s",
    "--source",
    "--pathspec-from-file",
}


@dataclass(frozen=True)
class GitInvocation:
    segment: CommandSegment
    subcommand: str
    args: list[str]
    config_overrides: tuple[str, ...] = ()


@dataclass(frozen=True)
class GitContext:
    project_root: Path
    current_branch: str | None
    dirty: bool | None
    protected_branches: list[str]


def evaluate(context: HookContext, parsed: ShellParseResult) -> list[Decision]:
    invocations = [invocation for segment in parsed.segments if (invocation := parse_git_invocation(segment))]
    if not invocations:
        return []

    git_context = load_git_context(context.cwd)
    decisions: list[Decision] = []
    for invocation in invocations:
        decisions.extend(evaluate_invocation(invocation, git_context))
    return decisions


def parse_git_invocation(segment: CommandSegment) -> GitInvocation | None:
    words = segment.words
    if not words or Path(words[0]).name != "git":
        return None

    index = 1
    config_overrides: list[str] = []
    while index < len(words):
        token = words[index]
        if token == "--":
            return None
        if token in GIT_GLOBAL_OPTIONS_WITH_VALUES:
            if token in GIT_CONFIG_VALUE_OPTIONS and index + 1 < len(words):
                config_overrides.append(words[index + 1])
            index += 2
            continue
        if any(token.startswith(f"{option}=") for option in GIT_GLOBAL_OPTIONS_WITH_VALUES if option.startswith("--")):
            if token.startswith("--config-env="):
                config_overrides.append(token.split("=", 1)[1])
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        return GitInvocation(
            segment=segment,
            subcommand=token,
            args=words[index + 1 :],
            config_overrides=tuple(config_overrides),
        )

    return None


def load_git_context(cwd: Path) -> GitContext:
    project_root = command_output(cwd, ["git", "rev-parse", "--show-toplevel"])
    root = Path(project_root).resolve() if project_root else cwd.resolve()
    current_branch = command_output(cwd, ["git", "branch", "--show-current"]) or None
    status = command_output(cwd, ["git", "status", "--porcelain"])
    dirty = None if status is None else bool(status.strip())

    return GitContext(
        project_root=root,
        current_branch=current_branch,
        dirty=dirty,
        protected_branches=load_protected_branches(root),
    )


def load_protected_branches(project_root: Path) -> list[str]:
    branches = string_list(load_policy(project_root).get("protectedBranches"))
    return branches or DEFAULT_PROTECTED_BRANCHES


def evaluate_invocation(invocation: GitInvocation, context: GitContext) -> list[Decision]:
    subcommand = invocation.subcommand
    config_decisions = evaluate_config_overrides(invocation.config_overrides)
    if config_decisions:
        return config_decisions

    if has_bypass_environment(invocation.segment) and subcommand in {"commit", "push"}:
        return [
            Decision.deny(
                "GIT-HOOK-BYPASS",
                f"Do not bypass repository hooks with environment variables during git {subcommand}.",
            )
        ]

    if subcommand == "commit":
        return evaluate_commit(invocation)
    if subcommand == "push":
        return evaluate_push(invocation, context)
    if subcommand == "branch":
        return evaluate_branch(invocation, context)
    if subcommand == "stash":
        return evaluate_stash(invocation)
    if subcommand == "reset":
        return evaluate_reset(invocation, context)
    if subcommand == "clean":
        return evaluate_clean(invocation)
    if subcommand == "restore":
        return evaluate_restore(invocation)
    if subcommand == "checkout":
        return evaluate_checkout(invocation)

    return []


def evaluate_config_overrides(config_overrides: tuple[str, ...]) -> list[Decision]:
    """`git -c core.hooksPath=/dev/null commit` is the most direct hook bypass there is."""
    decisions: list[Decision] = []
    for override in config_overrides:
        key = override.split("=", 1)[0].strip().lower()
        if key in HOOK_BYPASS_CONFIG_KEYS:
            decisions.append(
                Decision.deny(
                    "GIT-HOOK-BYPASS",
                    f"Do not bypass repository hooks with git -c {key}.",
                )
            )
        elif key in EXECUTING_CONFIG_KEYS:
            decisions.append(
                Decision.ask(
                    "GIT-CONFIG-OVERRIDE",
                    f"git -c {key} makes git run the configured value as a command. Confirm it is intended.",
                )
            )
    return decisions


def has_bypass_environment(segment: CommandSegment) -> bool:
    return segment.env.get("HUSKY") == "0" or "SKIP" in segment.env


def evaluate_commit(invocation: GitInvocation) -> list[Decision]:
    if has_no_verify(invocation.args, COMMIT_OPTIONS_WITH_VALUES, short_alias="-n"):
        return [Decision.deny("GIT-HOOK-BYPASS", "Do not bypass hooks with git commit --no-verify or -n.")]
    return []


def evaluate_push(invocation: GitInvocation, context: GitContext) -> list[Decision]:
    if has_no_verify(invocation.args, PUSH_OPTIONS_WITH_VALUES):
        return [Decision.deny("GIT-HOOK-BYPASS", "Do not bypass hooks with git push --no-verify.")]
    if has_option(invocation.args, ["--mirror"]):
        return [
            Decision.deny(
                "GIT-PUSH-MIRROR",
                "Do not mirror all refs. Push an explicit refspec instead.",
            )
        ]

    decisions: list[Decision] = []
    force = push_force_kind(invocation.args)
    if force is not None:
        branches = push_target_branches(invocation.args, context.current_branch)
        if any(is_protected_branch(branch, context.protected_branches) for branch in branches):
            decisions.append(Decision.deny(
                "GIT-PROTECTED-BRANCH",
                f"Do not force push protected branches: {', '.join(context.protected_branches)}.",
            ))
        else:
            decisions.append(
                Decision.ask(
                    "GIT-FORCE-PUSH",
                    f"Confirm git push {force} for non-protected or unknown branch context.",
                )
            )

    delete_branches = push_delete_target_branches(invocation.args)
    if delete_branches:
        if any(is_protected_branch(branch, context.protected_branches) for branch in delete_branches):
            decisions.append(Decision.deny(
                "GIT-PROTECTED-BRANCH",
                f"Do not delete remote protected branches: {', '.join(context.protected_branches)}.",
            ))
        else:
            decisions.append(Decision.ask("GIT-REMOTE-BRANCH-DELETE", "Confirm remote branch deletion with git push."))

    return decisions


def evaluate_branch(invocation: GitInvocation, context: GitContext) -> list[Decision]:
    if not branch_force_delete(invocation.args):
        return []

    deleted_branches = branch_delete_targets(invocation.args)
    if any(is_protected_branch(branch, context.protected_branches) for branch in deleted_branches):
        return [
            Decision.deny(
                "GIT-PROTECTED-BRANCH",
                f"Do not delete protected branches: {', '.join(context.protected_branches)}.",
            )
        ]
    return []


def evaluate_stash(invocation: GitInvocation) -> list[Decision]:
    if not invocation.args:
        return []
    action = invocation.args[0]
    if action == "clear":
        return [Decision.deny("GIT-STASH-CLEAR", "Do not clear all git stashes.")]
    if action == "drop":
        return [Decision.ask("GIT-STASH-DROP", "Confirm dropping a git stash entry.")]
    return []


def evaluate_reset(invocation: GitInvocation, context: GitContext) -> list[Decision]:
    if "--hard" not in invocation.args:
        return []
    if context.dirty is True:
        return [Decision.deny("GIT-RESET-HARD", "git reset --hard would discard uncommitted changes.")]
    return [Decision.ask("GIT-RESET-HARD", "Confirm git reset --hard.")]


def evaluate_clean(invocation: GitInvocation) -> list[Decision]:
    if has_option(invocation.args, ["--force"], short_letters="f"):
        return [Decision.ask("GIT-CLEAN-FORCE", "Confirm git clean with force flags.")]
    return []


def evaluate_restore(invocation: GitInvocation) -> list[Decision]:
    if has_help_option(invocation.args):
        return []
    if has_positional(invocation.args, RESTORE_OPTIONS_WITH_VALUES):
        return [Decision.ask("GIT-RESTORE", "Confirm git restore because it may discard file changes.")]
    return []


def evaluate_checkout(invocation: GitInvocation) -> list[Decision]:
    if "--" in invocation.args:
        separator = invocation.args.index("--")
        if invocation.args[separator + 1 :]:
            return [Decision.ask("GIT-CHECKOUT-PATH", "Confirm git checkout -- <path> because it may discard changes.")]
    return []


def has_no_verify(args: list[str], value_options: set[str], *, short_alias: str | None = None) -> bool:
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            return False
        if token == "--no-verify" or (short_alias is not None and token == short_alias):
            return True
        if short_alias is not None and has_short_alias_in_cluster(token, short_alias, value_options):
            return True
        if option_takes_value(token, value_options):
            index += 2
            continue
        index += 1
    return False


def has_short_alias_in_cluster(token: str, short_alias: str, value_options: set[str]) -> bool:
    if not token.startswith("-") or token.startswith("--") or len(short_alias) != 2:
        return False

    alias = short_alias[1]
    value_option_chars = {
        option[1]
        for option in value_options
        if option.startswith("-") and not option.startswith("--") and len(option) == 2
    }
    for char in token[1:]:
        if char == alias:
            return True
        if char in value_option_chars:
            return False
    return False


def push_force_kind(args: list[str]) -> str | None:
    for token in args:
        if token == "--":
            return None
        if token == "--force" or token == "-f" or (token.startswith("-") and not token.startswith("--") and "f" in token[1:]):
            return "--force"
        if token == "--force-with-lease" or token.startswith("--force-with-lease="):
            return "--force-with-lease"
    if any(refspec.startswith("+") for refspec in push_refspecs(args)):
        return "+refspec"
    return None


def push_target_branches(args: list[str], current_branch: str | None) -> list[str]:
    refspecs = push_refspecs(args)
    branches = [branch_from_refspec(refspec, current_branch) for refspec in refspecs]
    branches = [branch for branch in branches if branch]
    if branches:
        return branches
    return [current_branch] if current_branch else []


def push_delete_target_branches(args: list[str]) -> list[str]:
    positionals = positional_args(args, PUSH_OPTIONS_WITH_VALUES)
    branches: list[str] = []

    if has_option(args, ["--delete", "-d"]):
        branches.extend(short_branch_name(branch) for branch in positionals[1:])

    for refspec in push_refspecs(args):
        if refspec.startswith(":"):
            branch = branch_from_refspec(refspec)
            if branch:
                branches.append(branch)

    return [branch for branch in branches if branch]


def push_refspecs(args: list[str]) -> list[str]:
    positionals = positional_args(args, PUSH_OPTIONS_WITH_VALUES)
    return positionals[1:] if len(positionals) > 1 else []


def branch_from_refspec(refspec: str, current_branch: str | None = None) -> str | None:
    refspec = refspec.lstrip("+")
    target = refspec.split(":", 1)[1] if ":" in refspec else refspec
    if not target:
        return None
    if target == "HEAD":
        return current_branch
    return short_branch_name(target)


def short_branch_name(branch: str) -> str:
    prefix = "refs/heads/"
    return branch[len(prefix) :] if branch.startswith(prefix) else branch


def is_protected_branch(branch: str | None, protected_branches: list[str]) -> bool:
    if not branch:
        return False
    branch = short_branch_name(branch)
    return branch in protected_branches


def branch_force_delete(args: list[str]) -> bool:
    return "-D" in args or ("--delete" in args and "--force" in args)


def branch_delete_targets(args: list[str]) -> list[str]:
    targets: list[str] = []
    skip_next = False
    for token in args:
        if skip_next:
            skip_next = False
            continue
        if token in {"-m", "-M", "-c", "-C"}:
            skip_next = True
            continue
        if token in {"-D", "-d", "--delete", "--force"} or token.startswith("-"):
            continue
        targets.append(short_branch_name(token))
    return targets


def has_help_option(args: list[str]) -> bool:
    return "-h" in args or "--help" in args


def option_takes_value(token: str, value_options: set[str]) -> bool:
    return token in value_options
