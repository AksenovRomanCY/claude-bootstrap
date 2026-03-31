# CLAUDE.md

## Project Overview

**Stack:** Python 3.12+, Django 5.x, Django REST Framework, PostgreSQL, Celery + Redis, pytest
**Architecture:** DDD with apps per business domain. DRF for the API layer, Celery for async tasks. All endpoints return JSON — no template rendering.
**Purpose:** [describe the API]

## Critical Rules

### Python Conventions
- Type hints on all function signatures — `from __future__ import annotations`
- No `print()` statements — use `logging.getLogger(__name__)`
- f-strings for formatting, never `%` or `.format()`
- `pathlib.Path` instead of `os.path`
- Imports sorted by isort: stdlib, third-party, local (enforced by ruff)

### Database
- All queries via Django ORM — raw SQL only with `.raw()` and parameterized queries
- Migrations committed to git — never `--fake` in production
- `select_related()` and `prefetch_related()` to prevent N+1 queries
- All models must have `created_at` and `updated_at` auto-fields
- Indexes on any field used in `filter()`, `order_by()`, or `WHERE` clauses

### Auth
- JWT via `djangorestframework-simplejwt` — access token (15 min) + refresh token (7 days)
- Permission classes on every view — never rely on defaults
- Token blacklisting enabled for logout

### Serializers
- Separate read and write serializers when input/output shapes differ
- Validate at the serializer level, not in views — views should be thin

### Forbidden
- `print()` in any form
- `select_related` / `prefetch_related` without explicit fields
- Raw SQL without parameterization
- `*` imports
- Models without `created_at`/`updated_at`

## File Structure

```
config/
  settings/
    base.py              # Shared settings
    local.py             # Dev settings
    production.py        # Prod settings
  urls.py
  celery.py
apps/
  accounts/              # Users, auth
  orders/                # Orders
  products/              # Products
  # Each app contains:
  #   models.py, serializers.py, views.py,
  #   services.py, tasks.py, tests/
core/
  exceptions.py          # Custom exceptions
  permissions.py         # Shared permission classes
  pagination.py          # Pagination settings
  middleware.py          # Middleware
```

## Key Patterns

### Service Layer
```python
from django.db import transaction

class OrderService:
    @staticmethod
    @transaction.atomic
    def create_order(user: User, items: list[OrderItemInput]) -> Order:
        order = Order.objects.create(user=user, status=OrderStatus.PENDING)

        order_items = [
            OrderItem(order=order, product_id=item.product_id, quantity=item.quantity)
            for item in items
        ]
        OrderItem.objects.bulk_create(order_items)

        order.total = sum(item.subtotal for item in order_items)
        order.save(update_fields=["total"])

        return order
```

### ViewSet Pattern
```python
class OrderViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination

    def get_queryset(self):
        return (
            Order.objects
            .filter(user=self.request.user)
            .select_related("user")
            .prefetch_related("items__product")
            .order_by("-created_at")
        )

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return OrderWriteSerializer
        return OrderReadSerializer
```

### Test Pattern
```python
import pytest
from factories import UserFactory, OrderFactory

@pytest.mark.django_db
class TestOrderService:
    def test_create_order_calculates_total(self):
        user = UserFactory()
        items = [OrderItemInput(product_id=1, quantity=2)]

        order = OrderService.create_order(user, items)

        assert order.total > 0
        assert order.items.count() == 1

    def test_create_order_empty_items_raises(self):
        user = UserFactory()

        with pytest.raises(ValidationError):
            OrderService.create_order(user, items=[])
```

## Environment Variables

```
DATABASE_URL=                # required, postgres://user:pass@host:5432/db
DJANGO_SECRET_KEY=           # required
DJANGO_SETTINGS_MODULE=      # required, config.settings.local / config.settings.production
REDIS_URL=                   # required, redis://localhost:6379/0
CELERY_BROKER_URL=           # required, usually = REDIS_URL
ALLOWED_HOSTS=               # required in production, comma-separated
DEBUG=                       # optional, default False
```

## Git Workflow

- Format: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`
- CI: ruff (lint + format), mypy (types), pytest (tests), safety (dep check)
- Feature branches from main, PR required
- Deploy: Docker image, Kubernetes / Railway
