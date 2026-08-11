"""Configuration & CLI settings."""

from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """CLI & environment configuration for pin-actions."""

    model_config = SettingsConfigDict(
        env_prefix="PIN_ACTIONS_",
        case_sensitive=False,
        populate_by_name=True,
    )

    path: Path = Field(
        default=Path(".github/workflows"),
        description="Path to scan for workflow/action files",
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
    github_api: str = Field(
        default="https://api.github.com",
        description="GitHub API base URL",
    )
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
    cache_dir: Path = Field(
        default=Path.home() / ".cache" / "pin-actions",
        description="Directory for persistent disk cache",
    )
    cache_ttl: int = Field(
        default=3600,
        ge=1,
        description="Cache entry TTL in seconds (default 1 hour)",
    )
    cache: bool = Field(
        default=True,
        description="Enable persistent disk caching",
    )
    verbose: int = Field(
        default=0,
        ge=0,
        le=3,
        validation_alias=AliasChoices("verbose", "v"),
        description="Verbosity level 0-3: 0=warnings, 1=info, 2=debug, 3=debug+dependency logs (httpx/httpcore)",
    )
