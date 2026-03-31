# CLAUDE.md

## Project Overview

**Stack:** Nuxt 3, Vue 3, TypeScript, Pinia, Tailwind CSS, Vitest + Playwright
**Architecture:** Full-stack Nuxt with SSR by default. File-based routing, auto-imported composables. Pinia stores per feature domain. Server API routes via Nitro (H3). Client-side interactivity via `<script setup>`.
**Purpose:** [describe the application]

## Critical Rules

### Components
- Composition API only — no Options API
- `<script setup lang="ts">` in every component
- Props via `defineProps<T>()` with TypeScript interface — no runtime validation
- Emits via `defineEmits<T>()` — always typed
- One component per file, filename matches component name (PascalCase)

### Data Fetching
- `useFetch()` or `useAsyncData()` for all data fetching in pages/components
- Never raw `$fetch()` in components — only in Pinia actions or server routes
- Always handle loading and error states
- Key parameter required for `useAsyncData()` to enable proper caching

### State Management
- Pinia stores for shared state — one store per feature domain
- Server state via `useFetch()` / `useAsyncData()` — don't duplicate in Pinia
- Pinia for UI state only (sidebar open, selected filters, form drafts)
- No prop drilling deeper than 2 levels — use `provide`/`inject` or Pinia

### Routing
- File-based routing in `pages/` — don't create manual route configs
- `definePageMeta()` for auth guards and layout selection
- Dynamic routes via `[param]` naming convention
- Middleware in `middleware/` for auth and redirects

### Server
- Server API routes in `server/api/` — H3 event handlers
- `readBody()` for POST data, `getQuery()` for query params
- Always validate input with Zod in server routes
- Database access only in `server/` — never in client-side code

### Forbidden
- Options API (`data()`, `methods`, `computed`, `watch` as options)
- `any` in TypeScript
- `console.log` in production code
- `$fetch()` in components (use `useFetch()` or `useAsyncData()`)
- Direct DOM manipulation — use template refs and Vue reactivity
- CSS-in-JS — use Tailwind or scoped `<style>`

## File Structure

```
app/
  pages/
    index.vue                # Home page
    login.vue                # Auth page
    dashboard/
      index.vue              # Dashboard main
      [id].vue               # Dynamic route
  components/
    ui/                      # Generic UI (Button, Modal, Input)
    layout/                  # Header, Sidebar, Footer
    features/                # Feature-specific components
  composables/
    useAuth.ts               # Auth composable
    useNotification.ts       # Toast/notification composable
  stores/
    auth.ts                  # Auth Pinia store
    ui.ts                    # UI state store
  middleware/
    auth.ts                  # Route auth guard
  layouts/
    default.vue              # Default layout with nav
    auth.vue                 # Auth pages layout
server/
  api/
    auth/
      login.post.ts          # POST /api/auth/login
      register.post.ts
    users/
      index.get.ts           # GET /api/users
      [id].get.ts            # GET /api/users/:id
  middleware/
    auth.ts                  # Server auth middleware
  utils/
    db.ts                    # Database client
    validate.ts              # Zod validation helper
public/
  assets/
```

## Key Patterns

### Page with Data Fetching
```vue
<script setup lang="ts">
definePageMeta({ middleware: "auth" })

const route = useRoute()
const { data: order, status } = await useFetch(`/api/orders/${route.params.id}`)
</script>

<template>
  <div v-if="status === 'pending'">
    <LoadingSpinner />
  </div>
  <div v-else-if="status === 'error'">
    <ErrorMessage message="Failed to load order" />
  </div>
  <div v-else-if="order">
    <OrderDetails :order="order" />
  </div>
</template>
```

### Pinia Store
```typescript
// stores/auth.ts
export const useAuthStore = defineStore("auth", () => {
  const user = ref<User | null>(null)
  const isAuthenticated = computed(() => user.value !== null)

  async function login(credentials: LoginInput) {
    const data = await $fetch("/api/auth/login", {
      method: "POST",
      body: credentials,
    })
    user.value = data.user
    return navigateTo("/dashboard")
  }

  async function logout() {
    await $fetch("/api/auth/logout", { method: "POST" })
    user.value = null
    return navigateTo("/login")
  }

  return { user, isAuthenticated, login, logout }
})
```

### Server API Route
```typescript
// server/api/orders/index.post.ts
import { z } from "zod"

const createOrderSchema = z.object({
  productId: z.string().uuid(),
  quantity: z.number().int().min(1).max(100),
})

export default defineEventHandler(async (event) => {
  const session = await requireAuth(event)
  const body = await readValidatedBody(event, createOrderSchema.parse)

  const order = await db.order.create({
    data: { ...body, userId: session.userId },
  })

  setResponseStatus(event, 201)
  return order
})
```

## Environment Variables

```
NUXT_PUBLIC_API_BASE=         # optional, API base URL for client-side
NUXT_DATABASE_URL=            # required, server-only, postgresql://...
NUXT_SESSION_SECRET=          # required, server-only, session encryption
NUXT_PUBLIC_APP_TITLE=        # optional, shown in browser tab
```

## Git Workflow

- Format: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`
- CI: eslint, nuxt typecheck, vitest (unit), playwright (e2e)
- Feature branches from main, PR required
- Deploy: Vercel / Netlify / Docker with Node.js server
