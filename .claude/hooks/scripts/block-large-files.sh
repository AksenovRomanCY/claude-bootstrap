#!/bin/bash
# Hook: Block creation/editing of files over 800 lines
# Type: PreToolUse, Matcher: Write|Edit
# Exit code 2 = block

MAX_LINES=800

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

if [ -z "$FILE_PATH" ]; then
  exit 0
fi

if [ "$TOOL_NAME" = "Write" ]; then
  # For Write: check the content being written
  CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // empty')
  if [ -z "$CONTENT" ]; then
    exit 0
  fi
  LINE_COUNT=$(echo "$CONTENT" | wc -l | tr -d ' ')
elif [ "$TOOL_NAME" = "Edit" ]; then
  # For Edit: check the resulting file size after edit
  if [ ! -f "$FILE_PATH" ]; then
    exit 0
  fi
  OLD_STRING=$(echo "$INPUT" | jq -r '.tool_input.old_string // empty')
  NEW_STRING=$(echo "$INPUT" | jq -r '.tool_input.new_string // empty')
  OLD_LINES=$(echo "$OLD_STRING" | wc -l | tr -d ' ')
  NEW_LINES=$(echo "$NEW_STRING" | wc -l | tr -d ' ')
  CURRENT_LINES=$(wc -l < "$FILE_PATH" | tr -d ' ')
  LINE_COUNT=$((CURRENT_LINES - OLD_LINES + NEW_LINES))
else
  exit 0
fi

if [ "$LINE_COUNT" -gt "$MAX_LINES" ]; then
  echo "BLOCKED: $FILE_PATH would have $LINE_COUNT lines (max $MAX_LINES)."
  echo "Split the file into smaller modules."
  exit 2
fi

exit 0
