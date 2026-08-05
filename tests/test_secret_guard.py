import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
HOOKS_DIR = ROOT / "plugin" / "hooks"
SECRET_GUARD = HOOKS_DIR / "scripts" / "secret_guard.py"
SECRET_FIXTURES = ROOT / "tests" / "fixtures" / "secret-patterns.json"

if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from guard.decisions import DecisionKind
from guard.secrets import FileClass, classify_file, detect_secrets, evaluate

spec = importlib.util.spec_from_file_location("secret_guard", SECRET_GUARD)
secret_guard = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["secret_guard"] = secret_guard
spec.loader.exec_module(secret_guard)


AWS_KEY = "AKIA1234567890ABCDEF"
GITHUB_PAT = "ghp_1234567890abcdefABCDEF1234567890abcd"
FINE_GRAINED_GITHUB_PAT = "github_pat_11AAAAAAA0abcdefghijklmnopqrstuvwxyz_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdef"
PRIVATE_KEY = "-----BEGIN PRIVATE KEY-----\nnot-a-real-key\n-----END PRIVATE KEY-----"
DUMMY_PRIVATE_KEY = "-----BEGIN PRIVATE KEY-----\ndummy-placeholder-test-key\n-----END PRIVATE KEY-----"


def write_payload(path, content, cwd, tool_name="Write"):
    tool_input = {"file_path": str(path)}
    if tool_name == "Write":
        tool_input["content"] = content
    else:
        tool_input["new_string"] = content
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "cwd": str(cwd),
    }


def edit_payload(path, old_string, new_string, cwd, replace_all=False):
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(path),
            "old_string": old_string,
            "new_string": new_string,
            "replace_all": replace_all,
        },
        "cwd": str(cwd),
    }


class SecretGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.project = Path(self.tmpdir.name)
        subprocess.run(["git", "init"], cwd=self.project, text=True, capture_output=True, check=True)
        (self.project / ".gitignore").write_text(".env\nignored/\n", encoding="utf-8")
        self.tracked_file = self.project / "src" / "app.py"
        self.tracked_file.parent.mkdir()
        self.tracked_file.write_text("print('hello')\n", encoding="utf-8")
        subprocess.run(["git", "add", ".gitignore", "src/app.py"], cwd=self.project, text=True, capture_output=True, check=True)

    def tearDown(self):
        self.tmpdir.cleanup()

    def run_guard(self, payload):
        return subprocess.run(
            [sys.executable, str(SECRET_GUARD)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=False,
        )

    def hook_output(self, completed):
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stderr, "")
        return json.loads(completed.stdout)["hookSpecificOutput"]

    def test_pattern_fixtures(self):
        fixtures = json.loads(SECRET_FIXTURES.read_text(encoding="utf-8"))

        for fixture in fixtures:
            with self.subTest(fixture["name"]):
                findings = detect_secrets(fixture["content"])
                if fixture["decision"] == "none":
                    self.assertEqual(findings, [])
                    continue
                self.assertTrue(any(finding.rule_id == fixture["rule"] for finding in findings))

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
        completed = subprocess.run(
            [sys.executable, str(SECRET_GUARD)],
            input="{invalid",
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        self.assertIn("secret_guard warning", completed.stderr)
        self.assertNotIn("invalid", completed.stderr)


if __name__ == "__main__":
    unittest.main()
