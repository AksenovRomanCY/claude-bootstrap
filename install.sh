#!/bin/bash
set -euo pipefail

# claude-bootstrap installer
# Installs skills, hooks, rules, hardening to ~/.claude/ (global)
# Rules are stored in ~/.claude/bootstrap-rules/ as a library
# Use /bootstrap in a project to copy relevant rules to .claude/rules/

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE="$SCRIPT_DIR/plugin"
TEMPLATES_SOURCE="$SCRIPT_DIR/plugin/templates"
TARGET="$HOME/.claude"
VERSION_FILE="$SCRIPT_DIR/VERSION"
INSTALLED_VERSION_FILE="$TARGET/.bootstrap-version"

# Components retired in 1.4.0 — superseded by built-in Claude Code features.
# Listed here so an upgrade prunes stale copies from a previous install.
RETIRED_PATHS=(
  "agents/code-reviewer.md"
  "agents/security-reviewer.md"
  "agents/planner.md"
  "agents/refactor.md"
  "skills/explain"
  "skills/fix-build"
  "skills/init"
)
RETIRED_DIRS=("agents")

# Temporary files to remove however the script ends, including a failed `set -e`
# abort: the settings candidate used to leak on every path but one.
TMP_FILES=()
cleanup() {
  rm -f ${TMP_FILES[@]+"${TMP_FILES[@]}"}
}
trap cleanup EXIT

# --- Defaults ---
DRY_RUN=false
FORCE=false
SKIP_HOOKS=false
SKIP_SKILLS=false
SKIP_RULES=false
SKIP_HARDENING=false

# --- Help ---
show_help() {
  cat <<'HELP'
Usage: install.sh [OPTIONS]

Installs to ~/.claude/:
  skills/              Skills (/commit, /pr, /verify, /bootstrap, etc.)
  hooks/scripts/       Hook enforcement scripts
  hooks/guard/         Python hook guard modules
  hardening/           Hardening profiles, policies, and apply helpers
  bootstrap-rules/     Rules library (used by /bootstrap per-project)
  bootstrap-templates/ CLAUDE.md templates (used by /bootstrap-init)

Options:
  --dry-run        Preview changes without installing
  --force          Skip confirmation prompt, and install even if the backup fails
  --skip-hooks     Don't install hook scripts or merge settings.json
  --skip-skills    Don't install skills
  --skip-rules     Don't install rules library
  --skip-hardening Don't install hardening profiles, helpers, or the /harden skill
  --help           Show this help message

After install, run /bootstrap in any project to set up .claude/rules/

Examples:
  ./install.sh                  # Install everything
  ./install.sh --dry-run        # Preview without changes
  ./install.sh --force          # Install without confirmation
  ./install.sh --skip-hooks     # Everything except hooks
  ./install.sh --skip-hardening # Everything except hardening assets
HELP
}

# --- Argument parsing ---
while [[ $# -gt 0 ]]; do
  case $1 in
    --dry-run)     DRY_RUN=true ;;
    --force)       FORCE=true ;;
    --skip-hooks)  SKIP_HOOKS=true ;;
    --skip-skills) SKIP_SKILLS=true ;;
    --skip-rules)  SKIP_RULES=true ;;
    --skip-hardening) SKIP_HARDENING=true ;;
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

if [[ "$SKIP_HOOKS" == false ]] && ! command -v python3 > /dev/null 2>&1; then
  echo "Warning: python3 was not found; Python hooks will be installed but cannot run until python3 is available."
  echo ""
fi

# --- Component filter ---
should_install() {
  local component=$1
  case $component in
    hooks)  [[ "$SKIP_HOOKS" == false ]] ;;
    skills) [[ "$SKIP_SKILLS" == false ]] ;;
    rules)  [[ "$SKIP_RULES" == false ]] ;;
    hardening) [[ "$SKIP_HARDENING" == false ]] ;;
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

source_files() {
  local src_dir=$1
  find "$src_dir" -type f \
    ! -path '*/__pycache__/*' \
    ! -name '*.pyc'
}

# A component may exclude one relative subtree: the /harden skill lives under
# skills/ but belongs to the hardening component, so --skip-hardening must leave
# it out rather than install a skill whose assets are missing.
is_excluded() {
  local rel=$1 exclude=$2
  [[ -n "$exclude" ]] && [[ "$rel" == "$exclude" || "$rel" == "$exclude/"* ]]
}

