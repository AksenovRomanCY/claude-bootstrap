---
name: verify
description: Run all project checks — lint, typecheck, tests — and summarize results
disable-model-invocation: false
allowed-tools: Bash, Read, Grep, Glob
---

# Verify

Run all available project checks and summarize results.

## Process

1. **Detect** which checks are available by examining the project:
   - Look at `package.json` scripts, `Makefile`, `pyproject.toml`, `Cargo.toml`, `go.mod`, or similar
   - Identify: linter, type checker, test runner, build command

2. **Run** each available check in order:
   - **Lint** (eslint, ruff, golangci-lint, etc.)
   - **Type check** (tsc --noEmit, mypy, pyright, etc.)
   - **Tests** (jest, pytest, go test, cargo test, etc.)
   - **Build** (if applicable and quick)

3. **Summarize** results in this format:

   ```
   Lint:      PASS / FAIL (N errors)
   Typecheck: PASS / FAIL (N errors)
   Tests:     PASS / FAIL (N passed, M failed)
   Build:     PASS / FAIL
   ```

4. For any **FAIL**: show the first 3 errors with file paths and suggest fixes.

## Rules
- Don't fix anything automatically — report only
- If a check takes longer than 60 seconds, skip and note it
- If a check is not configured in the project, skip it (don't install tools)

If the user provides arguments, focus on that specific check: $ARGUMENTS
