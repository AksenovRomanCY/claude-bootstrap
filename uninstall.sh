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
def should_remove($bootstrap):
  (.command // "") as $command |
  is_legacy_hook or (($bootstrap | index($command)) != null);
def clean_group($bootstrap):
  .hooks = ((.hooks // []) | map(select(should_remove($bootstrap) | not)))
  | select((.hooks | length) > 0);
def clean_hooks($bootstrap):
  (.hooks // {}) | with_entries(.value = ((.value // []) | map(clean_group($bootstrap)))) | with_entries(select((.value | length) > 0));
.[0] as $settings |
([.[1].hooks[][]?.hooks[]?.command] | unique) as $bootstrap |
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

# Future-compatible /harden cleanup before task 15 adds the source skill.
if [[ -d "$TARGET/skills/harden" ]]; then
  while IFS= read -r target_file; do
    rel="${target_file#"$TARGET"/}"
    FILES_TO_REMOVE+=("$rel")
  done < <(find "$TARGET/skills/harden" -type f)
fi

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

for rel in "${FILES_TO_REMOVE[@]}"; do
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
for rel in "${FILES_TO_REMOVE[@]}"; do
  rm "$TARGET/$rel"
done
echo "[OK] ${#FILES_TO_REMOVE[@]} files removed"

# --- Phase 3: Clean hooks from settings.json ---
if [[ "$SETTINGS_WILL_CHANGE" == true ]]; then
  cp "$SETTINGS_CANDIDATE" "$SETTINGS_FILE"
  echo "[OK] Hooks removed from settings.json"
fi

# --- Phase 4: Remove empty directories ---
for dir in skills/commit skills/pr skills/verify skills/explain skills/fix-build \
           skills/init skills/test skills/changelog skills/deps-check skills/doctor \
           skills/bootstrap skills/harden skills hooks/scripts hooks/guard hooks agents hardening \
           bootstrap-rules/common bootstrap-rules/typescript \
           bootstrap-rules/python bootstrap-rules/golang bootstrap-rules \
           bootstrap-templates; do
  rmdir "$TARGET/$dir" 2>/dev/null || true
done

echo ""
echo "Done. claude-bootstrap has been removed."
