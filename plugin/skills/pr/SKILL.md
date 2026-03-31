---
name: pr
description: Create a pull/merge request with auto-generated description
disable-model-invocation: true
allowed-tools: Bash, Read, Grep
---

# Pull/Merge Request

Create a PR (GitHub) or MR (GitLab) with a generated description.

## Context

Current branch:
!`git branch --show-current`

Remote info:
!`git remote -v`

Commits since diverging from base branch:
!`git log --oneline $(git merge-base HEAD main 2>/dev/null || git merge-base HEAD master 2>/dev/null || echo HEAD~10)..HEAD 2>/dev/null`

Full diff from base:
!`git diff $(git merge-base HEAD main 2>/dev/null || git merge-base HEAD master 2>/dev/null || echo HEAD~10)..HEAD --stat 2>/dev/null`

## Process

1. **Detect platform** from remote URL:
   - `github.com` → use `gh pr create`
   - `gitlab.com` or GitLab self-hosted → use `glab mr create`
   - Other → show the description and let the user create manually

2. **Determine base branch**: `main` or `master` (whichever exists on remote)

3. **Analyze ALL commits** on this branch (not just the last one). Understand the full scope of changes.

4. **Push** the branch to remote if not already pushed:
   ```
   git push -u origin <branch-name>
   ```

5. **Generate PR/MR**:
   - Title: short (<70 chars), describes the change
   - Body format:
     ```
     ## Summary
     <2-4 bullet points covering all changes>

     ## Test plan
     - [ ] <how to verify each change>
     ```

6. **Create** using the appropriate CLI tool and return the URL.

If the user provides arguments, use them as context: $ARGUMENTS
