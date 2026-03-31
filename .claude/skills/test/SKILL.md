---
name: test
description: TDD workflow — write test first (RED), implement (GREEN), refactor (IMPROVE)
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Bash, Edit, Write
---

# TDD Workflow

Implement a feature using strict Test-Driven Development.

## Target

$ARGUMENTS

## Process

### Phase 1: RED — Write the test first

1. **Understand** what needs to be tested:
   - Read related code to understand existing patterns
   - Identify the test framework used in the project (jest, pytest, go test, vitest, etc.)
   - Find existing tests for style reference

2. **Write** a failing test:
   - Test file location follows project conventions (colocated or `tests/` dir)
   - Test name describes the expected behavior
   - Cover the happy path first
   - Include 1-2 edge cases (empty input, error case)

3. **Run** the test — it MUST fail:
   ```
   Expected: FAIL
   ```
   If it passes, the test is not testing new behavior — rewrite it.

### Phase 2: GREEN — Minimal implementation

4. **Write** the minimum code to make the test pass:
   - Don't over-engineer — just make it green
   - Don't add features the test doesn't require
   - Don't optimize yet

5. **Run** the test — it MUST pass:
   ```
   Expected: PASS
   ```
   If it fails, fix the implementation (not the test).

### Phase 3: IMPROVE — Refactor

6. **Review** the implementation:
   - Remove duplication
   - Improve naming
   - Simplify logic
   - Extract if needed

7. **Run** the test again — it MUST still pass:
   ```
   Expected: PASS (same tests, cleaner code)
   ```

### Phase 4: Expand coverage

8. **Add** edge case tests if not done in Phase 1:
   - Null/empty input
   - Boundary values
   - Error conditions
   - Authorization (if applicable)

9. **Repeat** RED → GREEN → IMPROVE for each new test.

## Rules
- NEVER write implementation before the test
- NEVER skip the RED phase — if the test doesn't fail first, it proves nothing
- NEVER modify a test to make it pass — fix the implementation
- Keep each cycle small — one behavior per test
- Run tests after EVERY change
- Show test output at each phase so the user sees RED → GREEN progression

## Summary Template

After completion, report:
```
TDD Summary:
- Tests written: N
- All passing: YES/NO
- Coverage: [files/functions covered]
- Cycles: RED → GREEN → IMPROVE × N
```
