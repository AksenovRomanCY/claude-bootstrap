# CLAUDE.md

## Project Overview

**Stack:** Next.js 15 (App Router), TypeScript, Supabase (auth + DB), Stripe (billing), Tailwind CSS, Playwright (E2E)
**Architecture:** Server Components by default. Client Components only for interactivity. API routes for webhooks, Server Actions for mutations.
**Purpose:** [describe the SaaS product]

## Critical Rules

### Database
- All queries via Supabase client with RLS enabled — never bypass RLS
- Migrations in `supabase/migrations/` — never modify the DB directly
- `select()` with explicit column list, never `select('*')`
- All user-facing queries must include `.limit()`

### Authentication
- Server Components: `createServerClient()` from `@supabase/ssr`
- Client Components: `createBrowserClient()` from `@supabase/ssr`
- Auth check via `getUser()` — never trust `getSession()` alone
- Middleware in `middleware.ts` refreshes auth tokens on every request

### Billing
- Stripe webhook handler in `app/api/webhooks/stripe/route.ts`
- Never trust client-side price data — always fetch from Stripe server-side
- Subscription status checked via `subscription_status` column, synced by webhook
- Free tier: [free plan limits]

### Code Style
- Immutable patterns — spread operator, never mutate
- Server Components: no `'use client'`, no `useState`/`useEffect`
- Client Components: `'use client'` at top, minimal — extract logic to hooks
- Zod schemas for all input validation (API routes, forms, env)
- No `any` in TypeScript
- console.log forbidden in production code

## File Structure

```
src/
  app/
    (auth)/              # Auth pages (login, signup, forgot-password)
    (dashboard)/         # Protected dashboard pages
    api/
      webhooks/          # Stripe, Supabase webhooks
    layout.tsx           # Root layout with providers
  components/
    ui/                  # Shadcn/ui components
    forms/               # Forms with validation
    dashboard/           # Dashboard-specific components
  hooks/                 # Custom React hooks
  lib/
    supabase/            # Supabase client factories
    stripe/              # Stripe client and helpers
    utils.ts             # General utilities
  types/                 # Shared TypeScript types
supabase/
  migrations/            # DB migrations
  seed.sql               # Development seed data
```

## Key Patterns

### API Response Format
```typescript
type ApiResponse<T> =
  | { success: true; data: T }
  | { success: false; error: string; code?: string }
```

### Server Action Pattern
```typescript
"use server"

import { z } from "zod"
import { createServerClient } from "@/lib/supabase/server"
import { revalidatePath } from "next/cache"
import { redirect } from "next/navigation"

const createProjectSchema = z.object({
  name: z.string().min(1).max(100),
  description: z.string().max(500).optional(),
})

export async function createProject(formData: FormData) {
  const parsed = createProjectSchema.safeParse(Object.fromEntries(formData))
  if (!parsed.success) {
    return { success: false, error: "Invalid input", code: "VALIDATION_ERROR" }
  }

  const supabase = await createServerClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) redirect("/login")

  const { data, error } = await supabase
    .from("projects")
    .insert({ ...parsed.data, user_id: user.id })
    .select("id, name")
    .single()

  if (error) {
    return { success: false, error: error.message, code: "DB_ERROR" }
  }

  revalidatePath("/dashboard")
  return { success: true, data }
}
```

### Error Boundary Pattern
```typescript
"use client"

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <div className="flex flex-col items-center gap-4 p-8">
      <h2 className="text-lg font-semibold">Something went wrong</h2>
      <button onClick={reset} className="btn btn-primary">
        Try again
      </button>
    </div>
  )
}
```

## Environment Variables

```
NEXT_PUBLIC_SUPABASE_URL=            # required
NEXT_PUBLIC_SUPABASE_ANON_KEY=       # required
SUPABASE_SERVICE_ROLE_KEY=           # required, server-only, NEVER expose to client
STRIPE_SECRET_KEY=                   # required, server-only
STRIPE_WEBHOOK_SECRET=               # required, server-only
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=  # required
NEXT_PUBLIC_APP_URL=                 # required, http://localhost:3000 for dev
```

## Git Workflow

- Format: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`
- Feature branches from main, PR required
- CI: lint, type-check, unit tests, E2E tests
- Deploy: Vercel preview on PR, production on merge to main
