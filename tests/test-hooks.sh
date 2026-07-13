#!/bin/bash
# shellcheck disable=SC2015,SC2016
set -euo pipefail

# Tests for claude-bootstrap hook scripts
# Run: bash tests/test-hooks.sh

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HOOKS="$SCRIPT_DIR/plugin/hooks/scripts"
PLUGIN_HOOKS_JSON="$SCRIPT_DIR/plugin/hooks/hooks.json"
SETTINGS_HOOKS_JSON="$SCRIPT_DIR/plugin/settings-hooks.json"
PASSED=0
FAILED=0

pass() { echo "  PASS: $1"; ((PASSED++)) || true; }
fail() { echo "  FAIL: $1"; ((FAILED++)) || true; }

run_hook() {
  local hook=$1 input=$2
  echo "$input" | bash "$HOOKS/$hook" 2>&1
  return "${PIPESTATUS[1]}"
}

bash_input() {
  local command=$1
  jq -n --arg command "$command" '{"tool_name":"Bash","tool_input":{"command":$command}}'
}

expect_hook_block() {
  local hook=$1 input=$2 label=$3
  run_hook "$hook" "$input" > /dev/null 2>&1 && fail "$label should block" || {
    [[ $? -eq 2 ]] && pass "$label blocks (exit 2)" || fail "$label wrong exit code"
  }
}

expect_hook_pass() {
  local hook=$1 input=$2 label=$3
  run_hook "$hook" "$input" > /dev/null 2>&1 && pass "$label passes" || fail "$label should pass"
}

echo "=== Hook Tests ==="
echo ""

# --------------------------------------------------
echo "hook configuration"
# --------------------------------------------------

