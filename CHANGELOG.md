# Changelog

<!-- --8<-- [start:body] -->
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Breaking Changes
- Consolidated `api_base_url` + `git_host` into a single `host` field; use `--host github.example.com` for GHE Server (API URL is derived automatically)

### Removed
- **Disk caching (`diskcache-rs`)** — Persistent disk cache removed. Rationale: in-memory cache already dedupes refs within a single run; disk cache across separate invocations violated documented re-resolution safety invariant without adding value in CI/CD (ephemeral runners) or batch multi-repo scenarios (staleness at scale). Kept: in-memory LRU cache (thread-safe, zero-cost dedup within-run).
  - Removed `--cache`, `--cache-dir`, `--cache-ttl` CLI flags
  - Removed `cache`, `cache_dir`, `cache_ttl` from `Settings`
  - Removed optional dependency `diskcache-rs>=0.4`
  - Updated docs: `configure-caching.md` now covers in-memory cache only

### Added
- GitHub Enterprise Server (GHE) support via `--host` setting: single flag automatically derives both API base URL and clone-URL hostname
- Cool-off period (`--exclude-newer`) for tag auto-selection: mitigates same-day supply-chain attacks by skipping tags younger than cutoff; accepts RFC 3339 timestamps, ISO 8601 durations, and friendly durations (e.g., `7 days`)

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
