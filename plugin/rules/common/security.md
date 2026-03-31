# Security

## Pre-Commit Checklist
- [ ] No hardcoded secrets (keys, passwords, tokens)
- [ ] All user inputs validated
- [ ] SQL injection not possible (parameterized queries)
- [ ] XSS not possible (output escaping)
- [ ] Error messages don't reveal internals

## Authentication & Authorization
- Auth check on every endpoint — don't rely on defaults
- Tokens stored securely (httpOnly cookies, not localStorage for auth tokens)
- Rate limiting on all public endpoints
- CSRF protection on all mutating requests

## Data
- Secrets — only via environment variables, never in code
- Passwords — bcrypt/argon2, never plain text or MD5/SHA without salt
- Logging: never log passwords, tokens, PII
- `.env` files — in `.gitignore`, always

## Dependencies
- Regularly update dependencies (dependabot / renovate)
- Run `npm audit` / `pip audit` / `go vuln` before releases
- Don't install packages from untrusted sources

## When a Vulnerability Is Found
1. Stop current work
2. Assess severity (critical/high/medium/low)
3. Critical/High — fix immediately
4. Rotate compromised secrets
5. Check codebase for similar issues
