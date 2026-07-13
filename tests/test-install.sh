#!/bin/bash
# shellcheck disable=SC2015,SC2016
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PASSED=0
FAILED=0

pass() { echo "  PASS: $1"; ((PASSED++)) || true; }
fail() { echo "  FAIL: $1"; ((FAILED++)) || true; }

run_install() {
  local home=$1
  HOME="$home" bash "$SCRIPT_DIR/install.sh" --force
}

run_uninstall() {
  local home=$1
  HOME="$home" bash "$SCRIPT_DIR/uninstall.sh" --force
}

assert_file() {
  local path=$1 label=$2
  [[ -f "$path" ]] && pass "$label" || fail "$label"
}

assert_no_file() {
  local path=$1 label=$2
  [[ ! -e "$path" ]] && pass "$label" || fail "$label"
}

assert_jq() {
  local file=$1 filter=$2 label=$3
  jq -e "$filter" "$file" > /dev/null && pass "$label" || fail "$label"
}

hook_count() {
  local file=$1 command_pattern=$2
  jq --arg pattern "$command_pattern" '[.hooks[][]?.hooks[]? | select((.command // "") | contains($pattern))] | length' "$file"
}

echo "=== Install Tests ==="
echo ""

TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT

# --------------------------------------------------
echo "fresh install"
# --------------------------------------------------

HOME_ONE="$TMP_ROOT/home-one"
mkdir -p "$HOME_ONE"
run_install "$HOME_ONE" > "$TMP_ROOT/fresh-install.log"

assert_file "$HOME_ONE/.claude/settings.json" "fresh install creates settings.json"
assert_file "$HOME_ONE/.claude/hooks/scripts/command_guard.py" "fresh install copies command_guard.py"
assert_file "$HOME_ONE/.claude/hooks/guard/rules.py" "fresh install copies hooks/guard"
assert_file "$HOME_ONE/.claude/hardening/apply_profile.py" "fresh install copies hardening assets"
assert_file "$HOME_ONE/.claude/skills/harden/SKILL.md" "fresh install copies harden skill"
assert_file "$HOME_ONE/.claude/.bootstrap-version" "fresh install records version"
if find "$HOME_ONE/.claude" -name '*.pyc' -o -name '__pycache__' | grep -q .; then
  fail "fresh install should not copy Python cache files"
else
  pass "fresh install skips Python cache files"
fi
assert_jq "$HOME_ONE/.claude/settings.json" '[.hooks.PreToolUse[]? | select(.matcher == "Bash") | .hooks[]? | select(.command == "python3 ~/.claude/hooks/scripts/command_guard.py" and (.if | startswith("Bash(")))] | length == 30' "fresh install has expected Bash command_guard hooks"
assert_jq "$HOME_ONE/.claude/settings.json" '[.hooks.PostToolUse[]? | select(.matcher == "Write|Edit") | .hooks[]? | select(.command | contains("remind-compact.sh"))] | length == 1' "fresh install keeps remind-compact hook"

echo ""

# --------------------------------------------------
echo "skip hooks keeps hardening"
# --------------------------------------------------

HOME_SKIP_HOOKS="$TMP_ROOT/home-skip-hooks"
mkdir -p "$HOME_SKIP_HOOKS"
HOME="$HOME_SKIP_HOOKS" bash "$SCRIPT_DIR/install.sh" --force --skip-hooks > "$TMP_ROOT/skip-hooks-install.log"
assert_file "$HOME_SKIP_HOOKS/.claude/hardening/apply_profile.py" "skip-hooks still copies hardening assets"
assert_no_file "$HOME_SKIP_HOOKS/.claude/hooks/scripts/command_guard.py" "skip-hooks skips hook scripts"
assert_no_file "$HOME_SKIP_HOOKS/.claude/settings.json" "skip-hooks does not create settings hooks"

echo ""

# --------------------------------------------------
echo "legacy migration"
# --------------------------------------------------

HOME_TWO="$TMP_ROOT/home-two"
mkdir -p "$HOME_TWO/.claude"
cat > "$HOME_TWO/.claude/settings.json" <<'JSON'
{
  "theme": "dark",
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {"type": "command", "command": "bash ~/.claude/hooks/scripts/block-no-verify.sh"},
          {"type": "command", "command": "custom-pre"}
        ]
      },
      {
        "matcher": "Write|Edit",
        "hooks": [
          {"type": "command", "command": "python3 ~/.claude/hooks/scripts/secret_guard.py"},
          {"type": "command", "command": "bash ~/.claude/hooks/scripts/block-large-files.sh"}
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {"type": "command", "command": "bash ~/.claude/hooks/scripts/warn-secrets.sh"},
          {"type": "command", "command": "bash ~/.claude/hooks/scripts/warn-debug-code.sh"},
          {"type": "command", "command": "custom-post"}
        ]
      }
    ]
  }
}
JSON

run_install "$HOME_TWO" > "$TMP_ROOT/migrate-install.log"

