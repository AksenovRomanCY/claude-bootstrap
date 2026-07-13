"""Infrastructure, release, and publication command guard rules."""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .context import HookContext
from .decisions import Decision
from .filesystem import find_project_root
from .shell import CommandSegment, ShellParseResult


CONTEXT_TIMEOUT_SECONDS = 2
DEFAULT_PRODUCTION_MARKERS = ["prod", "production"]
ENVIRONMENT_VARIABLES = ("ENV", "ENVIRONMENT", "STAGE", "NODE_ENV")
PRODUCTION_FLAG_NAMES = {
    "--env",
    "--environment",
    "--stage",
    "--namespace",
    "--context",
    "--kube-context",
    "--workspace",
    "-n",
}
REMOTE_SCRIPT_SHELLS = {"sh", "bash"}
TERRAFORM_GLOBAL_OPTIONS_WITH_VALUES = {"-chdir"}
KUBECTL_GLOBAL_OPTIONS_WITH_VALUES = {
    "--context",
    "--kubeconfig",
    "--namespace",
    "--server",
    "--token",
    "--user",
    "--cluster",
    "-n",
}
HELM_GLOBAL_OPTIONS_WITH_VALUES = {"--kube-context", "--namespace", "-n"}
KUBECTL_DELETE_OPTIONS_WITH_VALUES = {
    "--cascade",
    "--field-selector",
    "--filename",
    "--grace-period",
    "--kustomize",
    "--namespace",
    "--output",
    "--raw",
    "--selector",
    "--timeout",
    "--wait",
    "-f",
    "-k",
    "-l",
    "-n",
    "-o",
}


@dataclass(frozen=True)
class ProductionPolicy:
    markers: list[str]
    kube_contexts: list[str]
    terraform_workspaces: list[str]
    unknown_environment_high_risk: bool = False


@dataclass(frozen=True)
class ProductionSignals:
    confirmed: bool = False
    source: str = ""


@dataclass(frozen=True)
class GuardContext:
    cwd: Path
    project_root: Path
    policy: ProductionPolicy


@dataclass(frozen=True)
class Operation:
    rule_id: str
    reason: str
    production_sensitive: bool = False
    recommendation: str = ""


def evaluate(context: HookContext, parsed: ShellParseResult) -> list[Decision]:
    project_root = find_project_root(context.cwd)
    guard_context = GuardContext(
        cwd=context.cwd,
        project_root=project_root,
        policy=load_production_policy(project_root),
    )
    decisions: list[Decision] = []

    for index, segment in enumerate(parsed.segments):
        decisions.extend(evaluate_segment(segment, guard_context))
        if is_remote_script_pipe(parsed, index):
            decisions.append(
                Decision.ask(
                    "REMOTE-SCRIPT",
                    "Confirm remote script execution. Prefer download -> verify checksum -> inspect contents -> execute separately.",
                )
            )

    return decisions


def evaluate_segment(segment: CommandSegment, context: GuardContext) -> list[Decision]:
    operation = classify_operation(segment)
    if operation is None:
        return []

    if operation.rule_id in {"GH-REPO-DELETE", "NPM-UNPUBLISH", "KUBECTL-PROTECTED-NAMESPACE"}:
        return [Decision.deny(operation.rule_id, operation.reason)]

    if operation.production_sensitive:
        production = detect_production(segment, context)
        if production.confirmed:
            return [
                Decision.deny(
                    "PRODUCTION-DESTRUCTIVE",
                    f"{operation.reason} Production context detected via {production.source}.",
                )
            ]
        if context.policy.unknown_environment_high_risk:
            return [
                Decision.ask(
                    "UNKNOWN-ENVIRONMENT",
                    f"{operation.reason} Environment context is unknown and strict profile treats it as high risk.",
                )
            ]

    reason = operation.recommendation or operation.reason
    return [Decision.ask(operation.rule_id, reason)]


