#!/bin/bash
set -euo pipefail

# Tests for claude-bootstrap hardening profile templates.
# Run: bash tests/test-hardening-profiles.sh

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASELINE="$ROOT/plugin/hardening/profiles/baseline.settings.json"
README="$ROOT/README.md"

PASSED=0
FAILED=0

pass() { echo "  PASS: $1"; ((PASSED++)) || true; }
fail() { echo "  FAIL: $1"; ((FAILED++)) || true; }

assert_contains() {
  local path=$1 pattern=$2 label=$3
  if grep -Fq -- "$pattern" "$path"; then
    pass "$label"
  else
    fail "$label"
  fi
}

assert_jq_true() {
  local filter=$1 label=$2
  if jq -e "$filter" "$BASELINE" > /dev/null; then
    pass "$label"
  else
    fail "$label"
  fi
}

echo "=== Hardening Profile Tests ==="
echo ""

if [[ -f "$BASELINE" ]]; then
  pass "baseline profile exists"
else
  fail "baseline profile missing"
fi

if jq empty "$BASELINE" > /dev/null; then
  pass "baseline profile is valid JSON"
else
  fail "baseline profile has invalid JSON"
fi

assert_jq_true '.permissions.disableBypassPermissionsMode == "disable"' "baseline disables permission bypass"
assert_jq_true '(.permissions.deny | type) == "array" and (.permissions.ask | type) == "array"' "deny and ask are arrays"
assert_jq_true '(.permissions.deny | length) > 0 and (.permissions.ask | length) > 0' "deny and ask are populated"
assert_jq_true '(.permissions.deny | length) == (.permissions.deny | unique | length)' "deny has no duplicates"
assert_jq_true '(.permissions.ask | length) == (.permissions.ask | unique | length)' "ask has no duplicates"
assert_jq_true '([.permissions.deny[], .permissions.ask[]] | length) == ([.permissions.deny[], .permissions.ask[]] | unique | length)' "deny and ask do not overlap"
assert_jq_true '[.permissions.deny[], .permissions.ask[]] | all(test("^(Read|Bash)\\(.+\\)$"))' "permission rules use allowed format"

for forbidden in \
  "Bash(rm *)" \
  "Bash(git reset *)" \
  "Bash(git clean *)" \
  "Bash(sudo *)"
do
  if jq -e --arg rule "$forbidden" '[.permissions.deny[], .permissions.ask[]] | index($rule) == null' "$BASELINE" > /dev/null; then
    pass "profile excludes broad pattern $forbidden"
  else
    fail "profile must not include broad pattern $forbidden"
  fi
done

assert_jq_true '.permissions.deny | index("Read(./.env)") != null' "baseline denies .env reads"
assert_jq_true '.permissions.deny | index("Read(~/.ssh/**)") != null' "baseline denies ssh reads"
assert_jq_true '.permissions.deny | index("Bash(gh repo delete *)") != null' "baseline denies repo deletion"
assert_jq_true '.permissions.ask | index("Bash(npm publish *)") != null' "baseline asks on npm publish"
assert_jq_true '.permissions.ask | index("Bash(terraform apply *)") != null' "baseline asks on terraform apply"
assert_jq_true '.permissions.ask | index("Bash(kubectl delete *)") != null' "baseline asks on kubectl delete"

assert_contains "$README" "baseline.settings.json" "README mentions baseline profile file"
assert_contains "$README" "not applied automatically" "README explains baseline is not applied automatically"
assert_contains "$README" "context-aware hooks" "README explains broad commands need context-aware hooks"

echo ""
echo "=== Results: $PASSED passed, $FAILED failed ==="

if [[ $FAILED -gt 0 ]]; then
  exit 1
fi
