# Pin Pre-Commit Hooks

Pin GitHub-hosted `.pre-commit-config.yaml` `repos[].rev` entries to immutable commit SHAs.

This ships as the bundled script `scripts/update_precommit.py`, not as a `pin_actions` public API.
Its `--help` banner displays the program name as `pin-precommit`.

## Preview, Then Apply

```bash
export GITHUB_TOKEN=ghp_xxxx
uv run --with-editable . scripts/update_precommit.py --diff
uv run --with-editable . scripts/update_precommit.py
```

Each pinned `rev` becomes a commit SHA with the original tag or branch preserved as a trailing comment:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: abcdef0123456789abcdef0123456789abcdef01  # v0.8.0
```

## Paths and Flags

`--paths` defaults to `.pre-commit-config.yaml` in the current directory.
Override it for monorepos with multiple configs:

```bash
uv run --with-editable . scripts/update_precommit.py --paths "**/.pre-commit-config.yaml"
```

Every other `pin-actions` flag applies unchanged — `--update`, `--full-version`, `--exclude-newer`, `--concurrency`,
`--host`, `--provenance`.
See the [CLI reference](../reference/cli.md#pin-precommit-standalone-script).

## Non-GitHub Repos

`repos[].repo` entries that do not resolve to a `--host` clone URL — `local`, `meta`, or a non-GitHub host —
are skipped.

## See Also

- [Update Pinned Tags](./update-pinned-tags.md) — version constraint recipes shared with `pin-actions`
- [Verify SHA Provenance](./verify-provenance.md) — reject SHAs that do not belong to the named repository
