"""Shared path resolution for guard rules.

Every guard has to agree on where the project root is. When they disagree, the
same write is judged against two different policies, so the marker search lives
here once. What legitimately differs between callers is the *path space* they
compare against: rules that reason about paths as the user typed them must not
follow symlinks, while rules that reason about a file on disk must. Both spaces
are named explicitly below rather than hidden behind a flag.
"""

from __future__ import annotations

import fnmatch
import os
from collections.abc import Iterable
from pathlib import Path


def normalize_existing_path(path: Path) -> Path:
    """Absolute and lexically normalized, with symlinks left intact."""
    return Path(os.path.normpath(os.path.abspath(str(path))))


def find_project_root(cwd: Path) -> Path:
    """Project root in resolved path space, for comparing against files on disk.

    Pairs with `resolve_file_path`, which also resolves symlinks.
    """
    return walk_to_project_marker(cwd.resolve())


def find_project_root_literal(cwd: Path) -> Path:
    """Project root in literal path space, for comparing against paths as typed.

    Pairs with rules that normalize a command argument without resolving it, so
    that `rm -rf /tmp/repo` compares equal to a root discovered from the same cwd.
    """
    return walk_to_project_marker(normalize_existing_path(cwd))


def walk_to_project_marker(start: Path) -> Path:
    """Nearest enclosing repository, else the nearest directory holding `.claude`.

    `.git` wins at any depth so a checkout below the home directory resolves to
    the repository rather than to the user's global `~/.claude`.
    """
    claude_root: Path | None = None
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
        if claude_root is None and (candidate / ".claude").is_dir():
            claude_root = candidate
    return claude_root or start


def resolve_file_path(raw_file_path: str, cwd: Path) -> Path:
    path = Path(raw_file_path).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (cwd / path).resolve()


def relative_to_project(file_path: Path, project_root: Path) -> str:
    try:
        return file_path.relative_to(project_root).as_posix()
    except ValueError:
        return file_path.as_posix()


def path_matches_patterns(file_path: Path, project_root: Path, patterns: Iterable[str]) -> bool:
    """Match a file against policy globs, project-relative or by bare file name."""
    relative = relative_to_project(file_path, project_root)
    candidates = {relative, f"./{relative}", file_path.name}
    for pattern in patterns:
        normalized_pattern = pattern.replace("\\", "/")
        for candidate in candidates:
            if fnmatch.fnmatch(candidate, normalized_pattern):
                return True
            if normalized_pattern.startswith("**/") and fnmatch.fnmatch(candidate, normalized_pattern[3:]):
                return True
    return False
