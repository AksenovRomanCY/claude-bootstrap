#!/bin/bash
set -euo pipefail

# claude-bootstrap installer
# Copies .claude/ to ~/.claude/, merges hooks into settings.json

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE="$SCRIPT_DIR/.claude"
TARGET="$HOME/.claude"

echo "=== Claude Bootstrap Installer ==="
echo ""
echo "Source: $SOURCE"
echo "Target: $TARGET"
echo ""

# --- Copy rules, agents, hooks/scripts ---
for dir in rules agents hooks/scripts skills; do
  if [ -d "$SOURCE/$dir" ]; then
    mkdir -p "$TARGET/$dir"
    cp -r "$SOURCE/$dir/"* "$TARGET/$dir/"
    echo "[OK] $dir"
  fi
done

chmod +x "$TARGET/hooks/scripts/"*.sh 2>/dev/null || true

# --- Merge hooks into settings.json ---
SETTINGS_FILE="$TARGET/settings.json"
HOOKS_FILE="$SOURCE/settings-hooks.json"

if [ -f "$HOOKS_FILE" ]; then
  if [ ! -f "$SETTINGS_FILE" ]; then
    cp "$HOOKS_FILE" "$SETTINGS_FILE"
    echo "[OK] settings.json created with hooks"
  elif jq -e '.hooks' "$SETTINGS_FILE" > /dev/null 2>&1; then
    echo "[SKIP] settings.json already has hooks — merge manually from:"
    echo "       $SOURCE/settings-hooks.json"
  else
    MERGED=$(jq -s '.[0] * .[1]' "$SETTINGS_FILE" "$HOOKS_FILE")
    echo "$MERGED" > "$SETTINGS_FILE"
    echo "[OK] hooks merged into settings.json"
  fi
fi

echo ""
echo "Done. Next: copy a CLAUDE.md template to your project:"
echo "  cp $SCRIPT_DIR/templates/claude-md/SKELETON.md /your/project/CLAUDE.md"
