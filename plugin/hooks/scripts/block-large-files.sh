#!/bin/bash
# Compatibility wrapper for the large file policy hook.
# Type: PreToolUse, Matcher: Write|Edit
# Fails open: a missing script or interpreter must never block tool use.

# Directory resolved with shell builtins only: `dirname` is external, and a hook
# that runs with an empty PATH must fail open silently rather than print an error.
SCRIPT_SOURCE="${BASH_SOURCE[0]:-$0}"
case $SCRIPT_SOURCE in */*) SCRIPT_PARENT="${SCRIPT_SOURCE%/*}" ;; *) SCRIPT_PARENT="." ;; esac
SCRIPT_DIR="$(cd "$SCRIPT_PARENT" 2>/dev/null && pwd)" || exit 0
script="$SCRIPT_DIR/large_file_policy.py"
[ -f "$script" ] || exit 0
command -v python3 >/dev/null 2>&1 || exit 0
python3 "$script"
