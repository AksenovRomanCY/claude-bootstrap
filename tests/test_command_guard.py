import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
HOOKS_DIR = ROOT / "plugin" / "hooks"
COMMAND_GUARD = HOOKS_DIR / "scripts" / "command_guard.py"
BASH_FIXTURES = ROOT / "tests" / "fixtures" / "bash-commands.json"
FILESYSTEM_FIXTURES = ROOT / "tests" / "fixtures" / "filesystem-commands.json"
GIT_FIXTURES = ROOT / "tests" / "fixtures" / "git-commands.json"
INFRASTRUCTURE_FIXTURES = ROOT / "tests" / "fixtures" / "infrastructure-commands.json"

if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from guard.context import from_hook_payload
from guard.decisions import Decision, DecisionKind, combine
from guard.filesystem import evaluate as evaluate_filesystem
from guard.git import load_git_context
from guard.infrastructure import evaluate as evaluate_infrastructure
from guard.shell import parse

spec = importlib.util.spec_from_file_location("command_guard", COMMAND_GUARD)
command_guard = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["command_guard"] = command_guard
spec.loader.exec_module(command_guard)


def bash_payload(command, cwd=ROOT):
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {
            "command": command,
        },
        "cwd": str(cwd),
    }


@contextmanager
def prepared_git_workspace(fixture):
    with tempfile.TemporaryDirectory() as tmpdir:
        cwd = Path(tmpdir)

        if fixture.get("repo", True):
            subprocess.run(["git", "init"], cwd=cwd, text=True, capture_output=True, check=True)
            branch = fixture.get("branch", "main")
            subprocess.run(["git", "checkout", "-b", branch], cwd=cwd, text=True, capture_output=True, check=True)

            protected_branches = fixture.get("protectedBranches")
            if protected_branches is not None:
                policy_dir = cwd / ".claude"
                policy_dir.mkdir()
                (policy_dir / "security-policy.json").write_text(
                    json.dumps({"version": 1, "protectedBranches": protected_branches}),
                    encoding="utf-8",
                )

            if fixture.get("dirty", False):
                (cwd / "dirty.txt").write_text("dirty\n", encoding="utf-8")

        yield cwd


@contextmanager
def prepared_filesystem_workspace(fixture):
    with tempfile.TemporaryDirectory() as tmpdir:
        parent = Path(tmpdir)
        project = parent / "project"
        project.mkdir()
        (project / ".git").mkdir()
        for directory in ["dist", "build", "node_modules", "build output", "linked"]:
            (project / directory).mkdir()

        command = fixture["command"].replace("{{PROJECT}}", str(project)).replace("{{PARENT}}", str(parent))
        yield project, command


@contextmanager
def prepared_infrastructure_workspace(fixture):
    with tempfile.TemporaryDirectory() as tmpdir:
        project = Path(tmpdir) / "project"
        project.mkdir()
        (project / ".git").mkdir()

        policy = fixture.get("policy")
        if policy is not None:
            policy_dir = project / ".claude"
            policy_dir.mkdir()
            policy_data = {"version": 1}
            policy_data.update(policy)
            (policy_dir / "security-policy.json").write_text(json.dumps(policy_data), encoding="utf-8")

        yield project


