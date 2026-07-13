#!/usr/bin/env python3
"""Apply claude-bootstrap hardening profiles to project settings."""

from __future__ import annotations

import argparse
import copy
import difflib
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


PERMISSION_LISTS = {
    ("permissions", "allow"),
    ("permissions", "ask"),
    ("permissions", "deny"),
}
SCALAR_CONFLICTS = {
    ("permissions", "disableBypassPermissionsMode"),
    ("sandbox", "enabled"),
}


class ProfileError(Exception):
    """Raised for user-facing profile application failures."""


@dataclass
class ApplyResult:
    changed: bool
    conflicts: list[str]
    diff: str
    backup_path: Path | None = None


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError as exc:
        raise ProfileError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ProfileError(f"{label} has invalid JSON: {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ProfileError(f"{label} must be a JSON object: {path}")
    return data


def profile_path(profile: str) -> Path:
    return Path(__file__).resolve().parent / "profiles" / f"{profile}.settings.json"


def settings_path(project_root: Path) -> Path:
    return project_root / ".claude" / "settings.json"


def merge_unique(existing: list[Any], incoming: list[Any]) -> list[Any]:
    merged: list[Any] = []
    seen: set[str] = set()

    for item in [*existing, *incoming]:
        key = json.dumps(item, sort_keys=True, separators=(",", ":"))
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)

    return merged


def merge_settings(
    existing: dict[str, Any],
    profile: dict[str, Any],
    *,
    force: bool = False,
) -> tuple[dict[str, Any], list[str]]:
    merged = copy.deepcopy(existing)
    conflicts: list[str] = []

    def merge_node(target: dict[str, Any], source: dict[str, Any], path: tuple[str, ...]) -> None:
        for key, source_value in source.items():
            child_path = (*path, key)

            if key not in target:
                target[key] = copy.deepcopy(source_value)
                continue

            target_value = target[key]

            if child_path in PERMISSION_LISTS:
                if not isinstance(target_value, list) or not isinstance(source_value, list):
                    conflicts.append(".".join(child_path))
                    continue
                target[key] = merge_unique(target_value, source_value)
                continue

            if isinstance(target_value, dict) and isinstance(source_value, dict):
                merge_node(target_value, source_value, child_path)
                continue

            if target_value == source_value:
                continue

            if child_path in SCALAR_CONFLICTS:
                if force:
                    target[key] = copy.deepcopy(source_value)
                else:
                    conflicts.append(".".join(child_path))
                continue

            if force:
                target[key] = copy.deepcopy(source_value)
            else:
                conflicts.append(".".join(child_path))

    merge_node(merged, profile, ())
    permissions = merged.get("permissions")
    if isinstance(permissions, dict):
        for key in ("allow", "ask", "deny"):
            value = permissions.get(key)
            if isinstance(value, list):
                permissions[key] = merge_unique(value, [])
    return merged, conflicts


def format_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def unified_diff(before: str, after: str, path: Path) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=str(path),
            tofile=str(path),
        )
    )


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
        text=True,
    )
    temp_path = Path(temp_name)

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def create_backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = path.with_name(f"{path.name}.backup-{stamp}")
    counter = 1
    while backup_path.exists():
        backup_path = path.with_name(f"{path.name}.backup-{stamp}-{counter}")
        counter += 1
    shutil.copy2(path, backup_path)
    return backup_path


def apply_profile(
    *,
    project_root: Path,
    profile_name: str,
    dry_run: bool = False,
    check: bool = False,
    force: bool = False,
) -> ApplyResult:
    profile = load_json(profile_path(profile_name), f"profile '{profile_name}'")
    target = settings_path(project_root)

    if target.exists():
        existing = load_json(target, "settings")
        before = target.read_text(encoding="utf-8")
    else:
        existing = {}
        before = ""

    merged, conflicts = merge_settings(existing, profile, force=force)
    changed = merged != existing
    after = format_json(merged)
    diff = unified_diff(before, after, target) if changed else ""

    if conflicts:
        return ApplyResult(changed=False, conflicts=conflicts, diff="")

    if not changed or dry_run or check:
        return ApplyResult(changed=changed, conflicts=[], diff=diff)

    backup_path = create_backup(target) if target.exists() else None
    try:
        atomic_write(target, after)
    except OSError as exc:
        raise ProfileError(f"failed to write settings: {target}: {exc}") from exc

    return ApplyResult(changed=True, conflicts=[], diff=diff, backup_path=backup_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply a claude-bootstrap hardening profile.")
    parser.add_argument("--profile", required=True, help="Profile name, for example: baseline")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing settings")
    parser.add_argument("--check", action="store_true", help="Exit non-zero if the profile is not applied")
    parser.add_argument("--force", action="store_true", help="Resolve scalar conflicts by using profile values")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        result = apply_profile(
            project_root=Path.cwd(),
            profile_name=args.profile,
            dry_run=args.dry_run,
            check=args.check,
            force=args.force,
        )
    except ProfileError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if result.conflicts:
        print("Conflicts detected:", file=sys.stderr)
        for conflict in result.conflicts:
            print(f"  - {conflict}", file=sys.stderr)
        print("Use --force to replace conflicting scalar values.", file=sys.stderr)
        return 1

    if args.check:
        if result.changed:
            print(f"Profile '{args.profile}' is not fully applied.")
            if result.diff:
                print(result.diff, end="")
            return 1
        print(f"Profile '{args.profile}' is already applied.")
        return 0

    if args.dry_run:
        if result.changed:
            print(result.diff, end="")
        else:
            print("No changes.")
        return 0

    if result.changed:
        print(f"Applied profile '{args.profile}'.")
        if result.backup_path is not None:
            print(f"Backup: {result.backup_path}")
    else:
        print("No changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
