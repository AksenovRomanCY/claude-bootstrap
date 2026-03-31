---
paths:
  - "**/*.py"
---

# Python Conventions

## Typing
- Type hints on all function signatures: `def create_user(name: str, email: str) -> User:`
- `from __future__ import annotations` at the top of every file
- Pydantic for runtime validation of input data
- `Optional[X]` or `X | None` — explicit, never implicit None

## Structure
- One module — one responsibility
- Service layer for business logic (not in views/handlers)
- Factories (Factory Boy) for test data
- Configuration via pydantic-settings or django-environ

## Error Handling
- Custom exceptions for business logic (inherit from a base exception)
- Never bare `except:` or `except Exception:`
- Logging via `logging.getLogger(__name__)`, not `print()`

## Formatting
- Formatter: ruff format (or black)
- Linter: ruff (replaces flake8, isort, pyupgrade)
- Type checker: mypy with `strict = true`
- Max line length: 88 (ruff/black default)

## Django (if applicable)
- Thin views, fat services — logic in the service layer
- `select_related` / `prefetch_related` to prevent N+1 queries
- Separate read/write serializers in DRF
- Migrations — always in git, never `--fake` in prod
- `transaction.atomic()` for multi-step operations

## FastAPI (if applicable)
- Pydantic models for request/response schemas
- Dependency injection via `Depends()`
- Background tasks for heavy operations
- Middleware for cross-cutting concerns

## Forbidden
- `print()` in production code
- `import *`
- Bare `except:`
- `os.path` — use `pathlib.Path`
- `%` string formatting — f-strings only
- Mutable default arguments (`def foo(items=[])`)
