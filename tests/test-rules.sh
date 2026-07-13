#!/bin/bash
set -euo pipefail

# Tests for claude-bootstrap rule inventory.
# Run: bash tests/test-rules.sh

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMMON_RULES="$ROOT/plugin/rules/common"
BOOTSTRAP_SKILL="$ROOT/plugin/skills/bootstrap/SKILL.md"
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

echo "=== Rule Inventory Tests ==="
echo ""

expected_rules=(
  coding-style.md
  database.md
  dependencies.md
  destructive-operations.md
  documentation.md
  error-handling.md
  git-workflow.md
  linting.md
  security.md
  testing.md
)

for rule in "${expected_rules[@]}"; do
  assert_file "$COMMON_RULES/$rule" "common/$rule"
done

actual_count=$(find "$COMMON_RULES" -maxdepth 1 -type f -name '*.md' | wc -l | tr -d '[:space:]')
if [[ "$actual_count" == "${#expected_rules[@]}" ]]; then
  pass "common rule count is ${#expected_rules[@]}"
else
  fail "common rule count expected ${#expected_rules[@]}, got $actual_count"
fi

destructive_rule="$COMMON_RULES/destructive-operations.md"
required_sections=(
  "# Destructive Operations"
  "## Git Operations"
  "## Filesystem Operations"
  "## Infrastructure Operations"
  "## Database Operations"
  "## Package Publication"
  "## Secrets"
  "## Preferred Safe Alternatives"
)

for section in "${required_sections[@]}"; do
  assert_contains "$destructive_rule" "$section" "destructive rule has $section"
done

assert_contains "$destructive_rule" "git push --force" "destructive rule documents force-push alternative"
assert_contains "$destructive_rule" "terraform apply" "destructive rule documents terraform alternative"
assert_contains "$destructive_rule" "kubectl delete" "destructive rule documents kubectl alternative"
assert_contains "$destructive_rule" "curl URL | sh" "destructive rule documents remote script alternative"

assert_contains "$BOOTSTRAP_SKILL" "common/         10 files" "bootstrap documents 10 common files"
assert_contains "$BOOTSTRAP_SKILL" "destructive-operations" "bootstrap mentions destructive operations rule"
assert_contains "$BOOTSTRAP_SKILL" "copy any new files" "bootstrap update mode copies new files"
assert_contains "$DOCTOR_SKILL" "Common (10 files)" "doctor documents 10 common files"
assert_contains "$DOCTOR_SKILL" "common/destructive-operations.md" "doctor checks destructive operations rule"
assert_contains "$DOCTOR_SKILL" "10/10 common" "doctor summary uses 10/10 common"
assert_contains "$README" "destructive-operations.md" "README lists destructive operations rule"
assert_contains "$README" "not a technical security boundary" "README documents rules boundary"

echo ""
echo "=== Results: $PASSED passed, $FAILED failed ==="

if [[ $FAILED -gt 0 ]]; then
  exit 1
fi
