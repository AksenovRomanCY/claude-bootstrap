#!/bin/bash
# Hook: Compatibility wrapper for post_write_warnings.py
# Type: PostToolUse, Matcher: Edit|Write
# Warning only (exit 0)
# Fails open: a missing script or interpreter must never block tool use.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)" || exit 0
script="$SCRIPT_DIR/post_write_warnings.py"
[ -f "$script" ] || exit 0
command -v python3 >/dev/null 2>&1 || exit 0
python3 "$script"
