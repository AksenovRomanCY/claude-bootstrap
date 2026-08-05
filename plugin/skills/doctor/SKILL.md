---
name: doctor
description: Health check for claude-bootstrap installation — verify files, hooks, versions, hardening, and permissions
disable-model-invocation: false
allowed-tools: Bash, Read, Glob
---

# Doctor

Run a read-only health check on the claude-bootstrap installation and the current project's hardening state.

## Process

1. **Check installed version**
   - Read `~/.claude/.bootstrap-version`
   - If missing: report `NOT INSTALLED`
   - If present: report version number
   - If the bootstrap repo path is known (via `$ARGUMENTS` or by checking common locations like `~/Develop/claude-bootstrap`), compare installed vs available `VERSION` file
   - Report: `CURRENT` / `OUTDATED` / `NOT INSTALLED`

2. **Check Python**
   - Run `python3 --version`
   - Report the version as `OK` when present
   - If Python is missing, report `MISSING` and continue every other check that does not require Python
   - Mark Python-dependent checks such as policy schema validation and profile drift as `SKIPPED` when Python is unavailable

3. **Check rules library** — verify files exist in `~/.claude/bootstrap-rules/`:
   - Common (10 files): `common/coding-style.md`, `common/database.md`, `common/dependencies.md`, `common/destructive-operations.md`, `common/documentation.md`, `common/error-handling.md`, `common/git-workflow.md`, `common/linting.md`, `common/security.md`, `common/testing.md`
   - Language-specific: `typescript/conventions.md`, `python/conventions.md`, `golang/conventions.md`
   - Report per file: `OK` / `MISSING`
   - Note: these are the source library, not active rules. Active rules live in each project's `.claude/rules/`

4. **Check agents** — verify files exist in `~/.claude/agents/`:
   - `planner.md`, `code-reviewer.md`, `security-reviewer.md`, `refactor.md`
   - Report per file: `OK` / `MISSING`

5. **Check skills** — verify `SKILL.md` exists in each `~/.claude/skills/` subdirectory:
   - `commit`, `pr`, `verify`, `explain`, `fix-build`, `init`, `test`, `changelog`, `deps-check`, `doctor`, `bootstrap`, `harden`
   - Specifically verify `/harden` exists at `~/.claude/skills/harden/SKILL.md`
   - Report per skill: `OK` / `MISSING`

6. **Check hooks and hardening assets** — verify files in `~/.claude/`:
   - Scripts: `hooks/scripts/secret_guard.py`, `hooks/scripts/large_file_policy.py`, `hooks/scripts/command_guard.py`, `hooks/scripts/post_write_warnings.py`, `hooks/scripts/block-large-files.sh` compatibility wrapper, `hooks/scripts/block-no-verify.sh`, `hooks/scripts/warn-debug-code.sh` compatibility wrapper, `hooks/scripts/warn-secrets.sh` compatibility wrapper, `hooks/scripts/remind-compact.sh`
   - Guard modules: `hooks/guard/__init__.py`, `hooks/guard/context.py`, `hooks/guard/decisions.py`, `hooks/guard/filesystem.py`, `hooks/guard/git.py`, `hooks/guard/infrastructure.py`, `hooks/guard/rules.py`, `hooks/guard/secrets.py`, `hooks/guard/shell.py`
   - Hardening profiles: `hardening/profiles/baseline.settings.json`, `hardening/profiles/strict.settings.json`, `hardening/profiles/sandbox.settings.json`
   - Hardening defaults: `hardening/defaults/baseline-policy.json`, `hardening/defaults/strict-policy.json`, `hardening/security-policy.schema.json`, `hardening/apply_profile.py`
   - Verify `.sh` scripts are executable (`test -x`)
   - Report per file: `OK` / `MISSING` / `NOT EXECUTABLE`

7. **Check settings.json hooks** — read `~/.claude/settings.json`:
   - Verify `.hooks` key exists
   - Verify `PreToolUse` has entries for `Write|Edit` and `Bash` matchers
   - Verify `PostToolUse` has entries for `Write|Edit` matcher
   - Verify expected unified `command_guard.py` entries and `remind-compact.sh`
   - Detect legacy active hook commands: `block-no-verify.sh`, `block-large-files.sh`, `warn-secrets.sh`, `warn-debug-code.sh`
   - Detect duplicate hook fingerprints using `(event, matcher, if, command, args)`
   - Report: `OK` / `MISSING` / `PARTIAL` / `LEGACY` / `DUPLICATE`

8. **Check project hardening files** — read the current project's `.claude/` files:
   - Project settings: report `.claude/settings.json` as `OK`, `MISSING`, or `INVALID JSON`
   - Project policy: report `.claude/security-policy.json` as `MISSING`, `INVALID JSON`, `SCHEMA INVALID`, `baseline`, `strict`, or `custom valid`
   - Managed state: report `.claude/harden-state.json` as `MISSING`, `INVALID JSON`, `INVALID MANAGER`, `INVALID VERSION`, `baseline`, `strict`, and whether `sandboxOverlay` is present
   - Permissions: report managed permission count from `.claude/harden-state.json` and whether expected baseline/strict permissions appear applied
   - Profile drift: if Python and `hardening/apply_profile.py` are available, run `python3 "$APPLY_PROFILE" --profile "$PROFILE" --check`; otherwise report `SKIPPED`
   - Never write files while checking drift

9. **Check project sandbox configuration** — read the current project's `.claude/settings.json` and `.claude/harden-state.json` if present:
   - Report whether `sandbox.enabled` is present and true
   - Report whether the current platform is supported by Claude Code's built-in Bash sandbox: macOS, Linux, or WSL2 supported; native Windows unsupported
   - If sandbox is enabled, verify `sandbox.failIfUnavailable` is true and `sandbox.allowUnsandboxedCommands` is false
   - Verify credential deny entries for `~/.ssh`, `~/.aws/credentials`, `~/.kube/config`, `AWS_SECRET_ACCESS_KEY`, `NPM_TOKEN`, and `PYPI_API_TOKEN`
   - Report dangerous exclusions or unsafe sandbox defaults when present
   - Report whether sandbox entries are managed by claude-bootstrap via `sandboxOverlay`, unmanaged/custom, missing, or partially drifted
   - Sandbox runtime: always report `use Claude Code /sandbox`; tell users to run Claude Code's `/sandbox` for dependency and runtime checks
   - Do not perform runtime sandbox diagnostics; do not inspect Seatbelt, bubblewrap, network behavior, process isolation, or platform internals

10. **Summary** — output a table:
   ```
   claude-bootstrap doctor
   ========================
   Version:    1.0.0 (current)
   Python:     3.12.2 — OK
   Rules lib:  10/10 common, 3/3 language — OK
   Templates:  11/11 — OK
   Agents:     4/4 — OK
   Skills:     12/12 — OK
   Hooks:      18/18 files, shell scripts executable — OK
   Settings:   hooks configured — OK
   Hardening:  profiles, policy schema, command guard — OK
   Policy:     baseline — OK
   State:      baseline, sandboxOverlay absent — OK
   Drift:      none — OK
   Legacy:     none — OK
   Sandbox:    disabled / enabled managed / custom / drifted
   Runtime:    use Claude Code /sandbox
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
- Never auto-fix missing hooks, invalid policy, profile drift, or sandbox conflicts
- If bootstrap repo path not available, skip version comparison and note it
- If Python is missing, continue checks and mark Python-dependent checks as `SKIPPED`
- If project policy is invalid, report it separately from missing policy and schema-invalid policy
- Use colors in output if terminal supports them

$ARGUMENTS
