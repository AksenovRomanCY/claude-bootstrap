# CLAUDE.md

## Project Overview

**Stack:** Node.js, Express, TypeScript, Prisma ORM, PostgreSQL, Zod, Jest + Supertest
**Architecture:** Layered — routes (routing) → controllers (thin, HTTP) → services (business logic) → Prisma Client (data access). Zod for request validation. Centralized error handling middleware.
**Purpose:** [describe the API]

## Critical Rules

### Layers
- Routes define endpoints and apply middleware — no logic
- Controllers parse request, call service, format response — no business logic
- Services contain all business logic — no HTTP concepts (req, res, status codes)
- Prisma Client for all data access — never raw SQL without `$queryRaw`

### Database
- Migrations via `prisma migrate dev` — never modify the DB directly
- Use `select` to fetch only needed fields — never return full models with secrets
- Use `$transaction()` for multi-step operations
- All models must have `createdAt` and `updatedAt` fields
- Pagination on all list endpoints — cursor-based preferred

### Validation
- Zod schemas for all request bodies, query params, and route params
- Validation middleware applies schema before controller runs
- Separate schemas for create, update, and response
- Environment variables validated with Zod at startup

### Error Handling
- Custom `AppError` class with HTTP status code and error code
- Central error middleware catches all errors and returns consistent format
- Never expose internal details (stack traces, DB errors) to clients
- Log original error server-side, return safe message to client

### Forbidden
- `any` in TypeScript — use `unknown` or proper types
- `console.log` — use structured logger (pino / winston)
- Business logic in controllers or routes
- Throwing plain `Error` — use `AppError` with code
- `req.body` without Zod validation

## File Structure

```
src/
  app.ts                     # Express app, middleware setup
  server.ts                  # Server startup, graceful shutdown
  config/
    env.ts                   # Environment validation with Zod
  routes/
    index.ts                 # Route aggregation
    users.routes.ts          # /users route definitions
    orders.routes.ts         # /orders route definitions
  controllers/
    users.controller.ts      # HTTP request/response handling
    orders.controller.ts
  services/
    users.service.ts         # Business logic
    orders.service.ts
  middleware/
    auth.ts                  # JWT verification middleware
    validate.ts              # Zod validation middleware
    error-handler.ts         # Centralized error handling
  lib/
    prisma.ts                # Prisma Client singleton
    logger.ts                # Structured logger setup
    errors.ts                # AppError class, error codes
  types/
    express.d.ts             # Express type extensions
prisma/
  schema.prisma              # Database schema
  migrations/                # Migration files
  seed.ts                    # Development seed data
tests/
  setup.ts                   # Test setup, DB cleanup
  users.test.ts
  orders.test.ts
```

## Key Patterns

### Route + Validation + Controller
```typescript
// routes/orders.routes.ts
const router = Router();

router.post(
  "/",
  authenticate,
  validate(createOrderSchema),
  ordersController.create,
);

router.get(
  "/",
  authenticate,
  validate(listOrdersSchema, "query"),
  ordersController.list,
);

// middleware/validate.ts
function validate(schema: ZodSchema, source: "body" | "query" | "params" = "body") {
  return (req: Request, _res: Response, next: NextFunction) => {
    const result = schema.safeParse(req[source]);
    if (!result.success) {
      throw new AppError(400, "VALIDATION_ERROR", "Invalid input", result.error.flatten());
    }
    req[source] = result.data;
    next();
  };
}
```

### Service Layer
```typescript
// services/orders.service.ts
export class OrdersService {
  async create(userId: string, data: CreateOrderInput): Promise<Order> {
    return prisma.$transaction(async (tx) => {
      const product = await tx.product.findUniqueOrThrow({
        where: { id: data.productId },
        select: { id: true, price: true, stock: true },
      });

      if (product.stock < data.quantity) {
        throw new AppError(400, "INSUFFICIENT_STOCK", "Not enough stock");
      }

      await tx.product.update({
        where: { id: product.id },
        data: { stock: { decrement: data.quantity } },
      });

      return tx.order.create({
        data: { userId, productId: data.productId, quantity: data.quantity, total: product.price * data.quantity },
        select: { id: true, quantity: true, total: true, createdAt: true },
      });
    });
  }
}
```

### Error Handler Middleware
```typescript
// middleware/error-handler.ts
function errorHandler(err: Error, _req: Request, res: Response, _next: NextFunction) {
  if (err instanceof AppError) {
    res.status(err.statusCode).json({
      error: { message: err.message, code: err.code, details: err.details },
    });
    return;
  }

  logger.error("Unhandled error", { error: err });
  res.status(500).json({
    error: { message: "Internal server error", code: "INTERNAL_ERROR" },
  });
}
```

## Environment Variables

```
DATABASE_URL=                 # required, postgresql://user:pass@host:5432/db
JWT_SECRET=                   # required, secret for token signing
JWT_EXPIRATION=               # optional, default 3600 (seconds)
PORT=                         # optional, default 3000
NODE_ENV=                     # optional, default development
LOG_LEVEL=                    # optional, default info
```

## Git Workflow

- Format: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`
- CI: eslint, tsc --noEmit, jest (unit + integration), prisma generate
- Feature branches from main, PR required
- Deploy: Docker image, Railway / Render / AWS ECS
