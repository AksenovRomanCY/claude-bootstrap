import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
HOOKS_DIR = ROOT / "plugin" / "hooks"
COMMAND_GUARD = HOOKS_DIR / "scripts" / "command_guard.py"
FIXTURES = ROOT / "tests" / "fixtures" / "bash-commands.json"

if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from guard.decisions import Decision, DecisionKind, combine
from guard.shell import parse

spec = importlib.util.spec_from_file_location("command_guard", COMMAND_GUARD)
command_guard = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["command_guard"] = command_guard
spec.loader.exec_module(command_guard)


def bash_payload(command):
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {
            "command": command,
        },
        "cwd": str(ROOT),
    }


class CommandGuardTests(unittest.TestCase):
    def run_guard(self, payload):
        return subprocess.run(
            [sys.executable, str(COMMAND_GUARD)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=False,
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
        fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))

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
