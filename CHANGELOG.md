# Changelog

<!-- --8<-- [start:body] -->
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Breaking Changes
- Consolidated `api_base_url` + `git_host` into a single `host` field; use `--host github.example.com` for GHE Server (API URL is derived automatically)
- `pin_file(client, path, *, dry_run=False, options=None)` — collapsed from 6 params to 3; `UpdateOptions` now carries pre-parsed `cutoff: datetime | None`
- `Settings.path` default changed from `.github/workflows` to `.github` (also scans `.github/actions/**/action.yml`)
- Removed `versioning.select_latest_tag` (deprecated; use `select_latest_tags`, which returns a list)

### Removed
- **Disk caching (`diskcache-rs`)** — Persistent disk cache removed. Rationale: in-memory cache already dedupes refs within a single run; disk cache across separate invocations violated documented re-resolution safety invariant without adding value in CI/CD (ephemeral runners) or batch multi-repo scenarios (staleness at scale). Kept: in-memory LRU cache (thread-safe, zero-cost dedup within-run).
  - Removed `--cache`, `--cache-dir`, `--cache-ttl` CLI flags
  - Removed `cache`, `cache_dir`, `cache_ttl` from `Settings`
  - Removed optional dependency `diskcache-rs>=0.4`
  - Updated docs: `configure-caching.md` now covers in-memory cache only

### Added
- **Container image pinning** (`--image-pin`, default on): pins `uses: docker://` steps, `jobs.<job>.container.image`, and `jobs.<job>.services[*].image` tags to immutable `sha256:` content digests via the new `pin_actions.registry.ContainerRegistryClient`. Anonymous-first OCI Distribution Spec / Docker Registry v2 Bearer-token flow works against any public registry (Docker Hub, GHCR, Quay.io, MCR, etc.); GitHub token is used only for `ghcr.io` token exchange (enables private GHCR images). Non-Bearer registries (ECR, GCR) are skipped per-image with a warning via the new `UnsupportedRegistryError`. Disable with `--no-image-pin` or `Settings.image_pin = False`
- GitHub Enterprise Server (GHE) support via `--host` setting: single flag automatically derives both API base URL and clone-URL hostname
- Cool-off period (`--exclude-newer`) for tag auto-selection: mitigates same-day supply-chain attacks by skipping tags younger than cutoff; accepts RFC 3339 timestamps, ISO 8601 durations, and friendly durations (e.g., `7 days`)
- `scripts/update_repos.py`: added `--host` (GHE Server support with automatic API URL derivation and `GH_HOST` env override) and `--verbose`/`-v` (0–3 logging control); uses modern Python 3.14 idioms (PEP 695 type aliases)
- `scripts/update_repos.py`: **idempotent PR handling** — detects existing PRs via `gh pr view` and updates them in-place (force-pushes branch, reuses PR) instead of failing on re-run; also auto-configures `git user.email`/`user.name` to support CI runners lacking global git config
- `--diff`: print a unified diff of pending changes instead of writing files (implies `--dry-run`)
- `--version`: print the installed `pin-actions` version and exit
- New `pin-precommit` entry point (`pin_actions/precommit.py`): pins GitHub-hosted `.pre-commit-config.yaml` `repos[].rev` entries using the same resolution/versioning pipeline as `pin-actions`; `scripts/update_precommit.py` is now a thin shim calling it
- `AuthError` exception for 403 responses with exhausted rate limit (distinct from `RateLimitExhaustedError`)
- Concurrent commit-date prefetch for `--exclude-newer` candidate tags (was serial)
- `--host` file-or-directory `--path` handling: `pin-actions --path some/file.yml` now works alongside directory paths
- Redocumented per Diátaxis: split flag matrices/exception hierarchies out of how-to guides into `reference/cli.md`/`reference/errors.md`; merged `checkout-another-repo.md` + `pin-composite-actions.md` into `how-to/pin-non-standard-refs.md`; new `how-to/run-in-ci.md` and `how-to/pin-pre-commit-hooks.md`



## [0.1.0] - 2026-08-11

### Added
- Initial release: automatic GitHub Actions version pinning
- CLI tool for scanning and pinning workflows
- Library API for programmatic access
- Thread-safe async HTTP client with rate-limit backoff
- In-memory and persistent disk caching (via diskcache-rs)
- Round-trip YAML parsing to preserve comments and formatting
- Version constraint modes (`--update major/minor/patch`)
- Support for pinning `actions/checkout` `with.ref` parameters
- Comprehensive error hierarchy (PinActionsError, YAMLParseError, GitHubAPIError, etc.)
- Full documentation site (Zensical-based, Diátaxis framework)
- Google-style docstring linting (Ruff D, Interrogate)
- Pre-commit hooks for docstring coverage

[Unreleased]: https://github.com/drts01/pin-actions/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/drts01/pin-actions/releases/tag/v0.1.0
<!-- --8<-- [end:body] -->
