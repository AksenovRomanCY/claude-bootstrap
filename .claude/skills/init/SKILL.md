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

2. **Map structure** — scan top-level directories and key files:
   - `src/`, `app/`, `internal/`, `cmd/`, `lib/`, `pkg/`
   - Build output in `.gitignore` gives hints about the build system
   - Generate a 2-3 level directory tree with purpose comments

3. **Extract patterns** — find real code examples:
   - API response format: grep for common response patterns
   - Error handling: how errors are created and returned
   - Auth pattern: how auth is checked in handlers/middleware
   - Pick 2-3 representative snippets

4. **Find env vars** — scan for environment variable usage:
   - `.env.example`, `.env.sample`, `.env.template`
   - `process.env.`, `os.environ`, `os.Getenv`, `env::var`
   - Mark each as required/optional based on defaults

5. **Check git workflow** — read recent commits for convention:
   - `git log --oneline -20` for commit message format
   - CI config: `.github/workflows/`, `.gitlab-ci.yml`, `Makefile`

6. **Generate CLAUDE.md** — assemble using this structure:
   ```
   ## Project Overview
   ## Critical Rules
   ## File Structure
   ## Key Patterns
   ## Environment Variables
   ## Git Workflow
   ```

7. **Write** the file to `./CLAUDE.md` and show the result.

## Rules
- Keep it under 200 lines
- Use real code from the project, not generic examples
- If a section has no useful content (e.g., no env vars found), omit it
- Don't overwrite an existing CLAUDE.md without asking first
- If unsure about a convention, ask the user

$ARGUMENTS
