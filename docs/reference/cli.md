# CLI reference

`pin-actions` parses command-line flags via pydantic-settings, deriving them directly from the [`Settings`](config.md) fields below (kebab-case, e.g. `dry_run` → `--dry-run`). Run `pin-actions --help` for the live, authoritative flag list.

::: pin_actions.config.Settings

## `pin-precommit`

Pins GitHub-hosted `.pre-commit-config.yaml` `repos[].rev` entries; accepts the same flags as `pin-actions` (via `PrecommitSettings(Settings)`) plus:

- `--host` — matches against `repos[].repo` clone URLs (default `github.com`)
- Default `--path` is `.pre-commit-config.yaml` instead of `.github`

Run `pin-precommit --help` for the live flag list.

## `--update` flag matrix

| Mode | Constraint | Example |
|------|-----------|---------|
| `major` | None — absolute latest tag on the repo | `v4.0.5` → `v9.1.2` |
| `minor` | Same major version | `v4.0.5` → `v4.9.0`, never `v5.x` |
| `patch` | Same major.minor | `v4.2.3` → `v4.2.9`, never `v4.3.x` |
| *(unset)* | Re-resolve the exact tag/branch recorded in the comment | `v4` → `v4` (SHA updated if moved) |

## Precision preservation (`--full-version`)

Without `--full-version`, the rewritten tag comment matches the original's precision:

| Original | Latest Tag | Result |
|----------|-----------|--------|
| `v4` | `v4.9.0` | `v4` (major-only preserved) |
| `v4.0.5` | `v9.1.2` | `v9.1.2` (full precision kept) |
| `v4.0` | `v4.9.3` | `v4.9` (major.minor preserved) |

With `--full-version`, the full resolved tag version is always recorded (e.g. `v4.9.0` instead of `v4`).

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

# Print a unified diff instead of a file list (implies --dry-run)
pin-actions --diff --github-token $GITHUB_TOKEN

# Pin workflows with custom concurrency
pin-actions --path .workflows --concurrency 10 --github-token $GITHUB_TOKEN

# Move pins to latest version within same major
pin-actions --update minor --github-token $GITHUB_TOKEN

# Verbose output (also --verbose)
pin-actions -v 2 --github-token $GITHUB_TOKEN


# Use with GitHub Enterprise Server
pin-actions --host github.example.com --github-token $GITHUB_TOKEN

# Skip tags newer than a cool-off window (supply-chain safety)
pin-actions --update minor --exclude-newer "7 days" --github-token $GITHUB_TOKEN

# Increase retry attempts on 429/403 responses
pin-actions --max-retries 10 --github-token $GITHUB_TOKEN

# Print installed version
pin-actions --version


# Pin pre-commit hook revs instead of GitHub Actions
pin-precommit --github-token $GITHUB_TOKEN
```

## See also

- [Reference: Settings](config.md) — Python API configuration class
- [How-to: Update pinned tags](../how-to/update-pinned-tags.md) — Version constraint usage recipes
- [How-to: Pin pre-commit hooks](../how-to/pin-pre-commit-hooks.md) — `pin-precommit` usage
