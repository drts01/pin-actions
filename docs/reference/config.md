# Configuration Reference

Settings class for CLI and library usage.

::: pin_actions.config

## Config file

Settings can be provided via TOML config files, in addition to CLI flags and environment variables.

**Lookup order** (highest to lowest precedence):

1. CLI flags
2. `PIN_ACTIONS_*` / `GITHUB_TOKEN` environment variables
3. `.env` file
4. `./pin-actions.toml` (current directory)
5. `$XDG_CONFIG_HOME/pin-actions/config.toml` (falls back to `~/.config/pin-actions/config.toml`)
6. `pyproject.toml` under `[tool.pin-actions]`
7. Field defaults

All config files are optional — pin-actions runs with zero configuration if none are present.

**Example `pin-actions.toml`:**

```toml
concurrency = 10
host = "github.example.com"
```

Setting `host` to a GitHub Enterprise Server hostname automatically derives the API base URL (`https://{host}/api/v3`).

**Cool-off period example (`pin-actions.toml`):**

```toml
exclude_newer = "7 days"
```

The `exclude_newer` setting applies only to `--update` mode and accepts three formats:

- RFC 3339 timestamp: `2006-12-02T02:07:43Z` (absolute cutoff)
- ISO 8601 duration: `P7D`, `PT24H`, `P1W` (relative to now)
- Friendly duration: `7 days`, `24 hours`, `1 week` (case-insensitive)

Default: unset (no cool-off).
When set, tags younger than the cutoff are excluded from auto-selection, mitigating same-day supply-chain compromises.

**Provenance verification example (`pin-actions.toml`):**

```toml
provenance = "strict"
```

See [CLI: Provenance verification](cli.md#provenance-verification-provenance) for the `off`/`warn`/`strict` semantics
and the fork-network threat this mitigates.

**Example `pyproject.toml`:**

```toml
[tool.pin-actions]
concurrency = 10
update = "minor"
exclude_newer = "7 days"
```

## See Also

- [CLI Reference](cli.md) — Command-line flag mapping
- [Tutorial: Getting Started](../tutorials/getting-started.md)
