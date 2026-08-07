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
    expected_command='python3 "${CLAUDE_PLUGIN_ROOT:-$CLAUDE_PLUGIN_DIR}/hooks/scripts/command_guard.py"'
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
    [.hooks.PreToolUse[]? | select(.matcher == "Bash") | .hooks[]?]
    == [{"type":"command","command":$command,"timeout":30}]
  ' "$config" > /dev/null; then
    pass "$(basename "$config") uses one unconditional Bash command_guard.py hook"
  else
    fail "$(basename "$config") should use one unconditional Bash command_guard.py hook"
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

# Bare $CLAUDE_PLUGIN_DIR (without the ${CLAUDE_PLUGIN_ROOT:-...} fallback) is a
# fail-closed path: if the variable is unset, python3 exits 2 and PreToolUse denies.
if grep -q 'CLAUDE_PLUGIN_DIR/' "$PLUGIN_HOOKS_JSON"; then
  fail "hooks.json should not use bare \$CLAUDE_PLUGIN_DIR without CLAUDE_PLUGIN_ROOT fallback"
else
  pass "hooks.json has no bare \$CLAUDE_PLUGIN_DIR usage"
fi

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
WRAPPER_OUTPUT=$(run_hook "block-large-files.sh" "$INPUT" 2>/dev/null) && pass "compatibility wrapper exits 0" || fail "compatibility wrapper should exit 0"
# Exiting 0 is not enough: the wrapper has to actually reach the policy.
echo "$WRAPPER_OUTPUT" | jq -e '.hookSpecificOutput.permissionDecision == "ask"' > /dev/null \
  && pass "compatibility wrapper still produces a decision" \
  || fail "compatibility wrapper should still produce a decision"

# Without an interpreter the guard is off, and being off must be silent and open.
# The interpreter is addressed absolutely: an empty PATH also hides bash itself.
WRAPPER_OUTPUT=$(echo "$INPUT" | PATH="" "${BASH:-/bin/bash}" "$HOOKS/block-large-files.sh" 2>&1) && wrapper_status=0 || wrapper_status=$?
[[ $wrapper_status -eq 0 ]] && pass "compatibility wrapper exits 0 without python3" || fail "compatibility wrapper should exit 0 without python3"
[[ -z "$WRAPPER_OUTPUT" ]] && pass "compatibility wrapper is silent without python3" || fail "compatibility wrapper should be silent without python3"

# Should pass: non-Write/Edit tool
INPUT='{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"echo hello"}}'
echo "$INPUT" | python3 "$HOOKS/large_file_policy.py" > /dev/null 2>&1 && pass "non-Write tool passes" || fail "non-Write tool should pass"

echo ""

# --------------------------------------------------
echo "retired scripts"
# --------------------------------------------------

# block-no-verify.sh was a second shell tokenizer for the same commands
# command_guard.py judges, and secret_guard.py only re-exported guard.secrets.
# The git hook-bypass cases they covered live in tests/fixtures/git-commands.json.
for retired in block-no-verify.sh secret_guard.py; do
  [[ ! -e "$HOOKS/$retired" ]] && pass "$retired is gone" || fail "$retired should be gone"
  grep -q "hooks/scripts/$retired" "$SCRIPT_DIR/install.sh" && pass "install.sh prunes $retired from older installs" || fail "install.sh should prune $retired"
  grep -q "hooks/scripts/$retired" "$SCRIPT_DIR/uninstall.sh" && pass "uninstall.sh removes $retired from older installs" || fail "uninstall.sh should remove $retired"
done

# One implementation behind both legacy post-write names.
INPUT='{"hook_event_name":"PostToolUse","tool_name":"Write","tool_input":{"file_path":"/tmp/test.ts","content":"console.log(\"debug\")"}}'
OUTPUT=$(run_hook "warn-debug-code.sh" "$INPUT")
echo "$OUTPUT" | jq -e '.hookSpecificOutput.additionalContext | contains("[DEBUG-CONSOLE]")' > /dev/null \
  && pass "warn-debug-code.sh still warns through its sibling" \
  || fail "warn-debug-code.sh should still warn through its sibling"
grep -q "warn-secrets.sh" "$HOOKS/warn-debug-code.sh" && pass "warn-debug-code.sh defers instead of duplicating" || fail "warn-debug-code.sh should defer to warn-secrets.sh"

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

# The counter belongs to this user, not to whoever gets to /tmp first.
grep -q 'XDG_RUNTIME_DIR' "$HOOKS/remind-compact.sh" && pass "remind-compact keeps state in a per-user directory" || fail "remind-compact should keep state in a per-user directory"

echo ""

# --------------------------------------------------
echo "check-guard-runtime.sh"
# --------------------------------------------------

INPUT='{"hook_event_name":"SessionStart"}'
OUTPUT=$(run_hook "check-guard-runtime.sh" "$INPUT") && pass "guard runtime check exits 0 with python3" || fail "guard runtime check should exit 0 with python3"
[[ -z "$OUTPUT" ]] && pass "guard runtime check is silent when python3 exists" || fail "guard runtime check should be silent when python3 exists"

# Without an interpreter the guards are off; the session must be told so.
OUTPUT=$(echo "$INPUT" | PATH="" "${BASH:-/bin/bash}" "$HOOKS/check-guard-runtime.sh" 2>&1) && pass "guard runtime check exits 0 without python3" || fail "guard runtime check should exit 0 without python3"
echo "$OUTPUT" | jq -e '.hookSpecificOutput.hookEventName == "SessionStart" and (.hookSpecificOutput.additionalContext | contains("[GUARD-DISABLED]"))' > /dev/null \
  && pass "guard runtime check reports disabled guards" \
  || fail "guard runtime check should report disabled guards"

for config in "$SETTINGS_HOOKS_JSON" "$PLUGIN_HOOKS_JSON"; do
  jq -e '[.hooks.SessionStart[]?.hooks[]?.command] | map(select(contains("check-guard-runtime.sh"))) | length == 1' "$config" > /dev/null \
    && pass "$(basename "$config") wires the guard runtime check" \
    || fail "$(basename "$config") should wire the guard runtime check"
done

echo ""

# --------------------------------------------------
echo "=== Results: $PASSED passed, $FAILED failed ==="

if [[ $FAILED -gt 0 ]]; then
  exit 1
fi
