---
name: harden
description: Apply the claude-bootstrap baseline hardening profile to the current project
disable-model-invocation: true
allowed-tools: Bash, Read, Glob
---

# Harden Project

Apply claude-bootstrap baseline hardening to the current project.

## Supported Commands

- `/harden`
- `/harden --baseline`
- `/harden --dry-run`
- `/harden --check`
- `/harden --remove`

Default: `/harden` is the same as `/harden --baseline`.

## Process

1. **Parse arguments**
   - Treat no arguments as `--baseline`
   - Allow only `--baseline`, `--dry-run`, `--check`, `--remove`, and explicit user-requested `--force`
   - If another option is provided, explain that it is not supported yet and stop

2. **Find the project root**
   - Prefer `git rev-parse --show-toplevel`
   - If the command fails, use the current working directory
   - Run every project-modifying command from the resolved project root

3. **Find installed assets**
   - Prefer plugin assets when `$CLAUDE_PLUGIN_DIR` is set:
     - `$CLAUDE_PLUGIN_DIR/hardening/apply_profile.py`
     - `$CLAUDE_PLUGIN_DIR/rules/common/destructive-operations.md`
   - Otherwise use manual install assets:
     - `~/.claude/hardening/apply_profile.py`
     - `~/.claude/bootstrap-rules/common/destructive-operations.md`
   - If either file is missing, tell the user to install or update claude-bootstrap and stop

4. **Check Python**
   - Require `python3`
   - If it is missing, report the missing dependency and stop

5. **Preview the profile**
   - Run:
     ```bash
     cd "$PROJECT_ROOT" && python3 "$APPLY_PROFILE" --profile baseline --dry-run
     ```
   - Report the target files:
     - `.claude/settings.json`
     - `.claude/security-policy.json`
     - `.claude/harden-state.json`
     - `.claude/rules/common/destructive-operations.md`
   - Report whether each target will be created, updated, unchanged, or blocked by conflict
   - Show the settings and policy diff produced by `apply_profile.py`
   - For the rule file:
     - If missing, report it as new
     - If identical to the installed rule, report it as unchanged
     - If present and different, report a conflict and do not overwrite without explicit confirmation

6. **Dry-run mode**
   - If `$ARGUMENTS` contains `--dry-run`, stop after the preview
   - Do not write files

7. **Check mode**
   - If `$ARGUMENTS` contains `--check`, run:
     ```bash
     cd "$PROJECT_ROOT" && python3 "$APPLY_PROFILE" --profile baseline --check
     ```
   - Also check that `.claude/rules/common/destructive-operations.md` exists and matches the installed rule
   - Exit with a clear PASS/DRIFT summary
   - Do not write files

8. **Remove mode**
   - If `$ARGUMENTS` contains `--remove`, preview removal first:
     ```bash
     cd "$PROJECT_ROOT" && python3 "$APPLY_PROFILE" --profile baseline --remove --dry-run
     ```
   - Explain that removal only uses `.claude/harden-state.json`
   - Confirm that `.claude/rules/` is not removed
   - If conflicts are reported, stop and explain that `--force` is required for modified managed values
   - Ask for explicit confirmation before running:
     ```bash
     cd "$PROJECT_ROOT" && python3 "$APPLY_PROFILE" --profile baseline --remove
     ```
   - Use `--force` only when the user explicitly requested it
   - Summarize removed managed settings, policy removal, and state removal
   - Stop after remove mode

9. **Confirm**
   - Ask for explicit user confirmation before writing
   - Include the resolved project root and files that will change
   - If conflicts were reported, explain them and ask whether to proceed only for safe rule overwrite cases

10. **Apply**
    - Run:
      ```bash
      cd "$PROJECT_ROOT" && python3 "$APPLY_PROFILE" --profile baseline
      ```
    - Create `.claude/rules/common/`
    - Copy the installed `destructive-operations.md` rule into `.claude/rules/common/destructive-operations.md`
    - Do not run `/bootstrap`

11. **Summarize**
    - Report created/updated/unchanged files
    - Report any backup path printed by `apply_profile.py`
    - Suggest committing `.claude/settings.json`, `.claude/security-policy.json`, `.claude/harden-state.json`, and `.claude/rules/common/destructive-operations.md`

## Rules

- Never apply hardening without confirmation, except for `--dry-run` and `--check`
- Do not run `/bootstrap` automatically
- Do not overwrite a custom `.claude/security-policy.json`; `apply_profile.py` preserves existing valid policies
- Do not modify `.claude/settings.local.json`
- Do not enable sandbox settings in this task
- Do not require DCG or external guard tooling
- Do not use `--force` unless the user explicitly asks for a conflict override in a later workflow
- Do not remove `.claude/rules/` during `--remove`

$ARGUMENTS
