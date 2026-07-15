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
./install.sh --skip-hardening # Don't install hardening assets
./uninstall.sh                # Clean removal
```

</details>

---

## Quick Start

```bash
cd ~/your-project

/bootstrap                  # Detects stack, copies rules to .claude/rules/
/harden --baseline          # Applies baseline permissions and security policy
/harden --strict            # Applies stricter prompts and guard policy
/harden --baseline --sandbox # Opts in to Claude Code's built-in Bash sandbox
/harden --check             # Checks managed hardening drift without writing
/harden --remove            # Removes claude-bootstrap managed hardening
/doctor                     # Reports install, project, policy, and sandbox status
/init                       # Generates CLAUDE.md from project analysis
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

### Hardening Responsibility Model

| Layer | Responsibility |
| --- | --- |
| Rules | Behavioral guidance for Claude |
| Permissions | Native static `ask`/`deny` controls in Claude Code settings |
| Hooks | Project-specific contextual checks for commands and writes |
| Claude Code | Command matching, permissions runtime, hook runtime, and sandbox runtime |
| External guard | Optional future advanced analysis, not part of baseline or strict |

---

## Skills

| Command | Description | Auto |
| --- | --- | --- |
| `/bootstrap` | Set up `.claude/rules/` — detect stack, copy rules. `--update` to refresh | |
| `/harden` | Apply project hardening. `--baseline` by default, `--strict` for stricter prompts, `--sandbox` to opt in to Claude Code's built-in Bash sandbox, `--dry-run` to preview, `--check` to detect drift, `--remove` and `--remove-sandbox` to remove managed settings | |
| `/init` | Generate `CLAUDE.md` from project analysis. `--check` to validate existing | |
| `/commit` | Stage changes, generate conventional commit message, commit | |
| `/pr` | Create GitHub PR or GitLab MR with auto-generated description | |
| `/verify` | Run lint + typecheck + tests, report results | \* |
| `/explain <file>` | Explain file purpose, flow, and dependencies | \* |
| `/fix-build` | Diagnose and fix build/lint/test errors | |
| `/test <feature>` | TDD workflow: RED &rarr; GREEN &rarr; IMPROVE | |
| `/changelog` | Generate changelog from git history | |
| `/deps-check` | Audit outdated and vulnerable dependencies | \* |
| `/doctor` | Read-only health check: files, hooks, versions, hardening, permissions, and sandbox config status | \* |

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
| `command_guard` | Bash, Write, Edit | Unified guard for destructive commands, pre-write secrets, large files, and post-write warnings |
| `remind-compact` | Edit, Write | Remind to `/compact` every 50 actions |

---

## Rules

Installed to each project via `/bootstrap`. Common rules apply to all languages.
Rules guide Claude's behavior; they are not a technical security boundary.

| Rule | What it enforces |
| --- | --- |
| `coding-style.md` | Immutability, function size (&le;50 lines), naming, imports |
| `testing.md` | AAA pattern, 80%+ coverage for business logic, test independence |
| `git-workflow.md` | Conventional commits, branch naming, PR process |
| `destructive-operations.md` | Approval-first workflow for risky Git, filesystem, infra, database, publication, and secret operations |
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

## Hardening

`/harden` applies the baseline profile to the current project after showing a preview and asking for confirmation. `/harden --baseline` is explicit baseline mode, and `/harden --strict` applies the stricter profile for projects that can tolerate more permission prompts. Both profiles create or update `.claude/settings.json`, create `.claude/security-policy.json` when missing, write `.claude/harden-state.json`, and install `common/destructive-operations.md` without running `/bootstrap`.

`/harden --check` is read-only and reports drift between the current project and the managed profile. `/doctor` is also read-only; it reports installation health, active hooks, project policy, managed state, profile drift, legacy hooks, and sandbox configuration status.

`/harden --remove` rolls back only settings and policy defaults recorded in `.claude/harden-state.json`. User permission rules, hooks, custom policy changes, and `.claude/rules/` are preserved; modified managed values are reported as conflicts unless the user explicitly asks for `--force`. `/harden --remove-sandbox` removes only the managed sandbox overlay and leaves baseline or strict hardening in place.

`plugin/hardening/profiles/baseline.settings.json` is the static project settings template for baseline permissions. It defines targeted `permissions.deny` rules for sensitive files and clearly destructive commands, plus `permissions.ask` rules for publication, release, and infrastructure operations.

`plugin/hardening/profiles/strict.settings.json` builds on the same architecture with additional static prompts and deny rules. Unsupported or ambiguous shell syntax requires confirmation in every profile. `plugin/hardening/defaults/strict-policy.json` also treats unknown environment context as high risk for production-sensitive operations, lowers large-file thresholds, and denies high-confidence destructive database commands. External guard integrations are intentionally outside baseline and strict.

