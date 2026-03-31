# claude-bootstrap

Reusable preset for setting up Claude Code on any project.

## What's Inside

```
claude-bootstrap/
├── .claude/                           # Copied to ~/.claude/
│   ├── rules/
│   │   ├── common/                    # coding-style, testing, git-workflow, security,
│   │   │                              # error-handling, database, dependencies,
│   │   │                              # documentation, linting
│   │   ├── typescript/                # TypeScript conventions (*.ts, *.tsx)
│   │   ├── python/                    # Python conventions (*.py)
│   │   └── golang/                    # Go conventions (*.go)
│   ├── agents/
│   │   ├── planner.md                 # /plan
│   │   ├── code-reviewer.md           # /review
│   │   ├── security-reviewer.md       # /security
│   │   └── refactor.md                # /refactor
│   ├── skills/
│   │   ├── commit/                    # /commit
│   │   ├── pr/                        # /pr (GitHub + GitLab)
│   │   ├── verify/                    # /verify
│   │   ├── explain/                   # /explain <file>
│   │   ├── fix-build/                 # /fix-build
│   │   ├── init/                      # /init (generate CLAUDE.md)
│   │   ├── test/                      # /test <feature> (TDD)
│   │   ├── changelog/                 # /changelog
│   │   └── deps-check/               # /deps-check
│   ├── hooks/scripts/                 # Hook enforcement scripts
│   └── settings-hooks.json            # Hook config for settings.json
├── templates/claude-md/               # CLAUDE.md templates
│   ├── GUIDE.md                       # How to write a proper CLAUDE.md
│   ├── SKELETON.md                    # Minimal skeleton
│   ├── saas-nextjs.md                 # Next.js + Supabase + Stripe
│   ├── go-microservice.md             # Go + gRPC + PostgreSQL
│   ├── django-api.md                  # Django + DRF + Celery
│   ├── fastapi.md                     # FastAPI + SQLAlchemy + Alembic
│   └── react-spa.md                   # React + Vite + TanStack Query
├── install.sh
├── LICENSE
└── README.md
```

## Quick Start

```bash
cd ~/Develop/claude-bootstrap
./install.sh
```

Then in any project:
```bash
# Use a template:
cp ~/Develop/claude-bootstrap/templates/claude-md/SKELETON.md ./CLAUDE.md

# Or let Claude generate it:
/init
```

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
| `/commit` | Stage, generate commit message, commit |
| `/pr` | Create PR (GitHub) or MR (GitLab) |
| `/verify` | Run lint + typecheck + tests, summarize |
| `/explain <file>` | Explain file: purpose, flow, dependencies |
| `/fix-build` | Diagnose and fix build/test errors |
| `/init` | Generate CLAUDE.md by analyzing the project |
| `/test <feature>` | TDD: RED → GREEN → IMPROVE cycle |
| `/changelog` | Generate changelog from git history |
| `/deps-check` | Audit outdated and vulnerable dependencies |

### Hooks (automatic)
| Hook | Action |
|------|--------|
| block-large-files | Block files >800 lines (Write + Edit) |
| block-no-verify | Block `--no-verify` in git |
| warn-debug-code | Warn on console.log, print(), debugger, etc. |
| remind-compact | Remind /compact every 50 actions |

## Installing from Another Project

> Run `~/Develop/claude-bootstrap/install.sh`

Changes take effect in the **next session**.

## Customization

Edit files in `.claude/`, then `./install.sh` to apply.

## Inspiration

Based on ideas from [Everything Claude Code](https://github.com/affaan-m/everything-claude-code), adapted for a minimal, practical approach.
