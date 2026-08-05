# Destructive Operations

- Never discard uncommitted changes without explicit user approval.
- Prefer `git status`, `git diff`, dry-run and backup commands first.
- Never deploy, publish, force-push or modify production resources implicitly.
- When a destructive action is necessary, explain its impact and request approval.
- Never bypass repository hooks or CI checks.
- Treat production, credential and infrastructure operations as high risk.

## Git Operations

- Check repository state with `git status` and `git diff` before destructive Git commands.
- Do not use `git reset --hard`, `git clean`, branch deletion, history rewrite, or force-push without explicit user approval.
- Never discard, overwrite, or hide uncommitted user changes without approval.
- Prefer safer Git operations that preserve recovery options.

## Filesystem Operations

- Treat recursive deletion, broad glob deletion, ownership changes, and permission changes as destructive.
- Before deleting or overwriting files, identify the exact paths affected and whether they are tracked, generated, or user-authored.
- Prefer dry-run, listing, backup, or move-to-trash workflows before irreversible operations.
- Never delete project roots, parent directories, home directories, `.git`, credentials, or unknown paths.

## Infrastructure Operations

- Treat infrastructure, deployment, cluster, cloud, and production commands as high risk.
- Run planning or inspection commands before applying changes.
- Never deploy, destroy, scale, delete, or mutate production resources implicitly.
- Confirm target environment, account, namespace, workspace, and branch before proposing infrastructure changes.

## Database Operations

- Treat migrations, schema changes, truncation, deletion, restore, and direct production writes as high risk.
- Prefer backups, dry-run migrations, transactions, and staging validation first.
- Never run destructive database commands against production without explicit approval and rollback context.
- Explain likely data impact before any operation that can remove or rewrite records.

## Package Publication

- Treat package publication, release creation, and unpublish operations as high risk.
- Confirm package name, version, registry, release target, and credentials before publishing.
- Never publish, unpublish, or create releases implicitly.
- Prefer local validation, changelog review, and dry-run publication commands when available.

## Secrets

- Treat credential files, tokens, keys, kubeconfigs, cloud credentials, and deployment secrets as high risk.
- Never print, copy, move, delete, or upload secrets without explicit user approval.
- Prefer redacted summaries over exposing raw secret values.
- If a secret may have been exposed, recommend rotation and audit steps.

## Preferred Safe Alternatives

- `git push --force` -> `git push --force-with-lease`
- `git reset --hard` -> `git status` and `git diff`, then ask for approval
- `git clean -fdx` -> `git clean -ndx`
- `rm -rf path` -> `ls path`, confirm exact target, then ask for approval
- `terraform apply` -> `terraform plan`
- `terraform destroy` -> `terraform plan -destroy`
- `kubectl delete` -> `kubectl get` or `kubectl describe`
- `helm uninstall` -> `helm status` and `helm get values`
- `npm publish` -> `npm publish --dry-run`
- `curl URL | sh` -> download, inspect, execute
