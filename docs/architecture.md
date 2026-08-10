# Architecture

## Overview

`pin-actions` is a high-performance async utility for pinning mutable GitHub Actions versions to immutable commit SHAs. It combines async I/O, thread-safe caching, intelligent rate-limiting, and round-trip YAML editing to process workflows efficiently while preserving comments and formatting.

## Concurrency Model

### Async/Await (Primary)
- `run()` orchestrates all file processing as async tasks
- `pin_file()` performs file I/O and parsing (sync, CPU-bound)
- `GitHubClient.resolve_sha()` is async for API calls (I/O-bound)

### Rate Limiting via Semaphore
```python
_semaphore = asyncio.Semaphore(concurrency)
async with self._semaphore:
    # GitHub API request
```
- **Default concurrency: 5** concurrent requests
- Prevents API rate-limit errors (`429 Too Many Requests`)
- All requests wait if semaphore is at capacity

### Thread-Safe Cache
```python
_cache: dict[(repo, ref), str]  # guarded by threading.Lock
with self._cache_lock:
    if cache_key in self._cache:
        return self._cache[cache_key]
```
- **Purpose**: Satisfies spec requirement for thread-safe caching
- **Use case**: If `pin_actions` is imported and called from multiple async loops (e.g., via `asyncio.to_thread`), the lock ensures cache dict consistency
- **Performance**: Eliminates duplicate API requests for same `owner/repo@ref` within a run (common: many workflows use `actions/checkout@v4`)

## Rate-Limit Backoff Strategy

