import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import SCRIPTS_DIR, hook_payload, load_script, run_script, write_policy  # noqa: E402


LARGE_FILE_POLICY = SCRIPTS_DIR / "large_file_policy.py"
large_file_policy = load_script(LARGE_FILE_POLICY)


def content_lines(count):
    return "\n".join(f"line {index}" for index in range(count))


class LargeFilePolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.project = Path(self.tmpdir.name)
        (self.project / ".git").mkdir()
        write_policy(
            self.project,
            {
                "version": 1,
                "paths": {"generated": ["**/generated/**"]},
                "largeFiles": {
                    "warningLines": 800,
                    "askOnCreateLines": 1200,
                    "askOnGrowthLines": 100,
                },
            },
        )

    def tearDown(self):
        self.tmpdir.cleanup()

    def payload(self, tool_name, file_path, **tool_input):
        return hook_payload(
            "PreToolUse",
            tool_name,
            {"file_path": str(file_path), **tool_input},
            cwd=self.project,
        )

    def decision(self, output):
        if output is None:
            return None
        hook_output = output["hookSpecificOutput"]
        return hook_output.get("permissionDecision") or ("warning" if "additionalContext" in hook_output else None)

    def test_new_file_below_warning_has_no_decision(self):
        output = large_file_policy.run(
            self.payload("Write", self.project / "small.py", content=content_lines(799))
        )

        self.assertIsNone(output)

    def test_new_file_between_thresholds_warns(self):
        output = large_file_policy.run(
            self.payload("Write", self.project / "large.py", content=content_lines(800))
        )

        self.assertEqual(self.decision(output), "warning")

    def test_new_huge_file_asks(self):
        output = large_file_policy.run(
            self.payload("Write", self.project / "huge.py", content=content_lines(1201))
        )

        self.assertEqual(self.decision(output), "ask")

    def test_existing_file_can_shrink_without_noise(self):
        target = self.project / "existing.py"
        target.write_text(content_lines(1300), encoding="utf-8")

        output = large_file_policy.run(self.payload("Write", target, content=content_lines(700)))

        self.assertIsNone(output)

    def test_existing_file_small_growth_warns(self):
        target = self.project / "existing.py"
        target.write_text(content_lines(900), encoding="utf-8")

        output = large_file_policy.run(self.payload("Write", target, content=content_lines(950)))

        self.assertEqual(self.decision(output), "warning")

    def test_existing_file_large_growth_asks(self):
        target = self.project / "existing.py"
        target.write_text(content_lines(900), encoding="utf-8")

        output = large_file_policy.run(self.payload("Write", target, content=content_lines(1000)))

        self.assertEqual(self.decision(output), "ask")

    def test_generated_file_is_excluded(self):
        output = large_file_policy.run(
            self.payload("Write", self.project / "src" / "generated" / "huge.py", content=content_lines(2000))
        )

        self.assertIsNone(output)

    def test_edit_replace_all_uses_all_matches(self):
        target = self.project / "existing.py"
        target.write_text("anchor\n" * 900, encoding="utf-8")

        output = large_file_policy.run(
            self.payload(
                "Edit",
                target,
                old_string="anchor",
                new_string="anchor\nextra",
                replace_all=True,
            )
        )

        self.assertEqual(self.decision(output), "ask")

    def test_edit_with_ambiguous_match_warns(self):
        target = self.project / "existing.py"
        target.write_text("same\nsame\n", encoding="utf-8")

        output = large_file_policy.run(
            self.payload(
                "Edit",
                target,
                old_string="same",
                new_string="different",
            )
        )

        self.assertEqual(self.decision(output), "warning")


if __name__ == "__main__":
    unittest.main()
