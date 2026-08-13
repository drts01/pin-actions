# Configure Caching

Learn how to enable and customize pin-actions' caching behavior to avoid redundant API calls.

## In-Memory Cache

By default, pin-actions maintains an in-memory cache of resolved refs during a single run. Multiple references to `actions/checkout@v4` within the same session result in only one API call.

This cache is automatic and requires no configuration.

## Persistent Disk Cache

Enable persistent caching to reuse resolved refs across multiple runs:

```bash
pin-actions --cache --cache-dir ~/.cache/pin-actions --cache-ttl 3600
```

This requires the optional `diskcache-rs` dependency:

```bash
uv add 'pin-actions[cache]'
```

## Cache Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--cache` | bool | true | Enable persistent disk caching |
| `--no-cache` | bool | — | Disable persistent caching |
| `--cache-dir` | path | `~/.cache/pin-actions` | Directory for cache files |
| `--cache-ttl` | seconds | 3600 | Time-to-live for cache entries (1 hour) |

## Disable Caching

To skip all caching (in-memory and disk):

```bash
pin-actions --no-cache --github-token $GITHUB_TOKEN
```

Useful for:
- One-time runs without re-resolution
- Debugging ref resolution
- Offline workflows where cached data may be stale

## Cache Behavior

- **Cache hit**: Resolved SHA is returned immediately without an API call
- **Cache miss**: API call is made, result cached for TTL seconds
- **Expired entry**: After TTL expires, a fresh API call is made
- **Disk-first**: Persistent cache is checked before in-memory cache before hitting the API

## Library Usage

Control caching programmatically:

```python
from pin_actions import GitHubClient
from diskcache_rs import Cache

# Enable disk cache
disk_cache = Cache("/tmp/pin-actions-cache")

client = GitHubClient(
    token="ghp_xxxx",
    disk_cache=disk_cache,
    cache_ttl=7200,  # 2 hours
    max_cache_size=5000,  # Max entries in memory
)
```

## See Also

- [Reference: Settings](../reference/config.md) — All configuration options
- [Reference: Client](../reference/client.md) — `GitHubClient` constructor details
