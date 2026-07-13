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


def default_policy_path(profile: str) -> Path:
    return Path(__file__).resolve().parent / "defaults" / f"{profile}-policy.json"


def policy_schema_path() -> Path:
    return Path(__file__).resolve().parent / "security-policy.schema.json"


def settings_path(project_root: Path) -> Path:
    return project_root / ".claude" / "settings.json"


def security_policy_path(project_root: Path) -> Path:
    return project_root / ".claude" / "security-policy.json"


def type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    return True


def validate_json_schema(data: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    errors: list[str] = []

    expected_type = schema.get("type")
    if isinstance(expected_type, str) and not type_matches(data, expected_type):
        errors.append(f"{path}: expected {expected_type}")
        return errors

    if "const" in schema and data != schema["const"]:
        errors.append(f"{path}: expected {schema['const']!r}")

    if "enum" in schema and data not in schema["enum"]:
        errors.append(f"{path}: expected one of {schema['enum']!r}")

    if isinstance(data, int) and not isinstance(data, bool) and "minimum" in schema:
        if data < schema["minimum"]:
            errors.append(f"{path}: must be >= {schema['minimum']}")

    if isinstance(data, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        for key in required:
            if key not in data:
                errors.append(f"{path}.{key}: missing required field")

        if schema.get("additionalProperties") is False:
            for key in data:
                if key not in properties:
                    errors.append(f"{path}.{key}: unknown field")

        for key, value in data.items():
            if key in properties:
                errors.extend(validate_json_schema(value, properties[key], f"{path}.{key}"))

    if isinstance(data, list):
        if schema.get("uniqueItems") is True:
            seen: set[str] = set()
            for index, item in enumerate(data):
                key = json.dumps(item, sort_keys=True, separators=(",", ":"))
                if key in seen:
                    errors.append(f"{path}[{index}]: duplicate item")
                seen.add(key)

        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(data):
                errors.extend(validate_json_schema(item, item_schema, f"{path}[{index}]"))

    return errors


def validate_policy(policy: dict[str, Any], schema: dict[str, Any], label: str) -> None:
    errors = validate_json_schema(policy, schema)
    if errors:
        details = "; ".join(errors)
        raise ProfileError(f"{label} does not match security policy schema: {details}")


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


def prepare_security_policy(project_root: Path, profile_name: str) -> tuple[Path, bool, str, str]:
    schema = load_json(policy_schema_path(), "security policy schema")
    default_policy = load_json(default_policy_path(profile_name), f"default policy '{profile_name}'")
    validate_policy(default_policy, schema, f"default policy '{profile_name}'")

    target = security_policy_path(project_root)
    if target.exists():
        existing_policy = load_json(target, "security policy")
        validate_policy(existing_policy, schema, "security policy")
        return target, False, target.read_text(encoding="utf-8"), target.read_text(encoding="utf-8")

    after = format_json(default_policy)
    return target, True, "", after


def apply_profile(
    *,
    project_root: Path,
    profile_name: str,
    dry_run: bool = False,
    check: bool = False,
    force: bool = False,
) -> ApplyResult:
    profile = load_json(profile_path(profile_name), f"profile '{profile_name}'")
    policy_target, policy_changed, policy_before, policy_after = prepare_security_policy(project_root, profile_name)
    target = settings_path(project_root)

    if target.exists():
        existing = load_json(target, "settings")
        before = target.read_text(encoding="utf-8")
    else:
        existing = {}
        before = ""

    merged, conflicts = merge_settings(existing, profile, force=force)
    settings_changed = merged != existing
    changed = settings_changed or policy_changed
    after = format_json(merged)
    diff = ""
    if settings_changed:
        diff += unified_diff(before, after, target)
    if policy_changed:
        diff += unified_diff(policy_before, policy_after, policy_target)

    if conflicts:
        return ApplyResult(changed=False, conflicts=conflicts, diff="")

    if not changed or dry_run or check:
        return ApplyResult(changed=changed, conflicts=[], diff=diff)

    backup_path = create_backup(target) if settings_changed and target.exists() else None
    policy_existed = policy_target.exists()
    try:
        if policy_changed:
            atomic_write(policy_target, policy_after)
        if settings_changed:
            atomic_write(target, after)
    except OSError as exc:
        if policy_changed and not policy_existed:
            policy_target.unlink(missing_ok=True)
        raise ProfileError(f"failed to write profile files: {exc}") from exc

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
