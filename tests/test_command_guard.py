import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import (  # noqa: E402
    ROOT,
    SCRIPTS_DIR,
    edit_payload,
    env_without_path,
    init_git_repo,
    isolated_env,
    load_fixtures,
    load_script,
    run_script,
    write_policy,
)
from helpers import bash_payload as _bash_payload  # noqa: E402
from helpers import write_payload as _write_payload  # noqa: E402

from guard.context import from_hook_payload  # noqa: E402
from guard.decisions import Decision, DecisionKind, combine  # noqa: E402
from guard.filesystem import evaluate as evaluate_filesystem  # noqa: E402
from guard.git import evaluate as evaluate_git  # noqa: E402
from guard.git import GitContext  # noqa: E402
from guard.infrastructure import evaluate as evaluate_infrastructure  # noqa: E402
from guard.infrastructure import is_production_value  # noqa: E402
from guard.shell import parse  # noqa: E402


COMMAND_GUARD = SCRIPTS_DIR / "command_guard.py"
command_guard = load_script(COMMAND_GUARD)

# These tests default to running against the repository itself.
def bash_payload(command, cwd=ROOT):
    return _bash_payload(command, cwd)


def write_payload(file_path, content, cwd=ROOT):
    return _write_payload(file_path, content, cwd)


def post_write_payload(file_path, content, cwd=ROOT):
    return _write_payload(file_path, content, cwd, event="PostToolUse")


@contextmanager
def strict_policy_workspace(policy=None):
    with tempfile.TemporaryDirectory() as tmpdir:
        project = Path(tmpdir) / "project"
        project.mkdir()
        (project / ".git").mkdir()
        policy_data = {
            "version": 1,
            "managedBy": "claude-bootstrap",
            "profile": "strict",
            "commandGuard": {
                "parserUncertainty": "ask",
                "unknownEnvironment": "high-risk",
            },
            "database": {
                "destructiveOperations": "deny",
            },
        }
        if policy:
            policy_data.update(policy)
        write_policy(project, policy_data)
        yield project


@contextmanager
def prepared_git_workspace(fixture):
    with tempfile.TemporaryDirectory() as tmpdir:
        cwd = Path(tmpdir)

        if fixture.get("repo", True):
            init_git_repo(cwd, branch=fixture.get("branch", "main"))

            protected_branches = fixture.get("protectedBranches")
            if protected_branches is not None:
                write_policy(cwd, {"version": 1, "protectedBranches": protected_branches})

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
        for directory in ["dist", "build", "node_modules", "build output", "linked", "src", "artifacts"]:
            (project / directory).mkdir()

        policy = fixture.get("policy")
        if policy is not None:
            write_policy(project, {"version": 1, **policy})

        command = fixture["command"].replace("{{PROJECT}}", project.as_posix()).replace("{{PARENT}}", parent.as_posix())
        yield project, command


@contextmanager
def prepared_infrastructure_workspace(fixture):
    with tempfile.TemporaryDirectory() as tmpdir:
        project = Path(tmpdir) / "project"
        project.mkdir()
        (project / ".git").mkdir()

        policy = fixture.get("policy")
        if policy is not None:
            write_policy(project, {"version": 1, **policy})

        yield project


