# CLI reference

`pin-actions` parses command-line flags via pydantic-settings, deriving them directly from the [`Settings`](config.md) fields below (kebab-case, e.g. `dry_run` → `--dry-run`). Run `pin-actions --help` for the live, authoritative flag list.

::: pin_actions.config.Settings

## Environment variables

- `GITHUB_TOKEN` — GitHub API token
- `PIN_ACTIONS_TOKEN` — Alternative name for the GitHub token
- `PIN_ACTIONS_*` — Any other field can be set via its `PIN_ACTIONS_`-prefixed env var name (e.g. `PIN_ACTIONS_CONCURRENCY`)

## Config file

See [Config file](config.md#config-file) for TOML config file locations and precedence.

## Examples

```bash
# Dry-run to preview changes
pin-actions --dry-run --github-token $GITHUB_TOKEN

# Pin workflows with custom concurrency
pin-actions --path .workflows --concurrency 10 --github-token $GITHUB_TOKEN

# Move pins to latest version within same major
pin-actions --update minor --github-token $GITHUB_TOKEN

# Verbose output
pin-actions -v 2 --github-token $GITHUB_TOKEN

# Disable caching for debugging
pin-actions --no-cache --github-token $GITHUB_TOKEN

# Use with GitHub Enterprise Server
pin-actions --host github.example.com --github-token $GITHUB_TOKEN
```

## See also

- [Reference: Settings](config.md) — Python API configuration class
- [How-to: Update pinned tags](../how-to/update-pinned-tags.md) — Version constraint details
