#!/bin/bash
# Hook: Warn when potential secrets are detected in code
# Type: PostToolUse, Matcher: Edit|Write
# Warning only (exit 0) — flags potential secrets for review

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')

# Extract new content depending on tool type
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

# Skip .env files, test fixtures, and lock files — secrets are expected there
case "$FILE_PATH" in
  *.env|*.env.*|*fixture*|*mock*|*.lock|*.sum|*test*) exit 0 ;;
esac

WARNINGS=""

# AWS keys (AKIA...)
if printf '%s' "$CONTENT" | grep -qE 'AKIA[0-9A-Z]{16}'; then
  WARNINGS="${WARNINGS}  - AWS Access Key (AKIA...)\n"
fi

# Generic API key patterns: long hex/base64 strings assigned to key-like variables
if printf '%s' "$CONTENT" | grep -qiE '(api_key|apikey|api_secret|secret_key|access_token|auth_token|private_key)\s*[:=]\s*["\x27][a-zA-Z0-9_\-/+]{20,}["\x27]'; then
  WARNINGS="${WARNINGS}  - Hardcoded API key or secret\n"
fi

# JWT tokens
if printf '%s' "$CONTENT" | grep -qE 'eyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}'; then
  WARNINGS="${WARNINGS}  - JWT token\n"
fi

# Private keys
if printf '%s' "$CONTENT" | grep -qE -- '-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----'; then
  WARNINGS="${WARNINGS}  - Private key block\n"
fi

# Generic password assignments
if printf '%s' "$CONTENT" | grep -qiE '(password|passwd|pwd)\s*[:=]\s*["\x27][^"\x27]{8,}["\x27]'; then
  WARNINGS="${WARNINGS}  - Hardcoded password\n"
fi

# GitHub/GitLab tokens
if printf '%s' "$CONTENT" | grep -qE '(ghp_[a-zA-Z0-9]{36}|glpat-[a-zA-Z0-9\-]{20,})'; then
  WARNINGS="${WARNINGS}  - GitHub/GitLab personal access token\n"
fi

# Slack tokens
if printf '%s' "$CONTENT" | grep -qE 'xox[bpors]-[a-zA-Z0-9\-]{10,}'; then
  WARNINGS="${WARNINGS}  - Slack token\n"
fi

if [ -n "$WARNINGS" ]; then
  echo "WARNING: Potential secrets detected in $FILE_PATH:"
  echo -e "$WARNINGS"
  echo "Use environment variables instead of hardcoding secrets."
fi

exit 0
