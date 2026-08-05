#!/usr/bin/env python3
"""Claude Code PreToolUse secret guard entrypoint."""

from __future__ import annotations

import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
HOOKS_DIR = SCRIPT_DIR.parent
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from guard.hook_io import decision_output, run_hook  # noqa: E402
from guard.secrets import evaluate  # noqa: E402


def run(payload: dict[str, object]) -> dict[str, object] | None:
    return decision_output(evaluate(payload))


def main() -> int:
    return run_hook(run, name="secret_guard")


if __name__ == "__main__":
    sys.exit(main())
