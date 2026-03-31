# Dependencies

## When to Add a Package
- The problem is complex and the package is well-maintained (>1k stars, recent commits)
- Implementing it yourself would take >2 hours and be worse than the package
- The package doesn't pull in a large transitive dependency tree

## When NOT to Add a Package
- The functionality is achievable in <50 lines of code
- The package is unmaintained (no commits in 12+ months, open security issues)
- You only need 5% of what the package offers
- A built-in/stdlib solution exists (don't add lodash for `_.get`, use optional chaining)

## Selection Criteria
- Active maintenance: recent commits, responsive to issues
- Minimal dependencies: check the dependency tree before installing
- Security track record: no unpatched CVEs
- Bundle size matters for frontend — check with bundlephobia or similar
- License compatibility (MIT/Apache preferred)

## Rules
- Pin exact versions in lockfiles — always commit lockfiles
- Never install packages with `--force` or `--legacy-peer-deps` without understanding why
- Run `npm audit` / `pip audit` / `go vuln` after adding new packages
- Remove unused dependencies — don't leave dead packages in the manifest
- Prefer one package per concern — don't install 3 date libraries

## Updates
- Keep dependencies reasonably up to date (dependabot / renovate)
- Read changelogs before major version bumps
- Update one dependency at a time, run tests after each
