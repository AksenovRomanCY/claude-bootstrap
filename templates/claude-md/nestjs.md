# CLAUDE.md

## Project Overview

**Stack:** NestJS 10, TypeScript, Prisma ORM, PostgreSQL, Jest, Swagger
**Architecture:** Modular — each feature is a NestJS module with controllers (thin), services (business logic), DTOs (validation). Guards for auth, Pipes for validation, Interceptors for response transformation.
**Purpose:** [describe the API]

## Critical Rules

### Modules
- One module per feature domain — never cross-module service injection without explicit export
- Controllers are thin — delegate all logic to services
- Services hold business logic — never access `Request` or `Response` directly
- Use `@Injectable()` for all services — leverage NestJS DI container

### Database
- All queries through Prisma Client — never raw SQL without `$queryRaw`
- Migrations via `prisma migrate dev` — never modify the DB directly
- Use `select` to fetch only needed fields, avoid returning full models
- Use `$transaction()` for multi-step operations
- All models must have `createdAt` and `updatedAt` fields

### Validation
- DTOs with `class-validator` decorators for all request bodies
- `ValidationPipe` enabled globally — never validate manually in controllers
- Separate `CreateDto` and `UpdateDto` — use `PartialType()` for updates
- Transform incoming data with `class-transformer` decorators

### Auth
- JWT via `@nestjs/jwt` + `@nestjs/passport`
- `@UseGuards(JwtAuthGuard)` on all protected endpoints
- Role-based access via custom `@Roles()` decorator + `RolesGuard`
- Never trust client-side data for authorization decisions

### Forbidden
- `any` in TypeScript — use `unknown` or proper types
- `console.log` — use NestJS `Logger` service
- Direct Prisma Client access in controllers — always go through services
- Circular module dependencies — refactor to shared module
- Throwing plain `Error` — use NestJS `HttpException` subclasses

## File Structure

```
src/
  app.module.ts              # Root module, imports all feature modules
  main.ts                    # Bootstrap, global pipes/interceptors
  common/
    decorators/              # Custom decorators (@CurrentUser, @Roles)
    filters/                 # Exception filters
    guards/                  # JwtAuthGuard, RolesGuard
    interceptors/            # Transform, logging interceptors
    pipes/                   # Custom validation pipes
  modules/
    auth/
      auth.module.ts
      auth.controller.ts
      auth.service.ts
      dto/                   # LoginDto, RegisterDto
      strategies/            # JwtStrategy, LocalStrategy
    users/
      users.module.ts
      users.controller.ts
      users.service.ts
      dto/                   # CreateUserDto, UpdateUserDto
    orders/
      orders.module.ts
      orders.controller.ts
      orders.service.ts
      dto/
prisma/
  schema.prisma              # Database schema
  migrations/                # Migration files
  seed.ts                    # Development seed data
test/
  app.e2e-spec.ts            # E2E tests
```

## Key Patterns

### Controller (thin)
```typescript
@Controller("orders")
@UseGuards(JwtAuthGuard)
@ApiTags("orders")
export class OrdersController {
  constructor(private readonly ordersService: OrdersService) {}

  @Post()
  @ApiCreatedResponse({ type: OrderResponseDto })
  create(
    @CurrentUser() user: UserPayload,
    @Body() dto: CreateOrderDto,
  ): Promise<OrderResponseDto> {
    return this.ordersService.create(user.id, dto);
  }

  @Get()
  @ApiOkResponse({ type: [OrderResponseDto] })
  findAll(
    @CurrentUser() user: UserPayload,
    @Query() query: PaginationDto,
  ): Promise<OrderResponseDto[]> {
    return this.ordersService.findAll(user.id, query);
  }
}
```

### Service (business logic + Prisma)
```typescript
@Injectable()
export class OrdersService {
  private readonly logger = new Logger(OrdersService.name);

  constructor(private readonly prisma: PrismaService) {}

  async create(userId: string, dto: CreateOrderDto): Promise<OrderResponseDto> {
    const order = await this.prisma.$transaction(async (tx) => {
      const product = await tx.product.findUniqueOrThrow({
        where: { id: dto.productId },
        select: { id: true, price: true, stock: true },
      });

      if (product.stock < dto.quantity) {
        throw new BadRequestException("Insufficient stock");
      }

      await tx.product.update({
        where: { id: product.id },
        data: { stock: { decrement: dto.quantity } },
      });

      return tx.order.create({
        data: { userId, productId: dto.productId, quantity: dto.quantity, total: product.price * dto.quantity },
        select: { id: true, quantity: true, total: true, createdAt: true },
      });
    });

    this.logger.log(`Order created: ${order.id}`);
    return order;
  }
}
```

### DTO with Validation
```typescript
export class CreateOrderDto {
  @IsString()
  @IsNotEmpty()
  productId: string;

  @IsInt()
  @Min(1)
  @Max(100)
  quantity: number;
}

export class UpdateOrderDto extends PartialType(CreateOrderDto) {}
```

## Environment Variables

```
DATABASE_URL=                 # required, postgresql://user:pass@host:5432/db
JWT_SECRET=                   # required, secret for token signing
JWT_EXPIRATION=               # optional, default 3600 (seconds)
PORT=                         # optional, default 3000
NODE_ENV=                     # optional, default development
```

## Git Workflow

- Format: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`
- CI: eslint, tsc --noEmit, jest (unit + e2e), prisma generate
- Feature branches from main, PR required
- Deploy: Docker image, Kubernetes / Railway