def classify_operation(segment: CommandSegment) -> Operation | None:
    command = normalized_command(segment)
    args = segment.args

    if command == "terraform":
        action, _action_args = action_after_options(args, TERRAFORM_GLOBAL_OPTIONS_WITH_VALUES)
        if action == "apply":
            return Operation("TERRAFORM-APPLY", "Confirm terraform apply.", production_sensitive=True)
        if action == "destroy":
            return Operation("TERRAFORM-DESTROY", "Confirm terraform destroy.", production_sensitive=True)

    if command == "kubectl":
        action, action_args = action_after_options(args, KUBECTL_GLOBAL_OPTIONS_WITH_VALUES)
        if action != "delete":
            return None
        if deletes_protected_namespace(action_args):
            return Operation("KUBECTL-PROTECTED-NAMESPACE", "Do not delete protected Kubernetes namespaces.")
        return Operation("KUBECTL-DELETE", "Confirm kubectl delete.", production_sensitive=True)

    if command == "helm":
        action, _action_args = action_after_options(args, HELM_GLOBAL_OPTIONS_WITH_VALUES)
        if action == "uninstall":
            return Operation("HELM-UNINSTALL", "Confirm helm uninstall.", production_sensitive=True)

    if command == "docker" and args[:2] == ["system", "prune"]:
        return Operation("DOCKER-SYSTEM-PRUNE", "Confirm docker system prune.", production_sensitive=True)

    if command == "npm":
        if args and args[0] == "unpublish":
            return Operation("NPM-UNPUBLISH", "Do not unpublish npm packages.")
        if args and args[0] == "publish":
            return Operation("NPM-PUBLISH", "Confirm npm publish.")

    if command == "pnpm" and args and args[0] == "publish":
        return Operation("PNPM-PUBLISH", "Confirm pnpm publish.")

    if command == "yarn" and args[:2] == ["npm", "publish"]:
        return Operation("YARN-NPM-PUBLISH", "Confirm yarn npm publish.")

    if command == "cargo" and args and args[0] == "publish":
        return Operation("CARGO-PUBLISH", "Confirm cargo publish.")

    if command == "twine" and args and args[0] == "upload":
        return Operation("TWINE-UPLOAD", "Confirm twine upload.")

    if command == "gh" and len(args) >= 2:
        if args[:2] == ["repo", "delete"]:
            return Operation("GH-REPO-DELETE", "Do not delete GitHub repositories.")
        if args[:2] == ["release", "create"]:
            return Operation("GH-RELEASE-CREATE", "Confirm GitHub release creation.")
        if args[:2] == ["release", "delete"]:
            return Operation("GH-RELEASE-DELETE", "Confirm GitHub release deletion.")

    return None


def action_after_options(args: list[str], value_options: set[str]) -> tuple[str | None, list[str]]:
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            index += 1
            break
        if token in value_options:
            index += 2
            continue
        if any(token.startswith(f"{option}=") for option in value_options):
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        return token, args[index + 1 :]

    if index < len(args):
        return args[index], args[index + 1 :]
    return None, []


def normalized_command(segment: CommandSegment) -> str | None:
    if segment.command is None:
        return None
    return Path(segment.command).name


def deletes_protected_namespace(args: list[str]) -> bool:
    normalized_args = drop_options(args, KUBECTL_DELETE_OPTIONS_WITH_VALUES)
    if not normalized_args:
        return False

    resource = normalized_args[0]
    name = normalized_args[1] if len(normalized_args) > 1 else ""
    protected = {"kube-system", "default"}

    if resource in {"namespace", "namespaces", "ns"} and name in protected:
        return True
    if resource.startswith(("namespace/", "namespaces/", "ns/")):
        return resource.split("/", 1)[1] in protected
    return False


def drop_options(args: list[str], value_options: set[str]) -> list[str]:
    normalized: list[str] = []
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            normalized.extend(args[index + 1 :])
            break
        if token in value_options:
            index += 2
            continue
        if any(token.startswith(f"{option}=") for option in value_options):
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        normalized.append(token)
        index += 1
    return normalized


def is_remote_script_pipe(parsed: ShellParseResult, index: int) -> bool:
    if index + 1 >= len(parsed.segments):
        return False
    if index >= len(parsed.separators) or parsed.separators[index] != "|":
        return False

    current = parsed.segments[index]
    next_segment = parsed.segments[index + 1]
    command = normalized_command(current)
    next_command = normalized_command(next_segment)
    return command in {"curl", "wget"} and next_command in REMOTE_SCRIPT_SHELLS


