#!/bin/bash
# Compatibility wrapper for the large file policy hook.
# Type: PreToolUse, Matcher: Write|Edit
# Fails open: a missing script or interpreter must never block tool use.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)" || exit 0
script="$SCRIPT_DIR/large_file_policy.py"
[ -f "$script" ] || exit 0
command -v python3 >/dev/null 2>&1 || exit 0
python3 "$script"
