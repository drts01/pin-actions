"""Configuration & CLI settings."""

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """CLI & environment configuration for pin-actions."""

    model_config = SettingsConfigDict(
        env_prefix="PIN_ACTIONS_",
        case_sensitive=False,
    )

    path: Path = Field(
        default=Path(".github/workflows"),
        description="Path to scan for workflow/action files",
    )
    token: SecretStr | None = Field(
        default=None,
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
