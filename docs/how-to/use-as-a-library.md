# Use as a Library

Import pin-actions directly into your Python code for programmatic access.

## Basic Usage

```python
import asyncio
from pathlib import Path
from pin_actions import Settings, run


async def main():
    settings = Settings(paths=[Path(".github/workflows")], github_token="ghp_xxxx", concurrency=5)
    modified = await run(settings)
    print(f"Modified {len(modified)} file(s)")


asyncio.run(main())
```

## Direct Client Usage

Use `GitHubClient` directly to resolve refs without full file processing:

```python
import asyncio
from pin_actions import GitHubClient


async def main():
    async with GitHubClient(token="ghp_xxxx", concurrency=10) as client:
        sha = await client.resolve_sha("actions/checkout", "v4")
        print(f"actions/checkout@v4 -> {sha}")


asyncio.run(main())
```

## Per-File Pinning

Pin a single workflow file:

```python
import asyncio
from pathlib import Path
from pin_actions import GitHubClient, Settings, build_update_options, pin_file


async def main():
    options = build_update_options(Settings(update="minor"))
    async with GitHubClient(token="ghp_xxxx") as client:
        modified = await pin_file(client, Path(".github/workflows/ci.yml"), options=options)
        if modified:
            print("File was updated")


asyncio.run(main())
```

## Provenance Verification

`run()` forwards `settings.provenance` to every file,
and `pin_file()` accepts the same `"off"`/`"warn"`/`"strict"` values as its `provenance_mode` keyword:

```python
await run(Settings(provenance="strict"))

# client: a GitHubClient, as above
await pin_file(client, Path(".github/workflows/ci.yml"), provenance_mode="strict")
```

`"strict"` raises `UnverifiedProvenanceError` when a resolved SHA is not reachable from a real branch, tag,
or pull request on the named repository.
See [Verify Provenance](./verify-provenance.md) for the mode semantics.

## Multi-Repo Processing with a Shared Client

Reuse one `GitHubClient` across multiple repositories to share connection pooling, in-memory caching,
and rate-limit bookkeeping:

```python
import asyncio
from pathlib import Path
from pin_actions import GitHubClient, Settings, run


async def main():
    repos = [Path("/repos/service-a"), Path("/repos/service-b")]
    async with GitHubClient(token="ghp_xxxx", concurrency=10) as client:
        settings = Settings(dry_run=False)
        for repo_path in repos:
            try:
                modified = await run(settings, client=client, cwd=repo_path)
                print(f"{repo_path}: {len(modified)} file(s) pinned")
            except ExceptionGroup as eg:
                print(f"{repo_path}: {len(eg.exceptions)} error(s)")


asyncio.run(main())
```

A shared cache avoids redundant API calls when repositories use the same actions (e.g. `actions/checkout@v4`).

## Error Handling

Exception attributes, import paths, and the `ExceptionGroup` contract of `run()` are documented in
[Reference: errors](../reference/errors.md).

## See Also

- [Reference: core](../reference/core.md) — `run()`, `pin_file()`
- [Reference: client](../reference/client.md) — `GitHubClient` full API
- [Reference: errors](../reference/errors.md) — Exception hierarchy and exit codes
- [`scripts/update_repos.py`](https://github.com/drts01/pin-actions/blob/trunk/scripts/update_repos.py) —
  runnable multi-repo driver using these patterns with `gh`/`git`;
  see [Multi-Repo Automation](./multi-repo-automation.md) for its CLI options
- [`scripts/update_precommit.py`](https://github.com/drts01/pin-actions/blob/trunk/scripts/update_precommit.py) —
  `pin_precommit_file()` pins `.pre-commit-config.yaml` `repos[].rev` through the same pipeline as `pin_file()`;
  see [Pin Pre-Commit Hooks](./pin-pre-commit-hooks.md)