def detect_production(segment: CommandSegment, context: GuardContext) -> ProductionSignals:
    env_signal = production_from_env(segment, context.policy)
    if env_signal.confirmed:
        return env_signal

    flag_signal = production_from_flags(segment.args, context.policy)
    if flag_signal.confirmed:
        return flag_signal

    command = normalized_command(segment)
    if command in {"kubectl", "helm"}:
        kube_context = command_output(context.cwd, ["kubectl", "config", "current-context"])
        if kube_context and is_production_value(kube_context, context.policy.markers, context.policy.kube_contexts):
            return ProductionSignals(True, "Kubernetes context")

    if command == "terraform":
        workspace = command_output(context.cwd, ["terraform", "workspace", "show"])
        if workspace and is_production_value(workspace, context.policy.markers, context.policy.terraform_workspaces):
            return ProductionSignals(True, "Terraform workspace")

    return ProductionSignals()


def production_from_env(segment: CommandSegment, policy: ProductionPolicy) -> ProductionSignals:
    values: list[str] = []
    for name in ENVIRONMENT_VARIABLES:
        if name in segment.env:
            values.append(segment.env[name])
        if name in os.environ:
            values.append(os.environ[name])

    for value in values:
        if is_production_value(value, policy.markers, []):
            return ProductionSignals(True, "environment variable")

    return ProductionSignals()


def production_from_flags(args: list[str], policy: ProductionPolicy) -> ProductionSignals:
    values: list[str] = []
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            break
        if token in PRODUCTION_FLAG_NAMES and index + 1 < len(args):
            values.append(args[index + 1])
            index += 2
            continue
        flag_name = token.split("=", 1)[0]
        if flag_name in PRODUCTION_FLAG_NAMES and "=" in token:
            values.append(token.split("=", 1)[1])
        index += 1

    for value in values:
        if is_production_value(value, policy.markers, policy.kube_contexts + policy.terraform_workspaces):
            return ProductionSignals(True, "command flag")

    return ProductionSignals()


def command_output(cwd: Path, command: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=CONTEXT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def load_production_policy(project_root: Path) -> ProductionPolicy:
    policy_file = project_root / ".claude" / "security-policy.json"
    try:
        raw_policy: Any = json.loads(policy_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ProductionPolicy(markers=DEFAULT_PRODUCTION_MARKERS, kube_contexts=[], terraform_workspaces=[])

    if not isinstance(raw_policy, dict):
        return ProductionPolicy(markers=DEFAULT_PRODUCTION_MARKERS, kube_contexts=[], terraform_workspaces=[])

    production = raw_policy.get("production")
    if isinstance(production, dict):
        markers = string_list(production.get("markers")) or DEFAULT_PRODUCTION_MARKERS
        kube_contexts = string_list(production.get("kubeContexts"))
        terraform_workspaces = string_list(production.get("terraformWorkspaces"))
    else:
        markers = DEFAULT_PRODUCTION_MARKERS
        kube_contexts = []
        terraform_workspaces = []

    command_guard = raw_policy.get("commandGuard") if isinstance(raw_policy, dict) else None
    unknown_environment_high_risk = (
        isinstance(command_guard, dict) and command_guard.get("unknownEnvironment") == "high-risk"
    )
    return ProductionPolicy(
        markers=markers,
        kube_contexts=kube_contexts,
        terraform_workspaces=terraform_workspaces,
        unknown_environment_high_risk=unknown_environment_high_risk,
    )


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def is_production_value(value: str, markers: list[str], exact_values: list[str]) -> bool:
    normalized = value.lower()
    for exact in exact_values:
        if normalized == exact.lower():
            return True
    parts = [part for part in re.split(r"[^a-z0-9]+", normalized) if part]
    for marker in markers:
        normalized_marker = marker.lower()
        if not normalized_marker:
            continue
        if normalized == normalized_marker:
            return True
        if normalized_marker in parts:
            return True
    return False
