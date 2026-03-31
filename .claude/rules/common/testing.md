# Testing

## Principles
- Tests are a mandatory part of any business logic change
- Test behavior, not implementation
- Each test must be independent and reproducible

## Test Types
1. **Unit tests** — isolated logic, pure functions, services
2. **Integration tests** — interaction between layers, DB, external APIs
3. **E2E tests** — critical user flows

## Test Structure (AAA)
```
Arrange — prepare data and dependencies
Act     — execute the action under test
Assert  — verify the result
```

## Rules
- One assert per logical case (multiple asserts are fine if verifying a single result)
- Test data — factories/fixtures, not hardcoded values
- Mocks — only for external dependencies (HTTP, email, payment systems)
- DB in integration tests — real, not mocked (transaction with rollback)
- Test names describe the scenario: `test_create_order_with_empty_items_raises_error`

## Coverage
- Target coverage: 80%+ for business logic
- Utility and infrastructure coverage — as needed
- 100% coverage is not a goal, test quality matters more

## Must Cover
- Happy path for each public method
- Edge cases: empty data, null, boundary values
- Error scenarios: invalid input, unavailable dependencies
- Authorization: access allowed/denied
