# Error Handling

## Core Principles
- Errors are values — handle them explicitly, never ignore
- Fail fast at system boundaries, recover gracefully inside
- Every error path must be intentional, not accidental

## Structure
- Define custom error types/classes for business logic
- Separate business errors (user did something wrong) from system errors (something broke)
- Map internal errors to user-facing messages at the boundary layer (handler/controller)

## Rules
- Never swallow errors silently (empty catch, `_ = err`)
- Never expose internal details to users (stack traces, DB errors, file paths)
- Always wrap errors with context when re-throwing: what operation failed and why
- Log the original error with full details server-side
- Return a safe, generic message to the client

## Error Response Consistency
- Use a single error format across the entire project — define it in CLAUDE.md Key Patterns
- Include: error message, error code (machine-readable), HTTP status (for REST)
- Never mix formats — every endpoint returns the same error shape

## What NOT to Do
- Don't use exceptions for control flow
- Don't catch errors just to re-throw without adding context
- Don't log and throw — pick one, or the same error appears twice in logs
- Don't return null/undefined to signal errors — use Result types or throw
- Don't use generic error messages ("Something went wrong") without a unique error code
