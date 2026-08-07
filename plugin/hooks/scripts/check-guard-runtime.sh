#!/bin/bash
# Hook: warn once per session when the guards cannot run
# Type: SessionStart
#
# Every guard is a python3 script, and each hook fails open when the interpreter
# is missing — the right behavior, but a silent one: without this notice the
# session looks protected while nothing is being checked.

command -v python3 > /dev/null 2>&1 && exit 0

# printf is a builtin: the message must survive the same empty PATH that hid
# python3 in the first place.
printf '%s\n' \
  '{' \
  '  "hookSpecificOutput": {' \
  '    "hookEventName": "SessionStart",' \
  '    "additionalContext": "[GUARD-DISABLED] python3 was not found on PATH, so claude-bootstrap command, secret, and large-file guards are inactive for this session. Install python3 (or make it visible to Claude Code) to re-enable them."' \
  '  }' \
  '}'

exit 0
