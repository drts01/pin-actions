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

## Multi-Repo Processing with a Shared Client

Reuse one `GitHubClient` across multiple repositories to share connection pooling, in-memory caching, and rate-limit bookkeeping:

```python
import asyncio
from pathlib import Path
from pin_actions import GitHubClient, Settings, run


async def main():
    repos = [Path("/repos/service-a"), Path("/repos/service-b")]
    async with GitHubClient(token="ghp_xxxx", concurrency=10) as client:
        for repo_path in repos:
            settings = Settings(
                path=repo_path / ".github",
                dry_run=False,
            )
            try:
                modified = await run(settings, client=client)
                print(f"{repo_path}: {len(modified)} file(s) pinned")
            except ExceptionGroup as eg:
                print(f"{repo_path}: {len(eg.exceptions)} error(s)")


asyncio.run(main())
```

This pattern is especially efficient when many repositories share common actions (e.g. `actions/checkout@v4`), because the shared client's in-memory cache avoids redundant API calls.

## Real-World Example: `scripts/update_repos.py`

[`scripts/update_repos.py`](https://github.com/drts01/pin-actions/blob/main/scripts/update_repos.py) is a complete, runnable example combining the patterns above with `gh`/`git` for cloning, committing, and opening PRs across many repositories. The library integration is a single async function:

```python
async def _try_pin(client: GitHubClient, repo_dir: Path, settings: UpdateReposSettings, result: RepoResult) -> bool:
    pin_settings = Settings(
        path=repo_dir / ".github",
        github_token=settings.token,
        dry_run=settings.dry_run,
        update=settings.update,
        full_version=settings.full_version,
    )

    try:
        result.modified = await run(pin_settings, client=client)
    except ExceptionGroup as eg:
        result.error = f"{len(eg.exceptions)} file(s) failed"
        return False
    except PinActionsError as exc:
        result.error = str(exc)
        return False
    except ValueError:
        return False
    return True
```

Run it directly:

```bash
uv run --with-editable . scripts/update_repos.py --repos org/repo1 --repos org/repo2 --dry-run
```

See [Multi-Repo Automation](./multi-repo-automation.md) for full CLI options and output formats.

## Pin Pre-Commit Hook Revs

The `pin_precommit_file` function pins GitHub-hosted `.pre-commit-config.yaml` `repos[].rev` entries the same way `core.pin_file` pins workflow refs — both share the `_pin_doc()` load/resolve/rewrite pipeline. Import it from the standalone script (`scripts/update_precommit.py`):

```python
import asyncio
from pathlib import Path
from pin_actions import GitHubClient

# Import from the script (not installed via pip, must be in repo)
import sys
sys.path.insert(0, "scripts")
from update_precommit import pin_precommit_file


async def main():
    async with GitHubClient(token="ghp_xxxx") as client:
        modified = await pin_precommit_file(
            client,
            Path(".pre-commit-config.yaml"),
            dry_run=False,
        )
        if modified:
            print("Pre-commit config was updated")


asyncio.run(main())
```

See [Pin Pre-Commit Hooks](./pin-pre-commit-hooks.md) for the `pin-precommit` CLI, or run `uv run --with-editable . scripts/update_precommit.py --help` for the equivalent standalone-script invocation.

## See Also

- [Reference: core](../reference/core.md) — `run()`, `pin_file()`
- [Reference: client](../reference/client.md) — `GitHubClient` full API
- [Reference: errors](../reference/errors.md) — Exception hierarchy
- [How-To: Multi-Repo Automation](./multi-repo-automation.md) — Batch script for organizations
- [How-To: Pin Pre-Commit Hooks](./pin-pre-commit-hooks.md) — `pin-precommit` CLI usage
