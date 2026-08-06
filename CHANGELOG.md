# Changelog

## Unreleased

### Added
- Hardening release documentation for `/bootstrap`, `/harden --baseline`, `/harden --strict`, `/harden --baseline --sandbox`, `/harden --check`, `/harden --remove`, and `/doctor`
- Destructive operations guidance rule and project hardening profiles for baseline, strict, and explicit sandbox overlay workflows
- Unified `command_guard` hook documentation for Bash, Write/Edit secret checks, large-file checks, and post-write warnings
- Installer migration, managed hardening state, rollback commands, `/doctor` hardening diagnostics, and CI matrix coverage for owned guard/profile logic
- External guard integration documented as optional follow-up work, not required for the hardening release
- Shell redirections are parsed into `CommandSegment.redirects`, so `2>&1` no longer splits a command in two and redirect targets stay out of the arguments rules judge
- `paths.safeRecursiveDelete` is enforced: recursive deletion of a project's declared build output needs no confirmation
- `commandGuard.terraformWorkspaceCommand` opts into `terraform workspace show` as a fallback when `.terraform/environment` is missing
- A `SessionStart` hook reports that the guards are inactive when `python3` is not on `PATH`, instead of failing open in silence
- Fixture suites for database commands, shell redirections, inline interpreter code, and process substitution

### Changed
- Baseline hardening now **prompts** instead of denying on credential file reads (`.env`, `.env.local`, `.env.production`, `~/.ssh/**`, `~/.aws/credentials`, `~/.kube/config`) — an outright deny blocked legitimate work such as checking which variables a project declares. `--strict` is unchanged and still denies all of them
- **Breaking:** skill `init` renamed to `bootstrap-init` — the old name collided with Claude Code's built-in `/init`, making which one ran ambiguous. Behavior is unchanged, including seeding `CLAUDE.md` from a matching stack template in `~/.claude/bootstrap-templates/`
- `rm -r` is judged without requiring `-f`: recursion is the danger, `-f` only suppresses the prompts `rm` would ask itself
- Recursive deletion of a system root (`/usr`, `/etc`, `/home`, `/Users`, …) is denied rather than confirmed, and `//` is compared as `/`
- Repository facts are read from git only when a rule needs them and are cached per directory, so `git log` runs no subprocess and `git -C other` is judged against the repository it names
- An Edit is reconstructed once per tool call and shared by the secret and large-file rules
- Subcommands are located past each tool's own global options, so `gh -R o/r repo delete` and `npm --prefix pkg publish` are recognised; `kubectl delete ns a b` checks every name, and an unknown `--opt=value` before a kubectl action no longer reports uncertainty
- `combine` keeps the reasons of the weaker decisions instead of dropping them
- `install.sh` and `uninstall.sh` prune retired components left over from a previous install
- The installer aborts instead of overwriting when the backup fails, writes `settings.json` through a rename, and cleans up its temporary files
- `--skip-hardening` also skips the `/harden` skill, which cannot work without the hardening assets
- Post-write warnings skip debug statements in generated files and documentation, and stay quiet about a secret in a gitignored file that PreToolUse already asked about
- CI runs Python 3.9, 3.10 and 3.12 on Linux and macOS. The native Windows leg is gone: the shipped hooks are wired as `python3`, which does not exist there, so the leg only proved that the tests could call `sys.executable`. Windows remains supported through WSL2
- Documented hardening responsibility boundaries: rules guide behavior, permissions provide native static controls, hooks add contextual checks, Claude Code owns command matching and sandbox runtime, and external guard integration remains optional future work
- Documented hardening limitations, including editable project settings, native Windows sandbox limits, non-goals around full Bash AST parsing, and the need for CI secret scanning

### Fixed
- Run one unconditional Bash command guard so absolute executable paths cannot bypass hook dispatch
- Parse background and stderr-pipe separators fail-closed, and block `git commit -n` and `git push --mirror` bypasses
- Scan reconstructed Edit results for secrets and reconcile same-profile hardening upgrades without stale managed settings
- Judge the command behind shell control syntax (`if`, `while`, `do`, `time`) instead of asking about the keyword
- Keep quoting, line continuations and heredoc bodies out of parsing, and close the wrapper and `eval` bypasses of guard rules
- Inspect `git -c` values instead of skipping them, and stop reading the hook process environment for production signals
- Report an unreadable `settings.json` instead of aborting on a bare `jq` parse error
- `/doctor` reports the real hook inventory
- `/harden` backs up user files on `--remove`/`--force` and resolves the profile from managed state
- Editor-added `$schema` no longer fails policy validation
- `TRUNCATE` is matched as a statement, not as the MySQL rounding function
- Large-file thresholds reject `true` and `0`, which configured a one-line or always-on threshold
- `remind-compact.sh` keeps its counter under `${XDG_RUNTIME_DIR:-$HOME/.cache}` rather than in world-writable `/tmp`
- Hook wrappers resolve their own directory with builtins, so an empty `PATH` no longer makes them print an error

