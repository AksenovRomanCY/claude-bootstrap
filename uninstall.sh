#!/bin/bash
set -euo pipefail

# claude-bootstrap uninstaller
# Removes only files installed by install.sh, cleans hooks from settings.json

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE="$SCRIPT_DIR/plugin"
TARGET="$HOME/.claude"

DRY_RUN=false
FORCE=false
SETTINGS_WILL_CHANGE=false
SETTINGS_CANDIDATE=""

# Temporary files to remove however the script ends, including a failed `set -e` abort.
TMP_FILES=()
cleanup() {
  rm -f ${TMP_FILES[@]+"${TMP_FILES[@]}"}
}
trap cleanup EXIT

while [[ $# -gt 0 ]]; do
  case $1 in
    --dry-run) DRY_RUN=true ;;
    --force)   FORCE=true ;;
    --help)
      echo "Usage: uninstall.sh [--dry-run] [--force]"
      echo "  --dry-run  Preview removal without deleting"
      echo "  --force    Skip confirmation prompt"
      exit 0 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
  shift
done

if ! command -v jq > /dev/null 2>&1; then
  echo "Error: jq is required but not installed"
  exit 1
fi

echo "=== Claude Bootstrap Uninstaller ==="
echo ""

SETTINGS_FILE="$TARGET/settings.json"
HOOKS_FILE="$SOURCE/settings-hooks.json"