`/harden --baseline --sandbox` and `/harden --strict --sandbox` apply `plugin/hardening/profiles/sandbox.settings.json` as an explicit overlay for Claude Code's built-in Bash sandbox. The overlay writes only `.claude/settings.json` sandbox configuration, sets `failIfUnavailable`, disables unsandboxed fallback, and denies common credential files and environment variables to sandboxed commands. Native Windows is not supported by Claude Code's sandbox; use WSL2, a container, macOS, or Linux. `/harden --remove-sandbox` removes only sandbox entries managed by claude-bootstrap.

Sandbox may break commands that need credentials or external resources, including `gh`, `kubectl`, AWS CLI, package publication, and private registry access. Use Claude Code's `/sandbox` for dependency and runtime diagnostics.

| Behavior | Baseline | Strict |
| --- | --- | --- |
| Bypass permissions | Disabled | Disabled |
| Parser uncertainty | Warning context | Permission prompt |
| Infrastructure operations | Prompt or deny when production is detected | More prompts; unknown environment is high risk |
| Destructive database commands | No static profile decision | Deny high-confidence destructive CLI operations |
| Large files | Standard thresholds | Lower thresholds |
| External guard | Not enabled | Not enabled |
| Sandbox | Not enabled | Not enabled |

Hardening profiles are not applied automatically. Broad context-sensitive commands such as `rm`, `git reset`, `git clean`, and `sudo` are intentionally left out of static deny rules; they need context-aware hooks instead.

### Hardening Limitations

- Rules are behavioral guidance, not a security boundary.
- Project `.claude/settings.json` can be changed in a checkout; enterprise enforcement requires managed settings outside this repository.
- claude-bootstrap does not implement its own sandbox runtime; Claude Code owns command matching, permissions, hooks, and sandbox execution.
- Claude Code's built-in Bash sandbox is not supported on native Windows; use WSL2, a container, macOS, or Linux.
- `command_guard` is not a complete Bash AST security parser; embedded scripts such as downloaded shell scripts still need review.
- Hardening does not replace CI secret scanning or dependency/security review.
- Strict mode creates additional permission prompts by design.

### External Guard Follow-up

External guard integration is optional future work and is not required for baseline, strict, sandbox, `/doctor`, or CI. The current release does not call `dcg` or any other external analyzer.

Future policy support may use an explicit opt-in shape similar to:

```json
{
  "externalGuard": {
    "enabled": false,
    "command": "dcg",
    "timeoutMs": 1000
  }
}
```

That example is documentation only, not a supported schema field in this release. Any future integration must be disabled by default, enabled only explicitly, and independent of baseline, strict, and sandbox overlay behavior. A missing external executable must not affect current hardening profiles.

Future decision order must keep internal guard decisions first: internal high-confidence deny, internal context rules, optional external guard, then priority merge. External verdicts must never override an internal deny. Timeouts must be bounded, unknown output must not be treated as allow, stdout and stderr must be bounded and redacted, and secrets must not be written to debug logs.

---

## CLAUDE.md Templates

`/init` detects the project stack and uses a matching template as the starting structure, replacing placeholders with real project data.

| Template | Stack |
| --- | --- |
| [`SKELETON.md`](plugin/templates/SKELETON.md) | Minimal fill-in-the-blanks |
| [`saas-nextjs.md`](plugin/templates/saas-nextjs.md) | Next.js 15 + Supabase + Stripe |
| [`react-spa.md`](plugin/templates/react-spa.md) | React + Vite + TanStack Query |
| [`nestjs.md`](plugin/templates/nestjs.md) | NestJS + Prisma + PostgreSQL |
| [`express-prisma.md`](plugin/templates/express-prisma.md) | Express + Prisma + PostgreSQL |
| [`vue-nuxt.md`](plugin/templates/vue-nuxt.md) | Vue 3 + Nuxt 3 + Pinia |
| [`go-microservice.md`](plugin/templates/go-microservice.md) | Go + gRPC + PostgreSQL |
| [`django-api.md`](plugin/templates/django-api.md) | Django + DRF + Celery |
| [`fastapi.md`](plugin/templates/fastapi.md) | FastAPI + SQLAlchemy + Alembic |
| [`monorepo.md`](plugin/templates/monorepo.md) | Turborepo / pnpm workspaces |

See [`GUIDE.md`](plugin/templates/GUIDE.md) for how to write a CLAUDE.md from scratch.

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

Edit files in `plugin/`, then run `./install.sh` to apply. For plugin users — fork the repo, modify, and point your marketplace to your fork.

## License

[MIT](LICENSE)
