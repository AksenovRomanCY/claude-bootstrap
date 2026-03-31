#!/bin/bash
# Hook: Block --no-verify flag in git commands
# Type: PreToolUse, Matcher: Bash
# Exit code 2 = block

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

if [ -z "$COMMAND" ]; then
  exit 0
fi

if echo "$COMMAND" | grep -qE '\-\-no-verify'; then
  echo "BLOCKED: --no-verify is not allowed."
  echo "If a pre-commit hook is failing, fix the underlying issue instead of skipping it."
  exit 2
fi

exit 0
