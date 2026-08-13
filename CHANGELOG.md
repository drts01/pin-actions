# Changelog

<!-- --8<-- [start:body] -->
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
