# Documentation

## Code Documentation
- Document "why", not "what" — the code shows what, comments explain intent
- Public APIs must have docstrings/JSDoc with parameter descriptions and return values
- No obvious comments: `// increment counter` above `counter++` is noise
- Complex algorithms: explain the approach in a comment block before the function
- TODO format: `TODO(context): description` — never bare `TODO` or `FIXME` without explanation

## Project Documentation
- README.md: how to set up, run, test, and deploy — nothing more
- Keep README under 200 lines — link to detailed docs if needed
- CLAUDE.md is for Claude, README.md is for humans — don't duplicate
- Architecture decisions: document in ADRs (Architecture Decision Records) if the team uses them

## API Documentation
- Endpoints must be documented — OpenAPI/Swagger for REST, protobuf comments for gRPC
- Include: method, path, request/response format, auth requirements, error codes
- Keep API docs generated from code when possible — manual docs drift

## What NOT to Document
- Implementation details that change frequently — they become lies
- Obvious type information already expressed by the type system
- Git history — that's what `git log` and `git blame` are for
- Anything that can be derived from reading the code in <30 seconds