for config in "$PLUGIN_HOOKS_JSON" "$SETTINGS_HOOKS_JSON"; do
  if jq empty "$config" > /dev/null; then
    pass "$(basename "$config") is valid JSON"
  else
    fail "$(basename "$config") should be valid JSON"
  fi

  if [[ "$(basename "$config")" == "hooks.json" ]]; then
    expected_command='python3 "$CLAUDE_PLUGIN_DIR/hooks/scripts/command_guard.py"'
  else
    expected_command='python3 ~/.claude/hooks/scripts/command_guard.py'
  fi

  if jq -e --arg command "$expected_command" '
    [
      .hooks.PreToolUse[]?.hooks[]?,
      .hooks.PostToolUse[]?.hooks[]?
    ]
    | map(select((.command // "") | contains("remind-compact.sh") | not))
    | all(.command == $command)
  ' "$config" > /dev/null; then
    pass "$(basename "$config") active security hooks use command_guard.py"
  else
    fail "$(basename "$config") active security hooks should use only command_guard.py"
  fi

  if jq -e --arg command "$expected_command" '
    [
      "Bash(git *)",
      "Bash(rm *)",
      "Bash(sudo *)",
      "Bash(env *)",
      "Bash(command *)",
      "Bash(nohup *)",
      "Bash(curl *)",
      "Bash(wget *)",
      "Bash(terraform *)",
      "Bash(kubectl *)",
      "Bash(helm *)",
      "Bash(docker *)",
      "Bash(npm *)",
      "Bash(pnpm *)",
      "Bash(yarn *)",
      "Bash(cargo *)",
      "Bash(twine *)",
      "Bash(gh *)",
      "Bash(psql *)",
      "Bash(mysql *)",
      "Bash(sqlite3 *)",
      "Bash(prisma *)",
      "Bash(alembic *)",
      "Bash(mkfs *)",
      "Bash(wipefs *)",
      "Bash(fdisk *)",
      "Bash(parted *)",
      "Bash(dd *)",
      "Bash(chmod *)",
      "Bash(chown *)"
    ] as $expected_ifs |
    [.hooks.PreToolUse[]? | select(.matcher == "Bash") | .hooks[]?] as $hooks |
    ($hooks | length) == ($expected_ifs | length)
    and ($hooks | all(.type == "command" and .command == $command and .timeout == 30 and (.if | type) == "string"))
    and (($hooks | map(.if) | sort) == ($expected_ifs | sort))
  ' "$config" > /dev/null; then
    pass "$(basename "$config") uses expected Bash if-scoped command_guard.py hooks"
  else
    fail "$(basename "$config") should use expected Bash if-scoped command_guard.py hooks"
  fi

  if jq -e '[.hooks.PreToolUse[]? | select(.matcher == "Bash") | .hooks[]? | has("if")] | all' "$config" > /dev/null; then
    pass "$(basename "$config") uses handler-level if for Bash guard"
  else
    fail "$(basename "$config") should use handler-level if for Bash guard"
  fi

  if jq -e --arg command "$expected_command" '
    [.hooks.PreToolUse[]? | select(.matcher == "Write|Edit") | .hooks[]?]
    == [{"type":"command","command":$command,"timeout":30}]
  ' "$config" > /dev/null; then
    pass "$(basename "$config") uses command_guard.py for PreToolUse Write|Edit"
  else
    fail "$(basename "$config") should use command_guard.py for PreToolUse Write|Edit"
  fi

  if jq -e --arg command "$expected_command" '
    [.hooks.PostToolUse[]? | select(.matcher == "Write|Edit") | .hooks[]?]
    | length == 2
    and .[0].command == $command
    and .[0].timeout == 30
    and (.[1].command | contains("remind-compact.sh"))
    and .[1].timeout == 5
  ' "$config" > /dev/null; then
    pass "$(basename "$config") uses command_guard.py and remind-compact for PostToolUse Write|Edit"
  else
    fail "$(basename "$config") should use command_guard.py and remind-compact for PostToolUse Write|Edit"
  fi

  if jq -e '
    [.hooks.PreToolUse[]?.hooks[]?.command, .hooks.PostToolUse[]?.hooks[]?.command]
    | any(
        contains("block-no-verify.sh")
        or contains("block-large-files.sh")
        or contains("warn-secrets.sh")
        or contains("warn-debug-code.sh")
        or contains("secret_guard.py")
        or contains("large_file_policy.py")
        or contains("post_write_warnings.py")
      )
    | not
  ' "$config" > /dev/null; then
    pass "$(basename "$config") has no active legacy security references"
  else
    fail "$(basename "$config") should not reference legacy security hooks"
  fi

  fingerprints=$(jq -r '
    .hooks
    | to_entries[]
    | .key as $event
    | .value[]? as $group
    | $group.hooks[]?
    | [$event, ($group.matcher // ""), (.if // ""), (.command // "")]
    | @tsv
  ' "$config")
  total_fingerprints=$(printf '%s\n' "$fingerprints" | sed '/^$/d' | wc -l | tr -d ' ')
  unique_fingerprints=$(printf '%s\n' "$fingerprints" | sed '/^$/d' | sort -u | wc -l | tr -d ' ')
  if [[ "$total_fingerprints" == "$unique_fingerprints" ]]; then
    pass "$(basename "$config") has no duplicate hook fingerprints"
  else
    fail "$(basename "$config") should not have duplicate hook fingerprints"
  fi
done

echo ""

# --------------------------------------------------
echo "command_guard.py"
# --------------------------------------------------

INPUT='{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"git commit --no-verify -m test"}}'
OUTPUT=$(echo "$INPUT" | python3 "$HOOKS/command_guard.py" 2>&1)
echo "$OUTPUT" | jq -e '.hookSpecificOutput.permissionDecision == "deny"' > /dev/null && pass "unified guard blocks Bash payload" || fail "unified guard should block Bash payload"

INPUT='{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"echo ok && git commit --no-verify -m test"}}'
OUTPUT=$(echo "$INPUT" | python3 "$HOOKS/command_guard.py" 2>&1)
echo "$OUTPUT" | jq -e '.hookSpecificOutput.permissionDecision == "deny"' > /dev/null && pass "unified guard blocks compound Bash payload" || fail "unified guard should block compound Bash payload"

INPUT='{"hook_event_name":"PreToolUse","tool_name":"Write","tool_input":{"file_path":"/tmp/config.ts","content":"const key = \"AKIA1234567890ABCDEF\""}}'
OUTPUT=$(echo "$INPUT" | python3 "$HOOKS/command_guard.py" 2>&1)
echo "$OUTPUT" | jq -e '.hookSpecificOutput.permissionDecision == "deny" and (.hookSpecificOutput.permissionDecisionReason | contains("[SECRET-AWS-ACCESS-KEY]"))' > /dev/null && pass "unified guard blocks Write secret payload" || fail "unified guard should block Write secret payload"

INPUT='{"hook_event_name":"PostToolUse","tool_name":"Write","tool_input":{"file_path":"/tmp/test.ts","content":"console.log(\"debug\")"}}'
OUTPUT=$(echo "$INPUT" | python3 "$HOOKS/command_guard.py" 2>&1)
echo "$OUTPUT" | jq -e '.hookSpecificOutput.hookEventName == "PostToolUse" and (.hookSpecificOutput.additionalContext | contains("[DEBUG-CONSOLE]")) and (.hookSpecificOutput | has("permissionDecision") | not)' > /dev/null && pass "unified guard warns after Write payload" || fail "unified guard should warn after Write payload"

echo ""

# --------------------------------------------------
echo "large_file_policy.py"
# --------------------------------------------------

# Should pass: Write with small content
INPUT='{"hook_event_name":"PreToolUse","tool_name":"Write","tool_input":{"file_path":"/tmp/test.ts","content":"line1\nline2\nline3"}}'
echo "$INPUT" | python3 "$HOOKS/large_file_policy.py" > /dev/null 2>&1 && pass "small Write passes" || fail "small Write should pass"

# Should ask: new Write with >1200 lines
LONG_CONTENT=$(printf 'line %.0s\n' $(seq 1 1201))
INPUT=$(jq -n --arg c "$LONG_CONTENT" '{"hook_event_name":"PreToolUse","tool_name":"Write","tool_input":{"file_path":"/tmp/test.ts","content":$c}}')
OUTPUT=$(echo "$INPUT" | python3 "$HOOKS/large_file_policy.py" 2>&1)
echo "$OUTPUT" | jq -e '.hookSpecificOutput.permissionDecision == "ask"' > /dev/null && pass "huge Write asks" || fail "huge Write should ask"

# Compatibility wrapper should still call the new policy and never block with exit 2
run_hook "block-large-files.sh" "$INPUT" > /dev/null 2>&1 && pass "compatibility wrapper exits 0" || fail "compatibility wrapper should exit 0"

# Should pass: non-Write/Edit tool
INPUT='{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"echo hello"}}'
echo "$INPUT" | python3 "$HOOKS/large_file_policy.py" > /dev/null 2>&1 && pass "non-Write tool passes" || fail "non-Write tool should pass"

echo ""

# --------------------------------------------------
echo "block-no-verify.sh"
# --------------------------------------------------

# Should block: git commit/push hook bypass
expect_hook_block "block-no-verify.sh" "$(bash_input "git commit --no-verify -m test")" "git commit --no-verify"
expect_hook_block "block-no-verify.sh" "$(bash_input "git commit -m test --no-verify")" "git commit trailing --no-verify"
expect_hook_block "block-no-verify.sh" "$(bash_input "git --no-pager commit --no-verify")" "git --no-pager commit --no-verify"
expect_hook_block "block-no-verify.sh" "$(bash_input "git push origin main --no-verify")" "git push --no-verify"
expect_hook_block "block-no-verify.sh" "$(bash_input "HUSKY=0 git commit -m test")" "HUSKY=0 git commit"
expect_hook_block "block-no-verify.sh" "$(bash_input "HUSKY=0 git push origin main")" "HUSKY=0 git push"
expect_hook_block "block-no-verify.sh" "$(bash_input "SKIP=pre-commit git commit -m test")" "SKIP git commit"
expect_hook_block "block-no-verify.sh" "$(bash_input "SKIP=pre-commit git push origin main")" "SKIP git push"
expect_hook_block "block-no-verify.sh" "$(bash_input "echo ok && git commit --no-verify -m test")" "compound git commit --no-verify"

# Should pass: unrelated --no-verify usage
expect_hook_pass "block-no-verify.sh" "$(bash_input "git commit -m test")" "normal git commit"
expect_hook_pass "block-no-verify.sh" "$(bash_input "git commit -m \"--no-verify\"")" "quoted commit message"
expect_hook_pass "block-no-verify.sh" "$(bash_input "echo \"--no-verify\"")" "echo --no-verify"
expect_hook_pass "block-no-verify.sh" "$(bash_input "grep -- \"--no-verify\" README.md")" "grep --no-verify"
expect_hook_pass "block-no-verify.sh" "$(bash_input "git log --grep=\"--no-verify\"")" "git log --grep no-verify"
expect_hook_pass "block-no-verify.sh" "$(bash_input "some-tool --no-verify")" "some-tool --no-verify"

# Should pass: non-Bash tool
INPUT='{"tool_name":"Write","tool_input":{"file_path":"/tmp/test.ts","content":"hello"}}'
expect_hook_pass "block-no-verify.sh" "$INPUT" "non-Bash tool"

echo ""

# --------------------------------------------------
echo "post_write_warnings.py"
# --------------------------------------------------

# Should warn: console.log
INPUT='{"hook_event_name":"PostToolUse","tool_name":"Write","tool_input":{"file_path":"/tmp/test.ts","content":"console.log(\"debug\")"}}'
OUTPUT=$(echo "$INPUT" | python3 "$HOOKS/post_write_warnings.py" 2>&1)
echo "$OUTPUT" | jq -e '.hookSpecificOutput.additionalContext | contains("[DEBUG-CONSOLE]")' > /dev/null && pass "console.log triggers warning" || fail "console.log should warn"

# Should warn: Python print()
INPUT='{"hook_event_name":"PostToolUse","tool_name":"Write","tool_input":{"file_path":"/tmp/test.py","content":"  print(\"hello\")"}}'
OUTPUT=$(echo "$INPUT" | python3 "$HOOKS/post_write_warnings.py" 2>&1)
echo "$OUTPUT" | jq -e '.hookSpecificOutput.additionalContext | contains("[DEBUG-PRINT]")' > /dev/null && pass "print() triggers warning" || fail "print() should warn"

# Should not warn: clean code
INPUT='{"hook_event_name":"PostToolUse","tool_name":"Write","tool_input":{"file_path":"/tmp/test.ts","content":"const x = 1;\nreturn x;"}}'
OUTPUT=$(echo "$INPUT" | python3 "$HOOKS/post_write_warnings.py" 2>&1)
echo "$OUTPUT" | grep -q "." && fail "clean code should not warn" || pass "clean code no warning"

# Should warn: AWS key
INPUT='{"hook_event_name":"PostToolUse","tool_name":"Write","tool_input":{"file_path":"/tmp/config.ts","content":"const key = \"AKIA1234567890ABCDEF\""}}'
OUTPUT=$(echo "$INPUT" | python3 "$HOOKS/post_write_warnings.py" 2>&1)
echo "$OUTPUT" | jq -e '.hookSpecificOutput.additionalContext | contains("[SECRET-AWS-ACCESS-KEY]")' > /dev/null && pass "AWS key triggers warning" || fail "AWS key should warn"

# Should warn: private key
INPUT=$(jq -n '{"hook_event_name":"PostToolUse","tool_name":"Write","tool_input":{"file_path":"/tmp/key.pem","content":"-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA\n-----END RSA PRIVATE KEY-----"}}')
OUTPUT=$(echo "$INPUT" | python3 "$HOOKS/post_write_warnings.py" 2>&1)
echo "$OUTPUT" | jq -e '.hookSpecificOutput.additionalContext | contains("[SECRET-PRIVATE-KEY]")' > /dev/null && pass "private key triggers warning" || fail "private key should warn"

# Should warn: CI workflow change
INPUT='{"hook_event_name":"PostToolUse","tool_name":"Write","tool_input":{"file_path":".github/workflows/lint.yml","content":"jobs:\n  test:\n"}}'
OUTPUT=$(echo "$INPUT" | python3 "$HOOKS/post_write_warnings.py" 2>&1)
echo "$OUTPUT" | jq -e '.hookSpecificOutput.additionalContext | contains("[POST-CI-WORKFLOW]")' > /dev/null && pass "CI workflow triggers warning" || fail "CI workflow should warn"

# Should warn: migration change
INPUT='{"hook_event_name":"PostToolUse","tool_name":"Write","tool_input":{"file_path":"db/migrations/001.sql","content":"CREATE TABLE users(id int);"}}'
OUTPUT=$(echo "$INPUT" | python3 "$HOOKS/post_write_warnings.py" 2>&1)
echo "$OUTPUT" | jq -e '.hookSpecificOutput.additionalContext | contains("[POST-MIGRATION]")' > /dev/null && pass "migration triggers warning" || fail "migration should warn"

# PostToolUse should not deny after a write
INPUT='{"hook_event_name":"PostToolUse","tool_name":"Write","tool_input":{"file_path":"/tmp/config.ts","content":"const key = \"AKIA1234567890ABCDEF\""}}'
OUTPUT=$(echo "$INPUT" | python3 "$HOOKS/post_write_warnings.py" 2>&1)
echo "$OUTPUT" | jq -e '.hookSpecificOutput | has("permissionDecision") | not' > /dev/null && pass "post-write warnings never deny" || fail "post-write warnings should not deny"

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
