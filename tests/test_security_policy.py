import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import HARDENING_DIR, load_script  # noqa: E402


APPLY_PROFILE = HARDENING_DIR / "apply_profile.py"
SCHEMA = HARDENING_DIR / "security-policy.schema.json"
DEFAULT_POLICY = HARDENING_DIR / "defaults" / "baseline-policy.json"
STRICT_POLICY = HARDENING_DIR / "defaults" / "strict-policy.json"

apply_profile = load_script(APPLY_PROFILE)


class SecurityPolicySchemaTests(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.policy = json.loads(DEFAULT_POLICY.read_text(encoding="utf-8"))
        self.strict_policy = json.loads(STRICT_POLICY.read_text(encoding="utf-8"))

    def validate(self, policy):
        apply_profile.validate_policy(policy, self.schema, "test policy")

    def test_default_policy_matches_schema(self):
        self.validate(self.policy)

    def test_strict_policy_matches_schema(self):
        self.validate(self.strict_policy)
        self.assertEqual(self.strict_policy["profile"], "strict")

    def test_schema_allows_known_profiles(self):
        profiles = self.schema["properties"]["profile"]["enum"]

        self.assertEqual(profiles, ["baseline", "strict"])

    def test_schema_requires_version(self):
        policy = copy.deepcopy(self.policy)
        del policy["version"]

        with self.assertRaises(apply_profile.ProfileError):
            self.validate(policy)

    def test_schema_rejects_unknown_top_level_fields(self):
        policy = copy.deepcopy(self.policy)
        policy["unexpected"] = True

        with self.assertRaises(apply_profile.ProfileError):
            self.validate(policy)

    def test_schema_validates_types(self):
        policy = copy.deepcopy(self.policy)
        policy["protectedBranches"] = "main"

        with self.assertRaises(apply_profile.ProfileError):
            self.validate(policy)

    def test_schema_rejects_negative_thresholds(self):
        policy = copy.deepcopy(self.policy)
        policy["largeFiles"]["warningLines"] = -1

        with self.assertRaises(apply_profile.ProfileError):
            self.validate(policy)

    def test_schema_defines_guard_decisions(self):
        decisions = self.schema["$defs"]["decision"]["enum"]

        self.assertEqual(decisions, ["deny", "ask", "warning", "additionalContext", "none"])

    def test_schema_properties_have_descriptions(self):
        def check_descriptions(schema):
            for key, value in schema.get("properties", {}).items():
                self.assertIn("description", value, key)
                check_descriptions(value)

        check_descriptions(self.schema)

    def test_schema_uses_versioned_format(self):
        version = self.schema["properties"]["version"]

        self.assertEqual(version["const"], 1)


if __name__ == "__main__":
    unittest.main()
