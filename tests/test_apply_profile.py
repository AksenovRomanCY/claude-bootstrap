import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
APPLY_PROFILE = ROOT / "plugin" / "hardening" / "apply_profile.py"

spec = importlib.util.spec_from_file_location("apply_profile", APPLY_PROFILE)
apply_profile = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["apply_profile"] = apply_profile
spec.loader.exec_module(apply_profile)


class ApplyProfileTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.project = Path(self.tempdir.name)
        self.settings = self.project / ".claude" / "settings.json"
        self.policy = self.project / ".claude" / "security-policy.json"

    def tearDown(self):
        self.tempdir.cleanup()

    def write_settings(self, data):
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.settings.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def read_settings(self):
        return json.loads(self.settings.read_text(encoding="utf-8"))

    def write_policy(self, data):
        self.policy.parent.mkdir(parents=True, exist_ok=True)
        self.policy.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def read_policy(self):
        return json.loads(self.policy.read_text(encoding="utf-8"))

    def read_state(self):
        return json.loads((self.project / ".claude" / "harden-state.json").read_text(encoding="utf-8"))

    def apply(self, **kwargs):
        return apply_profile.apply_profile(
            project_root=self.project,
            profile_name="baseline",
            **kwargs,
        )

    def remove(self, **kwargs):
        return apply_profile.remove_profile(
            project_root=self.project,
            profile_name="baseline",
            **kwargs,
        )

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(APPLY_PROFILE), *args],
            cwd=self.project,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_creates_settings_when_missing(self):
        result = self.apply()

        self.assertTrue(result.changed)
        settings = self.read_settings()
        self.assertEqual(settings["permissions"]["disableBypassPermissionsMode"], "disable")
        self.assertIn("Bash(npm publish *)", settings["permissions"]["ask"])
        self.assertIn("Bash(gh repo delete *)", settings["permissions"]["deny"])
        self.assertEqual(self.read_policy()["profile"], "baseline")
        state = self.read_state()
        self.assertEqual(state["managedBy"], "claude-bootstrap")
        self.assertEqual(state["managedVersion"], 1)
        self.assertEqual(state["appliedProfile"], "baseline")
        self.assertIn("Bash(npm publish *)", state["insertedSettings"]["permissions.ask"])
        self.assertEqual(
            state["insertedSettings"]["scalars"]["permissions.disableBypassPermissionsMode"],
            "disable",
        )
        self.assertTrue(state["managedPolicy"]["created"])
        self.assertEqual(list(self.settings.parent.glob("settings.json.backup-*")), [])

    def test_preserves_existing_valid_policy(self):
        custom_policy = {
            "version": 1,
            "managedBy": "claude-bootstrap",
            "profile": "baseline",
            "protectedBranches": ["release"],
            "largeFiles": {
                "warningLines": 10,
                "askOnCreateLines": 20,
                "askOnGrowthLines": 5,
            },
        }
        self.write_policy(custom_policy)

        self.apply()

        self.assertEqual(self.read_policy(), custom_policy)

    def test_preserves_unknown_keys_and_hooks(self):
        hooks = {"PreToolUse": [{"matcher": "Bash", "hooks": [{"command": "custom"}]}]}
        self.write_settings({"custom": {"enabled": True}, "hooks": hooks})

        self.apply()

        settings = self.read_settings()
        self.assertEqual(settings["custom"], {"enabled": True})
        self.assertEqual(settings["hooks"], hooks)
        self.assertIn("permissions", settings)

    def test_merges_existing_permissions_and_deduplicates(self):
        self.write_settings(
            {
                "permissions": {
                    "allow": ["Bash(git status)", "Bash(git status)"],
                    "ask": ["Bash(existing *)", "Bash(npm publish *)"],
                    "deny": ["Read(./.env)", "Read(./.env)"],
                }
            }
        )

        self.apply()

        permissions = self.read_settings()["permissions"]
        self.assertEqual(permissions["allow"], ["Bash(git status)"])
        self.assertEqual(permissions["ask"][:2], ["Bash(existing *)", "Bash(npm publish *)"])
        self.assertEqual(permissions["ask"].count("Bash(npm publish *)"), 1)
        self.assertEqual(permissions["deny"].count("Read(./.env)"), 1)
        state = self.read_state()
        self.assertNotIn("Bash(npm publish *)", state["insertedSettings"]["permissions.ask"])
        self.assertNotIn("Read(./.env)", state["insertedSettings"]["permissions.deny"])

    def test_conflicting_scalar_requires_force(self):
        self.write_settings({"permissions": {"disableBypassPermissionsMode": "enable"}})

        result = self.apply()

        self.assertFalse(result.changed)
        self.assertEqual(result.conflicts, ["permissions.disableBypassPermissionsMode"])
        self.assertEqual(self.read_settings()["permissions"]["disableBypassPermissionsMode"], "enable")

    def test_force_replaces_conflicting_scalar(self):
        self.write_settings({"permissions": {"disableBypassPermissionsMode": "enable"}})

        result = self.apply(force=True)

        self.assertTrue(result.changed)
        self.assertEqual(result.conflicts, [])
        self.assertEqual(self.read_settings()["permissions"]["disableBypassPermissionsMode"], "disable")

    def test_sandbox_enabled_scalar_conflict(self):
        existing = {"sandbox": {"enabled": False}}
        profile = {"sandbox": {"enabled": True}}

        merged, conflicts = apply_profile.merge_settings(existing, profile)
        self.assertEqual(conflicts, ["sandbox.enabled"])
        self.assertEqual(merged["sandbox"]["enabled"], False)

        forced, conflicts = apply_profile.merge_settings(existing, profile, force=True)
        self.assertEqual(conflicts, [])
        self.assertEqual(forced["sandbox"]["enabled"], True)

    def test_invalid_existing_json_fails_before_write(self):
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.settings.write_text("{invalid", encoding="utf-8")

        with self.assertRaises(apply_profile.ProfileError):
            self.apply()
        self.assertEqual(self.settings.read_text(encoding="utf-8"), "{invalid")

    def test_invalid_existing_policy_fails_before_settings_write(self):
        self.write_settings({"custom": True})
        before = self.settings.read_text(encoding="utf-8")
        self.write_policy({"version": 1, "unknown": True})

        with self.assertRaises(apply_profile.ProfileError):
            self.apply()

        self.assertEqual(self.settings.read_text(encoding="utf-8"), before)

    def test_dry_run_outputs_diff_without_writing(self):
        self.write_settings({"permissions": {"ask": ["Bash(existing *)"]}})
        before = self.settings.read_text(encoding="utf-8")

        completed = self.run_cli("--profile", "baseline", "--dry-run")

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--- ", completed.stdout)
        self.assertIn("Bash(npm publish *)", completed.stdout)
        self.assertIn("security-policy.json", completed.stdout)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), before)
        self.assertFalse(self.policy.exists())

    def test_check_reports_drift_without_writing(self):
        self.write_settings({})
        before = self.settings.read_text(encoding="utf-8")

        completed = self.run_cli("--profile", "baseline", "--check")

        self.assertEqual(completed.returncode, 1)
        self.assertIn("not fully applied", completed.stdout)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), before)

    def test_check_passes_after_apply(self):
        self.apply()

        completed = self.run_cli("--profile", "baseline", "--check")

        self.assertEqual(completed.returncode, 0)
        self.assertIn("already applied", completed.stdout)

    def test_repeated_apply_is_idempotent_and_keeps_formatting(self):
        self.apply()
        first = self.settings.read_text(encoding="utf-8")
        state_first = (self.project / ".claude" / "harden-state.json").read_text(encoding="utf-8")

        result = self.apply()
        second = self.settings.read_text(encoding="utf-8")
        state_second = (self.project / ".claude" / "harden-state.json").read_text(encoding="utf-8")

        self.assertFalse(result.changed)
        self.assertEqual(first, second)
        self.assertEqual(state_first, state_second)
        self.assertEqual(len(list(self.settings.parent.glob("settings.json.backup-*"))), 0)

    def test_no_semantic_change_keeps_existing_formatting(self):
        data = json.loads(apply_profile.profile_path("baseline").read_text(encoding="utf-8"))
        policy = json.loads(apply_profile.default_policy_path("baseline").read_text(encoding="utf-8"))
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.settings.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
        self.policy.write_text(json.dumps(policy, separators=(",", ":")), encoding="utf-8")
        before = self.settings.read_text(encoding="utf-8")
        policy_before = self.policy.read_text(encoding="utf-8")

        result = self.apply()

        self.assertTrue(result.changed)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), before)
        self.assertEqual(self.policy.read_text(encoding="utf-8"), policy_before)
        self.assertTrue((self.project / ".claude" / "harden-state.json").exists())

    def test_existing_settings_get_backup_only_when_changed(self):
        self.write_settings({"permissions": {"ask": ["Bash(existing *)"]}})

        result = self.apply()

        backups = list(self.settings.parent.glob("settings.json.backup-*"))
        self.assertTrue(result.changed)
        self.assertEqual(len(backups), 1)
        self.assertEqual(json.loads(backups[0].read_text(encoding="utf-8"))["permissions"]["ask"], ["Bash(existing *)"])

        self.apply()
        self.assertEqual(len(list(self.settings.parent.glob("settings.json.backup-*"))), 1)

    def test_remove_deletes_only_managed_settings_and_policy(self):
        self.write_settings(
            {
                "permissions": {
                    "ask": ["Bash(existing *)"],
                    "deny": ["Read(./custom-secret)"],
                },
                "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"command": "custom"}]}]},
            }
        )
        self.apply()

        result = self.remove()

        self.assertTrue(result.changed)
        settings = self.read_settings()
        self.assertEqual(settings["permissions"]["ask"], ["Bash(existing *)"])
        self.assertEqual(settings["permissions"]["deny"], ["Read(./custom-secret)"])
        self.assertEqual(settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"], "custom")
        self.assertFalse(self.policy.exists())
        self.assertFalse((self.project / ".claude" / "harden-state.json").exists())

    def test_remove_preserves_existing_policy(self):
        policy = {
            "version": 1,
            "managedBy": "claude-bootstrap",
            "profile": "baseline",
            "protectedBranches": ["main"],
        }
        self.write_policy(policy)
        self.apply()

        self.remove()

        self.assertEqual(self.read_policy(), policy)

    def test_remove_conflicts_on_modified_managed_scalar(self):
        self.apply()
        settings = self.read_settings()
        settings["permissions"]["disableBypassPermissionsMode"] = "enable"
        self.write_settings(settings)

        result = self.remove()

        self.assertFalse(result.changed)
        self.assertEqual(result.conflicts, ["permissions.disableBypassPermissionsMode"])
        self.assertTrue((self.project / ".claude" / "harden-state.json").exists())

    def test_remove_conflicts_on_missing_managed_permission(self):
        self.apply()
        settings = self.read_settings()
        settings["permissions"]["ask"].remove("Bash(npm publish *)")
        settings["permissions"]["ask"].append("Bash(npm publish --tag beta *)")
        self.write_settings(settings)

        result = self.remove()

        self.assertFalse(result.changed)
        self.assertEqual(result.conflicts, ["permissions.ask"])
        self.assertTrue((self.project / ".claude" / "harden-state.json").exists())

    def test_force_remove_deletes_modified_managed_scalar(self):
        self.apply()
        settings = self.read_settings()
        settings["permissions"]["disableBypassPermissionsMode"] = "enable"
        self.write_settings(settings)

        result = self.remove(force=True)

        self.assertTrue(result.changed)
        self.assertNotIn("permissions", self.read_settings())
        self.assertFalse((self.project / ".claude" / "harden-state.json").exists())

    def test_remove_conflicts_on_modified_managed_policy(self):
        self.apply()
        policy = self.read_policy()
        policy["protectedBranches"].append("release")
        self.write_policy(policy)

        result = self.remove()

        self.assertFalse(result.changed)
        self.assertEqual(result.conflicts, ["security-policy.json"])
        self.assertTrue(self.policy.exists())

    def test_check_reports_modified_managed_policy(self):
        self.apply()
        policy = self.read_policy()
        policy["protectedBranches"].append("release")
        self.write_policy(policy)

        completed = self.run_cli("--profile", "baseline", "--check")

        self.assertEqual(completed.returncode, 1)
        self.assertIn("security-policy.json", completed.stderr)

    def test_repeated_remove_is_idempotent(self):
        self.apply()
        self.remove()

        result = self.remove()

        self.assertFalse(result.changed)
        self.assertEqual(result.conflicts, [])

    def test_atomic_write_failure_leaves_original_file(self):
        self.write_settings({"permissions": {"ask": ["Bash(existing *)"]}})
        before = self.settings.read_text(encoding="utf-8")

        with mock.patch.object(apply_profile.os, "replace", side_effect=OSError("boom")):
            with self.assertRaises(apply_profile.ProfileError):
                self.apply()

        self.assertEqual(self.settings.read_text(encoding="utf-8"), before)
        self.assertEqual(list(self.settings.parent.glob(".settings.json.*.tmp")), [])

    def test_settings_write_failure_removes_new_policy(self):
        self.write_settings({"permissions": {"ask": ["Bash(existing *)"]}})
        before = self.settings.read_text(encoding="utf-8")
        real_atomic_write = apply_profile.atomic_write

        def fail_settings_write(path, content):
            if path == self.settings:
                raise OSError("settings failed")
            real_atomic_write(path, content)

        with mock.patch.object(apply_profile, "atomic_write", side_effect=fail_settings_write):
            with self.assertRaises(apply_profile.ProfileError):
                self.apply()

        self.assertEqual(self.settings.read_text(encoding="utf-8"), before)
        self.assertFalse(self.policy.exists())
        self.assertFalse((self.project / ".claude" / "harden-state.json").exists())

    def test_state_write_failure_rolls_back_fresh_apply(self):
        state = self.project / ".claude" / "harden-state.json"
        real_atomic_write = apply_profile.atomic_write

        def fail_state_write(path, content):
            if path == state:
                raise OSError("state failed")
            real_atomic_write(path, content)

        with mock.patch.object(apply_profile, "atomic_write", side_effect=fail_state_write):
            with self.assertRaises(apply_profile.ProfileError):
                self.apply()

        self.assertFalse(self.settings.exists())
        self.assertFalse(self.policy.exists())
        self.assertFalse(state.exists())

    def test_state_write_failure_rolls_back_existing_files(self):
        self.write_settings({"permissions": {"ask": ["Bash(existing *)"]}})
        self.write_policy(
            {
                "version": 1,
                "managedBy": "claude-bootstrap",
                "profile": "baseline",
                "protectedBranches": ["main"],
            }
        )
        state = self.project / ".claude" / "harden-state.json"
        state.write_text(
            json.dumps(
                {
                    "managedBy": "claude-bootstrap",
                    "managedVersion": 1,
                    "appliedProfile": "baseline",
                    "insertedSettings": {"permissions.ask": ["Bash(old *)"], "scalars": {}},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        settings_before = self.settings.read_text(encoding="utf-8")
        policy_before = self.policy.read_text(encoding="utf-8")
        state_before = state.read_text(encoding="utf-8")
        real_atomic_write = apply_profile.atomic_write

        def fail_state_write(path, content):
            if path == state:
                raise OSError("state failed")
            real_atomic_write(path, content)

        with mock.patch.object(apply_profile, "atomic_write", side_effect=fail_state_write):
            with self.assertRaises(apply_profile.ProfileError):
                self.apply()

        self.assertEqual(self.settings.read_text(encoding="utf-8"), settings_before)
        self.assertEqual(self.policy.read_text(encoding="utf-8"), policy_before)
        self.assertEqual(state.read_text(encoding="utf-8"), state_before)

    def test_cli_conflict_exits_nonzero(self):
        self.write_settings({"permissions": {"disableBypassPermissionsMode": "enable"}})

        completed = self.run_cli("--profile", "baseline")

        self.assertEqual(completed.returncode, 1)
        self.assertIn("permissions.disableBypassPermissionsMode", completed.stderr)

    def test_cli_applies_profile(self):
        completed = self.run_cli("--profile", "baseline")

        self.assertEqual(completed.returncode, 0)
        self.assertIn("Applied profile", completed.stdout)
        self.assertTrue(self.settings.exists())
        self.assertTrue((self.project / ".claude" / "harden-state.json").exists())

    def test_cli_removes_profile(self):
        self.apply()

        completed = self.run_cli("--profile", "baseline", "--remove")

        self.assertEqual(completed.returncode, 0)
        self.assertIn("Removed profile", completed.stdout)
        self.assertFalse((self.project / ".claude" / "harden-state.json").exists())

    def test_cli_remove_conflict_exits_nonzero(self):
        self.apply()
        settings = self.read_settings()
        settings["permissions"]["disableBypassPermissionsMode"] = "enable"
        self.write_settings(settings)

        completed = self.run_cli("--profile", "baseline", "--remove")

        self.assertEqual(completed.returncode, 1)
        self.assertIn("permissions.disableBypassPermissionsMode", completed.stderr)
        self.assertIn("Use --force", completed.stderr)


if __name__ == "__main__":
    with contextlib.redirect_stdout(io.StringIO()):
        unittest.main()
