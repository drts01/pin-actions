# Caching

How pin-actions' in-memory cache avoids redundant GitHub API calls.

## In-Memory Cache

Every `GitHubClient` maintains an in-memory cache of resolved refs for its lifetime. Multiple references to the same `actions/checkout@v4` within one run result in only one API call.

This cache is:

- **Automatic** — no configuration needed
- **Scoped to the client's lifetime** — shared across all files processed in a single run
- **Safe for concurrent async use** — single-threaded asyncio event loop provides atomicity; no locks needed

## How It Works

1. **First ref encounter**: API call is made, result cached in memory.
2. **Subsequent encounters**: Cache hit, result returned instantly (no API call).
3. **Across multiple files in one run**: All files share the same cache, so `actions/checkout@v4` is only fetched once even if used in 100 workflows.

**Example**: A batch update of 50 repositories where every repo uses `actions/checkout@v4` and `actions/setup-python@v4`:

- Unauthenticated runs: ~2 API calls (1 per unique action) instead of ~100
- Authenticated runs: same, plus batch tag operations if using `--update`

## Cache Lifetime and Sharing

`run(settings)` (with no explicit `client=`) creates and closes a fresh `GitHubClient` per call — cache benefits are limited to files processed in that single call.

To share a cache across multiple `run()`/`pin_file()` calls (e.g. multiple repositories or `Settings` invocations), pass a shared client explicitly:

```python
from pin_actions import GitHubClient, Settings, run
import asyncio
from pathlib import Path


async def batch_update():
    repos = [Path("./repo1"), Path("./repo2"), Path("./repo3")]

    # Single client = shared cache across all repos
    async with GitHubClient(token="ghp_xxxx", concurrency=10) as client:
        for repo_path in repos:
            settings = Settings(path=repo_path / ".github", dry_run=False)
            modified = await run(settings, client=client)
            print(f"{repo_path}: {len(modified)} files pinned")


asyncio.run(batch_update())
```

Benefits of a shared client:

- **Connection pooling** — reuses HTTP connections across repos
- **In-memory cache hits** — refs shared across repos (e.g., all using `actions/checkout@v4`) cached once
- **Unified rate-limit handling** — semaphore bounds all API calls globally

## Cache Size

`GitHubClient(max_cache_size=...)` bounds the LRU cache (default 1000 entries per cache — SHA, tags, and commit-date caches are each independently bounded):

```python
from pin_actions import GitHubClient

# Bounded cache (default: 1000 entries, LRU eviction)
client = GitHubClient(token="ghp_xxxx", max_cache_size=1000)

# Unbounded cache (0 = no eviction, memory unbounded)
client = GitHubClient(token="ghp_xxxx", max_cache_size=0)
```

- **Default (1000)**: safe for most workflows; evicts least-recently-used entries on overflow.
- **0 (unbounded)**: for batch operations on very large repositories or repos with many unique actions.

There is no persistent (disk) cache — see [CHANGELOG](../changelog.md) for the rationale behind removing it.

## See Also

- [Reference: config](../reference/config.md) — All configuration options
- [Reference: client](../reference/client.md) — `GitHubClient` constructor details
- [How-To: Multi-Repo Automation](../how-to/multi-repo-automation.md) — Batch processing with shared client
