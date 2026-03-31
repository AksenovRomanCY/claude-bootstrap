#!/bin/bash
set -euo pipefail

# claude-bootstrap installer
# Installs skills, agents, hooks to ~/.claude/ (global)
# Rules are stored in ~/.claude/bootstrap-rules/ as a library
# Use /bootstrap in a project to copy relevant rules to .claude/rules/

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE="$SCRIPT_DIR/.claude"
TEMPLATES_SOURCE="$SCRIPT_DIR/templates/claude-md"
TARGET="$HOME/.claude"
VERSION_FILE="$SCRIPT_DIR/VERSION"
INSTALLED_VERSION_FILE="$TARGET/.bootstrap-version"

# --- Defaults ---
DRY_RUN=false
FORCE=false
SKIP_HOOKS=false
SKIP_SKILLS=false
SKIP_AGENTS=false
SKIP_RULES=false

# --- Help ---
show_help() {
  cat <<'HELP'
Usage: install.sh [OPTIONS]

Installs to ~/.claude/:
  skills/              Skills (/commit, /pr, /verify, /bootstrap, etc.)
  agents/              Agents (/plan, /review, /security, /refactor)
  hooks/scripts/       Hook enforcement scripts
  bootstrap-rules/     Rules library (used by /bootstrap per-project)
  bootstrap-templates/ CLAUDE.md templates (used by /init)

Options:
  --dry-run        Preview changes without installing
  --force          Skip confirmation prompt
  --skip-hooks     Don't install hook scripts or merge settings.json
  --skip-skills    Don't install skills
  --skip-agents    Don't install agents
  --skip-rules     Don't install rules library
  --help           Show this help message

After install, run /bootstrap in any project to set up .claude/rules/

Examples:
  ./install.sh                  # Install everything
  ./install.sh --dry-run        # Preview without changes
  ./install.sh --force          # Install without confirmation
  ./install.sh --skip-hooks     # Everything except hooks
HELP
}

# --- Argument parsing ---
while [[ $# -gt 0 ]]; do
  case $1 in
    --dry-run)     DRY_RUN=true ;;
    --force)       FORCE=true ;;
    --skip-hooks)  SKIP_HOOKS=true ;;
    --skip-skills) SKIP_SKILLS=true ;;
    --skip-agents) SKIP_AGENTS=true ;;
    --skip-rules)  SKIP_RULES=true ;;
    --help)        show_help; exit 0 ;;
    *) echo "Unknown option: $1 (use --help for usage)"; exit 1 ;;
  esac
  shift
done

# --- Check jq ---
if ! command -v jq > /dev/null 2>&1; then
  echo "Error: jq is required but not installed"
  echo "  brew install jq  (macOS)"
  echo "  apt install jq   (Ubuntu/Debian)"
  exit 1
fi

# --- Component filter ---
should_install() {
  local component=$1
  case $component in
    hooks)  [[ "$SKIP_HOOKS" == false ]] ;;
    skills) [[ "$SKIP_SKILLS" == false ]] ;;
    agents) [[ "$SKIP_AGENTS" == false ]] ;;
    rules)  [[ "$SKIP_RULES" == false ]] ;;
    *)      return 0 ;;
  esac
}

# --- Version info ---
AVAILABLE_VERSION=$(cat "$VERSION_FILE" 2>/dev/null | tr -d '[:space:]' || echo "unknown")
INSTALLED_VERSION=$(cat "$INSTALLED_VERSION_FILE" 2>/dev/null | tr -d '[:space:]' || echo "none")

echo "=== Claude Bootstrap Installer ==="
echo ""
echo "Source: $SOURCE"
echo "Target: $TARGET"
echo ""

if [[ "$INSTALLED_VERSION" == "none" ]]; then
  echo "Install: v$AVAILABLE_VERSION (fresh)"
elif [[ "$INSTALLED_VERSION" == "$AVAILABLE_VERSION" ]]; then
  echo "Version: v$AVAILABLE_VERSION (reinstall)"
else
  echo "Update:  v$INSTALLED_VERSION → v$AVAILABLE_VERSION"
fi
echo ""

# --- Diff preview ---
count_new=0
count_modified=0
count_unchanged=0

