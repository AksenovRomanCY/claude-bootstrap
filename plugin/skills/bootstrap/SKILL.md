---
name: bootstrap
description: Initialize a project with claude-bootstrap rules — detect stack, copy relevant rules to .claude/rules/, optionally generate CLAUDE.md
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Bash, Write
---

# Bootstrap Project

Set up `.claude/rules/` in the current project by detecting its stack and copying relevant rules from the bootstrap library (`~/.claude/bootstrap-rules/`).

## Process

1. **Verify library** — check `~/.claude/bootstrap-rules/` exists
   - If not: tell the user to run `install.sh` first and stop

2. **Detect stack** — read config files to identify languages:
   - `package.json` or `tsconfig.json` → **typescript**
   - `*.py`, `pyproject.toml`, `requirements.txt`, `setup.py` → **python**
   - `go.mod` → **golang**
   - Multiple languages in one project is normal (e.g., TypeScript + Python)

3. **Show plan** — before copying, show the user what will be installed:
   ```
   Detected stack: typescript, python

   Rules to install:
     common/         9 files (coding-style, testing, security, ...)
     typescript/     1 file  (conventions)
     python/         1 file  (conventions)

   Target: .claude/rules/
   ```
   Ask the user to confirm before proceeding.

4. **Copy rules** — from `~/.claude/bootstrap-rules/` to `./.claude/rules/`:
   - **Always** copy `common/` — these are universal (coding-style, testing, git-workflow, security, error-handling, database, dependencies, documentation, linting)
   - Copy language-specific directories only for detected languages
   - If `.claude/rules/` already has files, warn and ask before overwriting

5. **Ensure .gitignore** — check if `.gitignore` exists in the project root:
   - If `.gitignore` exists but does NOT contain `.claude/settings.local.json`:
     append the following lines and inform the user:
     ```
     # Claude Code local settings (personal, not shared)
     .claude/settings.local.json
     ```
   - If `.gitignore` already has the entry — skip silently
   - If no `.gitignore` exists — skip (don't create one just for this)

6. **Suggest next step** — after copying rules:
   - If `./CLAUDE.md` exists: suggest running `/init --check` to validate it
   - If no `./CLAUDE.md`: suggest running `/init` to generate one
   - Remind to commit `.claude/rules/` to git

## Update Mode (`--update`)

If `$ARGUMENTS` contains `--update`, skip stack detection and update existing rules:

1. **Read** `.claude/rules/` to find which language directories are present
2. **Compare** each file with `~/.claude/bootstrap-rules/` and show changes
3. **Copy** updated files from library, preserving the existing language selection
4. Do NOT add or remove language rules — only refresh what's already there
5. Show summary: "N files updated, M unchanged"

This is useful after running `git pull && ./install.sh` on the bootstrap repo to propagate rule changes to the project.

## Arguments

`$ARGUMENTS` may contain:
- Language names to force (e.g., `typescript python`) — skip auto-detection
- `--all` — install all language rules regardless of detection
- `--common-only` — install only common rules, skip language-specific
- `--update` — refresh existing rules without re-detecting stack

## Rules
- Never install rules without confirmation
- If `.claude/rules/` already exists with content, show diff of what will change
- Common rules are always included (they are language-agnostic)
- Don't modify existing files outside `.claude/rules/` (except .gitignore entry)
- Don't generate CLAUDE.md — that's the job of `/init`

$ARGUMENTS