settings_cleanup_jq_program() {
  cat <<'JQ'
def is_legacy_hook:
  (.command // "" | test("block-no-verify\\.sh|block-large-files\\.sh|warn-secrets\\.sh|warn-debug-code\\.sh"));
def canonical_matcher:
  split("|") | map(gsub("^\\s+|\\s+$"; "")) | sort | unique | join("|");
def historical_guard_conditions:
  [
    "Bash(git *)", "Bash(rm *)", "Bash(sudo *)", "Bash(env *)", "Bash(command *)", "Bash(nohup *)",
    "Bash(curl *)", "Bash(wget *)", "Bash(terraform *)", "Bash(kubectl *)", "Bash(helm *)", "Bash(docker *)",
    "Bash(npm *)", "Bash(pnpm *)", "Bash(yarn *)", "Bash(cargo *)", "Bash(twine *)", "Bash(gh *)",
    "Bash(psql *)", "Bash(mysql *)", "Bash(sqlite3 *)", "Bash(prisma *)", "Bash(alembic *)", "Bash(mkfs *)",
    "Bash(wipefs *)", "Bash(fdisk *)", "Bash(parted *)", "Bash(dd *)", "Bash(chmod *)", "Bash(chown *)"
  ];
def is_historical_scoped_guard:
  . as $hook |
  (($hook.command // "") == "python3 ~/.claude/hooks/scripts/command_guard.py")
  and (($hook.timeout // 0) == 30)
  and ((historical_guard_conditions | index($hook.if // "")) != null);
def hook_fingerprint($event; $matcher):
  [$event, ($matcher | canonical_matcher), (.type // ""), (.command // ""), (.if // ""), (.args // [])] | @json;
def should_remove($bootstrap; $event; $matcher):
  . as $hook |
  is_legacy_hook or is_historical_scoped_guard
  or (($bootstrap | index(($hook | hook_fingerprint($event; $matcher)))) != null);
def clean_group($bootstrap; $event):
  (.matcher // "") as $matcher |
  .hooks = ((.hooks // []) | map(select(should_remove($bootstrap; $event; $matcher) | not)))
  | select((.hooks | length) > 0);
def clean_hooks($bootstrap):
  (.hooks // {})
  | with_entries(.key as $event | .value = ((.value // []) | map(clean_group($bootstrap; $event))))
  | with_entries(select((.value | length) > 0));
.[0] as $settings |
([
  .[1].hooks
  | to_entries[]?
  | .key as $event
  | .value[]? as $group
  | ($group.matcher // "") as $matcher
  | $group.hooks[]?
  | hook_fingerprint($event; $matcher)
] | unique) as $bootstrap |
($settings | .hooks = ($settings | clean_hooks($bootstrap)))
| if .hooks == {} then del(.hooks) else . end
JQ
}

build_settings_cleanup_candidate() {
  local output=$1
  if [[ -f "$SETTINGS_FILE" && -f "$HOOKS_FILE" ]]; then
    jq -s "$(settings_cleanup_jq_program)" "$SETTINGS_FILE" "$HOOKS_FILE" > "$output"
  else
    return 1
  fi
}

json_equal() {
  local left=$1 right=$2
  [[ -f "$left" ]] || return 1
  [[ "$(jq -S -c . "$left")" == "$(jq -S -c . "$right")" ]]
}

# --- Phase 1: Scan files to remove ---
FILES_TO_REMOVE=()

# Global components: agents, hooks, skills (direct path match)
for dir in agents hooks/scripts hooks/guard hardening skills; do
  if [[ ! -d "$SOURCE/$dir" ]]; then continue; fi
  while IFS= read -r src_file; do
    rel="${src_file#"$SOURCE"/}"
    target_file="$TARGET/$rel"
    if [[ -f "$target_file" ]]; then
      FILES_TO_REMOVE+=("$rel")
    fi
  done < <(find "$SOURCE/$dir" -type f)
done

# Rules library: source is rules/, target is bootstrap-rules/
if [[ -d "$SOURCE/rules" ]]; then
  while IFS= read -r src_file; do
    rel="${src_file#"$SOURCE"/rules/}"
    target_file="$TARGET/bootstrap-rules/$rel"
    if [[ -f "$target_file" ]]; then
      FILES_TO_REMOVE+=("bootstrap-rules/$rel")
    fi
  done < <(find "$SOURCE/rules" -type f)
fi

# Templates: source is templates/claude-md/, target is bootstrap-templates/
TEMPLATES_SOURCE="$SCRIPT_DIR/plugin/templates"
if [[ -d "$TEMPLATES_SOURCE" ]]; then
  while IFS= read -r src_file; do
    rel="${src_file#"$TEMPLATES_SOURCE"/}"
    target_file="$TARGET/bootstrap-templates/$rel"
    if [[ -f "$target_file" ]]; then
      FILES_TO_REMOVE+=("bootstrap-templates/$rel")
    fi
  done < <(find "$TEMPLATES_SOURCE" -type f)
fi

# Check .bootstrap-version
if [[ -f "$TARGET/.bootstrap-version" ]]; then
  FILES_TO_REMOVE+=(".bootstrap-version")
fi

if [[ -f "$SETTINGS_FILE" ]] && [[ -f "$HOOKS_FILE" ]] && jq -e '.hooks' "$SETTINGS_FILE" > /dev/null 2>&1; then
  SETTINGS_CANDIDATE=$(mktemp)
  TMP_FILES+=("$SETTINGS_CANDIDATE")
  build_settings_cleanup_candidate "$SETTINGS_CANDIDATE"
  if json_equal "$SETTINGS_FILE" "$SETTINGS_CANDIDATE"; then
    SETTINGS_WILL_CHANGE=false
  else
    SETTINGS_WILL_CHANGE=true
  fi
fi

# --- Show what will be removed ---
echo "Files to remove:"

if [[ ${#FILES_TO_REMOVE[@]} -eq 0 ]]; then
  echo "  (nothing to remove — not installed?)"
fi

# `${ARR[@]+…}` because bash 3.2 (the system bash on macOS) treats an empty
# array as unset under `set -u`.
for rel in ${FILES_TO_REMOVE[@]+"${FILES_TO_REMOVE[@]}"}; do
  echo "  [REMOVE] $rel"
done

echo ""
echo "Total: ${#FILES_TO_REMOVE[@]} files"
if [[ "$SETTINGS_WILL_CHANGE" == true ]]; then
  echo "Settings cleanup: hooks will be removed from settings.json"
else
  echo "Settings cleanup: no changes"
fi
echo ""

if [[ ${#FILES_TO_REMOVE[@]} -eq 0 && "$SETTINGS_WILL_CHANGE" != true ]]; then
  exit 0
fi

# --- Dry run exit ---
if $DRY_RUN; then
  echo "(dry run — no changes made)"
  exit 0
fi

# --- Confirmation ---
if ! $FORCE; then
  printf "Proceed with uninstall? [y/N] "
  read -r answer
  if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
    echo "Aborted."
    exit 0
  fi
fi

# --- Phase 2: Remove files ---
for rel in ${FILES_TO_REMOVE[@]+"${FILES_TO_REMOVE[@]}"}; do
  rm "$TARGET/$rel"
done
echo "[OK] ${#FILES_TO_REMOVE[@]} files removed"

# --- Phase 3: Clean hooks from settings.json ---
if [[ "$SETTINGS_WILL_CHANGE" == true ]]; then
  # Stage beside the target and rename, so an interrupted copy cannot truncate
  # the user's settings.json.
  SETTINGS_STAGED="$SETTINGS_FILE.tmp.$$"
  TMP_FILES+=("$SETTINGS_STAGED")
  cp "$SETTINGS_CANDIDATE" "$SETTINGS_STAGED"
  mv "$SETTINGS_STAGED" "$SETTINGS_FILE"
  echo "[OK] Hooks removed from settings.json"
fi

# --- Phase 3b: Remove components retired in 1.4.0 (older installs) ---
for retired in agents/code-reviewer.md agents/security-reviewer.md \
               agents/planner.md agents/refactor.md \
               skills/explain skills/fix-build skills/init \
               hooks/scripts/block-no-verify.sh hooks/scripts/secret_guard.py; do
  rm -rf "${TARGET:?}/$retired" 2>/dev/null || true
done

# --- Phase 4: Remove empty directories ---
# Walked bottom-up over the installed subtrees rather than listed by name: a
# hardcoded list goes stale the moment a skill or a rules language is added, and
# it never covered the __pycache__ directories the Python hooks leave behind.
# rmdir only removes empty directories, so anything of the user's stays.
for dir in skills hooks hardening bootstrap-rules bootstrap-templates agents; do
  [[ -d "$TARGET/$dir" ]] || continue
  find "$TARGET/$dir" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
  find "$TARGET/$dir" -depth -type d -exec rmdir {} + 2>/dev/null || true
done

echo ""
echo "Done. claude-bootstrap has been removed."
