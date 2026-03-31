# Coding Style

## Immutability
- Always create new objects, never mutate existing ones
- Spread operator, `.map()`, `.filter()` instead of push/splice/direct assignment

## File Size
- 200-400 lines — typical size
- 800 lines — absolute maximum
- If a file grows — decompose by responsibility

## Functions
- Maximum 50 lines per function
- One function — one responsibility
- Maximum 4 nesting levels — extract to early return or separate function

## Naming
- Variables and functions: descriptive names reflecting purpose
- Booleans: prefix with is/has/can/should (`isLoading`, `hasAccess`)
- Constants: UPPER_SNAKE_CASE
- No abbreviations except commonly accepted (id, url, api)

## Error Handling
- Always handle errors explicitly
- Never swallow errors silently (empty catch)
- User-facing messages must not reveal internal details

## Input Validation
- Validate at system boundaries: user input, external APIs, env vars
- Internal code between layers — trust types and contracts

## Imports
- Group: stdlib → third-party → local
- No wildcard imports (`import *`, `from x import *`)
- Unused imports — remove immediately

## Comments
- Comment "why", not "what"
- Don't add obvious comments to self-documenting code
- TODOs are acceptable only with description and context
