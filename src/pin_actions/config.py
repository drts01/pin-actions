"""Configuration & CLI settings."""

import os
from pathlib import Path
from typing import Literal, override

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    PyprojectTomlConfigSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)


def _xdg_config_path() -> Path:
    """Resolve the XDG config file path for pin-actions.

    Returns:
        Path to ``$XDG_CONFIG_HOME/pin-actions/config.toml``, falling back to
        ``~/.config/pin-actions/config.toml`` when ``XDG_CONFIG_HOME`` is unset.
    """
    xdg_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg_home) if xdg_home else Path.home() / ".config"
    return base / "pin-actions" / "config.toml"


class Settings(BaseSettings):
    """CLI & environment configuration for pin-actions."""

    model_config = SettingsConfigDict(
        env_prefix="PIN_ACTIONS_",
        case_sensitive=False,
        populate_by_name=True,
        pyproject_toml_table_header=("tool", "pin-actions"),
    )

    @override
    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Add TOML config file sources (pyproject.toml, XDG, cwd) below env/CLI precedence.

        Precedence high→low: init/CLI, env, dotenv, secrets, pin-actions.toml (cwd),
        XDG config.toml, pyproject.toml [tool.pin-actions], field defaults.

        Args:
            settings_cls: Settings class.
            init_settings: CLI/init settings source.
            env_settings: Environment variable settings source.
            dotenv_settings: .env file settings source.
            file_secret_settings: Secrets directory settings source.

        Returns:
            Tuple of settings sources in precedence order (highest first).
        """
        toml_settings = TomlConfigSettingsSource(
            settings_cls,
            toml_file=[_xdg_config_path(), Path("pin-actions.toml")],
        )
        pyproject_settings = PyprojectTomlConfigSettingsSource(settings_cls)
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
            toml_settings,
            pyproject_settings,
        )

    paths: list[Path] = Field(
        default_factory=lambda: [Path(".github/workflows"), Path("**/action.yml"), Path("**/action.yaml")],
        description="Scan these files/directories for workflow/action files; glob patterns supported",
    )
    github_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("PIN_ACTIONS_TOKEN", "GITHUB_TOKEN"),
        description="GitHub API token (env: GITHUB_TOKEN or PIN_ACTIONS_TOKEN)",
    )

    dry_run: bool = Field(
        default=False,
        description="Print changes without writing",
    )
    diff: bool = Field(
        default=False,
        description="Print a unified diff of changes (implies --dry-run)",
    )
    concurrency: int = Field(
        default=5,
        ge=1,
        description="Max concurrent GitHub API requests",
    )
    max_retries: int = Field(
        default=5,
        ge=1,
        description="Max retry attempts on 429/403 errors",
    )
    host: str = Field(
        default="github.com",
        description="GitHub hostname: 'github.com' or GHE Server hostname (e.g. 'github.example.com')",
    )

    @property
    def api_base_url(self) -> str:
        """Derive REST API base URL from host (GHE Server uses /api/v3)."""
        if self.host == "github.com":
            return "https://api.github.com"
        return f"https://{self.host}/api/v3"

    update: Literal["major", "minor", "patch"] | None = Field(
        default=None,
        description="Update strategy for pinned semver tags: 'major' (cross major boundaries, "
        "e.g. v4.0.5 -> v9.1.2), 'minor' (stay within same major, e.g. v4.0.5 -> v4.9.0), "
        "or 'patch' (stay within same major.minor, e.g. v4.2.3 -> v4.2.9). None = re-resolve "
        "the exact tag/branch recorded in the comment",
    )
    full_version: bool = Field(
        default=False,
        description="When --update is used, record the full resolved tag version in the comment "
        "(e.g. v4.1.7) instead of truncating to match the original precision (e.g. v4)",
    )
    verbose: int = Field(
        default=0,
        ge=0,
        le=3,
        validation_alias=AliasChoices("verbose", "v"),
        description="Verbosity level 0-3: 0=warnings, 1=info, 2=debug, 3=debug+dependency logs (httpx/httpcore)",
    )
    exclude_newer: str | None = Field(
        default=None,
        description=(
            "Exclude tags newer than this cutoff (cool-off period). "
            "Accepted: RFC 3339 timestamp (e.g., 2006-12-02T02:07:43Z), "
            "ISO 8601 duration (e.g., P7D, PT24H, P1W), or friendly duration "
            "(e.g., 7 days, 24 hours, 1 week). Only applies to --update"
        ),
    )

    @model_validator(mode="after")
    def _diff_implies_dry_run(self) -> Settings:
        """--diff never writes; treat it as an alias that also sets dry_run."""
        if self.diff:
            self.dry_run = True
        return self
