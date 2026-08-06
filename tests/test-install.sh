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
assert_jq "$HOME_ONE/.claude/settings.json" '[.hooks.PreToolUse[]? | select(.matcher == "Bash") | .hooks[]? | select(.command == "python3 ~/.claude/hooks/scripts/command_guard.py" and ((.if // "") == ""))] | length == 1' "fresh install has one unconditional Bash command_guard hook"
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
echo "skip hardening"
# --------------------------------------------------

# The /harden skill lives under skills/ but is useless without hardening/, so
# the component that owns the assets owns the skill too.
HOME_SKIP_HARDENING="$TMP_ROOT/home-skip-hardening"
mkdir -p "$HOME_SKIP_HARDENING"
HOME="$HOME_SKIP_HARDENING" bash "$SCRIPT_DIR/install.sh" --force --skip-hardening > "$TMP_ROOT/skip-hardening-install.log"
assert_no_file "$HOME_SKIP_HARDENING/.claude/skills/harden/SKILL.md" "skip-hardening skips the harden skill"
assert_no_file "$HOME_SKIP_HARDENING/.claude/hardening/apply_profile.py" "skip-hardening skips hardening assets"
assert_file "$HOME_SKIP_HARDENING/.claude/skills/verify/SKILL.md" "skip-hardening keeps the other skills"
grep -q "skills/harden" "$TMP_ROOT/skip-hardening-install.log" && fail "skip-hardening should not preview the harden skill" || pass "skip-hardening omits the harden skill from the preview"

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
          {"type": "command", "if": "Bash(git *)", "command": "python3 ~/.claude/hooks/scripts/command_guard.py", "timeout": 30},
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
        "matcher": "Edit|Write",
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
assert_jq "$HOME_TWO/.claude/settings.json" '[.hooks[][]?.hooks[]?.command] | map(select(contains("command_guard.py"))) | length == 3' "migration replaces scoped guards with one unconditional Bash guard"
assert_jq "$HOME_TWO/.claude/settings.json" '[.hooks.PostToolUse[]? | select(((.matcher | split("|") | sort | join("|")) == "Edit|Write")) | .hooks[]?.command] | map(select(contains("remind-compact.sh"))) | length == 1' "migration canonicalizes matcher alternatives and adds remind-compact once"

backup_count=$(find "$HOME_TWO/.claude/backups" -name 'backup-*.tar.gz' -type f 2>/dev/null | wc -l | tr -d ' ')
[[ "$backup_count" -ge 1 ]] && pass "migration creates backup" || fail "migration should create backup"

before_hash=$(jq -S -c . "$HOME_TWO/.claude/settings.json")
backup_count_before_reinstall=$(find "$HOME_TWO/.claude/backups" -name 'backup-*.tar.gz' -type f 2>/dev/null | wc -l | tr -d ' ')
run_install "$HOME_TWO" > "$TMP_ROOT/reinstall.log"
after_hash=$(jq -S -c . "$HOME_TWO/.claude/settings.json")
backup_count_after_reinstall=$(find "$HOME_TWO/.claude/backups" -name 'backup-*.tar.gz' -type f 2>/dev/null | wc -l | tr -d ' ')
[[ "$before_hash" == "$after_hash" ]] && pass "reinstall keeps settings idempotent" || fail "reinstall should not change settings"
[[ "$backup_count_before_reinstall" == "$backup_count_after_reinstall" ]] && pass "reinstall does not create unnecessary backup" || fail "reinstall should not create unnecessary backup"
[[ "$(hook_count "$HOME_TWO/.claude/settings.json" "command_guard.py")" == "3" ]] && pass "reinstall does not duplicate command_guard hooks" || fail "reinstall should not duplicate command_guard hooks"

custom_guard_command="python3 ~/.claude/hooks/scripts/command_guard.py"
tmp_settings=$(mktemp)
jq --arg command "$custom_guard_command" '
  .hooks.PreToolUse += [
    {
      "matcher": "Bash",
      "hooks": [
        {
          "type": "command",
          "if": "Bash(custom-tool *)",
          "command": $command,
          "timeout": 11
        }
      ]
    }
  ]
' "$HOME_TWO/.claude/settings.json" > "$tmp_settings"
mv "$tmp_settings" "$HOME_TWO/.claude/settings.json"

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
assert_jq "$HOME_TWO/.claude/settings.json" '[.hooks.PreToolUse[]? | select(.matcher == "Bash") | .hooks[]? | select(.if == "Bash(custom-tool *)" and .command == "python3 ~/.claude/hooks/scripts/command_guard.py" and .timeout == 11)] | length == 1' "uninstall preserves custom command_guard hook"
assert_jq "$HOME_TWO/.claude/settings.json" '[.hooks[][]?.hooks[]? | select((.command // "") | test("remind-compact\\.sh|block-no-verify\\.sh|block-large-files\\.sh|warn-secrets\\.sh|warn-debug-code\\.sh"))] | length == 0' "uninstall removes legacy and remind-compact hook entries"
assert_jq "$HOME_TWO/.claude/settings.json" '[.hooks[][]?.hooks[]? | select((.command // "") | contains("command_guard.py")) | select((.if // "") != "Bash(custom-tool *)")] | length == 0' "uninstall removes bootstrap command_guard entries"
assert_file "$PROJECT_DIR/.claude/settings.json" "uninstall leaves project settings alone"
assert_file "$PROJECT_DIR/.claude/security-policy.json" "uninstall leaves project security policy alone"
assert_file "$PROJECT_DIR/.claude/rules/custom.md" "uninstall leaves project rules alone"

