#!/bin/bash
# Hook: Warn when debug code is added
# Type: PostToolUse, Matcher: Edit|Write
# Does not block (exit 0), warning only

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')

# Extract the new content depending on tool type
if [ "$TOOL_NAME" = "Edit" ]; then
  CONTENT=$(echo "$INPUT" | jq -r '.tool_input.new_string // empty')
elif [ "$TOOL_NAME" = "Write" ]; then
  CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // empty')
else
  exit 0
fi

if [ -z "$CONTENT" ]; then
  exit 0
fi

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // "unknown"')
WARNINGS=""

# JavaScript/TypeScript
if printf '%s' "$CONTENT" | grep -qE 'console\.(log|warn|error|debug|info)\('; then
  WARNINGS="${WARNINGS}  - console.log/warn/error/debug/info\n"
fi
if printf '%s' "$CONTENT" | grep -qE '\bdebugger\b'; then
  WARNINGS="${WARNINGS}  - debugger statement\n"
fi

# Python
if printf '%s' "$CONTENT" | grep -qE '^\s*print\('; then
  WARNINGS="${WARNINGS}  - print()\n"
fi
if printf '%s' "$CONTENT" | grep -qE '\bbreakpoint\(\)'; then
  WARNINGS="${WARNINGS}  - breakpoint()\n"
fi
if printf '%s' "$CONTENT" | grep -qE '\bipdb\b|\bpdb\.set_trace'; then
  WARNINGS="${WARNINGS}  - pdb/ipdb debugger\n"
fi

# Ruby
if printf '%s' "$CONTENT" | grep -qE '\bbinding\.(pry|irb)\b'; then
  WARNINGS="${WARNINGS}  - binding.pry/irb\n"
fi

if [ -n "$WARNINGS" ]; then
  echo "WARNING: Debug code detected in $FILE_PATH:"
  echo -e "$WARNINGS"
  echo "Remove before committing to production code."
fi

exit 0