assert_jq "$HOME_TWO/.claude/settings.json" '.theme == "dark"' "migration preserves unrelated settings"
assert_jq "$HOME_TWO/.claude/settings.json" '[.hooks[][]?.hooks[]?.command] | index("custom-pre") != null and index("custom-post") != null' "migration preserves custom hooks"
assert_jq "$HOME_TWO/.claude/settings.json" '[.hooks[][]?.hooks[]?.command] | map(select(test("block-no-verify\\.sh|block-large-files\\.sh|warn-secrets\\.sh|warn-debug-code\\.sh"))) | length == 0' "migration removes legacy hooks"
assert_jq "$HOME_TWO/.claude/settings.json" '[.hooks[][]?.hooks[]?.command] | map(select(contains("command_guard.py"))) | length == 32' "migration adds if-scoped command_guard entries once"
assert_jq "$HOME_TWO/.claude/settings.json" '[.hooks.PostToolUse[]? | select(.matcher == "Write|Edit") | .hooks[]?.command] | map(select(contains("remind-compact.sh"))) | length == 1' "migration adds remind-compact once"

backup_count=$(find "$HOME_TWO/.claude/backups" -name 'backup-*.tar.gz' -type f 2>/dev/null | wc -l | tr -d ' ')
[[ "$backup_count" -ge 1 ]] && pass "migration creates backup" || fail "migration should create backup"

before_hash=$(jq -S -c . "$HOME_TWO/.claude/settings.json")
backup_count_before_reinstall=$(find "$HOME_TWO/.claude/backups" -name 'backup-*.tar.gz' -type f 2>/dev/null | wc -l | tr -d ' ')
run_install "$HOME_TWO" > "$TMP_ROOT/reinstall.log"
after_hash=$(jq -S -c . "$HOME_TWO/.claude/settings.json")
backup_count_after_reinstall=$(find "$HOME_TWO/.claude/backups" -name 'backup-*.tar.gz' -type f 2>/dev/null | wc -l | tr -d ' ')
[[ "$before_hash" == "$after_hash" ]] && pass "reinstall keeps settings idempotent" || fail "reinstall should not change settings"
[[ "$backup_count_before_reinstall" == "$backup_count_after_reinstall" ]] && pass "reinstall does not create unnecessary backup" || fail "reinstall should not create unnecessary backup"
[[ "$(hook_count "$HOME_TWO/.claude/settings.json" "command_guard.py")" == "32" ]] && pass "reinstall does not duplicate command_guard hooks" || fail "reinstall should not duplicate command_guard hooks"

echo ""

# --------------------------------------------------
echo "dry run"
# --------------------------------------------------

HOME_THREE="$TMP_ROOT/home-three"
mkdir -p "$HOME_THREE"
HOME="$HOME_THREE" bash "$SCRIPT_DIR/install.sh" --dry-run > "$TMP_ROOT/dry-run.log"
assert_no_file "$HOME_THREE/.claude/settings.json" "dry run does not write settings"
grep -q "Settings migration:" "$TMP_ROOT/dry-run.log" && pass "dry run prints settings migration summary" || fail "dry run should print settings migration summary"

echo ""

# --------------------------------------------------
echo "uninstall"
# --------------------------------------------------

PROJECT_DIR="$TMP_ROOT/project"
mkdir -p "$PROJECT_DIR/.claude/rules"
cat > "$PROJECT_DIR/.claude/settings.json" <<'JSON'
{"project": true}
JSON
cat > "$PROJECT_DIR/.claude/security-policy.json" <<'JSON'
{"version": 1}
JSON
echo "rule" > "$PROJECT_DIR/.claude/rules/custom.md"

run_uninstall "$HOME_TWO" > "$TMP_ROOT/uninstall.log"

assert_no_file "$HOME_TWO/.claude/hooks/scripts/command_guard.py" "uninstall removes command_guard.py"
assert_no_file "$HOME_TWO/.claude/hooks/guard/rules.py" "uninstall removes hooks/guard files"
assert_no_file "$HOME_TWO/.claude/hardening/apply_profile.py" "uninstall removes hardening files"
assert_no_file "$HOME_TWO/.claude/skills/harden/SKILL.md" "uninstall removes harden skill"
assert_no_file "$HOME_TWO/.claude/.bootstrap-version" "uninstall removes version file"
assert_jq "$HOME_TWO/.claude/settings.json" '[.hooks[][]?.hooks[]?.command] | index("custom-pre") != null and index("custom-post") != null' "uninstall preserves custom hooks"
assert_jq "$HOME_TWO/.claude/settings.json" '[.hooks[][]?.hooks[]?.command] | map(select(test("command_guard\\.py|remind-compact\\.sh|block-no-verify\\.sh|block-large-files\\.sh|warn-secrets\\.sh|warn-debug-code\\.sh"))) | length == 0' "uninstall removes bootstrap and legacy hook entries"
assert_file "$PROJECT_DIR/.claude/settings.json" "uninstall leaves project settings alone"
assert_file "$PROJECT_DIR/.claude/security-policy.json" "uninstall leaves project security policy alone"
assert_file "$PROJECT_DIR/.claude/rules/custom.md" "uninstall leaves project rules alone"

echo ""
echo "=== Results: $PASSED passed, $FAILED failed ==="

if [[ $FAILED -gt 0 ]]; then
  exit 1
fi
