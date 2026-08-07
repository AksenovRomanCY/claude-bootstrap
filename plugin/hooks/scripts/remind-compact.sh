#!/bin/bash
# Hook: Remind to /compact every ~50 tool actions
# Type: PostToolUse, Matcher: Edit|Write
# Uses a fixed counter file per terminal session

# Use CLAUDE_SESSION_ID if available, fallback to parent PID (Claude Code process)
SESSION_ID="${CLAUDE_SESSION_ID:-$PPID}"
# Per-user state directory: /tmp is world-writable, so another user on a shared
# machine could pre-create the counter file and own this session's state.
STATE_DIR="${XDG_RUNTIME_DIR:-$HOME/.cache}/claude-bootstrap"
mkdir -p "$STATE_DIR" 2>/dev/null || true
COUNTER_FILE="$STATE_DIR/compact-counter-${SESSION_ID}"

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
