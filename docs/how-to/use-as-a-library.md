# Use as a Library

Import pin-actions directly into your Python code for programmatic access.

## Basic Usage

```python
import asyncio
from pathlib import Path
from pin_actions import GitHubClient, run
from pin_actions.config import Settings

async def main():
    settings = Settings(
        path=Path(".github/workflows"),
        github_token="ghp_xxxx",
        dry_run=False,
        concurrency=5,
    )
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
    client = GitHubClient(token="ghp_xxxx", concurrency=10)

    # Resolve mutable ref to commit SHA
    sha = await client.resolve_sha("actions/checkout", "v4")
    print(f"actions/checkout@v4 -> {sha}")

asyncio.run(main())
```

## Per-File Pinning

Pin a single workflow file:

```python
import asyncio
from pathlib import Path
from pin_actions import GitHubClient, pin_file

async def main():
    async with GitHubClient(token="ghp_xxxx") as client:
        modified = await pin_file(
            client,
            Path(".github/workflows/ci.yml"),
            dry_run=False,
            update="minor",
        )
        if modified:
            print("File was updated")

asyncio.run(main())
```

## Error Handling

Library functions raise exceptions; you decide how to handle them:

```python
import asyncio
from pin_actions import (
    PinActionsError,
    InvalidRefError,
    YAMLParseError,
    RateLimitExhaustedError,
    pin_file,
)

async def main():
    try:
        modified = await pin_file(client, path)
    except YAMLParseError as exc:
        print(f"Bad YAML in {exc.path}: {exc.reason}")
    except InvalidRefError as exc:
        print(f"{exc.repo}@{exc.ref} does not exist")
    except RateLimitExhaustedError as exc:
        print(f"Rate limited after {exc.attempts} attempts")
    except PinActionsError as exc:
        print(f"Pin failed: {exc}")

asyncio.run(main())
```

## Batch Processing with Error Details

When processing multiple files, catch the `ExceptionGroup` to inspect per-file failures:

```python
import asyncio
from pin_actions import run, PinActionsError

async def main():
    try:
        modified = await run(settings)
        print(f"Success: {len(modified)} files")
    except ExceptionGroup as eg:
        print(f"Errors: {len(eg.exceptions)} file(s) failed")
        for exc in eg.exceptions:
            print(f"  - {exc}")

asyncio.run(main())
```

## See Also

- [Reference: core](../reference/core.md) — `run()`, `pin_file()`
- [Reference: client](../reference/client.md) — `GitHubClient` full API
- [Reference: errors](../reference/errors.md) — Exception hierarchy
