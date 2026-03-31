# How to Write a Proper CLAUDE.md

CLAUDE.md is a file in the project root that Claude Code reads **every session**.
It should be **compact (100-200 lines)** and give Claude full project understanding in 5 seconds.

---

## Structure

Every CLAUDE.md should contain **6 mandatory sections**:

### 1. Project Overview (3-5 lines)

Stack, architecture, purpose. Claude should instantly understand the context.

```markdown
## Project Overview

**Stack:** Next.js 15, TypeScript, Supabase, Stripe, Tailwind CSS
**Architecture:** Server Components by default, Client Components only for interactivity.
API routes for webhooks, Server Actions for mutations.
**Purpose:** SaaS platform for subscription management.
```

**Anti-pattern:** half-page description. If you need more context — put it in a separate doc.

---

### 2. Critical Rules (the most important section)

Hard rules that **must not be broken**. Not abstractions like "write good code" —
specific bindings to files, patterns, tools.

```markdown
## Critical Rules

### Database
- All queries via Supabase client with RLS — never bypass RLS
- `select()` with explicit column list, never `select('*')`
- All user-facing queries must include `.limit()`

### Auth
- Server Components: `createServerClient()` from `@supabase/ssr`
- Auth check via `getUser()`, not `getSession()`

### Forbidden
- console.log in production code
- Object mutation — spread/copy only
- Files over 500 lines
- `any` in TypeScript
```

**Principle:** every rule must be verifiable. If you can't unambiguously detect a violation — the rule is too abstract.

---

### 3. File Structure (project tree)

Critical for Claude to create files in the right places.

```markdown
## File Structure

src/
  app/
    (auth)/            # Auth pages
    (dashboard)/       # Protected pages
    api/webhooks/      # Stripe, Supabase webhooks
  components/
    ui/                # Shadcn/ui components
    forms/             # Forms with validation
  lib/
    supabase/          # Supabase clients
    stripe/            # Stripe helpers
  types/               # Shared TypeScript types
```

**Tip:** don't copy a full 50-line tree. Show the top 2-3 levels with comments about each directory's purpose.

---

### 4. Key Patterns (2-3 snippets)

Concrete code examples showing "how to do it right" in this project.

```markdown
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
export async function createProject(formData: FormData) {
  const parsed = projectSchema.safeParse(Object.fromEntries(formData))
  if (!parsed.success) return { error: parsed.error.flatten() }

  const supabase = await createServerClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) redirect("/login")

  const { error } = await supabase.from("projects").insert({
    ...parsed.data,
    user_id: user.id,
  })
  if (error) return { error: error.message }

  revalidatePath("/dashboard")
  return { success: true }
}
```

**Rule:** snippets must be real patterns from the project, not abstractions.

---

### 5. Environment Variables

```markdown
## Environment Variables

NEXT_PUBLIC_SUPABASE_URL=         # required
NEXT_PUBLIC_SUPABASE_ANON_KEY=    # required
SUPABASE_SERVICE_ROLE_KEY=        # required, server-only
STRIPE_SECRET_KEY=                # required
STRIPE_WEBHOOK_SECRET=            # required
NEXT_PUBLIC_APP_URL=              # required, http://localhost:3000 for dev
```

**Tip:** mark required/optional and server-only/public.

---

### 6. Git Workflow

```markdown
## Git Workflow

- Commit format: `<type>: <description>` (feat, fix, refactor, docs, test, chore)
- Feature branches from main, PR required
- Before merge: lint + type-check + tests
- Deploy: preview on PR, production on merge to main
```

---

## Checklist Before Finalizing

- [ ] Under 100-200 lines?
- [ ] Every rule is specific and verifiable?
- [ ] File Structure reflects the real structure?
- [ ] Key Patterns use real code from the project?
- [ ] No duplication with README.md?
- [ ] No outdated information?

---

## Ready-Made Templates

| Template | File |
|----------|------|
| Minimal skeleton | `SKELETON.md` |
| Next.js SaaS | `saas-nextjs.md` |
| React SPA | `react-spa.md` |
| NestJS API | `nestjs.md` |
| Express + Prisma | `express-prisma.md` |
| Vue + Nuxt | `vue-nuxt.md` |
| Go Microservice | `go-microservice.md` |
| Django REST API | `django-api.md` |
| FastAPI | `fastapi.md` |
| Monorepo | `monorepo.md` |

Copy the matching template to your project root as `CLAUDE.md` and customize it.
