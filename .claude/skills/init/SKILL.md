---
name: init
description: Generate a CLAUDE.md for the current project by analyzing its structure, dependencies, and patterns
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Bash, Write
---

# Init CLAUDE.md

Generate a project-specific CLAUDE.md by analyzing the current codebase.

## Process

1. **Detect stack** — read config files to identify:
   - Language and version: `package.json`, `go.mod`, `pyproject.toml`, `Cargo.toml`, `Gemfile`
   - Framework: look for Next.js, Django, FastAPI, Gin, Rails, etc. in dependencies
   - Database: check for ORM configs, connection strings, migration dirs
   - Testing: jest, pytest, go test, vitest — what's configured
   - Linting: eslint, ruff, golangci-lint — what's in config

2. **Find matching template** — check `~/.claude/bootstrap-rules/../templates/claude-md/` for a template that matches the detected stack:
   - Next.js + Supabase → `saas-nextjs.md`
   - React + Vite → `react-spa.md`
   - NestJS → `nestjs.md`
   - Express + Prisma → `express-prisma.md`
   - Vue / Nuxt → `vue-nuxt.md`
   - Go + gRPC → `go-microservice.md`
   - Django → `django-api.md`
   - FastAPI → `fastapi.md`
   - Turborepo / Nx / pnpm workspaces → `monorepo.md`
   - No match → use `SKELETON.md`
   - If a template is found, use it as a **starting structure** — keep the section headings, rules, and patterns that apply, but **replace all placeholder content** with real data from the project (steps 3-6)

3. **Map structure** — scan top-level directories and key files:
   - `src/`, `app/`, `internal/`, `cmd/`, `lib/`, `pkg/`
   - Build output in `.gitignore` gives hints about the build system
   - Generate a 2-3 level directory tree with purpose comments

4. **Extract patterns** — find real code examples:
   - API response format: grep for common response patterns
   - Error handling: how errors are created and returned
   - Auth pattern: how auth is checked in handlers/middleware
   - Pick 2-3 representative snippets

5. **Find env vars** — scan for environment variable usage:
   - `.env.example`, `.env.sample`, `.env.template`
   - `process.env.`, `os.environ`, `os.Getenv`, `env::var`
   - Mark each as required/optional based on defaults

6. **Check git workflow** — read recent commits for convention:
   - `git log --oneline -20` for commit message format
   - CI config: `.github/workflows/`, `.gitlab-ci.yml`, `Makefile`

7. **Generate CLAUDE.md** — if a template was found in step 2, use it as the base structure and fill in real data from steps 1, 3-6. Otherwise assemble from scratch using:
   ```
   ## Project Overview
   ## Critical Rules
   ## File Structure
   ## Key Patterns
   ## Environment Variables
   ## Git Workflow
   ```

8. **Write** the file to `./CLAUDE.md` and show the result.

## Rules
- Keep it under 200 lines
- Use real code from the project, not generic examples
- If a section has no useful content (e.g., no env vars found), omit it
- Don't overwrite an existing CLAUDE.md without asking first
- If unsure about a convention, ask the user

## Check Mode (`--check`)

If `$ARGUMENTS` contains `--check`, run **validation mode** instead of generation.

### Validation Process

1. **Read** the existing `./CLAUDE.md`
   - If it doesn't exist: report "No CLAUDE.md found. Run `/init` to generate one." and stop

2. **Check 6 mandatory sections** — each must exist as a `##` heading:
   - `## Project Overview`
   - `## Critical Rules`
   - `## File Structure`
   - `## Key Patterns`
   - `## Environment Variables`
   - `## Git Workflow`

3. **Validate each section's content**:

   **Project Overview:**
   - Must contain `**Stack:**` and at least one of `**Architecture:**` or `**Purpose:**`
   - `INCOMPLETE` if any keyword is missing

   **Critical Rules:**
   - Must have at least one `###` sub-heading
   - Should have a `### Forbidden` sub-section
   - `WEAK` if fewer than 3 rules total

   **File Structure:**
   - Must contain a fenced code block (triple backticks)
   - Code block should have at least 5 lines of tree content
   - `SHALLOW` if code block is missing or too short

   **Key Patterns:**
   - Must contain at least one fenced code block with a language tag
   - Should have at least 2 `###` sub-headings inside
   - Report "has no code snippets" if empty

   **Environment Variables:**
   - Must contain a fenced code block
   - Each variable should have a comment (`#`)
   - `UNMARKED` if variables lack comments

   **Git Workflow:**
   - Must mention commit format
   - `INCOMPLETE` if no CI/CD mentioned

4. **Report** in this format:
   ```
   CLAUDE.md Health Check
   ======================
   Project Overview:       OK
   Critical Rules:         OK
   File Structure:         OK
   Key Patterns:           INCOMPLETE (has no code snippets)
   Environment Variables:  OK
   Git Workflow:            INCOMPLETE (no CI mentioned)
   ======================
   Score: 4/6 sections OK, 2 need attention
   ```

### Check Mode Rules
- Never modify CLAUDE.md — report only
- For each issue, suggest what to add
- `MISSING` = section heading absent, `INCOMPLETE` = exists but lacks key content

$ARGUMENTS
