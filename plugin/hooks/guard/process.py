"""Single subprocess wrapper for guard rules.

Guards run inside a PreToolUse hook, so every external command sits on the
critical path of a tool call. The rules here hold for all of them: pass the
command as a list so no shell is involved, bound it with a timeout, and treat a
command that cannot run as unknown rather than as an error. A guard that raises
would deny the tool call it was only meant to describe.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


DEFAULT_TIMEOUT_SECONDS = 2


def run_command(
    cwd: Path,
    command: list[str],
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str] | None:
    """The completed process, or None when the command could not be run at all."""
    try:
        return subprocess.run(
            command,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def command_output(
    cwd: Path,
    command: list[str],
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> str | None:
    """Trimmed stdout of a successful command, or None when it failed to run."""
    completed = run_command(cwd, command, timeout=timeout)
    if completed is None or completed.returncode != 0:
        return None
    return completed.stdout.strip()


def command_succeeds(
    cwd: Path,
    command: list[str],
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> bool:
    """Whether the command exited zero. A command that cannot run has not succeeded."""
    completed = run_command(cwd, command, timeout=timeout)
    return completed is not None and completed.returncode == 0
