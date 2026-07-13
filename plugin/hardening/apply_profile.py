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
MANAGED_BY = "claude-bootstrap"
MANAGED_VERSION = 1
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


def harden_state_path(project_root: Path) -> Path:
    return project_root / ".claude" / "harden-state.json"


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


def json_key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def path_string(path: tuple[str, ...]) -> str:
    return ".".join(path)


def get_nested(data: dict[str, Any], path: tuple[str, ...]) -> tuple[bool, Any]:
    current: Any = data
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return False, None
        current = current[key]
    return True, current


def delete_nested(data: dict[str, Any], path: tuple[str, ...]) -> None:
    parents: list[tuple[dict[str, Any], str]] = []
    current: Any = data
    for key in path[:-1]:
        if not isinstance(current, dict) or key not in current:
            return
        parents.append((current, key))
        current = current[key]

    if isinstance(current, dict):
        current.pop(path[-1], None)

    for parent, key in reversed(parents):
        value = parent.get(key)
        if isinstance(value, dict) and not value:
            parent.pop(key, None)
        else:
            break


def collect_inserted_settings(
    existing: dict[str, Any],
    profile: dict[str, Any],
    *,
    force: bool = False,
) -> dict[str, Any]:
    inserted: dict[str, Any] = {"scalars": {}}

    def collect(source: dict[str, Any], path: tuple[str, ...]) -> None:
        for key, source_value in source.items():
            child_path = (*path, key)
            exists, existing_value = get_nested(existing, child_path)

            if child_path in PERMISSION_LISTS:
                if not isinstance(source_value, list):
                    continue
                existing_items = existing_value if exists and isinstance(existing_value, list) else []
                existing_keys = {json_key(item) for item in existing_items}
                values = [item for item in source_value if json_key(item) not in existing_keys]
                if values:
                    inserted[path_string(child_path)] = merge_unique([], values)
                continue

            if isinstance(source_value, dict):
                collect(source_value, child_path)
                continue

            if not exists or (force and existing_value != source_value):
                inserted["scalars"][path_string(child_path)] = copy.deepcopy(source_value)

    collect(profile, ())
    return inserted