diff_component() {
  local src_dir=$1 dst_dir=$2 exclude=${3:-}
  if [[ ! -d "$src_dir" ]]; then return; fi
  while IFS= read -r src_file; do
    local rel="${src_file#"$src_dir"/}"
    if is_excluded "$rel" "$exclude"; then continue; fi
    local dst_file="$dst_dir/$rel"
    local label="${dst_dir#"$TARGET"/}/$rel"
    show_file_status "$src_file" "$dst_file" "$label"
  done < <(source_files "$src_dir")
}

skills_exclude() {
  if [[ "$SKIP_HARDENING" == true ]]; then echo "harden"; fi
}

SETTINGS_FILE="$TARGET/settings.json"
HOOKS_FILE="$SOURCE/settings-hooks.json"
SETTINGS_CANDIDATE=""
SETTINGS_WILL_CHANGE=false
SETTINGS_EXISTS=false
SETTINGS_LEGACY_COUNT=0
SETTINGS_MISSING_COUNT=0
SETTINGS_CUSTOM_COUNT=0

settings_jq_program() {
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
def hook_key:
  [(.type // ""), (.command // ""), (.if // ""), (.args // [])] | @json;
def dedupe_hooks:
  reduce .[] as $hook ([];
    ($hook | hook_key) as $key |
    if ($hook.command // "") == "" then
      . + [$hook]
    elif (map(hook_key) | index($key)) then
      .
    else
      . + [$hook]
    end
  );
def clean_group:
  .hooks = ((.hooks // []) | map(select((is_legacy_hook or is_historical_scoped_guard) | not)) | dedupe_hooks)
  | select((.hooks | length) > 0);
def merge_equivalent_groups:
  reduce .[] as $group ([];
    (($group.matcher // "") | canonical_matcher) as $matcher |
    (map(((.matcher // "") | canonical_matcher) == $matcher) | index(true)) as $index |
    if $index == null then
      . + [$group]
    else
      .[$index].hooks = ((.[$index].hooks // []) + ($group.hooks // []) | dedupe_hooks)
    end
  );
def clean_hooks:
  (.hooks // {}) | with_entries(.value = ((.value // []) | map(clean_group) | merge_equivalent_groups));
def merge_hooks($desired):
  reduce (($desired.hooks // {}) | to_entries[]) as $event (.;
    .hooks[$event.key] = (
      (.hooks[$event.key] // []) as $existing |
      reduce (($event.value // [])[]) as $group ($existing;
        (($group.matcher // "") | canonical_matcher) as $matcher |
        (map(((.matcher // "") | canonical_matcher) == $matcher) | index(true)) as $index |
        if $index == null then
          . + [$group]
        else
          .[$index].hooks = (
            (.[$index].hooks // []) as $existing_hooks |
            $existing_hooks + (($group.hooks // []) | map(
              . as $hook |
              select(($existing_hooks | map(hook_key) | index(($hook | hook_key))) == null)
            ))
          )
        end
      )
    )
  );
.[0] as $current |
.[1] as $desired |
($current | .hooks = ($current | clean_hooks)) | merge_hooks($desired)
JQ
}

build_settings_candidate() {
  local output=$1
  if [[ ! -f "$HOOKS_FILE" ]]; then
    return 1
  fi

  if [[ -f "$SETTINGS_FILE" ]]; then
    jq -s "$(settings_jq_program)" "$SETTINGS_FILE" "$HOOKS_FILE" > "$output"
  else
    jq . "$HOOKS_FILE" > "$output"
  fi
}

json_equal() {
  local left=$1 right=$2
  [[ -f "$left" ]] || return 1
  [[ "$(jq -S -c . "$left")" == "$(jq -S -c . "$right")" ]]
}

settings_legacy_count() {
  if [[ ! -f "$SETTINGS_FILE" ]]; then
    echo 0
    return
  fi
  jq '[.hooks[][]?.hooks[]? | select((.command // "") | test("block-no-verify\\.sh|block-large-files\\.sh|warn-secrets\\.sh|warn-debug-code\\.sh"))] | length' "$SETTINGS_FILE"
}

settings_custom_count() {
  if [[ ! -f "$SETTINGS_FILE" || ! -f "$HOOKS_FILE" ]]; then
    echo 0
    return
  fi
  jq -s '
    def hook_key:
      [(.type // ""), (.command // ""), (.if // ""), (.args // [])] | @json;
    ([.[1].hooks[][]?.hooks[]? | hook_key] | unique) as $bootstrap |
    [
      .[0].hooks[][]?.hooks[]?
      | . as $hook
      | (.command // "") as $command
      | select(($command | test("block-no-verify\\.sh|block-large-files\\.sh|warn-secrets\\.sh|warn-debug-code\\.sh") | not)
          and (($bootstrap | index(($hook | hook_key))) == null))
    ] | length
  ' "$SETTINGS_FILE" "$HOOKS_FILE"
}

settings_fingerprint_count() {
  local file=$1
  if [[ ! -f "$file" ]]; then
    echo 0
    return
  fi
  jq '
    [
      .hooks
      | to_entries[]?
      | .key as $event
      | .value[]? as $group
      | ($group.matcher // "") as $matcher
      | $group.hooks[]?
      | "\($event)\t\($matcher)\t\(.if // "")\t\(.command // "")"
    ] | unique | length
  ' "$file"
}

echo "Changes:"

should_install "hooks" && diff_component "$SOURCE/hooks/scripts" "$TARGET/hooks/scripts"
should_install "hooks" && diff_component "$SOURCE/hooks/guard" "$TARGET/hooks/guard"
should_install "hardening" && diff_component "$SOURCE/hardening" "$TARGET/hardening"
should_install "skills" && diff_component "$SOURCE/skills" "$TARGET/skills" "$(skills_exclude)"
should_install "rules" && diff_component "$SOURCE/rules" "$TARGET/bootstrap-rules"
diff_component "$TEMPLATES_SOURCE" "$TARGET/bootstrap-templates"

for retired in "${RETIRED_PATHS[@]}"; do
  if [[ -e "$TARGET/$retired" ]]; then
    echo "  [RETIRED]    $retired"
  fi
done

if [[ $count_new -eq 0 && $count_modified -eq 0 ]]; then
  echo "  (no changes)"
fi

echo ""
echo "Summary: $count_new new, $count_modified modified, $count_unchanged unchanged"
echo ""

if should_install "hooks" && [[ -f "$HOOKS_FILE" ]]; then
  SETTINGS_CANDIDATE=$(mktemp)
  TMP_FILES+=("$SETTINGS_CANDIDATE")
  if ! build_settings_candidate "$SETTINGS_CANDIDATE" 2>/dev/null; then
    echo "Error: could not read $SETTINGS_FILE as JSON." >&2
    echo "Claude Code accepts comments and trailing commas there, but this installer needs strict JSON." >&2
    echo "Remove any // comments and trailing commas, or move the file aside, then run install.sh again." >&2
    exit 1
  fi
  SETTINGS_LEGACY_COUNT=$(settings_legacy_count)
  SETTINGS_CUSTOM_COUNT=$(settings_custom_count)
  if [[ -f "$SETTINGS_FILE" ]]; then
    SETTINGS_EXISTS=true
    if json_equal "$SETTINGS_FILE" "$SETTINGS_CANDIDATE"; then
      SETTINGS_WILL_CHANGE=false
    else
      SETTINGS_WILL_CHANGE=true
    fi
  else
    SETTINGS_WILL_CHANGE=true
  fi
  desired_count=$(settings_fingerprint_count "$HOOKS_FILE")
  current_count=$(settings_fingerprint_count "$SETTINGS_FILE")
  candidate_count=$(settings_fingerprint_count "$SETTINGS_CANDIDATE")
  SETTINGS_MISSING_COUNT=$((candidate_count - current_count + SETTINGS_LEGACY_COUNT))
  if [[ $SETTINGS_MISSING_COUNT -lt 0 ]]; then
    SETTINGS_MISSING_COUNT=0
  elif [[ $SETTINGS_MISSING_COUNT -gt $desired_count ]]; then
    SETTINGS_MISSING_COUNT=$desired_count
  fi

  echo "Settings migration:"
  echo "  legacy hooks removed: $SETTINGS_LEGACY_COUNT"
  echo "  new guard entries added: $SETTINGS_MISSING_COUNT"
  echo "  custom hooks preserved: $SETTINGS_CUSTOM_COUNT"
  if [[ "$SETTINGS_WILL_CHANGE" == true ]]; then
    echo "  settings diff: yes"
    if [[ -f "$SETTINGS_FILE" ]]; then
      diff -u "$SETTINGS_FILE" "$SETTINGS_CANDIDATE" || true
    else
      echo "  [NEW]        settings.json"
    fi
  else
    echo "  settings diff: no"
  fi
  echo ""
fi

# --- Dry run exit ---
if $DRY_RUN; then
  echo "(dry run — no changes made)"
  exit 0
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

# --- Backup ---
if [[ -d "$TARGET" ]] && [[ $count_modified -gt 0 || ( "$SETTINGS_EXISTS" == true && "$SETTINGS_WILL_CHANGE" == true ) || ( -f "$INSTALLED_VERSION_FILE" && "$INSTALLED_VERSION" != "$AVAILABLE_VERSION" ) ]]; then
  BACKUP_DIR="$TARGET/backups"
  mkdir -p "$BACKUP_DIR"
  BACKUP_FILE="$BACKUP_DIR/backup-$(date +%Y%m%d-%H%M%S).tar.gz"
  if backup_error=$(tar -czf "$BACKUP_FILE" \
      --exclude='backups' \
      -C "$(dirname "$TARGET")" \
      "$(basename "$TARGET")" 2>&1); then
    echo "[OK] Backup: $BACKUP_FILE"
  else
    # A half-written archive is worse than none: it looks like a rollback point.
    rm -f "$BACKUP_FILE"
    echo "[WARN] Backup failed: $BACKUP_FILE" >&2
    [[ -n "$backup_error" ]] && echo "$backup_error" >&2
    if ! $FORCE; then
      echo "Nothing was changed. Fix the backup location or re-run with --force to install anyway." >&2
      exit 1
    fi
    echo "[WARN] Continuing without a backup because --force was given." >&2
  fi

  # Keep only last 5 backups
  find "$BACKUP_DIR" -name 'backup-*.tar.gz' -type f | sort -r | tail -n +6 | xargs rm -f 2>/dev/null || true
fi

# --- Install ---
copy_dir() {
  local src=$1 dst=$2 label=$3 exclude=${4:-}
  if [[ -d "$src" ]]; then
    while IFS= read -r src_file; do
      local rel="${src_file#"$src"/}"
      if is_excluded "$rel" "$exclude"; then continue; fi
      local dst_file="$dst/$rel"
      mkdir -p "$(dirname "$dst_file")"
      cp "$src_file" "$dst_file"
    done < <(source_files "$src")
    echo "[OK] $label"
  fi
}

if should_install "hooks"; then
  copy_dir "$SOURCE/hooks/scripts" "$TARGET/hooks/scripts" "hooks/scripts"
  copy_dir "$SOURCE/hooks/guard" "$TARGET/hooks/guard" "hooks/guard"
  chmod +x "$TARGET/hooks/scripts/"*.sh 2>/dev/null || true
fi
should_install "hardening" && copy_dir "$SOURCE/hardening" "$TARGET/hardening" "hardening"
should_install "skills" && copy_dir "$SOURCE/skills" "$TARGET/skills" "skills" "$(skills_exclude)"
should_install "rules" && copy_dir "$SOURCE/rules" "$TARGET/bootstrap-rules" "bootstrap-rules (library)"
copy_dir "$TEMPLATES_SOURCE" "$TARGET/bootstrap-templates" "bootstrap-templates"

# --- Prune retired components ---
retired_removed=0
for retired in "${RETIRED_PATHS[@]}"; do
  if [[ -e "${TARGET:?}/${retired:?}" ]]; then
    rm -rf "${TARGET:?}/${retired:?}"
    retired_removed=$((retired_removed + 1))
  fi
done
for dir in "${RETIRED_DIRS[@]}"; do
  rmdir "$TARGET/$dir" 2>/dev/null || true
done
if [[ $retired_removed -gt 0 ]]; then
  echo "[OK] $retired_removed retired component(s) removed"
fi

# --- Merge hooks into settings.json ---
if should_install "hooks" && [[ -f "$HOOKS_FILE" ]]; then
  mkdir -p "$TARGET"
  if [[ "$SETTINGS_WILL_CHANGE" != true ]]; then
    echo "[OK] settings.json hooks already up to date"
  else
    # Copy beside the target, then rename: an interrupted `cp` onto settings.json
    # itself would leave the user with a truncated settings file.
    SETTINGS_STAGED="$SETTINGS_FILE.tmp.$$"
    TMP_FILES+=("$SETTINGS_STAGED")
    if [[ -f "$SETTINGS_FILE" ]]; then
      settings_message="[OK] hooks migrated in settings.json"
    else
      settings_message="[OK] settings.json created with hooks"
    fi
    cp "$SETTINGS_CANDIDATE" "$SETTINGS_STAGED"
    mv "$SETTINGS_STAGED" "$SETTINGS_FILE"
    echo "$settings_message"
  fi
fi

# --- Write version ---
mkdir -p "$TARGET"
if [[ "$INSTALLED_VERSION" == "$AVAILABLE_VERSION" && -f "$INSTALLED_VERSION_FILE" ]]; then
  echo "[OK] version $AVAILABLE_VERSION already recorded"
else
  cp "$VERSION_FILE" "$INSTALLED_VERSION_FILE"
  echo "[OK] version $AVAILABLE_VERSION recorded"
fi

echo ""
echo "Done. Next steps:"
echo "  1. Open any project and run /bootstrap to set up rules"
echo "  2. Run /bootstrap-init to generate CLAUDE.md"
