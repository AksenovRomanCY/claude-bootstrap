#!/bin/bash
# Hook: Compatibility wrapper for post_write_warnings.py
# Type: PostToolUse, Matcher: Edit|Write
# Warning only (exit 0)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$SCRIPT_DIR/post_write_warnings.py"
