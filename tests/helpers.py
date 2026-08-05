"""Shared fixtures for the Python test suite.

Importing this module also puts the hook packages on sys.path, so a test file
only needs its own directory on the path to reach everything else.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HOOKS_DIR = ROOT / "plugin" / "hooks"
SCRIPTS_DIR = HOOKS_DIR / "scripts"
HARDENING_DIR = ROOT / "plugin" / "hardening"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

for _path in (HOOKS_DIR, SCRIPTS_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

# Variables that make the guard classify an environment as production. The suite
# must not depend on whichever of them the developer happens to have exported.
ENVIRONMENT_VARIABLES = ("ENV", "ENVIRONMENT", "STAGE", "NODE_ENV")


def load_script(path: Path, name: str | None = None) -> ModuleType:
    """Import an entrypoint that ships as a script rather than as a module."""
    module_name = name or path.stem
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_fixtures(name: str) -> list[dict[str, Any]]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def isolated_env(**overrides: str) -> dict[str, str]:
    """The current environment minus its own production classification."""
    env = os.environ.copy()
    for name in ENVIRONMENT_VARIABLES:
        env.pop(name, None)
    env.update(overrides)
    return env


def env_without_path(**overrides: str) -> dict[str, str]:
    """An environment where no external tool can be found."""
    return isolated_env(PATH="", **overrides)


def run_script(
    script: Path,
    payload: dict[str, Any] | str,
    *,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a hook entrypoint the way Claude Code does: JSON on stdin."""
    return subprocess.run(
        [sys.executable, str(script)],
        input=payload if isinstance(payload, str) else json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        env=isolated_env() if env is None else env,
        cwd=None if cwd is None else str(cwd),
    )


def hook_payload(
    event: str,
    tool_name: str,
    tool_input: dict[str, Any],
    cwd: Path | str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "hook_event_name": event,
        "tool_name": tool_name,
        "tool_input": tool_input,
    }
    if cwd is not None:
        payload["cwd"] = str(cwd)
    return payload


def bash_payload(command: str, cwd: Path | str | None = None) -> dict[str, Any]:
    return hook_payload("PreToolUse", "Bash", {"command": command}, cwd)


def write_payload(
    file_path: Path | str,
    content: str,
    cwd: Path | str | None = None,
    *,
    event: str = "PreToolUse",
) -> dict[str, Any]:
    return hook_payload(event, "Write", {"file_path": str(file_path), "content": content}, cwd)


def edit_payload(
    file_path: Path | str,
    old_string: str,
    new_string: str,
    cwd: Path | str | None = None,
    *,
    replace_all: bool = False,
    event: str = "PreToolUse",
) -> dict[str, Any]:
    return hook_payload(
        event,
        "Edit",
        {
            "file_path": str(file_path),
            "old_string": old_string,
            "new_string": new_string,
            "replace_all": replace_all,
        },
        cwd,
    )


def write_policy(project_root: Path, policy: dict[str, Any]) -> Path:
    """Write a project security policy, creating .claude when needed."""
    policy_dir = project_root / ".claude"
    policy_dir.mkdir(parents=True, exist_ok=True)
    target = policy_dir / "security-policy.json"
    target.write_text(json.dumps(policy), encoding="utf-8")
    return target


def init_git_repo(project_root: Path, *, branch: str | None = None) -> None:
    """A repository isolated from the developer's global git configuration."""
    env = isolated_env(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
    subprocess.run(
        ["git", "init"],
        cwd=project_root,
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )
    if branch is not None:
        subprocess.run(
            ["git", "checkout", "-b", branch],
            cwd=project_root,
            text=True,
            capture_output=True,
            check=True,
            env=env,
        )