### Removed
- **Breaking:** all four agents (`code-reviewer`, `security-reviewer`, `planner`, `refactor`) — superseded by built-in `/code-review`, `/review`, `/security-review`, `/simplify`, and the built-in `Plan` agent. `install.sh` no longer has `--skip-agents`
- **Breaking:** skills `explain` and `fix-build` — both duplicated default Claude Code behavior
- Dead code: the unused `PERMISSION_LISTS` grouping and the `dd of` spelling that `dd` does not accept

## [1.3.0] — 2026-03-31

### Added
- GitHub Actions CI: shellcheck, markdownlint, JSON validation, hook tests
- Smart hook merge in `install.sh` — adds missing hooks individually instead of skipping
- 14 tests for all 5 hook scripts (`tests/test-hooks.sh`)
- `.markdownlint.json` config

### Changed
- **`plugin/` is now the single source of truth** — all skills, agents, hooks, rules, and templates live only in `plugin/`. No more duplication with `.claude/`
- `install.sh` and `uninstall.sh` read from `plugin/` instead of `.claude/`
- Removed `build.sh` (no longer needed)

### Fixed
- `warn-secrets.sh` — grep crash when content starts with `-----` (private key detection)
- `warn-debug-code.sh` and `warn-secrets.sh` — use `printf '%s'` instead of `echo` for safe piping

## [1.2.0] — 2026-03-31

### Added
- **Plugin version** in `plugin/` — install via `/plugin marketplace add AksenovRomanCY/claude-bootstrap`
- **Marketplace manifest** (`.claude-plugin/marketplace.json`) for plugin distribution
- **Secret detection hook** (`warn-secrets`) — warns on hardcoded API keys, JWT tokens, private keys, passwords, GitHub/GitLab/Slack tokens
- Templates installed to `~/.claude/bootstrap-templates/` so `/init` works without the bootstrap repo
- `/bootstrap --update` — refresh project rules from updated library
- `/bootstrap` adds `.claude/settings.local.json` to `.gitignore`
- `/init` uses matching template as starting structure (e.g., NestJS project → `nestjs.md`)

### Changed
- `explain`, `verify`, `deps-check`, `doctor` — now auto-invocable by Claude (read-only, `disable-model-invocation: false`)
- `commit`, `pr`, `init`, `bootstrap`, `test`, `fix-build`, `changelog` — remain manual-only (side effects)

## [1.1.0] — 2026-03-31

### Added
- `/bootstrap` skill — detects project stack, copies relevant rules to `.claude/rules/`
- `/doctor` skill — health check for installation (files, hooks, versions)
- `/init --check` — validate existing CLAUDE.md against recommended structure
- Templates: nestjs, express-prisma, vue-nuxt, monorepo
- `uninstall.sh` — clean removal of all installed files
- `VERSION` file and changelog

### Changed
- **Rules are now per-project, not global** — `install.sh` stores rules in `~/.claude/bootstrap-rules/` as a library; use `/bootstrap` in each project to copy relevant rules to `.claude/rules/`
- `install.sh` — added backup, diff preview, `--dry-run`, `--force`, `--skip-*` flags
- Skills, agents, hooks remain global (`~/.claude/`)

## [1.0.0] — 2026-03-31

### Added
- Rules: 9 common (coding-style, testing, git-workflow, security, error-handling, database, dependencies, documentation, linting) + 3 language-specific (TypeScript, Python, Go)
- Agents: planner, code-reviewer, security-reviewer, refactor
- Skills: commit, pr, verify, explain, fix-build, init, test, changelog, deps-check
- Hooks: block-large-files, block-no-verify, warn-debug-code, remind-compact
- Templates: SKELETON, saas-nextjs, react-spa, fastapi, django-api, go-microservice
- install.sh with automatic hook merging into settings.json
- GUIDE.md for writing proper CLAUDE.md files
