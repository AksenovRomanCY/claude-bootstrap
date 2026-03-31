#!/bin/bash
set -euo pipefail

# claude-bootstrap uninstaller
# Removes only files installed by install.sh, cleans hooks from settings.json

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE="$SCRIPT_DIR/.claude"
TARGET="$HOME/.claude"

DRY_RUN=false
FORCE=false

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

# --- Phase 1: Scan files to remove ---
FILES_TO_REMOVE=()

# Global components: agents, hooks, skills (direct path match)
for dir in agents hooks/scripts skills; do
  if [[ ! -d "$SOURCE/$dir" ]]; then continue; fi
  while IFS= read -r src_file; do
    rel="${src_file#$SOURCE/}"
    target_file="$TARGET/$rel"
    if [[ -f "$target_file" ]]; then
      FILES_TO_REMOVE+=("$rel")
    fi
  done < <(find "$SOURCE/$dir" -type f)
done

# Rules library: source is rules/, target is bootstrap-rules/
if [[ -d "$SOURCE/rules" ]]; then
  while IFS= read -r src_file; do
    rel="${src_file#$SOURCE/rules/}"
    target_file="$TARGET/bootstrap-rules/$rel"
    if [[ -f "$target_file" ]]; then
      FILES_TO_REMOVE+=("bootstrap-rules/$rel")
    fi
  done < <(find "$SOURCE/rules" -type f)
fi

# Check .bootstrap-version
if [[ -f "$TARGET/.bootstrap-version" ]]; then
  FILES_TO_REMOVE+=(".bootstrap-version")
fi

# --- Show what will be removed ---
echo "Files to remove:"

if [[ ${#FILES_TO_REMOVE[@]} -eq 0 ]]; then
  echo "  (nothing to remove — not installed?)"
  echo ""
  exit 0
fi

for rel in "${FILES_TO_REMOVE[@]}"; do
  echo "  [REMOVE] $rel"
done

echo ""
echo "Total: ${#FILES_TO_REMOVE[@]} files"
echo ""

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
SETTINGS_FILE="$TARGET/settings.json"
HOOKS_FILE="$SOURCE/settings-hooks.json"

if [[ -f "$SETTINGS_FILE" ]] && [[ -f "$HOOKS_FILE" ]] && jq -e '.hooks' "$SETTINGS_FILE" > /dev/null 2>&1; then
  BOOTSTRAP_COMMANDS=$(jq -r '[.hooks[][] | .hooks[]? | .command] | unique | .[]' "$HOOKS_FILE" 2>/dev/null)

  if [[ -n "$BOOTSTRAP_COMMANDS" ]]; then
    FILTER='.'
    while IFS= read -r cmd; do
      FILTER="$FILTER | .hooks.PreToolUse = [.hooks.PreToolUse[]? | .hooks = [.hooks[]? | select(.command != \"$cmd\")] | select(.hooks | length > 0)]"
      FILTER="$FILTER | .hooks.PostToolUse = [.hooks.PostToolUse[]? | .hooks = [.hooks[]? | select(.command != \"$cmd\")] | select(.hooks | length > 0)]"
    done <<< "$BOOTSTRAP_COMMANDS"

    FILTER="$FILTER | if .hooks.PreToolUse == [] then del(.hooks.PreToolUse) else . end"
    FILTER="$FILTER | if .hooks.PostToolUse == [] then del(.hooks.PostToolUse) else . end"
    FILTER="$FILTER | if .hooks == {} then del(.hooks) else . end"

    CLEANED=$(jq "$FILTER" "$SETTINGS_FILE")
    echo "$CLEANED" > "$SETTINGS_FILE"
    echo "[OK] Hooks removed from settings.json"
  fi
fi

# --- Phase 4: Remove empty directories ---
for dir in skills/commit skills/pr skills/verify skills/explain skills/fix-build \
           skills/init skills/test skills/changelog skills/deps-check skills/doctor \
           skills/bootstrap skills hooks/scripts hooks agents \
           bootstrap-rules/common bootstrap-rules/typescript \
           bootstrap-rules/python bootstrap-rules/golang bootstrap-rules; do
  rmdir "$TARGET/$dir" 2>/dev/null || true
done

echo ""
echo "Done. claude-bootstrap has been removed."
