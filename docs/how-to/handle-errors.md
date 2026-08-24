# Handle Errors

Recover from common pin-actions failure modes.

## YAML Parse Error

Raised when a workflow or action file is not valid YAML:

```python
from pin_actions import YAMLParseError, pin_file

try:
    await pin_file(client, Path("workflow.yml"))
except YAMLParseError as exc:
    print(f"Bad YAML in {exc.path}: {exc.reason}")
```

## Invalid Ref Error

Raised when a ref (branch, tag, or SHA) doesn't exist on the remote:

```python
from pin_actions import InvalidRefError

try:
    sha = await client.resolve_sha("actions/checkout", "nonexistent-ref")
except InvalidRefError as exc:
    print(f"Ref not found: {exc.repo}@{exc.ref}")
```

## Rate Limit Exhausted

Raised when GitHub API rate limits are hit and retries are exhausted:

```python
from pin_actions import RateLimitExhaustedError

try:
    sha = await client.resolve_sha("actions/checkout", "v4")
except RateLimitExhaustedError as exc:
    print(f"Rate limited after {exc.attempts} attempts: {exc.repo}@{exc.ref}")
```

Mitigate with:

- Authenticated requests (use `--github-token`)
- Increased `--max-retries`
- Reduced `--concurrency` (fewer simultaneous requests)

## Auth Error

Raised on 401/403 responses that aren't rate-limiting (bad token, insufficient scope):

```python
from pin_actions import AuthError

try:
    sha = await client.resolve_sha("actions/checkout", "v4")
except AuthError as exc:
    print(f"Auth failed: {exc}")
```

Check that `--github-token`/`GITHUB_TOKEN` is set and has `repo` read scope.

## Network Error

Raised on DNS, connection, or timeout failures:

```python
from pin_actions import NetworkError

try:
    sha = await client.resolve_sha("actions/checkout", "v4")
except NetworkError as exc:
    print(f"Network error: {exc}")
```

## Unsupported Registry

Raised when a container registry doesn't support anonymous Bearer auth (e.g. ECR, GCR).
`run()`/`pin_file()` catch this per-image internally — the entry is left untouched and a
warning is logged, so this only surfaces if you call `ContainerRegistryClient.resolve_digest()`
directly:

```python
from pin_actions.errors import UnsupportedRegistryError
from pin_actions.registry import ContainerRegistryClient

client = ContainerRegistryClient()
try:
    digest = await client.resolve_digest("123456789.dkr.ecr.us-east-1.amazonaws.com/app", "v1")
except UnsupportedRegistryError as exc:
    print(f"Cannot pin {exc.registry}: {exc.reason}")
```

## Batch Processing


When using `run()`, per-file errors are collected into an `ExceptionGroup`:

```python
from pin_actions import run

try:
    modified = await run(settings)
except ExceptionGroup as eg:
    print(f"{len(eg.exceptions)} file(s) failed:")
    for exc in eg.exceptions:
        print(f"  - {exc}")
```

If you need partial results (process some files, skip others on error), call `pin_file()` directly for each file.

## CLI Error Handling

The CLI catches all `PinActionsError` subclasses and prints them to stderr:

```bash
$ pin-actions --github-token $TOKEN .github/workflows
Error: Ref not found: actions/checkout@fake-ref
```

## Best Practices

1. **Use authenticated tokens** — increases rate limits (60 → 5000 req/hr)
2. **Catch specific exceptions** — handle `InvalidRefError` differently from `RateLimitExhaustedError`
3. **Log context** — include the repo, ref, and file path in error messages
4. **Retry judiciously** — `max_retries` applies per-ref, not per-batch
5. **Check dry-run first** — validate workflows before making changes

## See Also

- [Reference: errors](../reference/errors.md) — Exception hierarchy and exit codes
- [Tutorial: Getting Started](../tutorials/getting-started.md) — CLI example
