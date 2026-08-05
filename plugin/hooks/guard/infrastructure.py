"""Infrastructure, release, and publication command guard rules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .context import HookContext
from .decisions import Decision
from .options import first_positional, positional_args
from .paths import find_project_root
from .policy import load_policy, policy_section, string_list
from .process import command_output
from .shell import CommandSegment, ShellParseResult, normalized_command


DEFAULT_PRODUCTION_MARKERS = ["prod", "production"]
ENVIRONMENT_VARIABLES = ("ENV", "ENVIRONMENT", "STAGE", "NODE_ENV")
# "pre-production" and "not-production" name environments that are not production.
NEGATED_PREFIXES = ("not-", "not_", "non-", "non_", "no-", "pre-", "pre_")
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
    "--as",
    "--as-group",
    "--as-uid",
    "--cache-dir",
    "--certificate-authority",
    "--client-certificate",
    "--client-key",
    "--cluster",
    "--context",
    "--kubeconfig",
    "--log-flush-frequency",
    "--namespace",
    "--password",
    "--profile",
    "--profile-output",
    "--request-timeout",
    "--server",
    "--tls-server-name",
    "--token",
    "--user",
    "--username",
    "--v",
    "--vmodule",
    "-n",
    "-v",
}
KUBECTL_GLOBAL_BOOLEAN_OPTIONS = {
    "--disable-compression",
    "--insecure-skip-tls-verify",
    "--match-server-version",
    "--warnings-as-errors",
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
        action, _action_args = first_positional(args, TERRAFORM_GLOBAL_OPTIONS_WITH_VALUES)
        if action == "apply":
            return Operation("TERRAFORM-APPLY", "Confirm terraform apply.", production_sensitive=True)
        if action == "destroy":
            return Operation("TERRAFORM-DESTROY", "Confirm terraform destroy.", production_sensitive=True)

    if command == "kubectl":
        action, action_args, uncertain_option = kubectl_action_after_options(args)
        if uncertain_option is not None:
            return Operation(
                "KUBECTL-OPTION-UNCERTAINTY",
                f"Unable to determine the kubectl action after leading option {uncertain_option}; confirm the command.",
            )
        if action != "delete":
            return None
        if deletes_protected_namespace(action_args):
            return Operation("KUBECTL-PROTECTED-NAMESPACE", "Do not delete protected Kubernetes namespaces.")
        return Operation("KUBECTL-DELETE", "Confirm kubectl delete.", production_sensitive=True)

    if command == "helm":
        action, _action_args = first_positional(args, HELM_GLOBAL_OPTIONS_WITH_VALUES)
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


def kubectl_action_after_options(args: list[str]) -> tuple[str | None, list[str], str | None]:
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            index += 1
            break

        option_name = token.split("=", 1)[0]
        if option_name in KUBECTL_GLOBAL_OPTIONS_WITH_VALUES:
            if "=" in token:
                index += 1
                continue
            if index + 1 >= len(args) or args[index + 1] == "--":
                return None, [], token
            index += 2
            continue

        if option_name in KUBECTL_GLOBAL_BOOLEAN_OPTIONS:
            index += 1
            continue

        if token.startswith("-"):
            return None, [], token

        return token, args[index + 1 :], None

    if index < len(args):
        return args[index], args[index + 1 :], None
    return None, [], None


def deletes_protected_namespace(args: list[str]) -> bool:
    normalized_args = positional_args(args, KUBECTL_DELETE_OPTIONS_WITH_VALUES)
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
    # Only variables set on the command itself count. The hook process inherits the
    # developer's shell, where an exported NODE_ENV=production says nothing about
    # what this command targets, and it produced an unappealable deny on every
    # infrastructure command. Production-sensitive operations still prompt.
    values = [segment.env[name] for name in ENVIRONMENT_VARIABLES if name in segment.env]

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


def load_production_policy(project_root: Path) -> ProductionPolicy:
    policy = load_policy(project_root)
    production = policy_section(policy, "production")
    command_guard = policy_section(policy, "commandGuard")
    return ProductionPolicy(
        markers=string_list(production.get("markers")) or DEFAULT_PRODUCTION_MARKERS,
        kube_contexts=string_list(production.get("kubeContexts")),
        terraform_workspaces=string_list(production.get("terraformWorkspaces")),
        unknown_environment_high_risk=command_guard.get("unknownEnvironment") == "high-risk",
    )


def is_production_value(value: str, markers: list[str], exact_values: list[str]) -> bool:
    """A marker counts only as the whole value or as its leading/trailing component.

    An interior match reads "pre-production-mirror" and "not-production" as
    production, which turns a mirror or a review environment into a hard deny.
    Name such environments explicitly through the policy's exact value lists.
    """
    normalized = value.lower()
    for exact in exact_values:
        if normalized == exact.lower():
            return True
    if normalized.startswith(NEGATED_PREFIXES):
        return False
    for marker in markers:
        normalized_marker = marker.lower()
        if not normalized_marker:
            continue
        if normalized == normalized_marker:
            return True
        head = normalized[: len(normalized_marker) + 1]
        if head == f"{normalized_marker}{head[-1:]}" and not head[-1:].isalnum():
            return True
        tail = normalized[-(len(normalized_marker) + 1) :]
        if tail[1:] == normalized_marker and not tail[:1].isalnum():
            return True
    return False
