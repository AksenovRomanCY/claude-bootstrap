---
name: fix-build
description: Read build/lint/test errors, diagnose root cause, and fix them
disable-model-invocation: true
allowed-tools: Bash, Read, Edit, Write, Grep, Glob
---

# Fix Build

Diagnose and fix build, lint, or test errors.

## Process

1. **Get errors** — run the failing command (or use provided error output):
   - If no specific command given, detect and run the project's build/check command
   - Capture the full error output

2. **Parse errors** — extract:
   - File path and line number
   - Error code/type
   - Error message

3. **Diagnose** — for each error:
   - Read the affected file at the error location
   - Understand the root cause (not just the symptom)
   - Check if multiple errors share a single root cause

4. **Fix** — apply fixes:
   - Fix the root cause, not each symptom individually
   - Prefer minimal changes that resolve the error
   - Don't refactor or "improve" surrounding code

5. **Verify** — re-run the original command to confirm the fix works

6. **Report** — summarize what was wrong and what was changed

## Rules
- Fix ONLY what's broken — don't touch working code
- If the fix requires a design decision, ask the user first
- If an error is in generated code (migrations, lockfiles), explain how to regenerate instead of editing
- If >10 errors, fix the most likely root causes first and re-run — cascading errors often resolve themselves

If the user provides error output or a specific command: $ARGUMENTS
