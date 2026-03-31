# CLAUDE.md

## Project Overview

**Stack:** Go 1.22+, PostgreSQL, gRPC + REST (grpc-gateway), Docker, sqlc, Wire (DI)
**Architecture:** Clean architecture — domain, repository, service, handler layers. gRPC as primary transport, REST gateway for external clients.
**Purpose:** [describe the microservice]

## Critical Rules

### Go Conventions
- Follow Effective Go and Go Code Review Comments
- `errors.New` / `fmt.Errorf` with `%w` for wrapping — never string-match on errors
- No `init()` functions — explicit initialization in `main()` or constructors
- No global mutable state — pass dependencies via constructors
- Context must be the first parameter and propagated through all layers

### Database
- All queries in `queries/` as plain SQL — sqlc generates type-safe Go code
- Migrations in `migrations/` via golang-migrate — never alter the DB directly
- Transactions via `pgx.Tx` for multi-step operations
- Parameterized placeholders (`$1`, `$2`) — never string formatting

### Error Handling
- Return errors, don't panic — panics only for truly unrecoverable situations
- Wrap errors with context: `fmt.Errorf("creating user: %w", err)`
- Sentinel errors for business logic in `domain/errors.go`
- Map domain errors to gRPC status codes in the handler layer

### Forbidden
- `panic()` in business logic
- Ignoring errors (`_ = doSomething()`)
- `select *` or implicit columns in SQL
- Direct use of `http.DefaultClient`

## File Structure

```
cmd/
  server/
    main.go              # Entry point, wire injection, server startup
internal/
  domain/                # Business types, interfaces, sentinel errors
    user.go
    errors.go
  service/               # Business logic
    user_service.go
  repository/
    postgres/            # sqlc-generated code + implementations
      user_repo.go
  handler/
    grpc/                # gRPC handlers
    rest/                # REST handlers (grpc-gateway)
  config/                # Configuration (env, flags)
proto/                   # Protobuf definitions
queries/                 # SQL queries for sqlc
migrations/              # DB migrations
```

## Key Patterns

### Service with DI
```go
type UserService struct {
    repo   UserRepository
    logger *slog.Logger
}

func NewUserService(repo UserRepository, logger *slog.Logger) *UserService {
    return &UserService{repo: repo, logger: logger}
}

func (s *UserService) CreateUser(ctx context.Context, req CreateUserRequest) (*User, error) {
    if err := req.Validate(); err != nil {
        return nil, fmt.Errorf("validating request: %w", err)
    }

    user, err := s.repo.Create(ctx, req.ToUser())
    if err != nil {
        return nil, fmt.Errorf("creating user: %w", err)
    }

    s.logger.InfoContext(ctx, "user created", "user_id", user.ID)
    return user, nil
}
```

### Error Mapping (handler layer)
```go
func mapError(err error) error {
    switch {
    case errors.Is(err, domain.ErrNotFound):
        return status.Error(codes.NotFound, err.Error())
    case errors.Is(err, domain.ErrAlreadyExists):
        return status.Error(codes.AlreadyExists, err.Error())
    case errors.Is(err, domain.ErrValidation):
        return status.Error(codes.InvalidArgument, err.Error())
    default:
        return status.Error(codes.Internal, "internal error")
    }
}
```

### Table-Driven Tests
```go
func TestUserService_CreateUser(t *testing.T) {
    tests := []struct {
        name    string
        req     CreateUserRequest
        wantErr error
    }{
        {
            name: "valid request",
            req:  CreateUserRequest{Name: "John", Email: "john@example.com"},
        },
        {
            name:    "empty name",
            req:     CreateUserRequest{Email: "john@example.com"},
            wantErr: domain.ErrValidation,
        },
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            svc := NewUserService(newMockRepo(), slog.Default())
            _, err := svc.CreateUser(context.Background(), tt.req)
            if !errors.Is(err, tt.wantErr) {
                t.Errorf("got %v, want %v", err, tt.wantErr)
            }
        })
    }
}
```

## Environment Variables

```
DATABASE_URL=            # required, postgres://user:pass@host:5432/db?sslmode=disable
GRPC_PORT=               # optional, default 50051
REST_PORT=               # optional, default 8080
LOG_LEVEL=               # optional, default info (debug, info, warn, error)
```

## Git Workflow

- Format: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`
- CI: `go vet`, `staticcheck`, `go test -race`, `golangci-lint`
- Feature branches from main, PR required
- Deploy: Docker image in CI, deployed to Kubernetes
