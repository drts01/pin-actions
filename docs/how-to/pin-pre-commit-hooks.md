# Pin Pre-Commit Hooks

Pin GitHub-hosted `.pre-commit-config.yaml` `repos[].rev` entries to immutable commit SHAs using the `pin-precommit` entry point.

## Dry-Run Preview

```bash
export GITHUB_TOKEN=ghp_xxxx
pin-precommit --dry-run
```

By default, `pin-precommit` reads `.pre-commit-config.yaml` in the current directory.

## Apply the Changes

```bash
pin-precommit --github-token $GITHUB_TOKEN
```

Each pinned `rev` becomes a commit SHA with the original tag/branch preserved as a trailing comment:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: abcdef0123456789abcdef0123456789abcdef01  # v0.8.0
```

## Version Constraints & Diffs

`pin-precommit` accepts the same flags as `pin-actions` — `--update`, `--full-version`, `--exclude-newer`, `--diff`, `--concurrency`, `--host`, etc. See the [CLI reference](../reference/cli.md#pin-precommit) for the full flag list.

```bash
# Preview a unified diff without writing
pin-precommit --diff

# Move pins forward within the same major version
pin-precommit --update minor --github-token $GITHUB_TOKEN
```

## Non-GitHub Repos

`repos[].repo` entries that don't resolve to a `--host` clone URL (e.g. `local`, `meta`, or non-GitHub hosts) are skipped — only GitHub-hosted hooks are pinned.

## See Also

- [Reference: CLI](../reference/cli.md#pin-precommit) — full `pin-precommit` flag list
- [How-to: Update pinned tags](./update-pinned-tags.md) — version constraint recipes shared with `pin-actions`
- [Use as a Library](./use-as-a-library.md) — programmatic access via `pin_actions.precommit`
