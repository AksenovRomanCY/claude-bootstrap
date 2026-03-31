---
name: deps-check
description: Check for outdated and vulnerable dependencies, suggest updates
disable-model-invocation: false
allowed-tools: Bash, Read, Glob
---

# Dependency Check

Audit project dependencies for outdated versions and known vulnerabilities.

## Process

1. **Detect package manager** by looking for:
   - `package-lock.json` / `yarn.lock` / `pnpm-lock.yaml` / `bun.lockb` → Node.js
   - `requirements.txt` / `Pipfile.lock` / `poetry.lock` / `uv.lock` → Python
   - `go.sum` → Go
   - `Cargo.lock` → Rust
   - `Gemfile.lock` → Ruby

2. **Check for vulnerabilities**:

   | Ecosystem | Command |
   |-----------|---------|
   | npm | `npm audit` |
   | yarn | `yarn audit` |
   | pnpm | `pnpm audit` |
   | pip | `pip audit` (if installed) or `safety check` |
   | go | `govulncheck ./...` (if installed) |
   | cargo | `cargo audit` (if installed) |

   If the audit tool is not installed, note it and skip.

3. **Check for outdated**:

   | Ecosystem | Command |
   |-----------|---------|
   | npm | `npm outdated` |
   | yarn | `yarn outdated` |
   | pip | `pip list --outdated` |
   | go | `go list -m -u all` |
   | cargo | `cargo outdated` (if installed) |

4. **Summarize**:

   ```
   Vulnerabilities:
     Critical: N
     High:     N
     Medium:   N

   Outdated packages:
     Major updates:  [list — breaking changes likely]
     Minor updates:  [list — new features, safe]
     Patch updates:  [list — bug fixes, safe]
   ```

5. **Recommend** actions:
   - Patch updates: safe to update all at once
   - Minor updates: update one by one, run tests after each
   - Major updates: check changelog for breaking changes, update separately
   - Vulnerabilities: prioritize by severity, show which package and fix version

## Rules
- Don't update anything automatically — report only
- If multiple package managers exist (e.g., npm + pip in a fullstack project), check both
- Note if audit tools are missing and suggest how to install them

$ARGUMENTS
