# claude-bootstrap

> Reusable preset for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) — rules, skills, agents, and hooks for any project.

## Installation

### Option A — Plugin (recommended)

```
/plugin marketplace add AksenovRomanCY/claude-bootstrap
/plugin install claude-bootstrap@claude-bootstrap
```

Done. Skills, agents, and hooks are available immediately.

### Option B — Manual

```bash
git clone https://github.com/AksenovRomanCY/claude-bootstrap.git ~/claude-bootstrap
cd ~/claude-bootstrap && ./install.sh
```

<details>
<summary>Install options</summary>

```bash
./install.sh --dry-run        # Preview changes
./install.sh --force          # Skip confirmation
./install.sh --skip-hooks     # Don't install hooks
./install.sh --skip-skills    # Don't install skills
./install.sh --skip-agents    # Don't install agents
./install.sh --skip-rules     # Don't install rules library
./uninstall.sh                # Clean removal
```

</details>

---

## Quick Start

```bash
cd ~/your-project

/bootstrap           # Detects stack, copies rules to .claude/rules/
/init                # Generates CLAUDE.md from project analysis
```

> **Plugin users:** commands are namespaced — `/claude-bootstrap:bootstrap`, `/claude-bootstrap:init`, etc.

---

## How It Works

```
Plugin or install.sh               In any project
        │                                │
        ▼                                ▼
  skills, agents, hooks          .claude/rules/ (in git)
  (global, all projects)           ├── common/
                                   ├── typescript/
  rules & templates                ├── python/
  (library for /bootstrap)         └── golang/
```

**Global** — skills, agents, hooks. Personal workflow tools, available everywhere.
**Per-project** — coding rules. Copied by `/bootstrap`, committed to git, shared with team.

---

## Skills

| Command | Description | Auto |
| --- | --- | --- |
| `/bootstrap` | Set up `.claude/rules/` — detect stack, copy rules. `--update` to refresh | |
| `/init` | Generate `CLAUDE.md` from project analysis. `--check` to validate existing | |
| `/commit` | Stage changes, generate conventional commit message, commit | |
| `/pr` | Create GitHub PR or GitLab MR with auto-generated description | |
| `/verify` | Run lint + typecheck + tests, report results | \* |
| `/explain <file>` | Explain file purpose, flow, and dependencies | \* |
| `/fix-build` | Diagnose and fix build/lint/test errors | |
| `/test <feature>` | TDD workflow: RED &rarr; GREEN &rarr; IMPROVE | |
| `/changelog` | Generate changelog from git history | |
| `/deps-check` | Audit outdated and vulnerable dependencies | \* |
| `/doctor` | Health check: files, hooks, versions, permissions | \* |

\* **Auto** — Claude can invoke these automatically when relevant (read-only, no side effects).

## Agents

Claude automatically delegates to these when the task matches.

| Agent | What it does |
| --- | --- |
| `/plan` | Implementation plan with phases, risks, and test strategy |
| `/review` | Code review: bugs, security, style, performance |
| `/security` | Security audit: OWASP Top 10, secrets, injections |
| `/refactor` | Refactoring plan that preserves behavior |

## Hooks

Run automatically — no manual invocation needed.

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

| Rule | What it enforces |
| --- | --- |
| `coding-style.md` | Immutability, function size (&le;50 lines), naming, imports |
| `testing.md` | AAA pattern, 80%+ coverage for business logic, test independence |
| `git-workflow.md` | Conventional commits, branch naming, PR process |
| `security.md` | No hardcoded secrets, input validation, CSRF, rate limiting |
| `error-handling.md` | Custom errors, no silent catches, safe user messages |
| `database.md` | Parameterized queries, N+1 prevention, migrations in VCS |
| `dependencies.md` | When to add/avoid packages, audit, lockfiles |
| `documentation.md` | Comment "why" not "what", API docs, no obvious comments |
| `linting.md` | Follow project linter config, no suppression without reason |

**Language-specific** (loaded only for matching file types via `paths:` frontmatter):

| Language | Key conventions |
| --- | --- |
| TypeScript | `strict: true`, no `any`, Zod validation, async/await, Server Components by default |
| Python | Type hints, Pydantic, ruff + mypy, `pathlib` over `os.path`, no `print()` |
| Go | Return errors (no panic), `context.Context` first, table-driven tests, `slog` logging |

---

## CLAUDE.md Templates

`/init` detects the project stack and uses a matching template as the starting structure, replacing placeholders with real project data.

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

**Plugin:**
Updates automatically when a new version is published.

**Manual install:**
```bash
cd ~/claude-bootstrap
git pull
./install.sh

# Then in each project:
/bootstrap --update
```

## Customization

Edit files in `.claude/`, then run `./install.sh` to apply. For plugin users — fork the repo, modify, and point your marketplace to your fork.

## License

[MIT](LICENSE)
