# Linting

## Core Rule
If the project has a linter/formatter configured — follow it. Do not override, argue with, or work around its rules.

## Do Not Modify
- Never change linter/formatter config files without explicit request
- This includes: `.eslintrc`, `biome.json`, `.prettierrc`, `ruff.toml`, `pyproject.toml` [tool.ruff], `.golangci.yml`, etc.

## Disable Comments
- Never add suppression comments (`// eslint-disable`, `# noqa`, `//nolint`) without a clear reason
- If suppression is genuinely needed — add a comment explaining WHY, not just the directive
- Acceptable: `// eslint-disable-next-line no-console -- debug logging for staging only`
- Not acceptable: `// eslint-disable-next-line no-console`

## Before Committing
- Run the project's lint/format command if it exists
- Fix lint errors in your changes — don't leave them for someone else
- Don't fix lint errors in code you didn't change — that's a separate refactoring task

## When Linter and Rule Conflict
- Linter config wins over general Claude rules — it's the project's source of truth
- Example: if the project's Prettier is set to tabs, use tabs even if you'd prefer spaces
