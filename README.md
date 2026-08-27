# pin-actions

<!-- --8<-- [start:overview] -->
Automatically pin mutable GitHub Actions versions (e.g., `@v4`, `@main`) to their immutable 40-character commit SHAs.

Works as both a **CLI tool** and an **importable library**,
scanning `.github/workflows/**/*.{yml,yaml}` and composite `action.yaml`/`action.yml` files.

## Features

- Resolves mutable refs (branches, tags, short SHAs) to full commit SHAs
- Updates already-pinned refs: re-resolves the tag/branch and rewrites SHA if it has moved
- Pins `actions/checkout` `with.ref` parameters (checkout-another-repo workflows)
- Skips local actions (`./...`) and Docker actions (`docker://...`)
- Thread-safe async/concurrent request handling with rate-limit backoff
- No-op when nothing has changed
- Preserves comments and formatting
- Optional `--update` to move pinned tags forward within version constraints

## Quick Start

```bash
# Install
uv add pin-actions

# Run with GitHub token
pin-actions --path .github/workflows --github-token $GITHUB_TOKEN

# Dry-run to see what would change
pin-actions --dry-run
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
```

After:

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b  # v4
      - uses: actions/setup-python@f1e2d3c4b5a6f7e8d9c0b1a2f3e4d5c6b7a8f9e  # main
```

<!-- --8<-- [end:overview] -->

## Documentation

📖 **[Full Documentation](https://drts01.github.io/pin-actions/)**

- **[Tutorials](https://drts01.github.io/pin-actions/tutorials/getting-started/)** — Getting started, first pin
- **[How-To Guides](https://drts01.github.io/pin-actions/how-to/update-pinned-tags/)** — Common tasks and workflows
- **[Reference](https://drts01.github.io/pin-actions/reference/cli/)** — Full API and CLI documentation
- **[Explanation](https://drts01.github.io/pin-actions/explanation/architecture/)** — Design, architecture,
  and rationale
- **[Threat Model](https://drts01.github.io/pin-actions/explanation/threat-model/)** —
  The supply-chain attack model this tool defends against
- **[Comparison with Similar Tools](https://drts01.github.io/pin-actions/explanation/comparison/)** —
  How `pin-actions` stacks up against zizmor, pinact, and pin-github-action

## Development

- **Lint & test**: `prek run -a` (ruff, interrogate, pytest)
- **Docs**: `zensical build --strict`
- **Contributing**: See [CONTRIBUTING.md](CONTRIBUTING.md)

## License

[Apache 2.0](LICENSE)