def merge_state(existing_state: dict[str, Any], new_state: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(existing_state) if existing_state else {}
    merged["managedBy"] = MANAGED_BY
    merged["managedVersion"] = MANAGED_VERSION
    merged["appliedProfile"] = new_state["appliedProfile"]

    existing_inserted = merged.get("insertedSettings")
    if not isinstance(existing_inserted, dict):
        existing_inserted = {}
    new_inserted = new_state.get("insertedSettings", {})
    if not isinstance(new_inserted, dict):
        new_inserted = {}

    combined_inserted: dict[str, Any] = {"scalars": {}}
    for key in sorted(set(existing_inserted) | set(new_inserted)):
        if key == "scalars":
            continue
        existing_values = existing_inserted.get(key, [])
        new_values = new_inserted.get(key, [])
        if isinstance(existing_values, list) and isinstance(new_values, list):
            combined_inserted[key] = merge_unique(existing_values, new_values)

    scalars: dict[str, Any] = {}
    for source in (existing_inserted.get("scalars"), new_inserted.get("scalars")):
        if isinstance(source, dict):
            scalars.update(copy.deepcopy(source))
    combined_inserted["scalars"] = scalars
    merged["insertedSettings"] = combined_inserted

    if "managedPolicy" in new_state:
        merged["managedPolicy"] = copy.deepcopy(new_state["managedPolicy"])
    elif "managedPolicy" in existing_state:
        merged["managedPolicy"] = copy.deepcopy(existing_state["managedPolicy"])

    return merged


def load_state(project_root: Path) -> dict[str, Any]:
    target = harden_state_path(project_root)
    if not target.exists():
        return {}
    state = load_json(target, "harden state")
    if state.get("managedBy") != MANAGED_BY:
        raise ProfileError(f"harden state is not managed by {MANAGED_BY}: {target}")
    if state.get("managedVersion") != MANAGED_VERSION:
        raise ProfileError(f"harden state has unsupported version: {target}")
    return state


def managed_settings_conflicts(state: dict[str, Any], settings: dict[str, Any]) -> list[str]:
    conflicts: list[str] = []
    inserted = state.get("insertedSettings", {})
    if not isinstance(inserted, dict):
        return conflicts

    for key, values in inserted.items():
        if key == "scalars":
            continue
        if not values:
            continue
        exists, current_value = get_nested(settings, tuple(key.split(".")))
        if exists and not isinstance(current_value, list):
            conflicts.append(key)

    scalars = inserted.get("scalars", {})
    if isinstance(scalars, dict):
        for key, managed_value in scalars.items():
            exists, current_value = get_nested(settings, tuple(key.split(".")))
            if exists and current_value != managed_value:
                conflicts.append(key)

    return conflicts


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


def restore_file(path: Path, content: str | None) -> None:
    if content is None:
        path.unlink(missing_ok=True)
    else:
        atomic_write(path, content)


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
    state_target = harden_state_path(project_root)

    if target.exists():
        existing = load_json(target, "settings")
        before = target.read_text(encoding="utf-8")
    else:
        existing = {}
        before = ""

    existing_state = load_state(project_root)
    merged, conflicts = merge_settings(existing, profile, force=force)
    if existing_state:
        state_conflicts = managed_settings_conflicts(existing_state, existing)
        if force:
            state_conflicts = []
        conflicts.extend(state_conflicts)

        managed_policy = existing_state.get("managedPolicy")
        if isinstance(managed_policy, dict) and managed_policy.get("created") is True and policy_target.exists():
            managed_content = managed_policy.get("content")
            current_policy = load_json(policy_target, "security policy")
            if current_policy != managed_content:
                if force:
                    policy_changed = True
                    policy_before = policy_target.read_text(encoding="utf-8")
                    policy_after = format_json(managed_content)
                else:
                    conflicts.append("security-policy.json")

    settings_changed = merged != existing
    state_before = state_target.read_text(encoding="utf-8") if state_target.exists() else ""
    inserted_settings = collect_inserted_settings(existing, profile, force=force)
    next_state: dict[str, Any] = {
        "managedBy": MANAGED_BY,
        "managedVersion": MANAGED_VERSION,
        "appliedProfile": profile_name,
        "insertedSettings": inserted_settings,
    }
    if policy_changed:
        next_state["managedPolicy"] = {
            "path": ".claude/security-policy.json",
            "created": True,
            "content": json.loads(policy_after),
        }
    state = merge_state(existing_state, next_state)
    state_after = format_json(state)
    state_changed = json.loads(state_after) != (json.loads(state_before) if state_before else {})
    changed = settings_changed or policy_changed or state_changed
    after = format_json(merged)
    diff = ""
    if settings_changed:
        diff += unified_diff(before, after, target)
    if policy_changed:
        diff += unified_diff(policy_before, policy_after, policy_target)
    if state_changed:
        diff += unified_diff(state_before, state_after, state_target)

    if conflicts:
        return ApplyResult(changed=False, conflicts=conflicts, diff="")

    if not changed or dry_run or check:
        return ApplyResult(changed=changed, conflicts=[], diff=diff)

    backup_path = create_backup(target) if settings_changed and target.exists() else None
    original_settings = before if target.exists() else None
    original_policy = policy_before if policy_target.exists() else None
    original_state = state_before if state_target.exists() else None
    try:
        if policy_changed:
            atomic_write(policy_target, policy_after)
        if settings_changed:
            atomic_write(target, after)
        if state_changed:
            atomic_write(state_target, state_after)
    except OSError as exc:
        rollback_errors: list[str] = []
        for rollback_path, rollback_content in (
            (target, original_settings),
            (policy_target, original_policy),
            (state_target, original_state),
        ):
            try:
                restore_file(rollback_path, rollback_content)
            except OSError as rollback_exc:
                rollback_errors.append(f"{rollback_path}: {rollback_exc}")

        if rollback_errors:
            details = "; ".join(rollback_errors)
            raise ProfileError(f"failed to write profile files: {exc}; rollback failed: {details}") from exc
        raise ProfileError(f"failed to write profile files: {exc}") from exc

    return ApplyResult(changed=True, conflicts=[], diff=diff, backup_path=backup_path)


def remove_list_items(existing: list[Any], managed_items: list[Any]) -> list[Any]:
    managed_keys = {json_key(item) for item in managed_items}
    return [item for item in existing if json_key(item) not in managed_keys]


def remove_profile(
    *,
    project_root: Path,
    profile_name: str,
    dry_run: bool = False,
    check: bool = False,
    force: bool = False,
) -> ApplyResult:
    state_target = harden_state_path(project_root)
    if not state_target.exists():
        return ApplyResult(changed=False, conflicts=[], diff="")

    state = load_state(project_root)
    if state.get("appliedProfile") != profile_name:
        raise ProfileError(
            f"harden state is for profile '{state.get('appliedProfile')}', not '{profile_name}'"
        )

    target = settings_path(project_root)
    if target.exists():
        existing = load_json(target, "settings")
        before = target.read_text(encoding="utf-8")
    else:
        existing = {}
        before = ""

    updated = copy.deepcopy(existing)
    conflicts: list[str] = []
    inserted = state.get("insertedSettings", {})
    if not isinstance(inserted, dict):
        raise ProfileError(f"harden state insertedSettings must be an object: {state_target}")

    for key, values in inserted.items():
        if key == "scalars":
            continue
        if not isinstance(values, list):
            raise ProfileError(f"harden state entry must be an array: {key}")
        path = tuple(key.split("."))
        exists, current_value = get_nested(updated, path)
        if not exists:
            if values and not force:
                conflicts.append(key)
            continue
        if not isinstance(current_value, list):
            if values:
                conflicts.append(key)
            continue
        current_keys = {json_key(item) for item in current_value}
        missing_managed_values = [item for item in values if json_key(item) not in current_keys]
        if missing_managed_values and not force:
            conflicts.append(key)
            continue
        remaining = remove_list_items(current_value, values)
        if remaining:
            parent_exists, parent = get_nested(updated, path[:-1])
            if parent_exists and isinstance(parent, dict):
                parent[path[-1]] = remaining
        else:
            delete_nested(updated, path)

    scalars = inserted.get("scalars", {})
    if not isinstance(scalars, dict):
        raise ProfileError("harden state insertedSettings.scalars must be an object")
    for key, managed_value in scalars.items():
        path = tuple(key.split("."))
        exists, current_value = get_nested(updated, path)
        if not exists:
            continue
        if current_value == managed_value or force:
            delete_nested(updated, path)
        else:
            conflicts.append(key)

    policy_target = security_policy_path(project_root)
    policy_before = policy_target.read_text(encoding="utf-8") if policy_target.exists() else ""
    remove_policy = False
    managed_policy = state.get("managedPolicy")
    if isinstance(managed_policy, dict) and managed_policy.get("created") is True:
        managed_content = managed_policy.get("content")
        if policy_target.exists():
            current_policy = load_json(policy_target, "security policy")
            if current_policy == managed_content or force:
                remove_policy = True
            else:
                conflicts.append("security-policy.json")

    settings_changed = updated != existing
    state_before = state_target.read_text(encoding="utf-8")
    diff = ""
    if settings_changed:
        diff += unified_diff(before, format_json(updated), target)
    if remove_policy:
        diff += unified_diff(policy_before, "", policy_target)
    diff += unified_diff(state_before, "", state_target)
    changed = settings_changed or remove_policy or state_target.exists()

    if conflicts:
        return ApplyResult(changed=False, conflicts=conflicts, diff="")

    if not changed or dry_run or check:
        return ApplyResult(changed=changed, conflicts=[], diff=diff)

    try:
        if settings_changed:
            atomic_write(target, format_json(updated))
        if remove_policy:
            policy_target.unlink(missing_ok=True)
        state_target.unlink(missing_ok=True)
    except OSError as exc:
        raise ProfileError(f"failed to remove profile files: {exc}") from exc

    return ApplyResult(changed=True, conflicts=[], diff=diff)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply a claude-bootstrap hardening profile.")
    parser.add_argument("--profile", default="baseline", help="Profile name, for example: baseline")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing settings")
    parser.add_argument("--check", action="store_true", help="Exit non-zero if the profile is not applied")
    parser.add_argument("--force", action="store_true", help="Resolve scalar conflicts by using profile values")
    parser.add_argument("--remove", action="store_true", help="Remove settings managed by the profile state")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        if args.remove:
            result = remove_profile(
                project_root=Path.cwd(),
                profile_name=args.profile,
                dry_run=args.dry_run,
                check=args.check,
                force=args.force,
            )
        else:
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
        if args.remove:
            print("Use --force to remove modified managed values.", file=sys.stderr)
        else:
            print("Use --force to replace conflicting scalar values.", file=sys.stderr)
        return 1

    if args.check:
        if result.changed:
            if args.remove:
                print(f"Profile '{args.profile}' still has managed state.")
            else:
                print(f"Profile '{args.profile}' is not fully applied.")
            if result.diff:
                print(result.diff, end="")
            return 1
        if args.remove:
            print(f"Profile '{args.profile}' has no managed state.")
        else:
            print(f"Profile '{args.profile}' is already applied.")
        return 0

    if args.dry_run:
        if result.changed:
            print(result.diff, end="")
        else:
            print("No changes.")
        return 0

    if result.changed:
        if args.remove:
            print(f"Removed profile '{args.profile}'.")
        else:
            print(f"Applied profile '{args.profile}'.")
        if result.backup_path is not None:
            print(f"Backup: {result.backup_path}")
    else:
        print("No changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
