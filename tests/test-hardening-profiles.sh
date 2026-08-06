#!/bin/bash
set -euo pipefail

# Tests for claude-bootstrap hardening profile templates.
# Run: bash tests/test-hardening-profiles.sh

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASELINE="$ROOT/plugin/hardening/profiles/baseline.settings.json"
STRICT="$ROOT/plugin/hardening/profiles/strict.settings.json"
SANDBOX="$ROOT/plugin/hardening/profiles/sandbox.settings.json"
STRICT_POLICY="$ROOT/plugin/hardening/defaults/strict-policy.json"
POLICY_SCHEMA="$ROOT/plugin/hardening/security-policy.schema.json"
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

assert_jq_true_path() {
  local path=$1 filter=$2 label=$3
  if jq -e "$filter" "$path" > /dev/null; then
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

if [[ -f "$STRICT" ]]; then
  pass "strict profile exists"
else
  fail "strict profile missing"
fi

if jq empty "$STRICT" > /dev/null; then
  pass "strict profile is valid JSON"
else
  fail "strict profile has invalid JSON"
fi

if [[ -f "$SANDBOX" ]]; then
  pass "sandbox overlay exists"
else
  fail "sandbox overlay missing"
fi

if jq empty "$SANDBOX" > /dev/null; then
  pass "sandbox overlay is valid JSON"
else
  fail "sandbox overlay has invalid JSON"
fi

if [[ -f "$STRICT_POLICY" ]]; then
  pass "strict policy exists"
else
  fail "strict policy missing"
fi

if jq empty "$STRICT_POLICY" > /dev/null; then
  pass "strict policy is valid JSON"
else
  fail "strict policy has invalid JSON"
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

assert_jq_true '.permissions.ask | index("Read(./.env)") != null' "baseline asks on .env reads"
assert_jq_true '.permissions.ask | index("Read(~/.ssh/**)") != null' "baseline asks on ssh reads"
assert_jq_true '.permissions.ask | index("Read(~/.aws/credentials)") != null' "baseline asks on aws credential reads"
assert_jq_true '.permissions.ask | index("Read(~/.kube/config)") != null' "baseline asks on kube config reads"
assert_jq_true '[.permissions.deny[]] | all(startswith("Read(") | not)' "baseline denies no credential reads outright"
assert_jq_true '.permissions.deny | index("Bash(gh repo delete *)") != null' "baseline denies repo deletion"
assert_jq_true '.permissions.ask | index("Bash(npm publish *)") != null' "baseline asks on npm publish"
assert_jq_true '.permissions.ask | index("Bash(terraform apply *)") != null' "baseline asks on terraform apply"
assert_jq_true '.permissions.ask | index("Bash(kubectl delete *)") != null' "baseline asks on kubectl delete"

assert_jq_true_path "$STRICT" '.permissions.disableBypassPermissionsMode == "disable"' "strict disables permission bypass"
assert_jq_true_path "$STRICT" '(.permissions.deny | type) == "array" and (.permissions.ask | type) == "array"' "strict deny and ask are arrays"
assert_jq_true_path "$STRICT" '(.permissions.deny | length) > 0' "strict deny is populated"
assert_jq_true_path "$STRICT" '(.permissions.ask | length) > 0' "strict ask is populated"
assert_jq_true_path "$STRICT" '(.permissions.deny | length) == (.permissions.deny | unique | length)' "strict deny has no duplicates"
assert_jq_true_path "$STRICT" '(.permissions.ask | length) == (.permissions.ask | unique | length)' "strict ask has no duplicates"
assert_jq_true_path "$STRICT" '([.permissions.deny[], .permissions.ask[]] | length) == ([.permissions.deny[], .permissions.ask[]] | unique | length)' "strict deny and ask do not overlap"
assert_jq_true_path "$STRICT" '[.permissions.deny[], .permissions.ask[]] | all(test("^(Read|Bash)\\(.+\\)$"))' "strict permission rules use allowed format"
assert_jq_true_path "$STRICT" '.permissions.deny | index("Bash(terraform destroy *)") != null' "strict denies terraform destroy statically"
assert_jq_true_path "$STRICT" '.permissions.deny | index("Read(./.env)") != null' "strict still denies .env reads"
assert_jq_true_path "$STRICT" '.permissions.deny | index("Read(~/.ssh/**)") != null' "strict still denies ssh reads"
assert_jq_true_path "$STRICT" '.permissions.deny | index("Read(~/.aws/credentials)") != null' "strict still denies aws credential reads"
assert_jq_true_path "$STRICT" '.permissions.deny | index("Read(~/.kube/config)") != null' "strict still denies kube config reads"
assert_jq_true_path "$STRICT" '[.permissions.ask[]] | all(startswith("Read(") | not)' "strict never downgrades a credential read to ask"
assert_jq_true_path "$STRICT" '.permissions.ask | index("Bash(docker system prune *)") != null' "strict asks on docker system prune"
assert_jq_true_path "$STRICT" '.permissions.ask | index("Bash(psql *)") != null' "strict asks on psql"
assert_jq_true_path "$STRICT" '[.permissions.deny[], .permissions.ask[]] | index("Bash(*)") == null' "strict does not block whole Bash tool"
assert_jq_true_path "$STRICT" 'has("sandbox") | not' "strict does not enable sandbox"

assert_jq_true_path "$SANDBOX" '.sandbox.enabled == true' "sandbox overlay enables sandbox"
assert_jq_true_path "$SANDBOX" '.sandbox.failIfUnavailable == true' "sandbox overlay fails if unavailable"
assert_jq_true_path "$SANDBOX" '.sandbox.allowUnsandboxedCommands == false' "sandbox overlay blocks unsandboxed fallback"
assert_jq_true_path "$SANDBOX" '.sandbox.credentials.files | index({"path":"~/.ssh","mode":"deny"}) != null' "sandbox overlay denies ssh credential reads"
assert_jq_true_path "$SANDBOX" '.sandbox.credentials.files | index({"path":"~/.aws/credentials","mode":"deny"}) != null' "sandbox overlay denies aws credential file reads"
assert_jq_true_path "$SANDBOX" '.sandbox.credentials.files | index({"path":"~/.kube/config","mode":"deny"}) != null' "sandbox overlay denies kube config reads"
assert_jq_true_path "$SANDBOX" '.sandbox.credentials.envVars | index({"name":"AWS_SECRET_ACCESS_KEY","mode":"deny"}) != null' "sandbox overlay denies aws secret env"
assert_jq_true_path "$SANDBOX" '.sandbox.credentials.envVars | index({"name":"NPM_TOKEN","mode":"deny"}) != null' "sandbox overlay denies npm token env"
assert_jq_true_path "$SANDBOX" '.sandbox.credentials.envVars | index({"name":"PYPI_API_TOKEN","mode":"deny"}) != null' "sandbox overlay denies pypi token env"

assert_jq_true_path "$STRICT_POLICY" '.profile == "strict"' "strict policy identifies strict profile"
# Deprecated keys are gone from what the profiles write; the schema still
# accepts them so a policy written by an older version keeps validating.
assert_jq_true_path "$STRICT_POLICY" '(.commandGuard | has("parserUncertainty") | not)' "strict policy drops the deprecated parser uncertainty key"
assert_jq_true_path "$STRICT_POLICY" '(.commandGuard | has("infrastructureChecks") | not)' "strict policy drops the deprecated infrastructure checks key"
assert_jq_true_path "$STRICT_POLICY" '(.production | has("awsAccountIds") | not)' "strict policy drops the deprecated aws account ids key"
assert_jq_true_path "$POLICY_SCHEMA" '.properties.commandGuard.properties.parserUncertainty.deprecated == true' "schema still accepts the deprecated parser uncertainty key"
assert_jq_true_path "$POLICY_SCHEMA" '.properties.commandGuard.properties.infrastructureChecks.deprecated == true' "schema still accepts the deprecated infrastructure checks key"
assert_jq_true_path "$POLICY_SCHEMA" '.properties.production.properties.awsAccountIds.deprecated == true' "schema still accepts the deprecated aws account ids key"
assert_jq_true_path "$STRICT_POLICY" '.commandGuard.unknownEnvironment == "high-risk"' "strict policy treats unknown environment as high risk"
assert_jq_true_path "$STRICT_POLICY" '(.commandGuard | has("externalGuard") | not)' "strict policy does not enable external guard"
assert_jq_true_path "$STRICT_POLICY" '.database.destructiveOperations == "deny"' "strict policy denies destructive database operations"
assert_jq_true_path "$STRICT_POLICY" 'has("sandbox") | not' "strict policy does not enable sandbox"

assert_contains "$README" "baseline.settings.json" "README mentions baseline profile file"
assert_contains "$README" "strict.settings.json" "README mentions strict profile file"
assert_contains "$README" "| Behavior | Baseline | Strict |" "README contains baseline/strict comparison table"
assert_contains "$README" "not applied automatically" "README explains baseline is not applied automatically"
assert_contains "$README" "context-aware hooks" "README explains broad commands need context-aware hooks"
assert_contains "$README" "sandbox.settings.json" "README mentions sandbox overlay file"
assert_contains "$README" "/harden --baseline --sandbox" "README documents sandbox opt-in"

echo ""
echo "=== Results: $PASSED passed, $FAILED failed ==="

if [[ $FAILED -gt 0 ]]; then
  exit 1
fi
