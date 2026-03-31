# CLAUDE.md

## Project Overview

**Stack:** TypeScript, Turborepo, pnpm workspaces, React (web), Node.js (API), shared packages
**Architecture:** Monorepo with independent apps and shared packages. Apps import from packages, never from each other. Each package has its own tsconfig, tests, and build. Turborepo orchestrates builds with caching.
**Purpose:** [describe the product]

## Critical Rules

### Package Boundaries
- Apps (`apps/`) consume packages (`packages/`) — never import between apps
- Each package declares its own dependencies in its `package.json`
- Shared types and utilities live in `packages/shared/`
- UI components shared via `packages/ui/` — never duplicate across apps
- Use workspace protocol for internal deps: `"@repo/ui": "workspace:*"`

### TypeScript
- Each package extends root `tsconfig.base.json`
- Strict mode enabled everywhere — no `any`
- Path aliases via `tsconfig.json` paths — not relative imports across packages
- Each package exports through `index.ts` barrel — consumers import from package root

### Dependencies
- Dependencies installed per-package, not hoisted to root
- Root `package.json` has only devDependencies for tooling (turbo, typescript, eslint)
- Shared configs in `packages/config-*` (eslint, typescript, tailwind)
- Lock file (`pnpm-lock.yaml`) always committed

### Building
- Turborepo `turbo.json` defines the build pipeline and dependencies
- Each package builds independently with its own `build` script
- `turbo run build --filter=...[origin/main]` for affected-only builds in CI
- Never import from `dist/` — use TypeScript project references or `exports` field

### Forbidden
- Imports between apps (`apps/web` importing from `apps/api`)
- Hoisting dependencies to root `package.json` (except tooling)
- Circular dependencies between packages
- `console.log` in shared packages
- Publishing packages without version bump

## File Structure

```
apps/
  web/                       # React frontend (Next.js / Vite)
    src/
    package.json
    tsconfig.json
  api/                       # Backend API (Express / Fastify)
    src/
    package.json
    tsconfig.json
  admin/                     # Admin dashboard (optional)
    src/
    package.json
packages/
  ui/                        # Shared React components
    src/
    package.json
    tsconfig.json
  shared/                    # Shared types, utils, constants
    src/
    package.json
  config-eslint/             # Shared ESLint config
    index.js
    package.json
  config-typescript/         # Shared tsconfig presets
    base.json
    react.json
    node.json
    package.json
turbo.json                   # Pipeline configuration
package.json                 # Root: workspaces + tooling deps
pnpm-workspace.yaml          # Workspace definition
```

## Key Patterns

### Package Exports (packages/ui/package.json)
```json
{
  "name": "@repo/ui",
  "main": "./src/index.ts",
  "types": "./src/index.ts",
  "exports": {
    ".": "./src/index.ts",
    "./button": "./src/button.tsx",
    "./modal": "./src/modal.tsx"
  },
  "dependencies": {
    "react": "^19.0.0"
  },
  "devDependencies": {
    "@repo/config-typescript": "workspace:*"
  }
}
```

### Turbo Pipeline (turbo.json)
```json
{
  "tasks": {
    "build": {
      "dependsOn": ["^build"],
      "outputs": ["dist/**", ".next/**"]
    },
    "test": {
      "dependsOn": ["^build"]
    },
    "lint": {},
    "typecheck": {
      "dependsOn": ["^build"]
    },
    "dev": {
      "cache": false,
      "persistent": true
    }
  }
}
```

### Shared TypeScript Config (packages/config-typescript/base.json)
```json
{
  "compilerOptions": {
    "strict": true,
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "isolatedModules": true
  }
}
```

## Environment Variables

```
# Per-app .env files (apps/web/.env, apps/api/.env)
# Never share .env between apps — each app has its own

# apps/web
NEXT_PUBLIC_API_URL=          # required, http://localhost:3001 for dev

# apps/api
DATABASE_URL=                 # required, postgresql://...
JWT_SECRET=                   # required, server-only
PORT=                         # optional, default 3001
```

## Git Workflow

- Format: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`
- Scope recommended: `feat(web):`, `fix(api):`, `chore(ui):`
- CI: `turbo run lint typecheck test build --filter=...[origin/main]`
- Only affected packages are tested/built in CI
- Feature branches from main, PR required
- Deploy: each app deploys independently on merge to main
