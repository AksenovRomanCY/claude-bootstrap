#!/bin/bash
# Hook: Remind to /compact every ~50 tool actions
# Type: PostToolUse, Matcher: Edit|Write
# Uses a fixed counter file per terminal session

# Use CLAUDE_SESSION_ID if available, fallback to parent PID (Claude Code process)
SESSION_ID="${CLAUDE_SESSION_ID:-$PPID}"
COUNTER_FILE="/tmp/claude-compact-counter-${SESSION_ID}"

# Initialize counter if it doesn't exist
if [ ! -f "$COUNTER_FILE" ]; then
  echo "0" > "$COUNTER_FILE"
fi

# Increment
COUNT=$(cat "$COUNTER_FILE")
COUNT=$((COUNT + 1))
echo "$COUNT" > "$COUNTER_FILE"

# Remind every 50 actions
if [ $((COUNT % 50)) -eq 0 ]; then
  echo "REMINDER: $COUNT tool actions in this session. Consider running /compact to save context."
fi

exit 0
