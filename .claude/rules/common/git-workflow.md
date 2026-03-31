# Git Workflow

## Commit Message Format
```
<type>: <description>
```

Types:
- `feat` — new feature
- `fix` — bug fix
- `refactor` — code change without behavior change
- `docs` — documentation
- `test` — tests
- `chore` — configuration, dependencies, CI
- `perf` — performance optimization

## Commit Rules
- Description in English, imperative mood: "add feature" not "added feature"
- One logical unit of change per commit
- Never commit: `.env`, credentials, node_modules, build artifacts
- Never `--no-verify` — if hooks are in the way, fix the root cause

## Branches
- `main` — stable branch, always deployable
- `feat/<description>` — new feature
- `fix/<description>` — bug fix
- `refactor/<description>` — refactoring

## Pull Request
- Short title (<70 characters), details in the body
- Body: what changed, why, how to test
- Before merge: CI green, code review passed, conflicts resolved
- Squash merge as default for feature branches

## Forbidden
- Force push to main/master
- Direct commits to main (only through PRs)
- Merge with failing CI
