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
- **Future**: [Hishel](https://github.com/karpetrosyan/hishel) (HTTP-level response caching) will replace this manual cache once Hishel adds `httpx2` support


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
  │   └─ pin_file(client, path, update_to_latest_major, update_to_latest_minor, update_branches)
  │       ├─ read bytes, yamlrocks.loads(..., OPT_ROUND_TRIP)
  │       ├─ doc.walk() → collect all "uses" key paths + values
  │       ├─ parse repo@ref, skip local/docker; if ref is already a SHA, read the
  │       │  trailing comment via doc.locate(path).comment (skip only if no comment)
  │       │   ├─ if a version-constraint flag is set AND the comment parses as semver:
  │       │   │   └─ _apply_version_constrained_tag(): list_tags(repo), select_latest_tag()
  │       │   │       ├─ match found & differs → rewrite SHA + comment to new tag
  │       │   │       ├─ match found & same → no-op
  │       │   │       └─ no match → warn to stderr, leave entry untouched
  │       │   ├─ elif a version-constraint flag is set AND comment is non-semver (a branch):
  │       │   │   └─ frozen unless update_branches is set (then re-resolved normally, below)
  │       │   └─ else: re-resolve against the tag/branch recorded in the comment (default path)
  │       ├─ batch resolve unique (repo, tag) pairs (default-path entries only):
  │       │   └─ for each ref:
  │       │       ├─ check cache (lock)
  │       │       ├─ if miss: resolve_sha(repo, ref)
  │       │       │   └─ GET /repos/{repo}/commits/{ref}
  │       │       │       └─ retry with backoff on 429/403
  │       │       └─ store in cache (lock)
  │       ├─ apply resolved SHAs (only where changed) via _set_path, and set the
  │       │  tag as a genuine comment via doc.locate(path).comment = tag
  │       ├─ doc.to_yaml() → compare to original bytes
  │       └─ write file (unless dry_run) if changed
  └─ return list of modified files

```


## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **httpx2 (not httpx)** | Spec requirement; avoids hishel compat issues |
| **yamlrocks (not regex/ruamel.yaml)** | Round-trip AST preserves comments/formatting on untouched lines; Rust-backed, faster than pure-Python ruamel.yaml. Trade-off: pre-1.0 alpha API, non-obvious mutation semantics (see above) |
| **Manual lock-guarded cache** | Explicit thread-safety per spec; simple & fast. Will migrate to Hishel-based HTTP caching once Hishel supports `httpx2` |
| **Semaphore (not global rate limiter)** | Async-native; respects GitHub API concurrency limits without blocking |
| **Batch ref resolution** | Deduplicate refs before API calls; faster for workflows with repeated actions |
| **Path-tuples instead of object references** | yamlrocks views lack stable identity across `__getitem__` calls; paths are stable and replayable against `doc` |
| **Re-resolve already-pinned refs against their comment** | Mirrors `mheap/pin-github-action`'s default: a `sha` with a trailing `# tag` comment is re-resolved on every run, and the SHA is rewritten if the tag has moved. A bare SHA with no comment has nothing to re-resolve against and is left untouched |
| **Preserve comments** | Rewrite pattern: `uses: owner/repo@sha # original-ref` — comment is set via `doc.locate(path).comment`, not embedded in the string, so it round-trips as a genuine (unquoted) YAML comment. Combined with yamlrocks round-trip preservation of all other content |
| **Dry-run mode** | Resolve & validate refs without writing files |
| **`packaging.version` for semver parsing** | Battle-tested PEP 440-based parser already a transitive dep of the packaging ecosystem; tolerates a leading `v` via a thin wrapper (`parse_tag_version`) rather than hand-rolling semver regex |
| **`--update-to-latest-major` means "no constraint" (crosses majors); `--update-to-latest-minor` means "same major"** | Explicit user directive, refined from an initial same-major-for-both design: `--update-to-latest-major` picks the single absolute-latest semver tag on the repo (e.g. `v4.0.5` → `v9.1.2`), while `--update-to-latest-minor` constrains to the current major but is free within it (e.g. `v4.0.5` → `v4.9.0`, never `v5.x`). When both are set, `--update-to-latest-minor`'s narrower constraint still wins |
| **Rewritten tag comment preserves the original comment's precision** | User directive: a comment like `v4` (major-only) should stay `v4` even if the winning remote tag is `v9.1.2` — rewriting to full precision would be a surprising, unrequested style change. `versioning._render_tag()` truncates/zero-pads the winning `Version.release` tuple to `len(current.release)` components before re-rendering with the original tag's `v`-prefix style |
| **Tags frozen by default under a version constraint; `--update-branches` opts branches back in** | A version constraint only makes sense for semver tags; branch refs (comment doesn't parse as a version) are left untouched unless the user explicitly opts in, avoiding surprise branch-ref rewrites when the user's intent was "move my tags forward" |
| **Warn-and-skip on no matching tag** | No tag on the remote satisfies the major/minor constraint (e.g. that major was never re-tagged) — printing a stderr warning and leaving the entry untouched is safer than raising (would abort the whole file/batch) or silently no-op'ing (user wouldn't know why nothing moved) |
| **Separate `list_tags()`/per-repo tags cache from `resolve_sha()`/`_cache`** | Different GitHub endpoint (`GET .../tags` vs `GET .../commits/{ref}`), different cache key shape (repo-only vs `(repo, ref)`) — kept as two independent lock-guarded caches rather than overloading one |


## Safety Invariants

1. **Stable no-op**: Running twice on the same workflows, with no tags having moved on the remote, produces an identical result (re-resolution happens every time, but the file is only rewritten if the resolved SHA differs from what's already there)
2. **Already-pinned refs are re-resolved, not frozen**: A `sha  # tag` entry is re-resolved against `tag` on every run and updated if the tag now points elsewhere; a bare SHA with no comment is left untouched (nothing to re-resolve against)
3. **No modification of local actions**: `./...` actions skipped entirely
4. **Cache consistency**: Lock guards all reads/writes to response cache
5. **Retry limits**: Max `max_retries` attempts; fails gracefully with informative errors
6. **Version constraints never silently drop a pin**: if `--update-to-latest-major`/`--update-to-latest-minor` finds no candidate tag, the entry is left exactly as-is and a warning is printed to stderr — never removed, never left in a half-written state
7. **Branch refs are frozen by default under a version constraint**: only re-resolved if `--update-branches` is explicitly passed, preventing an unrelated branch pin from moving as a side effect of a tag-focused flag



## Performance Characteristics

| Scenario | Time |
|----------|------|
| Single workflow, 5 actions, cached client | ~100ms (one API call per unique action, then cache hits) |
| 10 workflows, 50 unique actions, cold cache | ~2-5s (depends on API response time, rate limits, network) |
| Same 10 workflows again (warm cache) | ~10-50ms (all cache hits, no API calls) |
| Batch with 429 retry | ~60s worst-case (exponential backoff cap) |

**Optimization tips:**
- Set `--github-token $GITHUB_TOKEN` for higher rate limits (60 req/min unauthenticated → 5000 req/hr authenticated)
- Increase `--concurrency` (e.g., 10) if have sufficient GitHub API quota
- Use dry-run mode first to validate workflows without writing

## Error Handling

Contract: **library raises, caller handles**. No function in `client.py`/`core.py` prints-and-continues or returns a sentinel on failure — every failure mode is a typed exception (`pin_actions.errors`). The CLI (`main()`) is the *only* place that catches these and converts them to stderr + exit code.

```
PinActionsError                  # base for all pin-actions errors
├── YAMLParseError               # file cannot be parsed as YAML (path, reason)
└── GitHubAPIError               # base for GitHub API failures
    ├── InvalidRefError          # 404: repo@ref doesn't exist
    ├── RateLimitExhaustedError  # retries exhausted on 429/403 (repo, ref, attempts)
    └── NetworkError             # unrecoverable network failure (DNS, timeout, connection)
```

| Failure | Where raised | Type |
|---|---|---|
| Invalid ref (404) | `GitHubClient._request_with_backoff` | `InvalidRefError` |
| Rate limit exhausted (429/403 × `max_retries`) | `GitHubClient._request_with_backoff` | `RateLimitExhaustedError` |
| Network error (timeout, DNS, connection) | `GitHubClient._request_with_backoff` (via `httpx2.RequestError`) | `NetworkError` |
| Malformed YAML | `pin_file()` (via `yamlrocks.loads`) | `YAMLParseError` |
| File I/O error (permission, disk full) | `pin_file()` (`path.read_bytes`/`write_bytes`) | `OSError` (unwrapped — not pin-actions-specific) |
| Nonexistent scan path | `run()` | `ValueError` |
| One or more files fail during a batch `run()` | `run()` (via `asyncio.gather(..., return_exceptions=True)`) | `ExceptionGroup[PinActionsError]` — no partial results returned in that case |

`pin_file()` and `GitHubClient.resolve_sha()` never catch `GitHubAPIError`/`YAMLParseError` internally — they propagate straight to the caller, who chooses to skip/retry/abort. `run()` is the one place that catches per-file exceptions (via `return_exceptions=True`) so a single bad file doesn't abort the whole batch, but it still surfaces every failure by re-raising them together in an `ExceptionGroup` rather than silently dropping them.


## CLI (`--help` via pydantic-settings)

`Settings` (in `config.py`) is a normal `pydantic_settings.BaseSettings` with **no CLI options baked into `model_config`**. CLI parsing is opt-in per call site:

```python
settings = Settings(
    _cli_parse_args=True,     # parse sys.argv
    _cli_kebab_case=True,     # dry_run -> --dry-run
    _cli_implicit_flags=True, # --dry-run / --no-dry-run instead of --dry-run bool
    _cli_prog_name="pin-actions",
)
```

This is only done inside `main()`. **Why not `model_config = SettingsConfigDict(cli_parse_args=True, ...)`**: baking it into `model_config` makes *every* `Settings(...)` instantiation parse `sys.argv` — including direct instantiation in tests and library code, which breaks immediately under pytest (`unrecognized arguments: -v ...`) since pytest's own argv doesn't match the model's fields. Keeping it as call-time kwargs isolates CLI parsing to the one code path that actually wants it.

`github_token`'s field uses `validation_alias=AliasChoices("PIN_ACTIONS_TOKEN", "GITHUB_TOKEN")` (with `populate_by_name=True`) so both the prefixed and the conventional unprefixed `GITHUB_TOKEN` env var populate it — pydantic-settings' CLI layer also derives `--github-token`/`--pin-actions-token` flag aliases from the same `AliasChoices`.

## Testing Strategy


**Unit tests** (no network):
- Helper functions (`_is_local_action`, `_is_already_pinned`, `_parse_uses`, `_walk_uses_keys`)
- Cache hit/miss logic

**Integration tests** (mocked HTTP):
- Client retry logic (429, 403, backoff)
- `GitHubClient.list_tags()` pagination, caching, and 404/429 error paths
- File rewriting (before/after comparison), including comment/formatting preservation
- Batch resolution (deduplication)
- Dry-run mode
- Version-constrained selection (`versioning.py`) and the `pin_file()` branches it feeds: `--update-to-latest-major`/`--update-to-latest-minor` (including minor-takes-precedence), `--update-branches`, and the no-match stderr warning


**Fixtures:**
- `unittest.mock.AsyncMock(side_effect=...)`: mocks async client methods (`pytest-httpx` does not intercept `httpx2`)
- Temporary files for file I/O tests
- `asyncio_mode = "auto"` (pytest-asyncio)
