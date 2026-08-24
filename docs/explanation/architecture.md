# Architecture Overview

`pin-actions` combines async I/O, thread-safe caching, intelligent rate-limiting, and round-trip YAML editing to process workflows efficiently while preserving comments and formatting.

## High-Level Flow

```mermaid
sequenceDiagram
    participant CLI
    participant run
    participant pin_file as pin_file()
    participant Client as GitHubClient
    participant YAML as yamlrocks
    participant GH as GitHub API

    CLI->>run: Settings (path, token, etc.)
    run->>run: glob *.yml files

    loop For each file
        run->>pin_file: client, path
        pin_file->>YAML: load & parse
        YAML-->>pin_file: AST
        pin_file->>pin_file: collect uses: entries
        pin_file->>pin_file: batch resolve unique refs

        rect rgb(200, 230, 255)
            note over pin_file,Client: Ref resolution (cached)
            pin_file->>Client: resolve_sha(repo, "v4")

            alt Cache hit (memory)
                Client-->>pin_file: cached SHA ✓
            else Cache miss
                Client->>Client: check disk cache

                alt Disk cache hit
                    Client-->>pin_file: SHA from disk ✓
                else Disk miss → fetch
                    Client->>GH: GET /repos/{repo}/commits/{ref}
                    GH-->>Client: {"sha": "abc123..."}
                    Client->>Client: write to disk cache
                    Client-->>pin_file: SHA ✓
                end
            end
        end

        pin_file->>pin_file: rewrite changed entries
        pin_file->>YAML: set new SHAs + comments
        YAML-->>pin_file: modified AST
        pin_file->>pin_file: compare bytes

        alt Changed
            pin_file->>pin_file: write file (unless --dry-run)
        end

        pin_file-->>run: bool (changed?)
    end

    run-->>CLI: list[modified_paths]
```

## Entry Points

- **CLI**: `pin_actions.core.main()` — parses CLI args, calls `run()`
- **Library**: `pin_actions.run()` — orchestrator; processes all files
- **Per-file**: `pin_actions.pin_file()` — single workflow/action file
- **Direct client**: `GitHubClient.resolve_sha()` — resolve one ref

## YAML Round-Trip Editing

`pin_file()` uses `yamlrocks` (Rust-backed, preserves comments/formatting):

```python
doc = yamlrocks.loads(content, option=yamlrocks.OPT_ROUND_TRIP)

# Find all "uses:" paths
for path, value in doc.walk():
    if path and path[-1] == "uses" and isinstance(value, str):
        # Process, resolve, rewrite

# Rewrite: write to AST only as unbroken indexing chain
doc[...][...][...] = new_sha
doc.locate(path).comment = tag

# Serialize: only mutated nodes rewritten, everything else preserved
new_content = doc.to_yaml()
```

## Concurrency model

### Async/await foundation

- `run()` orchestrates all file processing as async tasks
- `pin_file()` performs file I/O and parsing (sync, CPU-bound)
- `GitHubClient.resolve_sha()` and `list_tags()` are async for API calls (I/O-bound)

### HTTP connection pooling

`GitHubClient` maintains a single `httpx2.AsyncClient` (lazily initialized) across all requests:

```python
client = await self._get_http_client()  # reused across all calls
# → connection pooling, TCP keep-alive, performance boost
```

Use `async with GitHubClient(...) as client:` for deterministic cleanup.

### Rate limiting via semaphore

```python
_semaphore = asyncio.Semaphore(concurrency)
async with self._semaphore:
    # GitHub API request
```

- Default concurrency: 5 concurrent requests
- Prevents 429 Too Many Requests errors
- All requests wait if semaphore is at capacity

### Rate-limit backoff decision tree

```mermaid
flowchart TD
    A["HTTP Request"] --> B{Status Code}
    B -->|200| C["✓ Return result"]
    B -->|404| D["✗ Raise InvalidRefError<br/>(ref doesn't exist)"]
    B -->|429 or 403| E["Retry Backoff"]
    B -->|5xx| F["Retry Backoff"]
    B -->|other 4xx| G["✗ Raise error<br/>(abort immediately)"]

    E --> H{"Retry Limit<br/>Exceeded?"}
    H -->|Yes| I["✗ Raise RateLimitExhaustedError"]
    H -->|No| J["delay = 2^attempt + jitter<br/>max 60s<br/><br/>if Retry-After header:<br/>  delay = parse header"]

    F --> H

    J --> K["await asyncio.sleep(delay)"]
    K --> A

    C --> L["✓ Success"]
    D --> L
    G --> L
    I --> L
```

**Exponential backoff formula:**
```
delay = 2^attempt + random(0, 1)  # capped at 60s
```

With `Retry-After` header, GitHub's advised delay is respected.

**Retry limit:** `max_retries` (default 5)

### In-memory LRU cache

`_Cache[T]` (`pin_actions/client.py`) guards its `OrderedDict` store and
in-flight task map with a `threading.Lock`, held only around the dict
mutations themselves — never across an `await`. This makes the cache
correct both under asyncio's single-threaded cooperative scheduling *and*
under a free-threaded (PEP 779, no-GIL) interpreter where multiple OS
threads might drive separate event loops against the same client instance.

```python
_sha_cache: _Cache[str]                       # (repo, ref) -> sha
_tags_cache: _Cache[list[tuple[str, str]]]    # repo -> tags
_date_cache: _Cache[str]                      # (repo, sha) -> commit date
```

**Pattern:** in-memory cache → fetch (semaphore-gated) → write-through cache

**LRU eviction:** `OrderedDict` + `move_to_end()` on hit; auto-evict oldest when `len(cache) > max_cache_size` (default 1000).

### Performance

| Scenario | Time |
|----------|------|
| Single workflow, 5 actions, cached | ~100ms |
| 10 workflows, 50 unique actions, cold | ~2-5s |
| Same 10 workflows again, warm cache | ~10-50ms |
| Batch with 429 retry | ~60s worst-case |

## Container image pinning

`ContainerRegistryClient` (`pin_actions/registry.py`) resolves `docker://` step
refs, `jobs.<job>.container.image`, and `jobs.<job>.services[*].image` tags to
immutable `sha256:` content digests, using the same OCI Distribution Spec /
Docker Registry v2 Bearer-token flow shared by all public registries (Docker
Hub, GHCR, Quay.io, MCR, etc.):

1. Anonymous `HEAD /v2/{name}/manifests/{tag}` request.
2. If `401` with a `WWW-Authenticate: Bearer realm=...,service=...,scope=...`
   challenge, exchange it anonymously for a token (GitHub token only injected
   for `ghcr.io`, enabling private GHCR image resolution).
3. Retry the `HEAD` with the token; read `Docker-Content-Digest`.

Registries using non-Bearer auth (ECR SigV4, GCR OAuth) raise
`UnsupportedRegistryError`, which is caught per-image — the entry is left
untouched and a warning logged, rather than failing the whole file. Reuses
the same `_Cache[T]` (LRU + single-flight dedup) and lazy `httpx2.AsyncClient`
patterns as `GitHubClient`. Toggle via `Settings.image_pin` (default `True`).

## See Also

- [Design Decisions](design-decisions.md) — Why these choices
- [Threat Model](threat-model.md) — The supply-chain attack model this tool defends against
- [Reference: client](../reference/client.md) — `GitHubClient` API
