# Exception Reference

Exception hierarchy, import paths, attributes, and CLI exit codes.

## Hierarchy

```text
PinActionsError                    # base for all errors
├── YAMLParseError                 # malformed YAML
├── GitHubAPIError                 # base for GitHub API failures
│   ├── AuthError                  # 403 that is not rate limiting
│   ├── InvalidRefError            # 404: ref does not exist
│   ├── RateLimitExhaustedError    # retries exhausted while rate-limited
│   ├── NetworkError               # unrecoverable network failure
│   └── UnverifiedProvenanceError  # --provenance strict: SHA not reachable from a real ref
└── UnsupportedRegistryError       # registry does not support anonymous Bearer auth (e.g. ECR, GCR)
```

## Catalogue

| Exception                   | Raised when                                                                                                                                               | Useful attributes                                                       | Remedy                                                                                                                                                                                                       |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `PinActionsError`           | Base class. `run()` also wraps non-`PinActionsError` per-file failures (for example `OSError`) in this type before collecting them.                       | —                                                                       | Catch as a last resort after the specific types below.                                                                                                                                                       |
| `YAMLParseError`            | A workflow or action file cannot be parsed as YAML.                                                                                                       | `path`, `reason`                                                        | Fix the YAML syntax. The file is never rewritten when parsing fails.                                                                                                                                         |
| `GitHubAPIError`            | Base for GitHub API failures. Raised directly when tag listing 404s, which means the repository itself was not found.                                     | —                                                                       | Confirm the repository exists and the token can read it.                                                                                                                                                     |
| `AuthError`                 | A GitHub API request returns 403 and the `x-ratelimit-remaining` header is not `0`.                                                                       | `path` (API path, not a file path)                                      | Set `--github-token` / `GITHUB_TOKEN` to a token with read access to the repository.                                                                                                                         |
| `InvalidRefError`           | A ref (branch, tag, or commit SHA) returns 404.                                                                                                           | `repo`, `ref`                                                           | Correct the ref. `resolve_sha()` and `get_commit_date()` re-raise with the real repo and ref; raised from any other API path, `repo` holds the API base URL and `ref` holds the request path.                |
| `RateLimitExhaustedError`   | Retries are exhausted while rate-limited (403 with `x-ratelimit-remaining: 0`, 429, or 5xx).                                                              | `repo` (API base URL), `ref` (request path), `attempts`                 | Authenticate the run (60 → 5000 requests/hour), raise `--max-retries`, or lower `--concurrency`.                                                                                                             |
| `NetworkError`              | Every attempt fails with a transport error (DNS, connection, timeout).                                                                                    | —                                                                       | Check connectivity and proxy configuration, then retry with a higher `--max-retries`.                                                                                                                        |
| `UnverifiedProvenanceError` | `--provenance strict` is active and a resolved SHA is not reachable from a branch head, tag, or pull request on the named repository.                     | `repo`, `sha`, `reason`                                                 | Verify the commit upstream. Then pin a different ref, or drop to `--provenance warn` to log instead of fail.                                                                                                 |
| `UnsupportedRegistryError`  | A container registry does not offer anonymous Bearer auth (ECR, GCR), returns no `Docker-Content-Digest` header, or the image reference cannot be parsed. | `registry` (registry host, or the unparsable image reference), `reason` | None required for normal runs: `run()` and `pin_file()` catch this per image, log a warning, and leave the entry untouched. It only propagates from direct `ContainerRegistryClient.resolve_digest()` calls. |

`AuthError` covers 403 only.
A 401 response is not mapped into this hierarchy; it surfaces as an `httpx2.HTTPStatusError`,
which `run()` then wraps in a `PinActionsError` while collecting per-file failures.

## Import paths

Six names are re-exported from the package root:

```python
from pin_actions import (
    GitHubAPIError,
    InvalidRefError,
    NetworkError,
    PinActionsError,
    RateLimitExhaustedError,
    YAMLParseError,
)
```

`AuthError`, `UnverifiedProvenanceError`, and `UnsupportedRegistryError` are not in `pin_actions.__all__`.
Import them from the module:

```python
from pin_actions.errors import AuthError, UnsupportedRegistryError, UnverifiedProvenanceError
```

## Batch failures from `run()`

`run()` processes every file concurrently and collects per-file failures instead of aborting the batch.
It raises an `ExceptionGroup` when any file fails, and returns no partial results in that case:

```python
from pin_actions import run

try:
    modified = await run(settings)
except ExceptionGroup as eg:
    print(f"{len(eg.exceptions)} file(s) failed:")
    for exc in eg.exceptions:
        print(f"  - {exc}")
```

Call `pin_file()` per file instead when you need the successful results alongside the failures.

::: pin_actions.errors

## CLI exit codes

- `0` — success, including `--version`, a no-op run, and `--dry-run`/`--diff` runs that report pending changes.
- `1` — any `PinActionsError`, the `ExceptionGroup` raised by `run()`,
  or a `ValueError` from an invalid `--exclude-newer` value.
  `main()` prints `Error: <message>` to stderr, listing each sub-exception for an `ExceptionGroup`.
- `2` — invalid command-line usage, such as an unknown flag or an out-of-range value,
  reported by the pydantic-settings argument parser.

`--diff` does not report pin drift through the exit status.
It implies `--dry-run`, prints a unified diff to stdout, and still exits `0` when refs would change.
Gate CI on the presence of diff output, not on the exit code.

## See Also

- [Reference: core](core.md) — `run()`, `pin_file()`, `main()`
- [Reference: client](client.md) — `GitHubClient` request and retry behavior
- [How-To: Use as a Library](../how-to/use-as-a-library.md) — Calling the library directly
- [How-To: Verify Provenance](../how-to/verify-provenance.md) — `--provenance` modes
