---
paths:
  - "**/*.ts"
  - "**/*.tsx"
  - "**/*.js"
  - "**/*.jsx"
---

# TypeScript Conventions

## Typing
- `strict: true` in tsconfig — always
- No `any` — use `unknown` if the type is unknown
- Explicit return types for public functions
- Zod for runtime validation, TypeScript for compile-time
- Prefer `interface` for objects, `type` for unions/intersections

## Structure
- Barrel exports (`index.ts`) — only for the module's public API
- One component/class per file
- Colocation: tests next to code (`user.service.ts` → `user.service.test.ts`)

## Async
- `async/await` instead of `.then()` chains
- Always handle rejected promises
- `Promise.all()` for parallel operations, not sequential await in a loop

## React (if applicable)
- Server Components by default
- `'use client'` only when interactivity is truly needed
- Hooks — for reusable stateful logic
- Props: destructure in parameters, not `props.x`
- Keys: stable identifiers, never `index`

## Tools
- Formatter: Prettier or Biome
- Linter: ESLint or Biome
- Package manager: determined by the project (npm/pnpm/yarn/bun)

## Forbidden
- `any`
- `@ts-ignore` without explanation (`@ts-expect-error` with a comment is acceptable)
- `enum` — use `as const` objects instead
- `class` components in React
- `var` — only `const`, `let` when necessary
