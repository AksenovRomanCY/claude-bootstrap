# Database

## Queries
- Always use parameterized queries — never string interpolation/concatenation
- Always specify columns explicitly — never `SELECT *`
- Always add `LIMIT` to user-facing queries — no unbounded result sets
- Use pagination for list endpoints (cursor-based preferred over offset)

## N+1 Prevention
- Fetch related data in the same query or batch (JOIN, subquery, eager loading)
- ORM-specific: `select_related`/`prefetch_related` (Django), `include` (Prisma), `Preload` (GORM)
- If you see a query inside a loop — it's probably N+1

## Migrations
- Migrations are always committed to version control
- Never modify the database directly — always through migration files
- Never use `--fake` or skip migrations in production
- Each migration should be reversible when possible
- Test migrations on a copy of production data before deploying

## Transactions
- Use transactions for multi-step operations that must succeed or fail together
- Keep transactions short — don't hold locks longer than necessary
- Never make external calls (HTTP, email) inside a transaction

## Indexes
- Add indexes on columns used in WHERE, ORDER BY, JOIN, and foreign keys
- Don't over-index — each index slows writes
- Composite indexes: put the most selective column first

## Schema Design
- Every table should have a primary key
- Timestamps: `created_at` and `updated_at` on every table
- Use appropriate types — don't store numbers as strings, dates as integers
- Prefer soft delete (`deleted_at`) over hard delete for important business data
