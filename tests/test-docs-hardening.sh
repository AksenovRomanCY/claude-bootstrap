#!/bin/bash
set -euo pipefail

# Tests for hardening release documentation.
# Run: bash tests/test-docs-hardening.sh

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
README="$ROOT/README.md"
CHANGELOG="$ROOT/CHANGELOG.md"
VERSION_FILE="$ROOT/VERSION"

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

assert_not_contains() {
  local path=$1 pattern=$2 label=$3
  if grep -Fq -- "$pattern" "$path"; then
    fail "$label"
  else
    pass "$label"
  fi
}

echo "=== Hardening Docs Tests ==="
echo ""

assert_contains "$README" "/bootstrap" "README documents bootstrap"
assert_contains "$README" "/harden --baseline" "README documents baseline hardening"
assert_contains "$README" "/harden --strict" "README documents strict hardening"
assert_contains "$README" "/harden --baseline --sandbox" "README documents sandbox opt-in"
assert_contains "$README" "/harden --check" "README documents hardening drift check"
assert_contains "$README" "/harden --remove" "README documents hardening rollback"
assert_contains "$README" "/harden --remove-sandbox" "README documents sandbox rollback"
assert_contains "$README" "/doctor" "README documents doctor diagnostics"

assert_contains "$README" "Hardening Responsibility Model" "README has responsibility model"
assert_contains "$README" "| Rules | Behavioral guidance for Claude |" "README describes rules responsibility"
assert_contains "$README" "| Permissions | Native static \`ask\`/\`deny\` controls in Claude Code settings |" "README describes permissions responsibility"
assert_contains "$README" "| Hooks | Project-specific contextual checks for commands and writes |" "README describes hooks responsibility"
assert_contains "$README" "| Claude Code | Command matching, permissions runtime, hook runtime, and sandbox runtime |" "README describes Claude Code responsibility"
assert_contains "$README" "| External guard | Optional future advanced analysis, not part of baseline or strict |" "README keeps external guard optional"

assert_contains "$README" "Hardening Limitations" "README has hardening limitations"
assert_contains "$README" "Rules are behavioral guidance, not a security boundary." "README documents rules boundary"
assert_contains "$README" "Project \`.claude/settings.json\` can be changed in a checkout" "README documents project settings mutability"
assert_contains "$README" "enterprise enforcement requires managed settings" "README documents enterprise enforcement boundary"
assert_contains "$README" "claude-bootstrap does not implement its own sandbox runtime" "README does not claim a custom sandbox"
assert_contains "$README" "Claude Code owns command matching, permissions, hooks, and sandbox execution" "README assigns runtime ownership to Claude Code"
assert_contains "$README" "not supported on native Windows" "README documents native Windows sandbox limitation"
assert_contains "$README" "not a complete Bash AST security parser" "README documents parser limitation"
assert_contains "$README" "embedded scripts" "README documents embedded script review"
assert_contains "$README" "does not replace CI secret scanning" "README documents secret scanning boundary"
assert_contains "$README" "Strict mode creates additional permission prompts" "README documents strict prompts"

assert_contains "$CHANGELOG" "## Unreleased" "CHANGELOG has Unreleased section"
assert_contains "$CHANGELOG" "hardening responsibility boundaries" "CHANGELOG documents responsibility model"
assert_contains "$CHANGELOG" "external guard integration remains optional future work" "CHANGELOG keeps external guard optional"
assert_contains "$CHANGELOG" "native Windows sandbox limits" "CHANGELOG documents platform limitation"
assert_contains "$CHANGELOG" "CI secret scanning" "CHANGELOG documents scanner boundary"
assert_contains "$VERSION_FILE" "1.3.0" "Task 21 does not bump VERSION"

assert_not_contains "$README" "claude-bootstrap implements its own sandbox" "README must not claim custom sandbox implementation"

echo ""
echo "=== Results: $PASSED passed, $FAILED failed ==="

if [[ $FAILED -gt 0 ]]; then
  exit 1
fi
