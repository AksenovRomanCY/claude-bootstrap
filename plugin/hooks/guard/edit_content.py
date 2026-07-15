"""Shared reconstruction of the content produced by an Edit tool call."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


class EditReconstructionError(ValueError):
    """Raised when an Edit payload cannot be applied unambiguously."""


@dataclass(frozen=True)
class ReconstructedEdit:
    current_content: str
    final_content: str


def reconstruct_edit(file_path: Path, tool_input: dict[str, Any]) -> ReconstructedEdit:
    if not file_path.exists():
        raise EditReconstructionError("Edit target does not exist.")

    old_string = tool_input.get("old_string")
    new_string = tool_input.get("new_string")
    replace_all = tool_input.get("replace_all", False)
    if not isinstance(old_string, str) or old_string == "":
        raise EditReconstructionError("old_string is missing.")
    if not isinstance(new_string, str):
        raise EditReconstructionError("new_string is missing.")
    if not isinstance(replace_all, bool):
        raise EditReconstructionError("replace_all must be a boolean.")

    try:
        current_content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise EditReconstructionError(f"unable to read Edit target: {exc}") from exc
    matches = current_content.count(old_string)
    if matches == 0:
        raise EditReconstructionError("old_string was not found.")
    if matches > 1 and not replace_all:
        raise EditReconstructionError("old_string is not unique.")

    final_content = (
        current_content.replace(old_string, new_string)
        if replace_all
        else current_content.replace(old_string, new_string, 1)
    )
    return ReconstructedEdit(current_content=current_content, final_content=final_content)
