# CLI reference

`pin-actions` parses command-line flags via pydantic-settings, deriving them directly from the [`Settings`](config.md) fields below (kebab-case, e.g. `dry_run` → `--dry-run`). Run `pin-actions --help` for the live, authoritative flag list.

**Breaking change**: `--path` is now `--paths` and accepts multiple file/directory arguments (glob patterns supported). Default scans `.github/workflows/` (all workflows) plus `**/action.yml` and `**/action.yaml` (composite actions in any path).

::: pin_actions.config.Settings

## `pin-precommit` (standalone script)

Pins GitHub-hosted `.pre-commit-config.yaml` `repos[].rev` entries to immutable commit SHAs. Available as a standalone `uv run` script (`scripts/update_precommit.py`); accepts the same flags as `pin-actions` (via `PrecommitSettings(Settings)`) plus:

- `--host` — matches against `repos[].repo` clone URLs (default `github.com`)
- Default `--paths` is `[.pre-commit-config.yaml]` instead of the main default

Run `uv run --with-editable . scripts/update_precommit.py --help` for the live flag list.

## Container image pinning (`--image-pin`)

By default, `pin-actions` also pins container image references to `sha256:` content digests:

- `uses: docker://image:tag` (step-level docker actions)
- `jobs.<job>.container.image`
- `jobs.<job>.services.<name>.image`

Resolution uses the OCI Distribution Spec Bearer-token auth flow, which works anonymously
for any public registry (Docker Hub, GHCR, Quay.io, MCR, etc. — no credentials required).
`--github-token` is additionally used for `ghcr.io` private image resolution. Registries
requiring non-Bearer auth (e.g. ECR, GCR) are skipped with a warning rather than failing
the whole file. Disable entirely with `--no-image-pin`.

```yaml
# Before
image: postgres:15
# After
image: postgres@sha256:a8560b36...  # 15
```

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

# Pin workflows with custom concurrency (single path)
pin-actions --paths .workflows --concurrency 10 --github-token $GITHUB_TOKEN

# Pin specific action file (not default scan)
pin-actions --paths action.yml --github-token $GITHUB_TOKEN

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


# Pin pre-commit hook revs instead of GitHub Actions (standalone script)
uv run --with-editable . scripts/update_precommit.py --github-token $GITHUB_TOKEN
```

## See also

- [Reference: Settings](config.md) — Python API configuration class
- [How-to: Update pinned tags](../how-to/update-pinned-tags.md) — Version constraint usage recipes
- [How-to: Pin pre-commit hooks](../how-to/pin-pre-commit-hooks.md) — `pin-precommit` usage