class CommandGuardTests(unittest.TestCase):
    def run_guard(self, payload, env=None):
        return subprocess.run(
            [sys.executable, str(COMMAND_GUARD)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )

    def test_decision_priority(self):
        decision = combine(
            [
                Decision.warning("WARN", "warning"),
                Decision.ask("ASK", "ask"),
                Decision.deny("DENY", "deny"),
            ]
        )

        self.assertEqual(decision.kind, DecisionKind.DENY)
        self.assertEqual(decision.formatted_reason(), "[DENY] deny")

    def test_ask_output_shape(self):
        output = command_guard.decision_output(Decision.ask("RULE-ID", "Confirmation is required."))

        self.assertEqual(
            output,
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": "[RULE-ID] Confirmation is required.",
                }
            },
        )

    def test_deny_output_shape(self):
        output = command_guard.decision_output(Decision.deny("RULE-ID", "Explanation."))

        self.assertEqual(
            output,
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "[RULE-ID] Explanation.",
                }
            },
        )

    def test_warning_output_shape(self):
        output = command_guard.decision_output(Decision.warning("RULE-ID", "Unsupported construct."))

        self.assertEqual(
            output,
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": "[RULE-ID] Unsupported construct.",
                }
            },
        )

    def test_no_decision_outputs_nothing(self):
        completed = self.run_guard(bash_payload("git status"))

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        self.assertEqual(completed.stderr, "")

    def test_unsupported_construct_adds_context(self):
        completed = self.run_guard(bash_payload("echo $(date)"))

        self.assertEqual(completed.returncode, 0)
        output = json.loads(completed.stdout)
        hook_output = output["hookSpecificOutput"]
        self.assertIn("additionalContext", hook_output)
        self.assertIn("[UNSUPPORTED-SHELL]", hook_output["additionalContext"])

    def test_non_bash_tool_outputs_nothing(self):
        completed = self.run_guard({"hook_event_name": "PreToolUse", "tool_name": "Write", "tool_input": {}})

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")

    def test_internal_error_fails_open_with_warning(self):
        with mock.patch.object(command_guard, "parse", side_effect=RuntimeError("boom")):
            with mock.patch("sys.stdin.read", return_value=json.dumps(bash_payload("git status"))):
                with mock.patch("sys.stderr") as stderr:
                    exit_code = command_guard.main()

        self.assertEqual(exit_code, 0)
        stderr.write.assert_called()

    def test_parser_fixtures(self):
        fixtures = json.loads(BASH_FIXTURES.read_text(encoding="utf-8"))

        for fixture in fixtures:
            with self.subTest(fixture["name"]):
                parsed = parse(fixture["command"])
                actual_segments = []
                for segment in parsed.segments:
                    data = {
                        "words": segment.words,
                        "env": segment.env,
                        "wrappers": segment.wrappers,
                    }
                    if segment.unsupported:
                        data["unsupported"] = segment.unsupported
                    actual_segments.append(data)

                self.assertEqual(actual_segments, fixture["segments"])
                self.assertEqual(parsed.unsupported, fixture["unsupported"])
                if "separators" in fixture:
                    self.assertEqual(parsed.separators, fixture["separators"])

    def test_git_decision_fixtures(self):
        fixtures = json.loads(GIT_FIXTURES.read_text(encoding="utf-8"))

        for fixture in fixtures:
            with self.subTest(fixture["name"]):
                with prepared_git_workspace(fixture) as cwd:
                    completed = self.run_guard(bash_payload(fixture["command"], cwd))

                self.assertEqual(completed.returncode, 0)
                self.assertEqual(completed.stderr, "")
                expected_decision = fixture["decision"]

                if expected_decision == "none":
                    self.assertEqual(completed.stdout, "")
                    continue

                output = json.loads(completed.stdout)
                hook_output = output["hookSpecificOutput"]
                self.assertEqual(hook_output["permissionDecision"], expected_decision)
                self.assertIn(f"[{fixture['rule']}]", hook_output["permissionDecisionReason"])

    def test_git_context_uses_only_read_only_commands(self):
        allowed = {
            ("git", "rev-parse", "--show-toplevel"),
            ("git", "branch", "--show-current"),
            ("git", "status", "--porcelain"),
        }
        seen = []

        def fake_run(command, **kwargs):
            seen.append(tuple(command))
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with mock.patch("guard.git.subprocess.run", side_effect=fake_run):
            load_git_context(ROOT)

        self.assertEqual(set(seen), allowed)

    def test_filesystem_decision_fixtures(self):
        fixtures = json.loads(FILESYSTEM_FIXTURES.read_text(encoding="utf-8"))

        for fixture in fixtures:
            with self.subTest(fixture["name"]):
                with prepared_filesystem_workspace(fixture) as (cwd, command):
                    completed = self.run_guard(bash_payload(command, cwd))

                self.assertEqual(completed.returncode, 0)
                self.assertEqual(completed.stderr, "")
                expected_decision = fixture["decision"]

                if expected_decision == "none":
                    self.assertEqual(completed.stdout, "")
                    continue

                output = json.loads(completed.stdout)
                hook_output = output["hookSpecificOutput"]
                self.assertEqual(hook_output["permissionDecision"], expected_decision)
                self.assertIn(f"[{fixture['rule']}]", hook_output["permissionDecisionReason"])

    def test_filesystem_rules_do_not_run_subprocesses(self):
        with mock.patch("subprocess.run", side_effect=AssertionError("filesystem rules must not run subprocesses")):
            decisions = evaluate_filesystem(from_hook_payload(bash_payload("rm -rf dist")), parse("rm -rf dist"))

        self.assertEqual(decisions[0].rule_id, "FS-RM-RF")

    def test_infrastructure_decision_fixtures(self):
        fixtures = json.loads(INFRASTRUCTURE_FIXTURES.read_text(encoding="utf-8"))

        for fixture in fixtures:
            with self.subTest(fixture["name"]):
                with prepared_infrastructure_workspace(fixture) as cwd:
                    completed = self.run_guard(bash_payload(fixture["command"], cwd), env={"PATH": ""})

                self.assertEqual(completed.returncode, 0)
                self.assertEqual(completed.stderr, "")
                if fixture["decision"] == "none":
                    self.assertEqual(completed.stdout, "")
                    continue

                output = json.loads(completed.stdout)
                hook_output = output["hookSpecificOutput"]
                self.assertEqual(hook_output["permissionDecision"], fixture["decision"])
                self.assertIn(f"[{fixture['rule']}]", hook_output["permissionDecisionReason"])

    def test_infrastructure_context_uses_only_allowed_commands(self):
        allowed = {
            ("kubectl", "config", "current-context"),
            ("terraform", "workspace", "show"),
        }
        seen = []

        def fake_run(command, **kwargs):
            seen.append(tuple(command))
            return subprocess.CompletedProcess(command, 0, stdout="production\n", stderr="")

        commands = ["kubectl delete deployment app", "terraform apply"]
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("guard.infrastructure.subprocess.run", side_effect=fake_run):
                for command in commands:
                    evaluate_infrastructure(from_hook_payload(bash_payload(command)), parse(command))

        self.assertEqual(set(seen), allowed)

    def test_infrastructure_missing_context_commands_do_not_break_guard(self):
        def missing_command(command, **kwargs):
            raise OSError("missing command")

        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("guard.infrastructure.subprocess.run", side_effect=missing_command):
                decisions = evaluate_infrastructure(from_hook_payload(bash_payload("terraform apply")), parse("terraform apply"))

        self.assertEqual(decisions[0].kind, DecisionKind.ASK)
        self.assertEqual(decisions[0].rule_id, "TERRAFORM-APPLY")

    def test_infrastructure_environment_detection_uses_process_env(self):
        with mock.patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=True):
            decisions = evaluate_infrastructure(from_hook_payload(bash_payload("terraform apply")), parse("terraform apply"))

        self.assertEqual(decisions[0].kind, DecisionKind.DENY)
        self.assertEqual(decisions[0].rule_id, "PRODUCTION-DESTRUCTIVE")

    def test_malformed_json_fails_open(self):
        completed = subprocess.run(
            [sys.executable, str(COMMAND_GUARD)],
            input="{invalid",
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        self.assertIn("command_guard warning", completed.stderr)


if __name__ == "__main__":
    unittest.main()
