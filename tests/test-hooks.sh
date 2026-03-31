#!/bin/bash
set -euo pipefail

# Tests for claude-bootstrap hook scripts
# Run: bash tests/test-hooks.sh

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HOOKS="$SCRIPT_DIR/.claude/hooks/scripts"
PASSED=0
FAILED=0

pass() { echo "  PASS: $1"; ((PASSED++)) || true; }
fail() { echo "  FAIL: $1"; ((FAILED++)) || true; }

run_hook() {
  local hook=$1 input=$2
  echo "$input" | bash "$HOOKS/$hook" 2>&1
  return "${PIPESTATUS[1]}"
}

echo "=== Hook Tests ==="
echo ""

# --------------------------------------------------
echo "block-large-files.sh"
# --------------------------------------------------

# Should pass: Write with small content
INPUT='{"tool_name":"Write","tool_input":{"file_path":"/tmp/test.ts","content":"line1\nline2\nline3"}}'
run_hook "block-large-files.sh" "$INPUT" > /dev/null 2>&1 && pass "small Write passes" || fail "small Write should pass"

# Should block: Write with >800 lines
LONG_CONTENT=$(printf 'line %.0s\n' $(seq 1 801))
INPUT=$(jq -n --arg c "$LONG_CONTENT" '{"tool_name":"Write","tool_input":{"file_path":"/tmp/test.ts","content":$c}}')
run_hook "block-large-files.sh" "$INPUT" > /dev/null 2>&1 && fail "large Write should block" || {
  [[ $? -eq 2 ]] && pass "large Write blocks (exit 2)" || fail "large Write wrong exit code"
}

# Should pass: non-Write/Edit tool
INPUT='{"tool_name":"Bash","tool_input":{"command":"echo hello"}}'
run_hook "block-large-files.sh" "$INPUT" > /dev/null 2>&1 && pass "non-Write tool passes" || fail "non-Write tool should pass"

echo ""

# --------------------------------------------------
echo "block-no-verify.sh"
# --------------------------------------------------

# Should block: git commit --no-verify
INPUT='{"tool_name":"Bash","tool_input":{"command":"git commit --no-verify -m test"}}'
run_hook "block-no-verify.sh" "$INPUT" > /dev/null 2>&1 && fail "no-verify should block" || {
  [[ $? -eq 2 ]] && pass "git --no-verify blocks (exit 2)" || fail "no-verify wrong exit code"
}

# Should pass: normal git commit
INPUT='{"tool_name":"Bash","tool_input":{"command":"git commit -m test"}}'
run_hook "block-no-verify.sh" "$INPUT" > /dev/null 2>&1 && pass "normal git commit passes" || fail "normal git commit should pass"

# Should pass: non-Bash tool
INPUT='{"tool_name":"Write","tool_input":{"file_path":"/tmp/test.ts","content":"hello"}}'
run_hook "block-no-verify.sh" "$INPUT" > /dev/null 2>&1 && pass "non-Bash tool passes" || fail "non-Bash tool should pass"

echo ""

# --------------------------------------------------
echo "warn-debug-code.sh"
# --------------------------------------------------

# Should warn: console.log
INPUT='{"tool_name":"Write","tool_input":{"file_path":"/tmp/test.ts","content":"console.log(\"debug\")"}}'
OUTPUT=$(run_hook "warn-debug-code.sh" "$INPUT" 2>&1)
echo "$OUTPUT" | grep -q "WARNING" && pass "console.log triggers warning" || fail "console.log should warn"

# Should warn: Python print()
INPUT='{"tool_name":"Write","tool_input":{"file_path":"/tmp/test.py","content":"  print(\"hello\")"}}'
OUTPUT=$(run_hook "warn-debug-code.sh" "$INPUT" 2>&1)
echo "$OUTPUT" | grep -q "WARNING" && pass "print() triggers warning" || fail "print() should warn"

# Should not warn: clean code
INPUT='{"tool_name":"Write","tool_input":{"file_path":"/tmp/test.ts","content":"const x = 1;\nreturn x;"}}'
OUTPUT=$(run_hook "warn-debug-code.sh" "$INPUT" 2>&1)
echo "$OUTPUT" | grep -q "WARNING" && fail "clean code should not warn" || pass "clean code no warning"

echo ""

# --------------------------------------------------
echo "warn-secrets.sh"
# --------------------------------------------------

# Should warn: AWS key
INPUT='{"tool_name":"Write","tool_input":{"file_path":"/tmp/config.ts","content":"const key = \"AKIAIOSFODNN7EXAMPLE\""}}'
OUTPUT=$(run_hook "warn-secrets.sh" "$INPUT" 2>&1)
echo "$OUTPUT" | grep -q "WARNING" && pass "AWS key triggers warning" || fail "AWS key should warn"

# Should warn: private key
INPUT=$(jq -n '{"tool_name":"Write","tool_input":{"file_path":"/tmp/key.pem","content":"-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA"}}')
OUTPUT=$(run_hook "warn-secrets.sh" "$INPUT" 2>&1)
echo "$OUTPUT" | grep -q "WARNING" && pass "private key triggers warning" || fail "private key should warn"

# Should skip: .env file
INPUT='{"tool_name":"Write","tool_input":{"file_path":"/tmp/.env","content":"API_KEY=sk-secret123456789012345678"}}'
OUTPUT=$(run_hook "warn-secrets.sh" "$INPUT" 2>&1)
echo "$OUTPUT" | grep -q "WARNING" && fail ".env file should be skipped" || pass ".env file skipped"

# Should not warn: clean code
INPUT='{"tool_name":"Write","tool_input":{"file_path":"/tmp/app.ts","content":"const port = 3000;\napp.listen(port);"}}'
OUTPUT=$(run_hook "warn-secrets.sh" "$INPUT" 2>&1)
echo "$OUTPUT" | grep -q "WARNING" && fail "clean code should not warn" || pass "clean code no warning"

echo ""

# --------------------------------------------------
echo "remind-compact.sh"
# --------------------------------------------------

# Should run without error (just increments counter)
INPUT='{"tool_name":"Write","tool_input":{"file_path":"/tmp/test.ts","content":"x"}}'
run_hook "remind-compact.sh" "$INPUT" > /dev/null 2>&1 && pass "remind-compact runs ok" || fail "remind-compact should not fail"

echo ""

# --------------------------------------------------
echo "=== Results: $PASSED passed, $FAILED failed ==="

if [[ $FAILED -gt 0 ]]; then
  exit 1
fi
