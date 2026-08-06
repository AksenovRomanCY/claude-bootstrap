import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import (  # noqa: E402
    SCRIPTS_DIR,
    edit_payload,
    hook_payload,
    init_git_repo,
    load_fixtures,
    load_script,
    run_script,
    write_policy,
)

from guard.decisions import DecisionKind  # noqa: E402
from guard.secrets import FileClass, classify_file, detect_secrets, evaluate  # noqa: E402


SECRET_GUARD = SCRIPTS_DIR / "secret_guard.py"
secret_guard = load_script(SECRET_GUARD)


AWS_KEY = "AKIA1234567890ABCDEF"
GITHUB_PAT = "ghp_1234567890abcdefABCDEF1234567890abcd"
FINE_GRAINED_GITHUB_PAT = "github_pat_11AAAAAAA0abcdefghijklmnopqrstuvwxyz_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdef"
PRIVATE_KEY = "-----BEGIN PRIVATE KEY-----\nnot-a-real-key\n-----END PRIVATE KEY-----"
DUMMY_PRIVATE_KEY = "-----BEGIN PRIVATE KEY-----\ndummy-placeholder-test-key\n-----END PRIVATE KEY-----"


def write_payload(path, content, cwd, tool_name="Write"):
    key = "content" if tool_name == "Write" else "new_string"
    return hook_payload("PreToolUse", tool_name, {"file_path": str(path), key: content}, cwd)


class SecretGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.project = Path(self.tmpdir.name)
        init_git_repo(self.project)
        (self.project / ".gitignore").write_text(".env\nignored/\n", encoding="utf-8")
        self.tracked_file = self.project / "src" / "app.py"
        self.tracked_file.parent.mkdir()
        self.tracked_file.write_text("print('hello')\n", encoding="utf-8")
        subprocess.run(  # noqa: S603 - fixture setup, not the code under test
            ["git", "add", ".gitignore", "src/app.py"],
            cwd=self.project,
            text=True,
            capture_output=True,
            check=True,
        )

    def tearDown(self):
        self.tmpdir.cleanup()

    def run_guard(self, payload):
        return run_script(SECRET_GUARD, payload)

    def hook_output(self, completed):
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stderr, "")
        return json.loads(completed.stdout)["hookSpecificOutput"]

    def test_pattern_fixtures(self):
        fixtures = load_fixtures("secret-patterns.json")

        for fixture in fixtures:
            with self.subTest(fixture["name"]):
                findings = detect_secrets(fixture["content"])
                if fixture["decision"] == "none":
                    self.assertEqual(findings, [])
                    continue
                self.assertTrue(any(finding.rule_id == fixture["rule"] for finding in findings))

                # The rule alone says nothing about severity: a deny silently
                # downgraded to a warning would still match the id.
                target = self.project / "src" / "fixture.py"
                decision = evaluate(write_payload(target, fixture["content"], self.project))
                self.assertEqual(decision.kind, DecisionKind(fixture["decision"]))
                self.assertIn(f"[{fixture['rule']}]", decision.formatted_reason())

    def test_tracked_private_key_is_denied_before_write(self):
        completed = self.run_guard(write_payload(self.tracked_file, PRIVATE_KEY, self.project))
        hook_output = self.hook_output(completed)

        self.assertEqual(hook_output["permissionDecision"], "deny")
        self.assertIn("[SECRET-PRIVATE-KEY]", hook_output["permissionDecisionReason"])

    def test_high_confidence_secret_in_untracked_committable_file_is_denied(self):
        target = self.project / "src" / "new.py"
        completed = self.run_guard(write_payload(target, f'AWS_KEY="{AWS_KEY}"', self.project))
        hook_output = self.hook_output(completed)

        self.assertEqual(hook_output["permissionDecision"], "deny")
        self.assertIn("[SECRET-AWS-ACCESS-KEY]", hook_output["permissionDecisionReason"])

    def test_ignored_env_secret_requires_confirmation(self):
        target = self.project / ".env"
        completed = self.run_guard(write_payload(target, f'API_KEY="{AWS_KEY}"', self.project))
        hook_output = self.hook_output(completed)

        self.assertEqual(hook_output["permissionDecision"], "ask")
        self.assertIn("[SECRET-IGNORED-FILE]", hook_output["permissionDecisionReason"])

    def test_generic_assignment_requires_confirmation(self):
        completed = self.run_guard(
            write_payload(self.tracked_file, 'password = "CorrectHorseBattery123"', self.project)
        )
        hook_output = self.hook_output(completed)

        self.assertEqual(hook_output["permissionDecision"], "ask")
        self.assertIn("[SECRET-GENERIC-LITERAL]", hook_output["permissionDecisionReason"])

    def test_generic_env_assignment_requires_confirmation(self):
        completed = self.run_guard(
            write_payload(self.tracked_file, "DATABASE_PASSWORD=CorrectHorseBattery123", self.project)
        )
        hook_output = self.hook_output(completed)

        self.assertEqual(hook_output["permissionDecision"], "ask")
        self.assertIn("[SECRET-GENERIC-LITERAL]", hook_output["permissionDecisionReason"])

    def test_jwt_defaults_to_warning(self):
        content = 'token = "eyJhbGciOiJIUzI1NiIsInR5cCI.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature123"'
        completed = self.run_guard(write_payload(self.tracked_file, content, self.project))
        hook_output = self.hook_output(completed)

        self.assertIn("additionalContext", hook_output)
        self.assertIn("[SECRET-JWT]", hook_output["additionalContext"])

    def test_placeholder_values_are_ignored(self):
        completed = self.run_guard(write_payload(self.tracked_file, 'api_key = "your-api-key-placeholder"', self.project))

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        self.assertEqual(completed.stderr, "")

    def test_edit_scans_resulting_content(self):
        current = self.tracked_file.read_text(encoding="utf-8")
        completed = self.run_guard(
            edit_payload(self.tracked_file, current, f'token = "{GITHUB_PAT}"\n', self.project)
        )
        hook_output = self.hook_output(completed)

        self.assertEqual(hook_output["permissionDecision"], "deny")
        self.assertIn("[SECRET-GITHUB-PAT]", hook_output["permissionDecisionReason"])

    def test_edit_detects_secret_assembled_from_existing_prefix(self):
        self.tracked_file.write_text('token = "ghp_PLACEHOLDER"\n', encoding="utf-8")
        suffix = GITHUB_PAT[len("ghp_") :]

        completed = self.run_guard(
            edit_payload(self.tracked_file, "PLACEHOLDER", suffix, self.project)
        )
        hook_output = self.hook_output(completed)

        self.assertEqual(hook_output["permissionDecision"], "deny")
        self.assertIn("[SECRET-GITHUB-PAT]", hook_output["permissionDecisionReason"])

    def test_edit_replace_all_scans_all_replacements(self):
        self.tracked_file.write_text("ghp_PLACEHOLDER\nghp_PLACEHOLDER\n", encoding="utf-8")
        suffix = GITHUB_PAT[len("ghp_") :]

        completed = self.run_guard(
            edit_payload(self.tracked_file, "PLACEHOLDER", suffix, self.project, replace_all=True)
        )
        hook_output = self.hook_output(completed)

        self.assertEqual(hook_output["permissionDecision"], "deny")
        self.assertIn("[SECRET-GITHUB-PAT]", hook_output["permissionDecisionReason"])

    def test_safe_edit_has_no_decision(self):
        completed = self.run_guard(
            edit_payload(self.tracked_file, "hello", "goodbye", self.project)
        )

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")

    def test_ambiguous_edit_requires_confirmation(self):
        self.tracked_file.write_text("same\nsame\n", encoding="utf-8")

        completed = self.run_guard(
            edit_payload(self.tracked_file, "same", "different", self.project)
        )
        hook_output = self.hook_output(completed)

        self.assertEqual(hook_output["permissionDecision"], "ask")
        self.assertIn("[SECRET-EDIT-UNCERTAIN]", hook_output["permissionDecisionReason"])

    def test_missing_edit_target_requires_confirmation(self):
        target = self.project / "src" / "missing.py"

        completed = self.run_guard(edit_payload(target, "old", "new", self.project))
        hook_output = self.hook_output(completed)

        self.assertEqual(hook_output["permissionDecision"], "ask")
        self.assertIn("[SECRET-EDIT-UNCERTAIN]", hook_output["permissionDecisionReason"])

    def test_edit_read_error_requires_confirmation(self):
        payload = edit_payload(self.tracked_file, "hello", "goodbye", self.project)

        with mock.patch("guard.edit_content.Path.read_text", side_effect=OSError("read failed")):
            decision = evaluate(payload)

        self.assertEqual(decision.kind, DecisionKind.ASK)
        self.assertEqual(decision.rule_id, "SECRET-EDIT-UNCERTAIN")

    def test_edit_decode_error_requires_confirmation(self):
        self.tracked_file.write_bytes(b"\xff\xfe")

        completed = self.run_guard(edit_payload(self.tracked_file, "old", "new", self.project))
        hook_output = self.hook_output(completed)

        self.assertEqual(hook_output["permissionDecision"], "ask")
        self.assertIn("[SECRET-EDIT-UNCERTAIN]", hook_output["permissionDecisionReason"])

    def test_fine_grained_github_pat_is_denied(self):
        completed = self.run_guard(write_payload(self.tracked_file, f'token = "{FINE_GRAINED_GITHUB_PAT}"', self.project))
        hook_output = self.hook_output(completed)

        self.assertEqual(hook_output["permissionDecision"], "deny")
        self.assertIn("[SECRET-GITHUB-PAT]", hook_output["permissionDecisionReason"])

    def test_placeholder_private_key_block_is_ignored(self):
        completed = self.run_guard(write_payload(self.tracked_file, DUMMY_PRIVATE_KEY, self.project))

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        self.assertEqual(completed.stderr, "")

    def test_reason_never_contains_secret_value_or_prefix(self):
        completed = self.run_guard(write_payload(self.tracked_file, f'token = "{GITHUB_PAT}"', self.project))
        hook_output = self.hook_output(completed)
        reason = hook_output["permissionDecisionReason"]

        self.assertNotIn(GITHUB_PAT, reason)
        self.assertNotIn("ghp_", reason)
        self.assertNotIn("1234567890abcdef", reason)

    def test_file_classification_uses_git_context(self):
        ignored = self.project / ".env"
        untracked = self.project / "src" / "new.py"

        self.assertEqual(classify_file(self.tracked_file, self.project), FileClass.TRACKED_SOURCE)
        self.assertEqual(classify_file(ignored, self.project), FileClass.IGNORED)
        self.assertEqual(classify_file(untracked, self.project), FileClass.UNTRACKED_COMMITTABLE)

    def test_evaluate_fails_open_for_missing_content(self):
        decision = evaluate(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": str(self.tracked_file)},
                "cwd": str(self.project),
            }
        )

        self.assertEqual(decision.kind, DecisionKind.NONE)

    def test_malformed_json_fails_open_without_content(self):
        completed = run_script(SECRET_GUARD, "{invalid")

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        self.assertIn("secret_guard warning", completed.stderr)
        self.assertNotIn("invalid", completed.stderr)

    def write_policy(self, policy):
        write_policy(self.project, policy)

    def test_edit_removing_an_existing_secret_is_allowed(self):
        self.tracked_file.write_text(f'key = "{AWS_KEY}"\n', encoding="utf-8")

        decision = evaluate(
            edit_payload(self.tracked_file, f'key = "{AWS_KEY}"', 'key = os.environ["KEY"]', self.project)
        )

        self.assertEqual(decision.kind, DecisionKind.NONE)

    def test_edit_elsewhere_in_a_file_holding_a_secret_is_allowed(self):
        self.tracked_file.write_text(f'key = "{AWS_KEY}"\nvalue = 1\n', encoding="utf-8")

        decision = evaluate(edit_payload(self.tracked_file, "value = 1", "value = 2", self.project))

        self.assertEqual(decision.kind, DecisionKind.NONE)

    def test_edit_introducing_a_secret_is_denied(self):
        self.tracked_file.write_text("value = 1\n", encoding="utf-8")

        decision = evaluate(edit_payload(self.tracked_file, "value = 1", f'key = "{AWS_KEY}"', self.project))

        self.assertEqual(decision.kind, DecisionKind.DENY)
        self.assertEqual(decision.rule_id, "SECRET-AWS-ACCESS-KEY")

    def test_edit_introducing_a_second_secret_class_is_denied(self):
        self.tracked_file.write_text(f'key = "{AWS_KEY}"\nvalue = 1\n', encoding="utf-8")

        decision = evaluate(edit_payload(self.tracked_file, "value = 1", f'token = "{GITHUB_PAT}"', self.project))

        self.assertEqual(decision.kind, DecisionKind.DENY)
        self.assertEqual(decision.rule_id, "SECRET-GITHUB-PAT")

    def test_allow_paths_downgrades_to_warning(self):
        self.write_policy({"version": 1, "secrets": {"allowPaths": ["tests/fixtures/**"]}})
        fixture = self.project / "tests" / "fixtures" / "keys.json"
        fixture.parent.mkdir(parents=True)

        decision = evaluate(write_payload(fixture, f'{{"key": "{AWS_KEY}"}}', self.project))

        self.assertEqual(decision.kind, DecisionKind.WARNING)
        self.assertEqual(decision.rule_id, "SECRET-ALLOWED-PATH")

    def test_allow_paths_does_not_affect_other_files(self):
        self.write_policy({"version": 1, "secrets": {"allowPaths": ["tests/fixtures/**"]}})

        decision = evaluate(write_payload(self.tracked_file, f'key = "{AWS_KEY}"', self.project))

        self.assertEqual(decision.kind, DecisionKind.DENY)

    def test_strict_format_key_containing_a_marker_is_denied(self):
        decision = evaluate(write_payload(self.tracked_file, 'key = "AKIATESTQWERTY123456"', self.project))

        self.assertEqual(decision.kind, DecisionKind.DENY)
        self.assertEqual(decision.rule_id, "SECRET-AWS-ACCESS-KEY")

    def test_credential_url_marker_in_host_does_not_suppress_detection(self):
        content = "DATABASE_URL=postgres://ci:R3alPassw0rd@db-test.acme.internal/app"

        self.assertEqual([finding.rule_id for finding in detect_secrets(content)], ["SECRET-CREDENTIAL-URL"])

    def test_credential_url_placeholder_password_is_ignored(self):
        content = "DATABASE_URL=postgres://ci:your-password-here@db.acme.internal/app"

        self.assertEqual(detect_secrets(content), [])

    def test_environment_reference_is_not_a_generic_secret(self):
        for content in (
            "const apiKey = process.env.API_KEY_PRODUCTION;",
            "password = getPasswordFromVaultService",
            "api_key = $SOME_ENV_VARIABLE_NAME_HERE",
        ):
            with self.subTest(content):
                self.assertEqual(detect_secrets(content), [])

    def test_unquoted_literal_is_still_a_generic_secret(self):
        content = "API_TOKEN=superSecretValue1234567890"

        self.assertEqual([finding.rule_id for finding in detect_secrets(content)], ["SECRET-GENERIC-LITERAL"])


if __name__ == "__main__":
    unittest.main()
