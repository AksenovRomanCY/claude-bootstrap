# CLAUDE.md

## Project Overview

**Stack:** Python 3.12+, FastAPI, SQLAlchemy 2.0 (async), Alembic, PostgreSQL, pytest
**Architecture:** Layered — routers (thin) → services (business logic) → repositories (data access). Pydantic models for all request/response schemas. Async throughout.
**Purpose:** [describe the API]

## Critical Rules

### Python Conventions
- Type hints on all function signatures — `from __future__ import annotations`
- No `print()` — use `logging.getLogger(__name__)`
- f-strings only, never `%` or `.format()`
- `pathlib.Path` instead of `os.path`
- Imports sorted by ruff (stdlib → third-party → local)

### Database
- All queries through SQLAlchemy async sessions — never raw SQL without `text()`
- Migrations in `alembic/versions/` — never modify the DB directly
- Use `selectinload()` / `joinedload()` to prevent N+1 queries
- All models must have `created_at` and `updated_at` columns
- Transactions via `async with session.begin():`

### Auth
- JWT via `python-jose` or `authlib` — access token (15 min) + refresh token (7 days)
- Dependencies for auth: `Depends(get_current_user)` on every protected route
- Never trust client-side data for authorization decisions

### API Design
- Pydantic models for all request/response — never return raw dicts
- Separate input and output schemas when shapes differ
- Consistent error responses via custom exception handlers
- Pagination on all list endpoints

### Forbidden
- `print()` in any form
- `import *`
- Bare `except:` or `except Exception:`
- Sync database calls in async context
- `os.path` — use `pathlib`
- Mutable default arguments

## File Structure

```
app/
  main.py                # FastAPI app, middleware, startup
  config.py              # Settings via pydantic-settings
  dependencies.py        # Shared dependencies (DB session, auth)
  routers/
    users.py             # /users endpoints
    orders.py            # /orders endpoints
  services/
    user_service.py      # Business logic
    order_service.py
  repositories/
    user_repo.py         # Data access layer
    order_repo.py
  models/
    user.py              # SQLAlchemy models
    order.py
  schemas/
    user.py              # Pydantic request/response schemas
    order.py
  core/
    exceptions.py        # Custom exceptions
    security.py          # JWT, password hashing
alembic/
  versions/              # DB migrations
tests/
  conftest.py            # Fixtures (async client, test DB)
  test_users.py
  test_orders.py
```

## Key Patterns

### Router (thin)
```python
@router.post("/", response_model=OrderResponse, status_code=201)
async def create_order(
    data: OrderCreate,
    user: User = Depends(get_current_user),
    service: OrderService = Depends(get_order_service),
) -> OrderResponse:
    return await service.create_order(user_id=user.id, data=data)
```

### Service (business logic)
```python
class OrderService:
    def __init__(self, repo: OrderRepository, session: AsyncSession):
        self.repo = repo
        self.session = session

    async def create_order(self, user_id: int, data: OrderCreate) -> Order:
        async with self.session.begin():
            order = Order(user_id=user_id, **data.model_dump())
            self.session.add(order)
            await self.session.flush()
            return order
```

### Test Pattern
```python
@pytest.mark.asyncio
async def test_create_order(async_client: AsyncClient, auth_headers: dict):
    response = await async_client.post(
        "/orders/",
        json={"product_id": 1, "quantity": 2},
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["product_id"] == 1
```

## Environment Variables

```
DATABASE_URL=               # required, postgresql+asyncpg://user:pass@host:5432/db
SECRET_KEY=                 # required, for JWT signing
ALGORITHM=                  # optional, default HS256
ACCESS_TOKEN_EXPIRE=        # optional, default 15 (minutes)
REDIS_URL=                  # optional, for caching
DEBUG=                      # optional, default false
```

## Git Workflow

- Format: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`
- CI: ruff (lint + format), mypy (types), pytest (tests)
- Feature branches from main, PR required
- Deploy: Docker image, Kubernetes / Railway
