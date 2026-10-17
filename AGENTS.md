# AGENTS.md

## Role

Act as a Python expert and accomplished technical writer.
Write direct, precise, technically accurate code and documentation with imperative statements.
Prefer succinct solutions and the smallest complete change that fixes the root cause.

## Project Purpose

Maintain `pin-actions`, a Python 3.14 CLI and library that replaces mutable GitHub Action refs
and container image tags with immutable digests.
Preserve its supply-chain security guarantees.
Preserve YAML comments, formatting, and no-op behavior through `yamlrocks` round-trip editing.
Support both CLI users and library callers.

## Repository Layout

- Keep package code in `src/pin_actions/` and public exports in `src/pin_actions/__init__.py`.
- Keep orchestration in `core.py`, configuration in `config.py`, GitHub API behavior in `client.py`, registry resolution
  in `registry.py`, version logic in `versioning.py`, and domain exceptions in `errors.py`.
- Keep tests in `tests/`, script tests in `scripts/test_*.py`, documentation in `docs/`,
  and benchmarks in `benchmarks/`.

## Python Requirements

- Target Python `>=3.14,<4`.
- Use the latest stable Python 3.14 language and standard-library features when they improve clarity, safety,
  or performance.
- Prefer PEP 695 aliases and generic syntax, built-in generics, `X | None`, and `X | Y` over legacy typing forms.
- Use `override`, `Self`, `Literal`, `TYPE_CHECKING`, pattern matching, `ExceptionGroup`, strict `zip`,
  and modern asyncio APIs when they clarify intent.
- Use `pathlib.Path` for paths and frozen, slotted dataclasses for immutable values.
- Avoid pre-3.14 compatibility code and novelty that reduces readability or conflicts with dependencies.

## Coding Style

- Follow Ruff formatting with double quotes, spaces, and a 120-character line limit.
- Add complete type annotations to production code.
- Satisfy Pyrefly strict mode.
- Prefer succinct, readable code over verbose abstractions and unnecessary indirection.
- Keep functions focused, use explicit names and guard clauses, and use comprehensions only when immediately readable.
- Prioritize performance in hot paths and network workflows without sacrificing correctness, security,
  or maintainability.
- Measure performance-sensitive changes with representative benchmarks; do not optimize based on assumptions.
- Avoid hidden mutation, unnecessary shared state, and broad exception handlers.
- Raise specific `PinActionsError` subclasses and chain translated failures with `raise ... from exc`.
- Use module-level loggers with parameterized messages; keep printing and exit-code conversion at the CLI boundary.
- Comment only non-obvious constraints or tradeoffs; remove dead code instead of commenting it out.

## Async and Concurrency

- Use async I/O for network operations.
- Reuse pooled HTTP clients.
- Close owned async clients deterministically with async context managers or `aclose()`.
- Bound external concurrency with semaphores.
- Deduplicate concurrent requests when practical.
- Never hold a thread lock across an `await`.
- Protect shared cache state for free-threaded Python, not only single-threaded asyncio.
- Preserve retry limits, `Retry-After` handling, exponential backoff, and jitter.
- Avoid blocking I/O in async request paths.

## YAML and Security Invariants

- Preserve YAML comments and formatting through `yamlrocks.OPT_ROUND_TRIP`.
- Mutate YAML AST values through one continuous indexing chain or the existing `_set_path()` helper.
- Compare serialized output before writing.
- Leave files untouched when content does not change.
- Preserve dry-run and diff semantics.
- Skip local actions.
- Preserve immutable 40-character commit SHAs and `sha256:` image digests.
- Preserve the original mutable tag or branch in the trailing YAML comment.
- Pin third-party GitHub Actions in workflow files to full commit SHAs.
- Set `persist-credentials: false` on checkout steps unless a documented workflow requirement forbids it.
- Grant GitHub workflow permissions explicitly and minimally.
- Never log, serialize, commit, or expose tokens and secrets.
- Pass the GitHub token only to intended GitHub endpoints, including GHCR where supported.
- Treat provenance verification and registry authentication as security-sensitive behavior.

## Public API and Configuration

- Preserve backward compatibility for exported names unless the change explicitly requires a breaking API update.
- Update `src/pin_actions/__init__.py` when adding or removing public APIs.
- Use Pydantic settings fields and validators for configuration.
- Preserve settings precedence: explicit initialization or CLI, environment, dotenv, file secrets, local TOML, XDG TOML,
  `pyproject.toml`, defaults.
- Store tokens as `SecretStr` where configuration models expose them.
- Document behavior changes in CLI help, reference documentation, and `CHANGELOG.md` when appropriate.

## Documentation

- Write Google-style docstrings for public APIs.
- Document arguments, return values, raised exceptions, side effects, and non-obvious invariants.
- Keep docstrings concise and useful.
- Keep terminology consistent: use "ref," "commit SHA," "tag," "digest," and "provenance" precisely.
- Use semantic line breaks and keep Markdown compatible with the configured `rumdl` and `ryl` rules.
- Update architecture, threat-model, or design documentation when changing the corresponding guarantees.
- Treat `pyproject.toml`, `tox.toml`,
  and executable code as authoritative when documentation conflicts with implementation.

## Testing

- Add or update tests for every behavior change and regression fix.
- Use pytest and `pytest-asyncio` for async behavior.
- Use Hypothesis for parsing, normalization, and input-space invariants when property-based testing provides value.
- Mock network boundaries; do not depend on live GitHub or registry services in the default test suite.
- Assert observable behavior, errors,
  and side effects instead of implementation details unless testing concurrency or cache invariants.
- Cover success, no-op, invalid input, retries, partial failure, and cleanup paths.
- Preserve strict markers and doctest compatibility.
- Benchmark performance-sensitive changes separately; avoid timing assertions in normal tests.

## Validation Commands

Run the narrowest relevant checks first.

```bash
uv run --group test pytest tests/path/to/test_file.py
uv run --group typecheck pyrefly check
uv run --group lint prek run -a
uv run --group docs zensical build --strict
uv run --group ci tox run
```

Run `uv run --group ci tox run` before declaring a substantial change complete.
Run `uv run --group docs zensical build --strict` after documentation or public API changes.
Report any check that could not run and include the reason.
Do not claim a check passed unless it ran successfully.

## Dependencies and Tooling

- Use `uv` for dependency management and command execution.
- Update `uv.lock` when dependency metadata changes.
- Prefer existing dependencies and the standard library; add a dependency only when it provides clear, necessary value.
- Configure formatting, linting, typing,
  and testing in `pyproject.toml` or `tox.toml` rather than adding competing tool configuration.
- Use Pyrefly for static type checking; do not introduce mypy-specific configuration.
- Preserve Conventional Commit formatting when asked to create a commit: `<type>(<scope>): <description>`.
- Keep commit headers at or below 72 characters and omit a final period.

## Change Discipline

- Read the relevant implementation, tests, and documentation before editing.
- Fix root causes instead of symptoms.
- Preserve unrelated user changes.
- Avoid unrelated refactors.
- Update tests and documentation in the same change when behavior changes.
- State assumptions explicitly when repository evidence is incomplete.
- Summarize changed files and executed validation at completion.
