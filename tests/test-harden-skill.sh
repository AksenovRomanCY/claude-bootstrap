#!/bin/bash
set -euo pipefail

# Tests for the /harden skill instructions.
# Run: bash tests/test-harden-skill.sh

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SKILL="$ROOT/plugin/skills/harden/SKILL.md"
DOCTOR_SKILL="$ROOT/plugin/skills/doctor/SKILL.md"
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

echo "=== Harden Skill Tests ==="
echo ""

assert_file "$SKILL" "harden skill"
assert_contains "$SKILL" "name: harden" "skill frontmatter names harden"
assert_contains "$SKILL" "/harden --baseline" "skill documents baseline command"
assert_contains "$SKILL" "/harden --baseline --sandbox" "skill documents baseline sandbox command"
assert_contains "$SKILL" "/harden --strict" "skill documents strict command"
assert_contains "$SKILL" "/harden --strict --sandbox" "skill documents strict sandbox command"
assert_contains "$SKILL" "/harden --dry-run" "skill documents dry-run command"
assert_contains "$SKILL" "/harden --check" "skill documents check command"
assert_contains "$SKILL" "/harden --remove" "skill documents remove command"
assert_contains "$SKILL" "/harden --remove-sandbox" "skill documents remove-sandbox command"
assert_contains "$SKILL" "Default: \`/harden\` is the same as \`/harden --baseline\`" "skill documents default behavior"
assert_contains "$SKILL" "PROFILE=strict" "skill maps strict profile"
assert_contains "$SKILL" "SANDBOX_FLAG=--sandbox" "skill maps sandbox flag"
assert_contains "$SKILL" "\$CLAUDE_PLUGIN_DIR/hardening/apply_profile.py" "skill supports plugin hardening assets"
assert_contains "$SKILL" ".claude/hardening/apply_profile.py" "skill supports manual hardening assets"
assert_contains "$SKILL" "--profile \"\$PROFILE\" \$SANDBOX_FLAG --dry-run" "skill previews selected profile with apply_profile dry-run"
assert_contains "$SKILL" "--profile \"\$PROFILE\" \$SANDBOX_FLAG --check" "skill checks selected profile drift with apply_profile"
assert_contains "$SKILL" ".claude/settings.json" "skill lists settings target"
assert_contains "$SKILL" ".claude/security-policy.json" "skill lists security policy target"
assert_contains "$SKILL" ".claude/harden-state.json" "skill lists harden state target"
assert_contains "$SKILL" ".claude/rules/common/destructive-operations.md" "skill lists destructive rule target"
assert_contains "$SKILL" "--remove-sandbox --dry-run" "skill previews sandbox removal"
assert_contains "$SKILL" "--remove-sandbox" "skill applies sandbox removal"
assert_contains "$SKILL" "--profile \"\$PROFILE\" --remove --dry-run" "skill previews selected profile remove mode"
assert_contains "$SKILL" "--profile \"\$PROFILE\" --remove" "skill applies selected profile remove mode"
assert_contains "$SKILL" "Ask for explicit user confirmation before writing" "skill requires confirmation"
assert_contains "$SKILL" "Do not run \`/bootstrap\` automatically" "skill does not auto-bootstrap"
assert_contains "$SKILL" "Do not modify \`.claude/settings.local.json\`" "skill protects local settings"
assert_contains "$SKILL" "Enable sandbox settings only when \`--sandbox\` is explicit" "skill keeps sandbox opt-in"
assert_contains "$SKILL" "Do not remove \`.claude/rules/\` during \`--remove\`" "skill preserves project rules on remove"

assert_contains "$DOCTOR_SKILL" "bootstrap\`, \`harden\`" "doctor checks harden skill"
assert_contains "$DOCTOR_SKILL" "Skills:     12/12" "doctor summary uses 12/12 skills"
assert_contains "$DOCTOR_SKILL" "project sandbox configuration" "doctor checks sandbox configuration"
assert_contains "$DOCTOR_SKILL" "Claude Code's \`/sandbox\`" "doctor delegates runtime sandbox diagnostics"
assert_contains "$README" "| \`/harden\` |" "README lists harden command"
assert_contains "$README" "/harden --strict" "README documents strict command"
assert_contains "$README" "/harden --remove" "README documents harden remove"
assert_contains "$README" "/harden --remove-sandbox" "README documents harden remove-sandbox"
assert_contains "$README" "not applied automatically" "README explains hardening is explicit"

echo ""
echo "=== Results: $PASSED passed, $FAILED failed ==="

if [[ $FAILED -gt 0 ]]; then
  exit 1
fi
