# CLAUDE.md

## Project Overview

**Stack:** React 19, TypeScript, Vite, React Router, TanStack Query, Tailwind CSS, Vitest + Playwright
**Architecture:** SPA with client-side routing. API calls via TanStack Query. State: server state in Query cache, UI state in React context/zustand. No SSR.
**Purpose:** [describe the application]

## Critical Rules

### Components
- Functional components only — no class components
- One component per file, filename matches component name
- Props: destructure in parameters with TypeScript interface
- Co-locate styles, tests, and types with the component
- Extract reusable logic into custom hooks

### Data Fetching
- All API calls through TanStack Query — never raw `fetch` in components
- Query keys must be consistent and predictable
- Mutations must invalidate related queries on success
- Loading and error states must be handled for every query

### Routing
- Route definitions in a central file (`routes.tsx`)
- Protected routes via auth wrapper component
- Lazy load route components with `React.lazy()`

### State Management
- Server state: TanStack Query (the cache IS the state)
- UI state: React context for global (theme, auth), `useState` for local
- No prop drilling deeper than 2 levels — use context or composition
- Never duplicate server data into local state

### Code Style
- No `any` — use `unknown` or proper types
- Zod for form validation and API response validation
- Immutable patterns only — spread, `.map()`, `.filter()`
- No `index` as key in lists

### Forbidden
- `any` in TypeScript
- `useEffect` for data fetching (use TanStack Query)
- Direct `fetch()` calls in components
- `var` — only `const`, `let` when necessary
- `console.log` in production code
- CSS-in-JS — use Tailwind

## File Structure

```
src/
  app/
    App.tsx              # Root component, providers
    routes.tsx           # Route definitions
  components/
    ui/                  # Generic UI components (Button, Modal, Input)
    layout/              # Layout components (Header, Sidebar, Footer)
  features/
    auth/                # Auth feature
      components/        # Feature-specific components
      hooks/             # Feature-specific hooks
      api.ts             # API functions for TanStack Query
      types.ts           # Feature types
    dashboard/
    settings/
  hooks/                 # Shared custom hooks
  lib/
    api-client.ts        # Axios/fetch wrapper with interceptors
    query-client.ts      # TanStack Query client config
    utils.ts             # General utilities
  types/                 # Shared TypeScript types
  stores/                # Zustand stores (if used)
public/
  assets/
```

## Key Patterns

### API + Query Pattern
```typescript
// features/orders/api.ts
import { apiClient } from "@/lib/api-client"
import type { Order, CreateOrderInput } from "./types"

export const ordersApi = {
  list: (params: { page: number }) =>
    apiClient.get<Order[]>("/orders", { params }),
  create: (data: CreateOrderInput) =>
    apiClient.post<Order>("/orders", data),
}

// features/orders/hooks/useOrders.ts
export function useOrders(page: number) {
  return useQuery({
    queryKey: ["orders", { page }],
    queryFn: () => ordersApi.list({ page }),
  })
}

export function useCreateOrder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ordersApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["orders"] })
    },
  })
}
```

### Protected Route
```typescript
function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, isLoading } = useAuth()

  if (isLoading) return <LoadingSpinner />
  if (!user) return <Navigate to="/login" replace />

  return children
}
```

### Form with Validation
```typescript
const orderSchema = z.object({
  productId: z.number().positive(),
  quantity: z.number().min(1).max(100),
})

type OrderForm = z.infer<typeof orderSchema>

function CreateOrderForm() {
  const { register, handleSubmit, formState: { errors } } = useForm<OrderForm>({
    resolver: zodResolver(orderSchema),
  })
  const createOrder = useCreateOrder()

  const onSubmit = (data: OrderForm) => createOrder.mutate(data)

  return <form onSubmit={handleSubmit(onSubmit)}>...</form>
}
```

## Environment Variables

```
VITE_API_URL=               # required, http://localhost:8000/api for dev
VITE_APP_TITLE=             # optional, shown in browser tab
```

## Git Workflow

- Format: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`
- CI: lint (eslint/biome), type-check (tsc), unit tests (vitest), E2E (playwright)
- Feature branches from main, PR required
- Deploy: Vercel / Netlify / S3+CloudFront
