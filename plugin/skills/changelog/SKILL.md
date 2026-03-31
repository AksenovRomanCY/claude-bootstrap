---
name: changelog
description: Generate a changelog from git history between tags or date ranges
disable-model-invocation: true
allowed-tools: Bash, Read, Grep
---

# Changelog

Generate a human-readable changelog from git history.

## Context

Tags:
!`git tag --sort=-version:refname | head -10`

Recent commits:
!`git log --oneline -30`

## Process

1. **Determine range**:
   - If `$ARGUMENTS` specifies a range (e.g., `v1.2.0..v1.3.0`), use it
   - If `$ARGUMENTS` specifies one tag, use `<tag>..HEAD`
   - If no arguments, use last tag to HEAD: `<latest-tag>..HEAD`
   - If no tags exist, use last 30 commits

2. **Collect commits** in the range:
   ```
   git log <range> --oneline --no-merges
   ```

3. **Categorize** by commit type prefix:
   - **Added** — `feat:` commits
   - **Fixed** — `fix:` commits
   - **Changed** — `refactor:`, `perf:` commits
   - **Other** — `docs:`, `test:`, `chore:` (group as "Maintenance")

4. **Format** the changelog:

   ```markdown
   ## [version or Unreleased] — YYYY-MM-DD

   ### Added
   - Description of feature ([commit-hash])

   ### Fixed
   - Description of fix ([commit-hash])

   ### Changed
   - Description of change ([commit-hash])
   ```

5. **Output** the changelog. Don't write to a file unless asked.

## Rules
- Rewrite commit messages into user-facing language (not "fix: resolve NPE" but "Fixed crash when opening empty project")
- Group related commits into a single entry if they're part of the same feature
- Skip trivial commits (typo fixes, merge commits, CI tweaks) unless they're the only changes
- Include short commit hashes for reference

$ARGUMENTS
