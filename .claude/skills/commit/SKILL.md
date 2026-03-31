---
name: commit
description: Analyze changes, generate a conventional commit message, and commit
disable-model-invocation: true
allowed-tools: Bash, Read, Grep
---

# Commit

Create a commit following the project's conventional commit format.

## Context

Staged changes:
!`git diff --cached --stat`

Unstaged changes:
!`git diff --stat`

Untracked files:
!`git status --short`

Recent commits for style reference:
!`git log --oneline -10`

## Process

1. **Analyze** all staged changes. If nothing is staged, identify the relevant changed files and stage them (prefer specific files over `git add -A`).
2. **Never stage** files matching: `.env*`, `credentials*`, `*secret*`, `*.key`, `*.pem`, `node_modules/`, `__pycache__/`, `.DS_Store`
3. **Draft** a commit message following the format from recent commits. If no clear convention exists, use:
   ```
   <type>: <description>
   ```
   Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`
4. **Show** the message to the user and ask for confirmation before committing.
5. **Commit** with the approved message.

If the user provides arguments, use them as context for the commit message: $ARGUMENTS
