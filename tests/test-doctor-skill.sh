#!/bin/bash
set -euo pipefail

# Tests for the /doctor skill instructions.
# Run: bash tests/test-doctor-skill.sh

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SKILL="$ROOT/plugin/skills/doctor/SKILL.md"
README="$ROOT/README.md"

PASSED=0
FAILED=0

pass() { echo "  PASS: $1"; ((PASSED++)) || true; }
fail() { echo "  FAIL: $1"; ((FAILED++)) || true; }

assert_file() {
  local path=$1 label=$2
  if [[ -f "$path" ]]; then
    pass "$label exists"
  else
    fail "$label missing"
  fi
}

assert_contains() {
  local path=$1 pattern=$2 label=$3
  if grep -Fq -- "$pattern" "$path"; then
    pass "$label"
  else
    fail "$label"
  fi
}

echo "=== Doctor Skill Tests ==="
echo ""

assert_file "$SKILL" "doctor skill"
assert_contains "$SKILL" "name: doctor" "doctor skill frontmatter names doctor"
assert_contains "$SKILL" "read-only health check" "doctor documents read-only health check"
assert_contains "$SKILL" "python3 --version" "doctor checks Python version"
assert_contains "$SKILL" "Python is missing" "doctor continues when Python is missing"
assert_contains "$SKILL" "hooks/scripts/command_guard.py" "doctor checks installed command guard path"
assert_contains "$SKILL" "hooks/scripts/secret_guard.py" "doctor checks installed hook script paths"
assert_contains "$SKILL" "hooks/guard/context.py" "doctor checks installed guard module paths"
assert_contains "$SKILL" "PostToolUse\` has entries for \`Write|Edit\` matcher" "doctor checks active PostToolUse matcher"
assert_contains "$SKILL" "hardening/profiles/baseline.settings.json" "doctor checks baseline profile"
assert_contains "$SKILL" "hardening/profiles/strict.settings.json" "doctor checks strict profile"
assert_contains "$SKILL" "hardening/profiles/sandbox.settings.json" "doctor checks sandbox overlay"
assert_contains "$SKILL" "hardening/security-policy.schema.json" "doctor checks policy schema"
assert_contains "$SKILL" "hardening/defaults/baseline-policy.json" "doctor checks baseline policy"
assert_contains "$SKILL" "hardening/defaults/strict-policy.json" "doctor checks strict policy"
assert_contains "$SKILL" "~/.claude/skills/harden/SKILL.md" "doctor checks harden skill"
assert_contains "$SKILL" "block-no-verify.sh" "doctor detects legacy hook command"
assert_contains "$SKILL" "block-large-files.sh" "doctor detects legacy large-file hook"
assert_contains "$SKILL" "warn-secrets.sh" "doctor detects legacy secrets hook"
assert_contains "$SKILL" "warn-debug-code.sh" "doctor detects legacy debug hook"
assert_contains "$SKILL" "duplicate hook fingerprints" "doctor detects duplicate hooks"
assert_contains "$SKILL" "(event, matcher, if, command, args)" "doctor uses scoped hook fingerprints"
assert_contains "$SKILL" ".claude/settings.json" "doctor checks project settings"
assert_contains "$SKILL" ".claude/security-policy.json" "doctor checks project policy"
assert_contains "$SKILL" "INVALID JSON" "doctor reports invalid JSON separately"
assert_contains "$SKILL" "SCHEMA INVALID" "doctor reports schema-invalid policy"
assert_contains "$SKILL" "custom valid" "doctor reports custom valid policy"
assert_contains "$SKILL" ".claude/harden-state.json" "doctor checks managed state"
assert_contains "$SKILL" "INVALID MANAGER" "doctor reports invalid state manager"
assert_contains "$SKILL" "INVALID VERSION" "doctor reports invalid state version"
assert_contains "$SKILL" "sandboxOverlay" "doctor reports sandbox overlay state"
assert_contains "$SKILL" "managed permission count" "doctor reports managed permission count"
assert_contains "$SKILL" "--profile \"\$PROFILE\" --check" "doctor uses apply_profile check for drift"
assert_contains "$SKILL" "Profile drift" "doctor documents profile drift"
assert_contains "$SKILL" "SKIPPED" "doctor skips Python-dependent checks when needed"
assert_contains "$SKILL" "sandbox.failIfUnavailable" "doctor checks failIfUnavailable"
assert_contains "$SKILL" "sandbox.allowUnsandboxedCommands" "doctor checks unsandboxed fallback"
assert_contains "$SKILL" "~/.aws/credentials" "doctor checks credential file deny entries"
assert_contains "$SKILL" "AWS_SECRET_ACCESS_KEY" "doctor checks credential env deny entries"
assert_contains "$SKILL" "dangerous exclusions" "doctor reports dangerous sandbox exclusions"
assert_contains "$SKILL" "Sandbox runtime: always report \`use Claude Code /sandbox\`" "doctor delegates sandbox runtime"
assert_contains "$SKILL" "do not inspect Seatbelt, bubblewrap, network behavior, process isolation, or platform internals" "doctor avoids runtime probing"
assert_contains "$SKILL" "Never auto-fix missing hooks, invalid policy, profile drift, or sandbox conflicts" "doctor does not auto-fix hardening issues"
assert_contains "$SKILL" "Report ALL issues" "doctor reports all issues"
assert_contains "$SKILL" "Hardening:" "doctor summary includes hardening"
assert_contains "$SKILL" "Legacy:" "doctor summary includes legacy hooks"
assert_contains "$SKILL" "Runtime:" "doctor summary includes sandbox runtime delegation"
assert_contains "$README" "hardening, permissions, and sandbox config status" "README describes doctor hardening scope"

echo ""
echo "=== Results: $PASSED passed, $FAILED failed ==="

if [[ $FAILED -gt 0 ]]; then
  exit 1
fi
