#!/bin/bash
set -euo pipefail

# Tests for hardening release documentation.
# Run: bash tests/test-docs-hardening.sh

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
README="$ROOT/README.md"
CHANGELOG="$ROOT/CHANGELOG.md"
VERSION_FILE="$ROOT/VERSION"
SETTINGS_HOOKS="$ROOT/plugin/settings-hooks.json"
PLUGIN_HOOKS="$ROOT/plugin/hooks/hooks.json"
BASELINE_POLICY="$ROOT/plugin/hardening/defaults/baseline-policy.json"
STRICT_POLICY="$ROOT/plugin/hardening/defaults/strict-policy.json"
POLICY_SCHEMA="$ROOT/plugin/hardening/security-policy.schema.json"

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
assert_contains "$README" "External Guard Follow-up" "README documents external guard follow-up"
assert_contains "$README" "optional future work" "README keeps external guard future-only"
assert_contains "$README" "not required for baseline, strict, sandbox, \`/doctor\`, or CI" "README keeps release independent of external guard"
assert_contains "$README" "does not call \`dcg\`" "README says current release does not invoke dcg"
assert_contains "$README" "\"externalGuard\"" "README shows future external guard example"
assert_contains "$README" "\"enabled\": false" "README documents disabled-by-default external guard"
assert_contains "$README" "\"command\": \"dcg\"" "README shows configurable external guard command"
assert_contains "$README" "\"timeoutMs\": 1000" "README shows bounded external guard timeout example"
assert_contains "$README" "documentation only, not a supported schema field" "README keeps example out of current schema"
assert_contains "$README" "enabled only explicitly" "README requires explicit external guard opt-in"
assert_contains "$README" "independent of baseline, strict, and sandbox overlay behavior" "README keeps profiles independent"
assert_contains "$README" "A missing external executable must not affect current hardening profiles" "README handles missing executable"
assert_contains "$README" "internal high-confidence deny, internal context rules, optional external guard, then priority merge" "README documents future decision order"
assert_contains "$README" "External verdicts must never override an internal deny" "README protects internal deny"
assert_contains "$README" "unknown output must not be treated as allow" "README handles unknown output"
assert_contains "$README" "stdout and stderr must be bounded and redacted" "README requires bounded redacted output"
assert_contains "$README" "secrets must not be written to debug logs" "README protects secrets in future guard logs"

assert_contains "$CHANGELOG" "## Unreleased" "CHANGELOG has Unreleased section"
assert_contains "$CHANGELOG" "hardening responsibility boundaries" "CHANGELOG documents responsibility model"
assert_contains "$CHANGELOG" "external guard integration remains optional future work" "CHANGELOG keeps external guard optional"
assert_contains "$CHANGELOG" "External guard integration documented as optional follow-up work" "CHANGELOG documents optional external guard follow-up"
assert_contains "$CHANGELOG" "native Windows sandbox limits" "CHANGELOG documents platform limitation"
assert_contains "$CHANGELOG" "CI secret scanning" "CHANGELOG documents scanner boundary"
# VERSION is checked for shape and ordering rather than pinned to one release:
# a pin turns every legitimate bump into a failing test.
VERSION_VALUE="$(tr -d '[:space:]' < "$VERSION_FILE")"
if [[ "$VERSION_VALUE" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$ ]]; then
  pass "VERSION is valid semver"
else
  fail "VERSION is valid semver"
fi

CHANGELOG_VERSION="$(grep -Eo '^## \[?[0-9]+\.[0-9]+\.[0-9]+\]?' "$CHANGELOG" | head -1 | tr -cd '0-9.')"
if [[ -z "$CHANGELOG_VERSION" ]]; then
  fail "CHANGELOG has a released version heading"
else
  pass "CHANGELOG has a released version heading"
  # sort -V puts the smaller version first: VERSION must not be behind the
  # newest release the CHANGELOG already documents.
  lowest="$(printf '%s\n%s\n' "$VERSION_VALUE" "$CHANGELOG_VERSION" | sort -V | head -1)"
  if [[ "$VERSION_VALUE" == "$CHANGELOG_VERSION" || "$lowest" == "$CHANGELOG_VERSION" ]]; then
    pass "VERSION is not behind the newest CHANGELOG entry"
  else
    fail "VERSION is not behind the newest CHANGELOG entry"
  fi
fi

assert_not_contains "$README" "claude-bootstrap implements its own sandbox" "README must not claim custom sandbox implementation"
assert_not_contains "$SETTINGS_HOOKS" "externalGuard" "manual hook config must not reference externalGuard"
assert_not_contains "$SETTINGS_HOOKS" "dcg" "manual hook config must not call dcg"
assert_not_contains "$PLUGIN_HOOKS" "externalGuard" "plugin hook config must not reference externalGuard"
assert_not_contains "$PLUGIN_HOOKS" "dcg" "plugin hook config must not call dcg"
assert_not_contains "$BASELINE_POLICY" "externalGuard" "baseline policy must not include externalGuard"
assert_not_contains "$BASELINE_POLICY" "dcg" "baseline policy must not mention dcg"
assert_not_contains "$STRICT_POLICY" "externalGuard" "strict policy must not include externalGuard"
assert_not_contains "$STRICT_POLICY" "dcg" "strict policy must not mention dcg"
assert_not_contains "$POLICY_SCHEMA" "externalGuard" "policy schema must not expose externalGuard yet"
assert_not_contains "$POLICY_SCHEMA" "dcg" "policy schema must not mention dcg"

echo ""
echo "=== Results: $PASSED passed, $FAILED failed ==="

if [[ $FAILED -gt 0 ]]; then
  exit 1
fi