echo ""

# --------------------------------------------------
echo "uninstall leaves no empty directories"
# --------------------------------------------------

HOME_DIRS="$TMP_ROOT/home-dirs"
mkdir -p "$HOME_DIRS"
run_install "$HOME_DIRS" > "$TMP_ROOT/dirs-install.log"
# The Python hooks leave these behind once they have run; the uninstaller used
# to trip over them and leave hooks/guard in place.
mkdir -p "$HOME_DIRS/.claude/hooks/guard/__pycache__"
echo "cached" > "$HOME_DIRS/.claude/hooks/guard/__pycache__/rules.pyc"
run_uninstall "$HOME_DIRS" > "$TMP_ROOT/dirs-uninstall.log"
assert_no_file "$HOME_DIRS/.claude/hooks" "uninstall removes the hooks tree including __pycache__"
assert_no_file "$HOME_DIRS/.claude/skills" "uninstall removes the skills tree"
assert_no_file "$HOME_DIRS/.claude/bootstrap-rules" "uninstall removes the rules library tree"

HOME_EMPTY="$TMP_ROOT/home-empty"
mkdir -p "$HOME_EMPTY/.claude"
if run_uninstall "$HOME_EMPTY" > "$TMP_ROOT/empty-uninstall.log" 2>&1; then
  pass "uninstall with nothing installed exits cleanly"
else
  fail "uninstall with nothing installed should exit cleanly"
fi

echo ""

# --------------------------------------------------
echo "failed backup"
# --------------------------------------------------

# A backup that did not happen must not be reported as one, and must not be
# followed by an overwrite the user cannot roll back.
if [[ "$(id -u)" == "0" ]]; then
  echo "  SKIP: running as root, a read-only directory would not stop tar"
else
  HOME_BACKUP="$TMP_ROOT/home-backup"
  mkdir -p "$HOME_BACKUP"
  run_install "$HOME_BACKUP" > "$TMP_ROOT/backup-install.log"

  # A modified file is what makes the installer take the backup branch at all.
  echo "local edit" > "$HOME_BACKUP/.claude/skills/verify/SKILL.md"
  mkdir -p "$HOME_BACKUP/.claude/backups"
  chmod 555 "$HOME_BACKUP/.claude/backups"

  set +e
  printf 'y\n' | HOME="$HOME_BACKUP" bash "$SCRIPT_DIR/install.sh" \
    > "$TMP_ROOT/backup-fail.log" 2> "$TMP_ROOT/backup-fail.err"
  backup_status=$?
  set -e
  chmod 755 "$HOME_BACKUP/.claude/backups"

  [[ $backup_status -ne 0 ]] && pass "failed backup aborts the install" || fail "failed backup should abort the install"
  grep -q "Backup failed" "$TMP_ROOT/backup-fail.err" && pass "failed backup is reported" || fail "failed backup should be reported"
  grep -q "\[OK\] Backup" "$TMP_ROOT/backup-fail.log" && fail "failed backup should not print [OK] Backup" || pass "failed backup does not print [OK] Backup"
  grep -q "local edit" "$HOME_BACKUP/.claude/skills/verify/SKILL.md" && pass "failed backup leaves installed files untouched" || fail "failed backup should leave installed files untouched"

  chmod 555 "$HOME_BACKUP/.claude/backups"
  set +e
  HOME="$HOME_BACKUP" bash "$SCRIPT_DIR/install.sh" --force \
    > "$TMP_ROOT/backup-force.log" 2> "$TMP_ROOT/backup-force.err"
  backup_force_status=$?
  set -e
  chmod 755 "$HOME_BACKUP/.claude/backups"

  [[ $backup_force_status -eq 0 ]] && pass "--force installs despite a failed backup" || fail "--force should install despite a failed backup"
  grep -q "local edit" "$HOME_BACKUP/.claude/skills/verify/SKILL.md" && fail "--force should overwrite the modified file" || pass "--force overwrites the modified file"
fi

echo ""

# Claude Code reads settings.json with comments and trailing commas; jq does not.
# The installer must say so instead of aborting mid-run on a bare jq parse error.
HOME_JSONC="$TMP_ROOT/home-jsonc"
mkdir -p "$HOME_JSONC/.claude"
cat > "$HOME_JSONC/.claude/settings.json" <<'JSON'
{
  // Claude Code tolerates this
  "model": "opus",
}
JSON

set +e
HOME="$HOME_JSONC" bash "$SCRIPT_DIR/install.sh" --dry-run > "$TMP_ROOT/jsonc-install.log" 2> "$TMP_ROOT/jsonc-install.err"
jsonc_status=$?
set -e

if [[ $jsonc_status -ne 0 ]]; then
  pass "install fails cleanly on JSONC settings"
else
  fail "install should fail on JSONC settings"
fi

if grep -q "could not read" "$TMP_ROOT/jsonc-install.err" && grep -q "settings.json" "$TMP_ROOT/jsonc-install.err"; then
  pass "install names the unreadable settings file"
else
  fail "install should name the unreadable settings file"
fi

echo ""
echo "=== Results: $PASSED passed, $FAILED failed ==="

if [[ $FAILED -gt 0 ]]; then
  exit 1
fi
