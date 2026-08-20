# Configure Caching

Learn how pin-actions' in-memory caching works to avoid redundant API calls.

## In-Memory Cache

By default, pin-actions maintains an in-memory cache of resolved refs during a single run. Multiple references to the same `actions/checkout@v4` within the same session result in only one API call.

This cache is:
- **Automatic** — no configuration needed
- **Scoped to the client's lifetime** — shared across all files processed in a single run
- **Safe for concurrent async use** — Single-threaded asyncio event loop provides atomicity; no locks needed

## How It Works

When you run pin-actions against multiple files or repositories:

1. **First ref encounter**: API call is made, result cached in memory
2. **Subsequent encounters**: Cache hit, result returned instantly (no API call)
3. **Across multiple files in one run**: All files share the same cache, so `actions/checkout@v4` is only fetched once even if used in 100 workflows

**Example**: A batch update of 50 repositories where every repo uses `actions/checkout@v4` and `actions/setup-python@v4`:

- Unauthenticated runs: ~2 API calls (1 per unique action, 50 repos ÷ 25 refs per repo ≈ massive savings)
- Authenticated runs: Same, plus batch tag operations if using `--update`

## Disable Caching (Advanced)

To skip in-memory caching (rare, for debugging only):

```bash
# Recreate client for each file
# (no direct flag; use library API if needed)
```

For library usage, create a new client per file:

```python
import asyncio
from pathlib import Path
from pin_actions import GitHubClient, Settings, pin_file


async def process_files_without_cache():
    files = [Path("repo1/.github/workflows/ci.yml"), Path("repo2/.github/workflows/ci.yml")]
    token = "ghp_xxxx"

    # Fresh client per file = fresh cache each time
    for file in files:
        async with GitHubClient(token=token) as client:
            await pin_file(client, file)
```

**Preferred**: Share a client across files for cache benefits (see below).

## Library Usage: Shared Client Pattern

Control caching programmatically by reusing a single client:

```python
from pin_actions import GitHubClient, Settings, run
import asyncio
from pathlib import Path


async def batch_update():
    repos = [Path("./repo1"), Path("./repo2"), Path("./repo3")]

    # Single client = shared cache across all repos
    async with GitHubClient(token="ghp_xxxx", concurrency=10) as client:
        for repo_path in repos:
            settings = Settings(path=repo_path / ".github/workflows", dry_run=False)
            modified = await run(settings, client=client)
            print(f"{repo_path}: {len(modified)} files pinned")


asyncio.run(batch_update())
```

Benefits:
- **Connection pooling** — reuses HTTP connections across repos
- **In-memory cache hits** — refs shared across repos (e.g., all using `actions/checkout@v4`) cached once
- **Unified rate-limit handling** — semaphore bounds all API calls globally

## Cache Tuning

Control in-memory cache size:

```python
from pin_actions import GitHubClient

# Bounded cache (default: 1000 entries, LRU eviction)
client = GitHubClient(token="ghp_xxxx", max_cache_size=1000)

# Unbounded cache (0 = no eviction, memory unbounded)
client = GitHubClient(token="ghp_xxxx", max_cache_size=0)
```

Typical usage:
- **Default (1000)**: Safe for most workflows; evicts least-recently-used entries on overflow
- **0 (unbounded)**: For batch operations on very large repositories or repos with many unique actions

## See Also

- [Reference: Settings](../reference/config.md) — All configuration options
- [Reference: Client](../reference/client.md) — `GitHubClient` constructor details
- [Multi-Repo Automation](./multi-repo-automation.md) — Batch processing with shared client
