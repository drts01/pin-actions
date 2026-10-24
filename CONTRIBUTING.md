# Contributing

Thank you for your interest in pinref!

## Development Setup

### Prerequisites

- Python 3.14+
- `uv` for dependency management

### Clone & Install

```bash
git clone https://github.com/drts01/pinref.git
cd pinref
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
uv run --group docs zensical build --strict
```

Then open `site/index.html` in your browser.

## Security Automation in CI

`pinref` enforces supply-chain and workflow security in CI, not in pre-commit hooks.
Run these checks in GitHub Actions only:

- `uv lock --check`
- `uv audit --locked`
- CodeQL Python analysis
- OpenSSF Scorecard analysis
- SARIF uploads for Ruff, Zizmor, `uv audit`, and Scorecard

Keep local hooks focused on fast author feedback.
Do not add `uv audit` or Renovate execution to `.pre-commit-config.yaml`.

### Why Trivy, Checkov, and Semgrep are intentionally excluded

Do not add Trivy, Checkov, or Semgrep in this repository's default CI stack.
Use the existing coverage instead:

- Ruff with security rules (`S` family)
- Zizmor for GitHub Actions policy and hardening checks
- Actionlint for workflow correctness
- CodeQL for semantic data-flow analysis in Python and workflow-sensitive paths

This repository has no product IaC deployment or container build pipeline to justify container/IaC scanners
as required checks.

## Dependency Updates with Renovate

Run Renovate from `.github/workflows/renovate.yml` (scheduled + manual dispatch).
Configure repository secret `RENOVATE_TOKEN` before enabling the workflow.
Keep Renovate policy in `.github/renovate.json5`.
Renovate updates Python/uv dependencies, GitHub Actions, and pre-commit hooks after a three-day minimum release age.

## Release Workflow

Use `.github/workflows/release.yml` for tag and manual releases.
The workflow builds and validates `sdist` + wheel, exports a CycloneDX SBOM from `uv.lock`,
creates separate GitHub provenance and SBOM attestations for both distributions,
and publishes only the distributions to PyPI/TestPyPI.

Supported publication modes:

1. Trusted Publishing (OIDC, preferred)
2. Token-based publishing using repository secrets:
   - `PYPI_API_TOKEN`
   - `TEST_PYPI_API_TOKEN`

Prefer Trusted Publishing and configure the protected `pypi`
and `testpypi` GitHub environments with the corresponding PyPI trusted publishers.
Add required reviewers to the production `pypi` environment.
Use `PYPI_API_TOKEN` and `TEST_PYPI_API_TOKEN` only as fallback repository or environment secret placeholders.
Never hardcode tokens in workflow files, scripts, or repository content.

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

Thank you for contributing to pinref!
🙏
