# Changelog

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
