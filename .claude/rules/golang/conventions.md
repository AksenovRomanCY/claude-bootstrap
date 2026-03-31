---
paths:
  - "**/*.go"
---

# Go Conventions

## Style
- Follow Effective Go and Go Code Review Comments
- `gofmt` / `goimports` for formatting — no exceptions
- Linter: `golangci-lint` with project config

## Errors
- Return errors, don't panic — panics only for truly unrecoverable situations
- Wrap with context: `fmt.Errorf("creating user: %w", err)`
- Define sentinel errors in a central location (e.g., `domain/errors.go`)
- Never string-match on error messages — use `errors.Is` / `errors.As`
- Never ignore errors: `_ = doSomething()` is a bug

## Structure
- No `init()` functions — explicit initialization in `main()` or constructors
- No global mutable state — pass dependencies via constructors
- Context as first parameter, propagated through all layers
- Interfaces where they're consumed, not where they're implemented
- Small interfaces: 1-3 methods preferred

## Naming
- MixedCaps, not underscores: `userID` not `user_id`
- Exported = capitalized, unexported = lowercase
- Interface names: `-er` suffix for single-method (`Reader`, `Writer`)
- Package names: short, lowercase, no underscores, no plurals
- Avoid `Get` prefix for getters: `user.Name()` not `user.GetName()`

## Concurrency
- Don't start goroutines without a way to stop them
- Always pass `context.Context` to cancellable operations
- Use `sync.WaitGroup` or `errgroup` to wait for goroutines
- Channels for communication, mutexes for state protection
- Never assume goroutine execution order

## Testing
- Table-driven tests as default pattern
- `t.Helper()` in test helper functions
- `t.Parallel()` where safe
- Subtests: `t.Run("case name", func(t *testing.T) {...})`
- `testdata/` directory for fixtures

## Forbidden
- `panic()` in business logic
- Bare `go func()` without lifecycle management
- `interface{}` / `any` without strong justification
- `select *` or implicit columns in SQL
- `http.DefaultClient` in production (no timeouts)