show_file_status() {
  local src=$1 dst=$2 label=$3
  if [[ ! -f "$dst" ]]; then
    echo "  [NEW]        $label"
    ((count_new++)) || true
  elif ! diff -q "$src" "$dst" > /dev/null 2>&1; then
    echo "  [MODIFIED]   $label"
    ((count_modified++)) || true
  else
    ((count_unchanged++)) || true
  fi
}

diff_component() {
  local src_dir=$1 dst_dir=$2
  if [[ ! -d "$src_dir" ]]; then return; fi
  while IFS= read -r src_file; do
    local rel="${src_file#$src_dir/}"
    local dst_file="$dst_dir/$rel"
    local label="${dst_dir#$TARGET/}/$rel"
    show_file_status "$src_file" "$dst_file" "$label"
  done < <(find "$src_dir" -type f)
}

echo "Changes:"

should_install "agents" && diff_component "$SOURCE/agents" "$TARGET/agents"
should_install "hooks" && diff_component "$SOURCE/hooks/scripts" "$TARGET/hooks/scripts"
should_install "skills" && diff_component "$SOURCE/skills" "$TARGET/skills"
should_install "rules" && diff_component "$SOURCE/rules" "$TARGET/bootstrap-rules"
diff_component "$TEMPLATES_SOURCE" "$TARGET/bootstrap-templates"

if [[ $count_new -eq 0 && $count_modified -eq 0 ]]; then
  echo "  (no changes)"
fi

echo ""
echo "Summary: $count_new new, $count_modified modified, $count_unchanged unchanged"
echo ""

# --- Dry run exit ---
if $DRY_RUN; then
  echo "(dry run — no changes made)"
  exit 0
fi

# --- Backup ---
if [[ -d "$TARGET" ]] && [[ $count_modified -gt 0 || -f "$INSTALLED_VERSION_FILE" ]]; then
  BACKUP_DIR="$TARGET/backups"
  mkdir -p "$BACKUP_DIR"
  BACKUP_FILE="$BACKUP_DIR/backup-$(date +%Y%m%d-%H%M%S).tar.gz"
  tar -czf "$BACKUP_FILE" \
    --exclude='backups' \
    -C "$(dirname "$TARGET")" \
    "$(basename "$TARGET")" 2>/dev/null || true
  echo "[OK] Backup: $BACKUP_FILE"

  # Keep only last 5 backups
  ls -t "$BACKUP_DIR"/backup-*.tar.gz 2>/dev/null | tail -n +6 | xargs rm -f 2>/dev/null || true
fi

# --- Confirmation ---
if ! $FORCE; then
  printf "Proceed with installation? [y/N] "
  read -r answer
  if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
    echo "Aborted."
    exit 0
  fi
fi

# --- Install ---
copy_dir() {
  local src=$1 dst=$2 label=$3
  if [[ -d "$src" ]]; then
    mkdir -p "$dst"
    cp -r "$src/"* "$dst/"
    echo "[OK] $label"
  fi
}

should_install "agents" && copy_dir "$SOURCE/agents" "$TARGET/agents" "agents"
if should_install "hooks"; then
  copy_dir "$SOURCE/hooks/scripts" "$TARGET/hooks/scripts" "hooks/scripts"
  chmod +x "$TARGET/hooks/scripts/"*.sh 2>/dev/null || true
fi
should_install "skills" && copy_dir "$SOURCE/skills" "$TARGET/skills" "skills"
should_install "rules" && copy_dir "$SOURCE/rules" "$TARGET/bootstrap-rules" "bootstrap-rules (library)"
copy_dir "$TEMPLATES_SOURCE" "$TARGET/bootstrap-templates" "bootstrap-templates"

# --- Merge hooks into settings.json ---
SETTINGS_FILE="$TARGET/settings.json"
HOOKS_FILE="$SOURCE/settings-hooks.json"

if should_install "hooks" && [[ -f "$HOOKS_FILE" ]]; then
  if [[ ! -f "$SETTINGS_FILE" ]]; then
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

# --- Write version ---
cp "$VERSION_FILE" "$INSTALLED_VERSION_FILE"
echo "[OK] version $AVAILABLE_VERSION recorded"

echo ""
echo "Done. Next steps:"
echo "  1. Open any project and run /bootstrap to set up rules"
echo "  2. Run /init to generate CLAUDE.md"
