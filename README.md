# pin-actions

Automatically pin mutable GitHub Actions versions (e.g., `@v4`, `@main`) to their immutable 40-character commit SHAs.

Works as both a **CLI tool** and an **importable library**, scanning `.github/workflows/**/*.{yml,yaml}` and composite `action.yaml`/`action.yml` files.

## Installation

```bash
uv add pin-actions
```

Or via pip:
```bash
pip install pin-actions
```

## CLI Usage

### Basic Usage

```bash
pin-actions --path .github/workflows --token $GITHUB_TOKEN
```

### Options

```
--path PATH              Root directory to scan (default: .github/workflows)
--token TOKEN            GitHub API token (default: env GITHUB_TOKEN)
--dry-run                Print changes without writing files
--concurrency N          Max concurrent API calls (default: 5)
--max-retries N          Retry attempts on rate limits (default: 5)
--github-api URL         GitHub API base URL (default: https://api.github.com)
```

### Examples

```bash
# Dry-run to see what would change
pin-actions --dry-run --token ghp_xxxx

# Process custom directory with 10 concurrent requests
pin-actions --path ./.workflows --concurrency 10

# Use GITHUB_TOKEN environment variable
export GITHUB_TOKEN=ghp_xxxx
pin-actions
```

## Library Usage

### Import and Pin Files

```python
import asyncio
from pathlib import Path
from pin_actions import GitHubClient, run
from pin_actions.config import Settings

async def main():
    settings = Settings(
        path=Path(".github/workflows"),
        token="ghp_xxxx",
        dry_run=False,
        concurrency=5,
    )
    modified = await run(settings)
    print(f"Modified {len(modified)} file(s)")

asyncio.run(main())
```

### Use Client Directly

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

## What It Does

Before:
```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@main
      - uses: ./local-action@v1
```

After:
```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b  # v4
      - uses: actions/setup-python@f1e2d3c4b5a6f7e8d9c0b1a2f3e4d5c6b7a8f9e  # main
      - uses: ./local-action@v1
```

Features:
- ✅ Resolves mutable refs (branches, tags, short SHAs) to full commit SHAs
- ✅ Skips already-pinned refs (40-char hex SHAs)
- ✅ Skips local actions (`./...`) and Docker actions (`docker://...`)
- ✅ Thread-safe async/concurrent request handling with rate-limit backoff
- ✅ Idempotent (running twice produces same result)
- ✅ Preserves comments and formatting (round-trip YAML via `yamlrocks`)

## Performance

- **Concurrent requests**: Limited by `--concurrency` flag (default 5) to avoid API rate limits
- **Caching**: In-process cache prevents duplicate API calls for same ref within a run
- **Rate-limit handling**: Exponential backoff on 429/403 with `Retry-After` header support
- **Dry-run**: Parse and resolve refs without writing files

## Design

| Component | Purpose |
|-----------|---------|
| `GitHubClient` | Async HTTP client with rate-limit backoff, caching, and semaphore-bounded concurrency |
| `Settings` | Pydantic-based CLI/env config |
| `pin_file()` | Parse (via `yamlrocks`) and rewrite individual workflow files |
| `run()` | Main orchestrator: glob files, resolve refs, write results |
| `yamlrocks` | Round-trip YAML parser (Rust-backed). `doc.walk()` finds `uses:` key paths; indexed assignment (`doc[k1][k2]... = value`) writes through to the AST, preserving comments/formatting on untouched lines |

Thread-safety:
- `asyncio.Semaphore` bounds concurrent API requests
- `threading.Lock` guards response cache dict (safe for multi-loop usage)

## Testing

Run test suite:
```bash
pytest tests/
```

With coverage:
```bash
pytest --cov=pin_actions tests/
```

Tests cover:
- `uses:` string parsing (mutable refs, sub-paths, comments)
- Caching and deduplication
- Rate-limit retry logic (429, 403)
- File modification, dry-run mode, and comment/formatting preservation
- Batch workflow processing

## Contributing

PRs welcome. Maintain:
- Type hints on all public APIs
- Descriptive docstrings
- Test coverage for new features
- Conventional commit messages

## License

MIT
