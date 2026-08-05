import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOKS_DIR = ROOT / "plugin" / "hooks"

if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from guard.paths import (  # noqa: E402
    find_project_root,
    find_project_root_literal,
    normalize_existing_path,
    path_matches_patterns,
    relative_to_project,
    resolve_file_path,
)
from guard.policy import load_policy, policy_section, string_list  # noqa: E402
from guard.process import command_output, command_succeeds, run_command  # noqa: E402


class ProjectRootTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name).resolve()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_finds_repository_root_from_a_subdirectory(self):
        (self.root / ".git").mkdir()
        nested = self.root / "src" / "app"
        nested.mkdir(parents=True)

        self.assertEqual(find_project_root(nested), self.root)

    def test_git_wins_over_an_enclosing_claude_directory(self):
        """A checkout below the home directory must not resolve to ~/.claude."""
        (self.root / ".claude").mkdir()
        checkout = self.root / "projects" / "app"
        checkout.mkdir(parents=True)
        (checkout / ".git").mkdir()
        nested = checkout / "src"
        nested.mkdir()

        self.assertEqual(find_project_root(nested), checkout)

    def test_claude_directory_is_the_fallback_outside_a_repository(self):
        (self.root / ".claude").mkdir()
        nested = self.root / "src"
        nested.mkdir()

        self.assertEqual(find_project_root(nested), self.root)

    def test_unmarked_directory_is_its_own_root(self):
        nested = self.root / "src"
        nested.mkdir()

        self.assertEqual(find_project_root(nested), nested)

    def test_git_file_of_a_worktree_counts_as_a_marker(self):
        (self.root / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
        nested = self.root / "src"
        nested.mkdir()

        self.assertEqual(find_project_root(nested), self.root)

    def test_literal_and_resolved_roots_name_the_same_directory(self):
        (self.root / ".git").mkdir()
        nested = self.root / "src"
        nested.mkdir()

        literal = find_project_root_literal(nested)
        self.assertEqual(literal.resolve(), find_project_root(nested))
        self.assertEqual(literal, normalize_existing_path(nested).parent)


class PathHelperTests(unittest.TestCase):
    def test_relative_to_project_falls_back_to_the_absolute_path(self):
        self.assertEqual(relative_to_project(Path("/a/b/c.py"), Path("/a")), "b/c.py")
        self.assertEqual(relative_to_project(Path("/other/c.py"), Path("/a")), "/other/c.py")

    def test_resolve_file_path_joins_relative_paths_to_cwd(self):
        with tempfile.TemporaryDirectory() as name:
            cwd = Path(name).resolve()
            self.assertEqual(resolve_file_path("src/app.py", cwd), cwd / "src" / "app.py")
            self.assertEqual(resolve_file_path(str(cwd / "app.py"), cwd), cwd / "app.py")

    def test_pattern_matching_covers_globs_relative_paths_and_bare_names(self):
        root = Path("/repo")
        fixture = Path("/repo/tests/fixtures/keys.json")

        self.assertTrue(path_matches_patterns(fixture, root, ["tests/fixtures/**"]))
        self.assertTrue(path_matches_patterns(fixture, root, ["**/keys.json"]))
        self.assertTrue(path_matches_patterns(fixture, root, ["keys.json"]))
        self.assertTrue(path_matches_patterns(fixture, root, ["./tests/fixtures/keys.json"]))
        self.assertFalse(path_matches_patterns(fixture, root, ["docs/**"]))

    def test_no_patterns_never_matches(self):
        self.assertFalse(path_matches_patterns(Path("/repo/a.py"), Path("/repo"), []))


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name).resolve()
        self.policy_file = self.root / ".claude" / "security-policy.json"
        self.policy_file.parent.mkdir()

    def tearDown(self):
        self.tmpdir.cleanup()

    def write(self, data):
        text = data if isinstance(data, str) else json.dumps(data)
        self.policy_file.write_text(text, encoding="utf-8")

    def test_missing_policy_is_an_empty_mapping(self):
        self.assertEqual(load_policy(self.root / "elsewhere"), {})

    def test_malformed_policy_is_an_empty_mapping(self):
        self.write("{ not json")

        self.assertEqual(load_policy(self.root), {})

    def test_non_object_policy_is_an_empty_mapping(self):
        self.write([1, 2, 3])

        self.assertEqual(load_policy(self.root), {})

    def test_policy_is_read_once_per_process(self):
        self.write({"version": 1, "protectedBranches": ["release"]})
        reads = []
        original_read_text = Path.read_text

        def counting_read_text(path, *args, **kwargs):
            if path.name == "security-policy.json":
                reads.append(path)
            return original_read_text(path, *args, **kwargs)

        Path.read_text = counting_read_text
        try:
            for _ in range(5):
                self.assertEqual(load_policy(self.root)["protectedBranches"], ["release"])
        finally:
            Path.read_text = original_read_text

        self.assertEqual(len(reads), 1)

    def test_rewritten_policy_is_picked_up(self):
        self.write({"version": 1, "protectedBranches": ["release"]})
        self.assertEqual(load_policy(self.root)["protectedBranches"], ["release"])

        self.write({"version": 1, "protectedBranches": ["trunk"]})

        self.assertEqual(load_policy(self.root)["protectedBranches"], ["trunk"])

    def test_policy_section_tolerates_missing_and_wrong_types(self):
        policy = {"production": {"markers": ["prod"]}, "paths": "not an object"}

        self.assertEqual(policy_section(policy, "production"), {"markers": ["prod"]})
        self.assertEqual(policy_section(policy, "paths"), {})
        self.assertEqual(policy_section(policy, "absent"), {})

    def test_string_list_drops_non_strings_and_blanks(self):
        self.assertEqual(string_list(["a", "", 1, None, "b"]), ["a", "b"])
        self.assertEqual(string_list("not a list"), [])
        self.assertEqual(string_list(None), [])


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmpdir.name).resolve()

    def tearDown(self):
        self.tmpdir.cleanup()

    def python(self, source):
        return [sys.executable, "-c", source]

    def test_run_command_returns_the_completed_process(self):
        completed = run_command(self.cwd, self.python("print('hello')"))

        self.assertIsNotNone(completed)
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout.strip(), "hello")

    def test_a_missing_binary_is_unknown_rather_than_an_error(self):
        self.assertIsNone(run_command(self.cwd, ["claude-bootstrap-no-such-binary"]))
        self.assertIsNone(command_output(self.cwd, ["claude-bootstrap-no-such-binary"]))
        self.assertFalse(command_succeeds(self.cwd, ["claude-bootstrap-no-such-binary"]))

    def test_a_command_that_outlives_its_timeout_is_unknown(self):
        slow = self.python("import time; time.sleep(30)")

        self.assertIsNone(run_command(self.cwd, slow, timeout=0.3))

    def test_command_output_trims_and_requires_success(self):
        self.assertEqual(command_output(self.cwd, self.python("print('  spaced  ')")), "spaced")
        self.assertIsNone(command_output(self.cwd, self.python("raise SystemExit(3)")))

    def test_command_succeeds_reports_the_exit_status(self):
        self.assertTrue(command_succeeds(self.cwd, self.python("pass")))
        self.assertFalse(command_succeeds(self.cwd, self.python("raise SystemExit(1)")))

    def test_arguments_are_never_interpreted_by_a_shell(self):
        marker = self.cwd / "shell-ran"
        completed = run_command(self.cwd, ["echo", f"x; touch {marker}"])

        self.assertIsNotNone(completed)
        self.assertIn(";", completed.stdout)
        self.assertFalse(marker.exists())

    def test_commands_run_in_the_requested_directory(self):
        nested = self.cwd / "nested"
        nested.mkdir()

        output = command_output(nested, self.python("import os; print(os.getcwd())"))

        self.assertEqual(Path(output).resolve(), nested)


if __name__ == "__main__":
    unittest.main()