class CommandGuardTests(unittest.TestCase):
    def run_guard(self, payload, env=None):
        return run_script(COMMAND_GUARD, payload, env=env)

    def test_decision_priority(self):
        decision = combine(
            [
                Decision.warning("WARN", "warning"),
                Decision.ask("ASK", "ask"),
                Decision.deny("DENY", "deny"),
            ]
        )

        self.assertEqual(decision.kind, DecisionKind.DENY)
        self.assertEqual(decision.rule_id, "DENY")
        # The strictest decision leads, but the weaker findings are still reported:
        # a write can be denied for one reason and worth mentioning for another.
        self.assertEqual(decision.formatted_reason(), "[DENY] deny [WARN] warning [ASK] ask")

    def test_decision_combine_keeps_one_reason_when_they_agree(self):
        decision = combine([Decision.ask("RULE", "same"), Decision.ask("RULE", "same"), Decision.none()])

        self.assertEqual(decision.formatted_reason(), "[RULE] same")

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

    def test_unsupported_construct_requires_confirmation(self):
        completed = self.run_guard(bash_payload("echo $(date)"))

        self.assertEqual(completed.returncode, 0)
        output = json.loads(completed.stdout)
        hook_output = output["hookSpecificOutput"]
        self.assertEqual(hook_output["permissionDecision"], "ask")
        self.assertIn("[UNSUPPORTED-SHELL]", hook_output["permissionDecisionReason"])

    def test_strict_parser_uncertainty_requires_confirmation(self):
        with strict_policy_workspace() as cwd:
            completed = self.run_guard(bash_payload("echo $(date)", cwd))

        self.assertEqual(completed.returncode, 0)
        output = json.loads(completed.stdout)
        hook_output = output["hookSpecificOutput"]
        self.assertEqual(hook_output["permissionDecision"], "ask")
        self.assertIn("[UNSUPPORTED-SHELL]", hook_output["permissionDecisionReason"])

    def test_shell_control_syntax_is_judged_by_the_command_it_guards(self):
        completed = self.run_guard(bash_payload("if true; then git commit -n -m test; fi"))

        self.assertEqual(completed.returncode, 0)
        output = json.loads(completed.stdout)
        hook_output = output["hookSpecificOutput"]
        self.assertEqual(hook_output["permissionDecision"], "deny")
        self.assertIn("[GIT-HOOK-BYPASS]", hook_output["permissionDecisionReason"])

    def test_subshell_does_not_hide_the_command_it_wraps(self):
        completed = self.run_guard(bash_payload("(cd /tmp && git push --mirror origin)"))

        self.assertEqual(completed.returncode, 0)
        output = json.loads(completed.stdout)
        hook_output = output["hookSpecificOutput"]
        self.assertEqual(hook_output["permissionDecision"], "deny")
        self.assertIn("[GIT-PUSH-MIRROR]", hook_output["permissionDecisionReason"])

    def test_loop_body_does_not_hide_the_command_it_runs(self):
        completed = self.run_guard(bash_payload("for f in *; do git commit -n -m test; done"))

        self.assertEqual(completed.returncode, 0)
        output = json.loads(completed.stdout)
        hook_output = output["hookSpecificOutput"]
        self.assertEqual(hook_output["permissionDecision"], "deny")
        self.assertIn("[GIT-HOOK-BYPASS]", hook_output["permissionDecisionReason"])

    def test_control_syntax_alone_does_not_prompt(self):
        completed = self.run_guard(bash_payload("if true; then time git status; fi"))

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")

    def test_compound_bash_payload_runs_through_guard(self):
        completed = self.run_guard(bash_payload("echo ok && git commit --no-verify -m test"))

        self.assertEqual(completed.returncode, 0)
        output = json.loads(completed.stdout)
        hook_output = output["hookSpecificOutput"]
        self.assertEqual(hook_output["permissionDecision"], "deny")
        self.assertIn("[GIT-HOOK-BYPASS]", hook_output["permissionDecisionReason"])

    def test_background_bash_payload_runs_each_segment_through_guard(self):
        completed = self.run_guard(bash_payload("git status & git commit -n -m test"))

        self.assertEqual(completed.returncode, 0)
        output = json.loads(completed.stdout)
        hook_output = output["hookSpecificOutput"]
        self.assertEqual(hook_output["permissionDecision"], "deny")
        self.assertIn("[GIT-HOOK-BYPASS]", hook_output["permissionDecisionReason"])

    def test_stderr_pipe_payload_runs_each_segment_through_guard(self):
        completed = self.run_guard(bash_payload("safe-command |& git push --mirror origin"))

        self.assertEqual(completed.returncode, 0)
        output = json.loads(completed.stdout)
        hook_output = output["hookSpecificOutput"]
        self.assertEqual(hook_output["permissionDecision"], "deny")
        self.assertIn("[GIT-PUSH-MIRROR]", hook_output["permissionDecisionReason"])

    def test_non_bash_tool_outputs_nothing(self):
        completed = self.run_guard({"hook_event_name": "PreToolUse", "tool_name": "Write", "tool_input": {}})

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")

    def test_write_payload_runs_secret_guard(self):
        completed = self.run_guard(write_payload("/tmp/config.ts", 'const key = "AKIA1234567890ABCDEF"'))

        self.assertEqual(completed.returncode, 0)
        output = json.loads(completed.stdout)
        hook_output = output["hookSpecificOutput"]
        self.assertEqual(hook_output["hookEventName"], "PreToolUse")
        self.assertEqual(hook_output["permissionDecision"], "deny")
        self.assertIn("[SECRET-AWS-ACCESS-KEY]", hook_output["permissionDecisionReason"])

    def test_write_payload_runs_large_file_policy(self):
        content = "".join(f"line {index}\n" for index in range(1201))
        completed = self.run_guard(write_payload("/tmp/large.ts", content))

        self.assertEqual(completed.returncode, 0)
        output = json.loads(completed.stdout)
        hook_output = output["hookSpecificOutput"]
        self.assertEqual(hook_output["hookEventName"], "PreToolUse")
        self.assertEqual(hook_output["permissionDecision"], "ask")
        self.assertIn("[LARGE-FILE]", hook_output["permissionDecisionReason"])

    def test_edit_payload_is_reconstructed_once_for_both_rules(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "config.ts"
            target.write_text("const key = \"placeholder\"\n", encoding="utf-8")
            payload = edit_payload(target, "placeholder", "AKIA1234567890ABCDEF", tmpdir)

            with mock.patch("guard.secrets.reconstruct_edit") as secret_reconstruct:
                with mock.patch("large_file_policy.reconstruct_edit") as large_file_reconstruct:
                    output = command_guard.run_pre_write_guard(payload)

        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        secret_reconstruct.assert_not_called()
        large_file_reconstruct.assert_not_called()

    def test_edit_payload_that_cannot_be_applied_is_reported(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "config.ts"
            target.write_text("const key = \"placeholder\"\n", encoding="utf-8")
            payload = edit_payload(target, "missing text", "replacement", tmpdir)

            output = command_guard.run_pre_write_guard(payload)

        hook_output = output["hookSpecificOutput"]
        self.assertEqual(hook_output["permissionDecision"], "ask")
        self.assertIn("[SECRET-EDIT-UNCERTAIN]", hook_output["permissionDecisionReason"])

    def test_post_write_payload_runs_warning_guard_without_denial(self):
        completed = self.run_guard(post_write_payload("/tmp/test.ts", 'console.log("debug")'))

        self.assertEqual(completed.returncode, 0)
        output = json.loads(completed.stdout)
        hook_output = output["hookSpecificOutput"]
        self.assertEqual(hook_output["hookEventName"], "PostToolUse")
        self.assertIn("[DEBUG-CONSOLE]", hook_output["additionalContext"])
        self.assertNotIn("permissionDecision", hook_output)

    def test_unknown_event_outputs_nothing(self):
        completed = self.run_guard({"hook_event_name": "SessionStart", "tool_name": "Bash", "tool_input": {"command": "git status"}})

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
        fixtures = load_fixtures("bash-commands.json")

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
                    if segment.redirects:
                        data["redirects"] = [
                            {"op": redirect.op, "target": redirect.target, "fd": redirect.fd}
                            for redirect in segment.redirects
                        ]
                    actual_segments.append(data)

                self.assertEqual(actual_segments, fixture["segments"])
                self.assertEqual(parsed.unsupported, fixture["unsupported"])
                if "separators" in fixture:
                    self.assertEqual(parsed.separators, fixture["separators"])

    def test_git_decision_fixtures(self):
        fixtures = load_fixtures("git-commands.json")

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

        with mock.patch("guard.process.subprocess.run", side_effect=fake_run):
            context = GitContext(ROOT)
            self.assertEqual(seen, [], "constructing the context must not run git")
            _ = (context.project_root, context.current_branch, context.dirty)

        self.assertEqual(set(seen), allowed)

    def test_git_context_is_loaded_per_fact_and_cached(self):
        seen = []

        def fake_run(command, **kwargs):
            seen.append(tuple(command))
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with mock.patch("guard.process.subprocess.run", side_effect=fake_run):
            context = GitContext(ROOT)
            self.assertIsNone(context.current_branch)
            self.assertIsNone(context.current_branch)

        self.assertEqual(seen, [("git", "branch", "--show-current")])

    def test_read_only_git_commands_run_no_subprocess(self):
        with mock.patch("guard.process.subprocess.run", side_effect=AssertionError("git log needs no repository facts")):
            for command in ("git log --oneline", "git status", "git push origin feature"):
                with self.subTest(command=command):
                    evaluate_git(from_hook_payload(bash_payload(command)), parse(command))

    def test_git_directory_option_selects_the_repository(self):
        seen = []

        def fake_run(command, **kwargs):
            seen.append(kwargs.get("cwd"))
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        command = "git -C repo/inner reset --hard"
        with mock.patch("guard.process.subprocess.run", side_effect=fake_run):
            evaluate_git(from_hook_payload(bash_payload(command, ROOT)), parse(command))

        self.assertEqual(seen, [str(ROOT / "repo" / "inner")])

    def test_filesystem_decision_fixtures(self):
        fixtures = load_fixtures("filesystem-commands.json")

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
            decisions = evaluate_filesystem(from_hook_payload(bash_payload("rm -rf src")), parse("rm -rf src"))

        self.assertEqual(decisions[0].rule_id, "FS-RM-RF")

    def test_infrastructure_decision_fixtures(self):
        fixtures = load_fixtures("infrastructure-commands.json")

        for fixture in fixtures:
            with self.subTest(fixture["name"]):
                with prepared_infrastructure_workspace(fixture) as cwd:
                    completed = self.run_guard(bash_payload(fixture["command"], cwd), env=env_without_path())

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
        seen = []

        def fake_run(command, **kwargs):
            seen.append(tuple(command))
            return subprocess.CompletedProcess(command, 0, stdout="production\n", stderr="")

        commands = ["kubectl delete deployment app", "terraform apply"]
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("guard.process.subprocess.run", side_effect=fake_run):
                for command in commands:
                    evaluate_infrastructure(from_hook_payload(bash_payload(command)), parse(command))

        # terraform is read from .terraform/environment, so the only subprocess
        # left is the local kubectl context lookup.
        self.assertEqual(set(seen), {("kubectl", "config", "current-context")})

    def test_terraform_workspace_is_read_from_the_state_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / ".git").mkdir()
            (project / ".terraform").mkdir()
            (project / ".terraform" / "environment").write_text("production\n", encoding="utf-8")

            with mock.patch.dict(os.environ, {}, clear=True):
                with mock.patch("guard.process.subprocess.run", side_effect=AssertionError("no subprocess allowed")):
                    decisions = evaluate_infrastructure(
                        from_hook_payload(bash_payload("terraform apply", project)),
                        parse("terraform apply"),
                    )

        self.assertEqual([decision.rule_id for decision in decisions], ["PRODUCTION-DESTRUCTIVE"])

    def test_terraform_workspace_command_runs_only_when_policy_allows_it(self):
        def fake_run(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, stdout="production\n", stderr="")

        for allowed in (False, True):
            with self.subTest(allowed=allowed), tempfile.TemporaryDirectory() as tmpdir:
                project = Path(tmpdir)
                (project / ".git").mkdir()
                write_policy(project, {"version": 1, "commandGuard": {"terraformWorkspaceCommand": allowed}})

                with mock.patch.dict(os.environ, {}, clear=True):
                    with mock.patch("guard.process.subprocess.run", side_effect=fake_run):
                        decisions = evaluate_infrastructure(
                            from_hook_payload(bash_payload("terraform apply", project)),
                            parse("terraform apply"),
                        )

                rules = [decision.rule_id for decision in decisions]
                self.assertEqual(rules, ["PRODUCTION-DESTRUCTIVE"] if allowed else ["TERRAFORM-APPLY"])

    def test_infrastructure_missing_context_commands_do_not_break_guard(self):
        def missing_command(command, **kwargs):
            raise OSError("missing command")

        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("guard.process.subprocess.run", side_effect=missing_command):
                decisions = evaluate_infrastructure(from_hook_payload(bash_payload("terraform apply")), parse("terraform apply"))

        self.assertEqual(decisions[0].kind, DecisionKind.ASK)
        self.assertEqual(decisions[0].rule_id, "TERRAFORM-APPLY")

    def test_infrastructure_ignores_ambient_process_env(self):
        with mock.patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=True):
            decisions = evaluate_infrastructure(from_hook_payload(bash_payload("terraform apply")), parse("terraform apply"))

        self.assertEqual(decisions[0].kind, DecisionKind.ASK)
        self.assertEqual(decisions[0].rule_id, "TERRAFORM-APPLY")

    def test_infrastructure_environment_detection_uses_command_env(self):
        command = "ENVIRONMENT=production terraform apply"
        with mock.patch.dict(os.environ, {}, clear=True):
            decisions = evaluate_infrastructure(from_hook_payload(bash_payload(command)), parse(command))

        self.assertEqual(decisions[0].kind, DecisionKind.DENY)
        self.assertEqual(decisions[0].rule_id, "PRODUCTION-DESTRUCTIVE")

    def test_production_marker_matches_only_whole_or_edge_components(self):
        markers = ["prod", "production"]
        for value in ("production", "prod-eu-1", "cluster-prod"):
            with self.subTest(value=value, expected=True):
                self.assertTrue(is_production_value(value, markers, []))
        for value in ("pre-production-mirror", "not-production", "staging.production-mirror.local", "myprod"):
            with self.subTest(value=value, expected=False):
                self.assertFalse(is_production_value(value, markers, []))

    def test_strict_unknown_environment_requires_confirmation(self):
        with strict_policy_workspace() as cwd:
            completed = self.run_guard(bash_payload("terraform apply", cwd), env=env_without_path())

        self.assertEqual(completed.returncode, 0)
        output = json.loads(completed.stdout)
        hook_output = output["hookSpecificOutput"]
        self.assertEqual(hook_output["permissionDecision"], "ask")
        self.assertIn("[UNKNOWN-ENVIRONMENT]", hook_output["permissionDecisionReason"])

    def test_database_decision_fixtures(self):
        fixtures = load_fixtures("database-commands.json")

        for fixture in fixtures:
            with self.subTest(fixture["name"]):
                with prepared_infrastructure_workspace(fixture) as cwd:
                    completed = self.run_guard(bash_payload(fixture["command"], cwd), env=env_without_path())

                self.assertEqual(completed.returncode, 0)
                self.assertEqual(completed.stderr, "")
                expected_decision = fixture["decision"]

                if expected_decision == "none":
                    self.assertEqual(completed.stdout, "")
                    continue

                hook_output = json.loads(completed.stdout)["hookSpecificOutput"]
                self.assertEqual(hook_output["permissionDecision"], expected_decision)
                self.assertIn(f"[{fixture['rule']}]", hook_output["permissionDecisionReason"])

    def test_strict_destructive_database_command_denies(self):
        with strict_policy_workspace() as cwd:
            completed = self.run_guard(bash_payload("psql -c 'DROP DATABASE app'", cwd))

        self.assertEqual(completed.returncode, 0)
        output = json.loads(completed.stdout)
        hook_output = output["hookSpecificOutput"]
        self.assertEqual(hook_output["permissionDecision"], "deny")
        self.assertIn("[DB-DESTRUCTIVE]", hook_output["permissionDecisionReason"])

    def test_malformed_json_fails_open(self):
        completed = run_script(COMMAND_GUARD, "{invalid")

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        self.assertIn("command_guard warning", completed.stderr)


if __name__ == "__main__":
    unittest.main()
