"""Hook input parsing for command guard."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class HookContext:
    hook_event_name: str
    tool_name: str
    command: str
    cwd: Path
    raw: dict[str, Any]

    @property
    def is_bash_pre_tool_use(self) -> bool:
        return self.hook_event_name == "PreToolUse" and self.tool_name == "Bash"


def from_hook_payload(payload: dict[str, Any]) -> HookContext:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}

    command = tool_input.get("command")
    if not isinstance(command, str):
        command = ""

    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        cwd = "."

    return HookContext(
        hook_event_name=str(payload.get("hook_event_name", "")),
        tool_name=str(payload.get("tool_name", "")),
        command=command,
        cwd=Path(cwd),
        raw=payload,
    )
