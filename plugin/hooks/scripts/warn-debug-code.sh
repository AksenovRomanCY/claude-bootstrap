#!/bin/bash
# Hook: Compatibility wrapper for post_write_warnings.py
# Type: PostToolUse, Matcher: Edit|Write
# Warning only (exit 0)
#
# Both legacy names ran the same post-write warnings, so this one defers to its
# sibling instead of being a second copy of it. The name is kept because it may
# still be wired in a settings.json that has not been migrated.

SCRIPT_SOURCE="${BASH_SOURCE[0]:-$0}"
case $SCRIPT_SOURCE in */*) SCRIPT_PARENT="${SCRIPT_SOURCE%/*}" ;; *) SCRIPT_PARENT="." ;; esac
SCRIPT_DIR="$(cd "$SCRIPT_PARENT" 2>/dev/null && pwd)" || exit 0
wrapper="$SCRIPT_DIR/warn-secrets.sh"
[ -f "$wrapper" ] || exit 0
exec "${BASH:-/bin/bash}" "$wrapper"
