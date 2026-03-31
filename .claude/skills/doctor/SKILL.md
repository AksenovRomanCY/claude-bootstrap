---
name: doctor
description: Health check for claude-bootstrap installation — verify files, hooks, versions, and permissions
disable-model-invocation: true
allowed-tools: Bash, Read, Glob
---

# Doctor

Run a health check on the claude-bootstrap installation.

## Process

1. **Check installed version**
   - Read `~/.claude/.bootstrap-version`
   - If missing: report `NOT INSTALLED`
   - If present: report version number
   - If the bootstrap repo path is known (via `$ARGUMENTS` or by checking common locations like `~/Develop/claude-bootstrap`), compare installed vs available `VERSION` file
   - Report: `CURRENT` / `OUTDATED` / `NOT INSTALLED`

2. **Check rules library** — verify files exist in `~/.claude/bootstrap-rules/`:
   - Common (9 files): `common/coding-style.md`, `common/database.md`, `common/dependencies.md`, `common/documentation.md`, `common/error-handling.md`, `common/git-workflow.md`, `common/linting.md`, `common/security.md`, `common/testing.md`
   - Language-specific: `typescript/conventions.md`, `python/conventions.md`, `golang/conventions.md`
   - Report per file: `OK` / `MISSING`
   - Note: these are the source library, not active rules. Active rules live in each project's `.claude/rules/`

3. **Check agents** — verify files exist in `~/.claude/agents/`:
   - `planner.md`, `code-reviewer.md`, `security-reviewer.md`, `refactor.md`
   - Report per file: `OK` / `MISSING`

4. **Check skills** — verify `SKILL.md` exists in each `~/.claude/skills/` subdirectory:
   - `commit`, `pr`, `verify`, `explain`, `fix-build`, `init`, `test`, `changelog`, `deps-check`, `doctor`, `bootstrap`
   - Report per skill: `OK` / `MISSING`

5. **Check hooks** — verify scripts in `~/.claude/hooks/scripts/`:
   - Files: `block-large-files.sh`, `block-no-verify.sh`, `warn-debug-code.sh`, `remind-compact.sh`
   - Verify each is executable (`test -x`)
   - Report per script: `OK` / `MISSING` / `NOT EXECUTABLE`

6. **Check settings.json hooks** — read `~/.claude/settings.json`:
   - Verify `.hooks` key exists
   - Verify `PreToolUse` has entries for `Write|Edit` and `Bash` matchers
   - Verify `PostToolUse` has entries for `Edit|Write` matcher
   - Report: `OK` / `MISSING` / `PARTIAL`

7. **Summary** — output a table:
   ```
   claude-bootstrap doctor
   ========================
   Version:    1.0.0 (current)
   Rules lib:  9/9 common, 3/3 language — OK
   Agents:     4/4 — OK
   Skills:     11/11 — OK
   Hooks:      4/4 scripts, all executable — OK
   Settings:   hooks configured — OK
   ========================
   Overall: OK
   ```

   If issues found:
   ```
   Overall: 3 issues found
   ```

## Rules
- Read-only — never modify any files
- Report ALL issues, don't stop at the first one
- If bootstrap repo path not available, skip version comparison and note it
- Use colors in output if terminal supports them

$ARGUMENTS
