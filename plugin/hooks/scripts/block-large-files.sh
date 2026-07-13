#!/bin/bash
# Compatibility wrapper for the large file policy hook.
# Type: PreToolUse, Matcher: Write|Edit

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$SCRIPT_DIR/large_file_policy.py"
