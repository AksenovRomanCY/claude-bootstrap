# claude-bootstrap

Reusable preset for setting up Claude Code on any project.

## How It Works

```
install.sh → ~/.claude/              /bootstrap → .claude/rules/ (per project)
               ├── skills/              ├── common/        (always)
               ├── agents/              ├── typescript/    (if detected)
               ├── hooks/scripts/       ├── python/        (if detected)
               └── bootstrap-rules/     └── golang/        (if detected)
                   (library)
```

**Global** (`~/.claude/`): skills, agents, hooks — personal workflow, all projects.
**Per-project** (`.claude/rules/`): coding rules — committed to git, shared with team.

## What's Inside

```
claude-bootstrap/
├── .claude/
│   ├── rules/                         # Rules library (→ ~/.claude/bootstrap-rules/)
│   │   ├── common/                    # coding-style, testing, git-workflow, security,
│   │   │                              # error-handling, database, dependencies,
│   │   │                              # documentation, linting
│   │   ├── typescript/                # TypeScript conventions
│   │   ├── python/                    # Python conventions
│   │   └── golang/                    # Go conventions
│   ├── agents/                        # → ~/.claude/agents/
│   ├── skills/                        # → ~/.claude/skills/
│   ├── hooks/scripts/                 # → ~/.claude/hooks/scripts/
│   └── settings-hooks.json            # Hook config for settings.json
├── templates/claude-md/               # CLAUDE.md templates (manual copy)
│   ├── GUIDE.md                       # How to write a proper CLAUDE.md
│   ├── SKELETON.md                    # Minimal skeleton
│   ├── saas-nextjs.md                 # Next.js + Supabase + Stripe
│   ├── react-spa.md                   # React + Vite + TanStack Query
│   ├── nestjs.md                      # NestJS + Prisma + PostgreSQL
│   ├── express-prisma.md              # Express + Prisma + PostgreSQL
│   ├── vue-nuxt.md                    # Vue 3 + Nuxt 3 + Pinia
│   ├── go-microservice.md             # Go + gRPC + PostgreSQL
│   ├── django-api.md                  # Django + DRF + Celery
│   ├── fastapi.md                     # FastAPI + SQLAlchemy + Alembic
│   └── monorepo.md                    # Turborepo / pnpm workspaces
├── install.sh                         # Global installer
├── uninstall.sh                       # Clean removal
├── VERSION
├── CHANGELOG.md
└── LICENSE
```

## Quick Start

```bash
# 1. Install globally (once)
cd ~/Develop/claude-bootstrap
./install.sh

# 2. In any project — set up rules and CLAUDE.md
/bootstrap           # Detects stack, copies rules to .claude/rules/
/init                # Generates CLAUDE.md from project analysis
```

## Install Options

| Flag | Description |
|------|-------------|
| `--dry-run` | Preview changes without installing |
| `--force` | Skip confirmation prompt |
| `--skip-hooks` | Don't install hook scripts |
| `--skip-skills` | Don't install skills |
| `--skip-agents` | Don't install agents |
| `--skip-rules` | Don't install rules library |

## Commands

### Agents (isolated context, read-only)

| Command | What it does |
|---------|-------------|
| `/plan` | Implementation plan with phases, risks, tests |
| `/review` | Code review: bugs, security, style, performance |
| `/security` | Security audit: OWASP Top 10, secrets, injections |
| `/refactor` | Refactoring plan preserving behavior |

### Skills (in-session, can modify code)

| Command | What it does |
|---------|-------------|
| `/bootstrap` | Set up `.claude/rules/` — detect stack, copy rules |
| `/init` | Generate CLAUDE.md (`--check` to validate existing) |
| `/commit` | Stage, generate commit message, commit |
| `/pr` | Create PR (GitHub) or MR (GitLab) |
| `/verify` | Run lint + typecheck + tests, summarize |
| `/explain <file>` | Explain file: purpose, flow, dependencies |
| `/fix-build` | Diagnose and fix build/test errors |
| `/test <feature>` | TDD: RED → GREEN → IMPROVE cycle |
| `/changelog` | Generate changelog from git history |
| `/deps-check` | Audit outdated and vulnerable dependencies |
| `/doctor` | Health check: files, hooks, version, permissions |

### Hooks (automatic)

| Hook | Action |
|------|--------|
| block-large-files | Block files >800 lines (Write + Edit) |
| block-no-verify | Block `--no-verify` in git |
| warn-debug-code | Warn on console.log, print(), debugger, etc. |
| remind-compact | Remind /compact every 50 actions |

## Templates

| Template | File |
|----------|------|
| Minimal skeleton | `SKELETON.md` |
| Next.js SaaS | `saas-nextjs.md` |
| React SPA | `react-spa.md` |
| NestJS API | `nestjs.md` |
| Express + Prisma | `express-prisma.md` |
| Vue + Nuxt | `vue-nuxt.md` |
| Go Microservice | `go-microservice.md` |
| Django REST API | `django-api.md` |
| FastAPI | `fastapi.md` |
| Monorepo | `monorepo.md` |

## Customization

Edit files in `.claude/`, then `./install.sh` to apply.
