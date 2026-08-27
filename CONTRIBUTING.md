# Contributing

Thank you for your interest in pin-actions!

## Development Setup

### Prerequisites

- Python 3.14+
- `uv` for dependency management

### Clone & Install

```bash
git clone https://github.com/drts01/pin-actions.git
cd pin-actions
uv sync
```

## Testing & Linting

Run the full lint/test suite:

```bash
prek run -a
```

This runs:

- `ruff format` — code formatting
- `ruff check --fix` — style & type-checking (with D rules for docstrings)
- `interrogate` — docstring coverage (must reach 95%)
- `pytest --cov` — unit and integration tests

Run individual checks:

```bash
# Format only
ruff format .

# Lint only (without auto-fix)
ruff check .

# Test only
pytest tests/ --cov

# Docstring coverage
interrogate --config pyproject.toml
```

## Documentation

Build the docs locally:

```bash
uv run -g docs zensical build --strict
```

Then open `site/index.html` in your browser.

## Commit Convention

This project uses [Conventional Commits](https://www.conventionalcommits.org/):

```text
<type>(<scope>): <short description>

[body: optional intent/why]

[footer: optional BREAKING CHANGE]
```

Examples:

```text
feat(client): add exponential backoff with jitter

Implement 2^attempt + jitter backoff strategy respecting Retry-After headers.
Fixes issue with rate-limit retries on 429/403 responses.

fix(core): preserve YAML comments on already-pinned refs

The yamlrocks round-trip parser now correctly sets doc.locate(path).comment
for trailing YAML comments on updated entries.

test(versioning): add CalVer tag parsing tests

Covers dash-separated CalVer tags (2024-05-01 → 2024.05.01 normalization).
```

The pre-commit hook (`commitlint`) will validate your commit messages.

## Docstrings

All public APIs require Google-style docstrings (enforced by `ruff` D rules + `interrogate`):

```python
def resolve_sha(self, repo: str, ref: str) -> str:
    """Resolve a mutable ref to its immutable commit SHA.

    Args:
        repo: Repository in 'owner/repo' format.
        ref: Commit reference (branch, tag, or partial SHA).

    Returns:
        40-character commit SHA.

    Raises:
        InvalidRefError: If the ref does not exist on the remote repository.
        RateLimitExhaustedError: If retries are exhausted while rate-limited.
        NetworkError: On unrecoverable network errors.
    """
```

## Pull Requests

1. **Fork & create a branch**: `git checkout -b feature/my-feature`
2. **Make changes**: update code, docstrings, tests
3. **Run checks**: `prek run -a` must pass (including docstring coverage & pre-commit)
4. **Build docs**: `uv run -g docs zensical build --strict` must pass
5. **Create PR**: link any related issues, describe the intent

## Style Reminders

- **No filler**: clear, direct code comments only on complex logic
- **Type hints**: all public APIs require type annotations
- **Minimal docstrings**: only non-obvious behavior; skip trivial getters/setters
- **DRY**: refactor repeated patterns into helpers
- **Async-first**: new I/O code should use async/await
- **Error handling**: raise exceptions; don't print-and-continue

## Questions?

Open an issue or discussion on GitHub — we're happy to help!

---

Thank you for contributing to pin-actions! 🙏