| HTTP Status | Action |
|------------|--------|
| **200 OK** | Return result |
| **404 Not Found** | Raise error immediately (invalid ref) |
| **429 Rate Limited** | Parse `Retry-After` header, exponential backoff, retry |
| **403 Forbidden** | Same as 429 (GitHub's secondary rate limit) |
| **5xx Server Error** | Exponential backoff + retry |
| **Other 4xx** | Raise error immediately |

**Backoff algorithm:**
```
delay = 2^attempt + random(0, 1)  # exponential + jitter, capped at 60s
if Retry-After header present:
    delay = parse(Retry-After)  # respects GitHub's advised delay
await asyncio.sleep(delay)
```

**Retry limit:** `max_retries` (default 5)

## YAML Round-Trip Editing (yamlrocks)

`pin_file()` parses each file with `yamlrocks.loads(content, option=yamlrocks.OPT_ROUND_TRIP)`, which returns a `YAMLRocksDocument` backed by a Rust AST that preserves comments, blank lines, and key ordering.

### Key API characteristics (not dict-like in all respects)
| Method/behavior | Notes |
|---|---|
| `doc[key]` / `doc[idx]` | Subscriptable; returns a fresh `YAMLRocksDocumentView` on every call (no stable identity across calls) |
| `doc.keys()` | Available; **`doc.items()` is not** |
| `doc.get(key, default)` | Requires both positional args (no implicit `None`) |
| `doc.walk()` | Yields flat `(path_tuple, value)` pairs for every scalar leaf — the reliable way to traverse nested list/dict structure, since list elements are `YAMLRocksDocumentView`, not `list` |
| `doc[k1][k2]...[kn] = value` | Writes through to the AST **only** as a single unbroken indexing chain starting at `doc`. Storing an intermediate view (`x = doc["jobs"]`) and mutating it later (`x["build"] = ...`) also writes through — identity instability does not affect correctness, since each view stays bound to the same underlying node — but paths captured once must be replayed from `doc` fresh (see `_set_path`) rather than assuming a cached parent-object reference from an earlier custom walker is reusable across phases |
| `doc.to_yaml()` | Re-serializes; only mutated nodes are rewritten, everything else (comments, indentation, blank lines) is byte-preserved |

### Finding and rewriting `uses:` entries
```python
def _find_uses_paths(doc):
    return [(p, v) for p, v in doc.walk() if p and p[-1] == "uses" and isinstance(v, str)]

def _set_path(doc, item_path, value):
    target = doc
    for key in item_path[:-1]:
        target = target[key]
    target[item_path[-1]] = value
```
This two-phase approach (collect paths, then resolve SHAs, then apply mutations by path) avoids relying on object identity of intermediate views and matches yamlrocks' documented mutation pattern.

## File Processing Flow

```
run(Settings)
  ├─ glob *.yml/*.yaml in path
  ├─ for each file:
  │   └─ pin_file(client, path)
  │       ├─ read bytes, yamlrocks.loads(..., OPT_ROUND_TRIP)
  │       ├─ doc.walk() → collect all "uses" key paths + values
  │       ├─ parse repo@ref, skip local/docker/already-pinned
  │       ├─ batch resolve unique (repo, ref) pairs:
  │       │   └─ for each ref:
  │       │       ├─ check cache (lock)
  │       │       ├─ if miss: resolve_sha(repo, ref)
  │       │       │   └─ GET /repos/{repo}/commits/{ref}
  │       │       │       └─ retry with backoff on 429/403
  │       │       └─ store in cache (lock)
  │       ├─ apply resolved SHAs via _set_path (path-based, doc-rooted assignment)
  │       ├─ doc.to_yaml() → compare to original bytes
  │       └─ write file (unless dry_run) if changed
  └─ return list of modified files
```

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **httpx2 (not httpx)** | Spec requirement; avoids hishel compat issues |
| **yamlrocks (not regex/ruamel.yaml)** | Round-trip AST preserves comments/formatting on untouched lines; Rust-backed, faster than pure-Python ruamel.yaml. Trade-off: pre-1.0 alpha API, non-obvious mutation semantics (see above) |
| **Manual lock-guarded cache** | Explicit thread-safety per spec; simple & fast |
| **Semaphore (not global rate limiter)** | Async-native; respects GitHub API concurrency limits without blocking |
| **Batch ref resolution** | Deduplicate refs before API calls; faster for workflows with repeated actions |
| **Path-tuples instead of object references** | yamlrocks views lack stable identity across `__getitem__` calls; paths are stable and replayable against `doc` |
| **Skip already-pinned SHAs** | Idempotent: running twice = no changes second time |
| **Preserve comments** | Rewrite pattern: `uses: owner/repo@sha  # original-ref`, combined with yamlrocks round-trip preservation of all other content |
| **Dry-run mode** | Resolve & validate refs without writing files |

## Safety Invariants

1. **Idempotency**: Running twice on same workflows produces identical result
2. **No modification of already-pinned refs**: Only rewrites mutable (non-SHA) refs
3. **No modification of local actions**: `./...` actions skipped entirely
4. **Cache consistency**: Lock guards all reads/writes to response cache
5. **Retry limits**: Max `max_retries` attempts; fails gracefully with informative errors

## Performance Characteristics

| Scenario | Time |
|----------|------|
| Single workflow, 5 actions, cached client | ~100ms (one API call per unique action, then cache hits) |
| 10 workflows, 50 unique actions, cold cache | ~2-5s (depends on API response time, rate limits, network) |
| Same 10 workflows again (warm cache) | ~10-50ms (all cache hits, no API calls) |
| Batch with 429 retry | ~60s worst-case (exponential backoff cap) |

**Optimization tips:**
- Set `--token $GITHUB_TOKEN` for higher rate limits (60 req/min unauthenticated → 5000 req/hr authenticated)
- Increase `--concurrency` (e.g., 10) if have sufficient GitHub API quota
- Use dry-run mode first to validate workflows without writing

## Error Handling

- **Invalid ref (404)**: Logged to stderr, file continues processing other refs
- **Rate limit exhausted (429x5)**: Logged to stderr, file continues
- **Network error (timeout, DNS)**: Retry with backoff; raise after `max_retries`
- **File I/O error (permission, disk full)**: Propagate as exception
- **YAML parse error**: Logged to stderr, file skipped (returns `False`, not raised)

## Testing Strategy

**Unit tests** (no network):
- Helper functions (`_is_local_action`, `_is_already_pinned`, `_parse_uses`, `_walk_uses_keys`)
- Cache hit/miss logic

**Integration tests** (mocked HTTP):
- Client retry logic (429, 403, backoff)
- File rewriting (before/after comparison), including comment/formatting preservation
- Batch resolution (deduplication)
- Dry-run mode

**Fixtures:**
- `unittest.mock.AsyncMock(side_effect=...)`: mocks async client methods (`pytest-httpx` does not intercept `httpx2`)
- Temporary files for file I/O tests
- `asyncio_mode = "auto"` (pytest-asyncio)
