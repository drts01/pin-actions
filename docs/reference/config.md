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
cache_ttl = 7200
host = "github.example.com"
```

Setting `host` to a GitHub Enterprise Server hostname automatically derives the API base URL (`https://{host}/api/v3`).

**Example `pyproject.toml`:**

```toml
[tool.pin-actions]
concurrency = 10
update = "minor"
```

## See Also

- [CLI Reference](cli.md) — Command-line flag mapping
- [Tutorial: Getting Started](../tutorials/getting-started.md)
