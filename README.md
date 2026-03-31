# claude-bootstrap

> Reusable preset for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) — rules, skills, agents, and hooks for any project.

## How It Works

```
install.sh                             In any project
    │                                      │
    ▼                                      ▼
~/.claude/ (global)                .claude/rules/ (per-project, in git)
  ├── skills/         ──────────►    ├── common/        ← always
  ├── agents/         /bootstrap     ├── typescript/    ← if detected
  ├── hooks/scripts/                 ├── python/        ← if detected
  ├── bootstrap-rules/               └── golang/        ← if detected
  └── bootstrap-templates/
```

**Global** — skills, agents, hooks. Personal workflow tools, available in all projects.
**Per-project** — coding rules. Committed to git, shared with team via `/bootstrap`.

---

## Quick Start

```bash
# 1. Clone and install (once)
git clone https://github.com/anthropics/claude-bootstrap.git ~/claude-bootstrap
cd ~/claude-bootstrap && ./install.sh

# 2. In any project
/bootstrap           # Detects stack, copies rules to .claude/rules/
/init                # Generates CLAUDE.md from project analysis
```

<details>
<summary><strong>Install options</strong></summary>

```bash
./install.sh --dry-run        # Preview changes without installing
./install.sh --force          # Skip confirmation prompt
./install.sh --skip-hooks     # Don't install hook scripts
./install.sh --skip-skills    # Don't install skills
./install.sh --skip-agents    # Don't install agents
./install.sh --skip-rules     # Don't install rules library
./uninstall.sh                # Clean removal
./uninstall.sh --dry-run      # Preview what would be removed
```

</details>

---

## Commands

### Skills

| Command | Description |
| --- | --- |
| `/bootstrap` | Set up `.claude/rules/` — detect stack, copy rules. `--update` to refresh |
| `/init` | Generate `CLAUDE.md` from project analysis. `--check` to validate existing |
| `/commit` | Stage changes, generate conventional commit message, commit |
| `/pr` | Create GitHub PR or GitLab MR with auto-generated description |
| `/verify` | Run lint + typecheck + tests, report results |
| `/explain <file>` | Explain file purpose, flow, and dependencies |
| `/fix-build` | Diagnose and fix build/lint/test errors |
| `/test <feature>` | TDD workflow: RED &rarr; GREEN &rarr; IMPROVE |
| `/changelog` | Generate changelog from git history |
| `/deps-check` | Audit outdated and vulnerable dependencies |
| `/doctor` | Health check: files, hooks, versions, permissions |

### Agents

| Command | Description |
| --- | --- |
| `/plan` | Implementation plan with phases, risks, and test strategy |
| `/review` | Code review: bugs, security, style, performance |
| `/security` | Security audit: OWASP Top 10, secrets, injections |
| `/refactor` | Refactoring plan that preserves behavior |

### Hooks

Hooks run automatically on every tool call — no manual invocation needed.

| Hook | Trigger | Action |
| --- | --- | --- |
| `block-large-files` | Write, Edit | Block files > 800 lines |
| `block-no-verify` | Bash | Block `--no-verify` in git commands |
| `warn-debug-code` | Edit, Write | Warn on `console.log`, `print()`, `debugger` |
| `warn-secrets` | Edit, Write | Warn on hardcoded API keys, tokens, passwords |
| `remind-compact` | Edit, Write | Remind to `/compact` every 50 actions |

---

## Rules

Installed to each project via `/bootstrap`. Common rules apply to all languages.

| Category | File | What it enforces |
| --- | --- | --- |
| Coding Style | `coding-style.md` | Immutability, function size, naming, imports |
| Testing | `testing.md` | AAA pattern, coverage targets, test independence |
| Git Workflow | `git-workflow.md` | Commit format, branch naming, PR process |
| Security | `security.md` | No hardcoded secrets, input validation, CSRF |
| Error Handling | `error-handling.md` | Custom errors, no silent catches, safe messages |
| Database | `database.md` | Parameterized queries, N+1 prevention, migrations |
| Dependencies | `dependencies.md` | When to add/avoid packages, audit, lockfiles |
| Documentation | `documentation.md` | Comment "why" not "what", API docs, ADRs |
| Linting | `linting.md` | Follow project linter, no suppression without reason |

**Language-specific** (loaded only for matching file types):

| Language | Key conventions |
| --- | --- |
| TypeScript | `strict: true`, no `any`, Zod validation, async/await |
| Python | Type hints, Pydantic, ruff + mypy, no `print()` in prod |
| Go | Return errors (no panic), context first, table-driven tests |

---

## CLAUDE.md Templates

Templates for `/init` to use as a starting structure. Real project data replaces all placeholders.

| Template | Stack |
| --- | --- |
| [`SKELETON.md`](templates/claude-md/SKELETON.md) | Minimal fill-in-the-blanks |
| [`saas-nextjs.md`](templates/claude-md/saas-nextjs.md) | Next.js 15 + Supabase + Stripe |
| [`react-spa.md`](templates/claude-md/react-spa.md) | React + Vite + TanStack Query |
| [`nestjs.md`](templates/claude-md/nestjs.md) | NestJS + Prisma + PostgreSQL |
| [`express-prisma.md`](templates/claude-md/express-prisma.md) | Express + Prisma + PostgreSQL |
| [`vue-nuxt.md`](templates/claude-md/vue-nuxt.md) | Vue 3 + Nuxt 3 + Pinia |
| [`go-microservice.md`](templates/claude-md/go-microservice.md) | Go + gRPC + PostgreSQL |
| [`django-api.md`](templates/claude-md/django-api.md) | Django + DRF + Celery |
| [`fastapi.md`](templates/claude-md/fastapi.md) | FastAPI + SQLAlchemy + Alembic |
| [`monorepo.md`](templates/claude-md/monorepo.md) | Turborepo / pnpm workspaces |

See [`GUIDE.md`](templates/claude-md/GUIDE.md) for how to write a CLAUDE.md from scratch.

---

## Updating

```bash
cd ~/claude-bootstrap
git pull
./install.sh          # Updates global tools

# Then in each project:
/bootstrap --update   # Refreshes rules from updated library
```

## Customization

Edit files in `.claude/`, then run `./install.sh` to apply.

## License

[MIT](LICENSE)
