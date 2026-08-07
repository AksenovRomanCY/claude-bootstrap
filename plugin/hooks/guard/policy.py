"""Single reader for the project security policy.

Guards evaluate several rules per tool call, and each rule used to open, read and
parse `.claude/security-policy.json` for itself. The file is read once per
process here; every rule then picks its own section out of the parsed mapping.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


POLICY_FILE_NAME = "security-policy.json"

_policy_cache: dict[str, tuple[tuple[int, int], dict[str, Any]]] = {}


def security_policy_path(project_root: Path) -> Path:
    return project_root / ".claude" / POLICY_FILE_NAME


def load_policy(project_root: Path) -> dict[str, Any]:
    """Parsed policy, or an empty mapping when it is missing or unreadable.

    A missing, malformed or non-object policy is not an error: guards fall back
    to their own defaults, so a broken file must never block a tool call. The
    cache is keyed by the file's stat signature, so a policy rewritten inside one
    process is still picked up.
    """
    path = security_policy_path(project_root)
    key = str(path)
    try:
        stat = path.stat()
    except OSError:
        _policy_cache.pop(key, None)
        return {}

    signature = (stat.st_mtime_ns, stat.st_size)
    cached = _policy_cache.get(key)
    if cached is not None and cached[0] == signature:
        return cached[1]

    try:
        raw_policy: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw_policy = {}

    policy = raw_policy if isinstance(raw_policy, dict) else {}
    _policy_cache[key] = (signature, policy)
    return policy


def policy_section(policy: Mapping[str, Any], name: str) -> dict[str, Any]:
    section = policy.get(name)
    return section if isinstance(section, dict) else {}


def string_list(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str) and item] if isinstance(value, list) else []
