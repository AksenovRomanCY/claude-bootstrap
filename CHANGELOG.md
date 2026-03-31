# Changelog

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
