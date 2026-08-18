"""Tests for Settings configuration (env vars, validation, defaults)."""

from pathlib import Path

import pytest
from pin_actions.config import Settings
from pydantic import ValidationError


class TestSettingsDefaults:
    """Test Settings default values."""

    def test_default_values(self) -> None:
        """Check default values for all fields."""
        # Arrange, Act
        settings = Settings()

        # Assert
        assert settings.path == Path(".github/workflows")
        assert settings.github_token is None
        assert settings.dry_run is False
        assert settings.concurrency == 5
        assert settings.max_retries == 5
        assert settings.github_api == "https://api.github.com"
        assert settings.update is None
        assert settings.full_version is False
        assert settings.cache_dir == Path.home() / ".cache" / "pin-actions"
        assert settings.cache_ttl == 3600
        assert settings.cache is True
        assert settings.verbose == 0


class TestSettingsValidation:
    """Test Settings validation constraints."""

    def test_concurrency_must_be_positive(self) -> None:
        """Concurrency must be >= 1."""
        # Arrange, Act, Assert
        with pytest.raises(ValidationError):
            Settings(concurrency=0)

        with pytest.raises(ValidationError):
            Settings(concurrency=-1)

    def test_max_retries_must_be_positive(self) -> None:
        """Max retries must be >= 1."""
        # Arrange, Act, Assert
        with pytest.raises(ValidationError):
            Settings(max_retries=0)

        with pytest.raises(ValidationError):
            Settings(max_retries=-1)

    def test_cache_ttl_must_be_positive(self) -> None:
        """Cache TTL must be >= 1."""
        # Arrange, Act, Assert
        with pytest.raises(ValidationError):
            Settings(cache_ttl=0)

        with pytest.raises(ValidationError):
            Settings(cache_ttl=-1)

    def test_verbose_bounds(self) -> None:
        """Verbose must be 0-3."""
        # Arrange, Act
        settings_min = Settings(verbose=0)
        settings_max = Settings(verbose=3)

        # Assert
        assert settings_min.verbose == 0
        assert settings_max.verbose == 3

        # Act, Assert
        with pytest.raises(ValidationError):
            Settings(verbose=-1)

        with pytest.raises(ValidationError):
            Settings(verbose=4)

    def test_update_constraint_enum(self) -> None:
        """Update must be 'major', 'minor', 'patch', or None."""
        # Arrange, Act
        settings_none = Settings(update=None)
        settings_major = Settings(update="major")
        settings_minor = Settings(update="minor")
        settings_patch = Settings(update="patch")

        # Assert
        assert settings_none.update is None
        assert settings_major.update == "major"
        assert settings_minor.update == "minor"
        assert settings_patch.update == "patch"

        # Act, Assert
        with pytest.raises(ValidationError):
            Settings(update="invalid")


class TestSettingsEnvVars:
    """Test environment variable precedence and aliasing."""

    def test_github_token_from_env_pin_actions_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Read GITHUB_TOKEN from PIN_ACTIONS_TOKEN env var."""
        # Arrange
        monkeypatch.setenv("PIN_ACTIONS_TOKEN", "test_token_from_env")

        # Act
        settings = Settings(_cli_parse_args=False)

        # Assert
        assert settings.github_token is not None
        assert settings.github_token.get_secret_value() == "test_token_from_env"

    def test_github_token_from_env_github_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Read GITHUB_TOKEN from GITHUB_TOKEN env var (standard)."""
        # Arrange
        monkeypatch.delenv("PIN_ACTIONS_TOKEN", raising=False)
        monkeypatch.setenv("GITHUB_TOKEN", "test_token_from_github")

        # Act
        settings = Settings(_cli_parse_args=False)

        # Assert
        assert settings.github_token is not None
        assert settings.github_token.get_secret_value() == "test_token_from_github"

    def test_github_token_pin_actions_precedence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """PIN_ACTIONS_TOKEN takes precedence over GITHUB_TOKEN."""
        # Arrange
        monkeypatch.setenv("PIN_ACTIONS_TOKEN", "pin_actions_token")
        monkeypatch.setenv("GITHUB_TOKEN", "github_token")

        # Act
        settings = Settings(_cli_parse_args=False)

        # Assert
        assert settings.github_token is not None
        assert settings.github_token.get_secret_value() == "pin_actions_token"

    def test_cache_ttl_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Read cache_ttl from PIN_ACTIONS_CACHE_TTL env var."""
        # Arrange
        monkeypatch.setenv("PIN_ACTIONS_CACHE_TTL", "7200")

        # Act
        settings = Settings(_cli_parse_args=False)

        # Assert
        assert settings.cache_ttl == 7200

    def test_verbose_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Read verbose from PIN_ACTIONS_VERBOSE or PIN_ACTIONS_V env var."""
        # Arrange
        monkeypatch.setenv("PIN_ACTIONS_VERBOSE", "2")

        # Act
        settings = Settings(_cli_parse_args=False)

        # Assert
        assert settings.verbose == 2


class TestSettingsUpdateFlag:
    """Test update strategy flag."""

    def test_update_major(self) -> None:
        """Update strategy 'major' accepted."""
        # Arrange, Act
        settings = Settings(update="major")

        # Assert
        assert settings.update == "major"

    def test_update_minor(self) -> None:
        """Update strategy 'minor' accepted."""
        # Arrange, Act
        settings = Settings(update="minor")

        # Assert
        assert settings.update == "minor"

    def test_update_patch(self) -> None:
        """Update strategy 'patch' accepted."""
        # Arrange, Act
        settings = Settings(update="patch")

        # Assert
        assert settings.update == "patch"


class TestSettingsFullVersion:
    """Test full_version flag."""

    def test_full_version_true(self) -> None:
        """full_version=True preserves full tag precision."""
        # Arrange, Act
        settings = Settings(full_version=True)

        # Assert
        assert settings.full_version is True

    def test_full_version_false_default(self) -> None:
        """full_version defaults to False."""
        # Arrange, Act
        settings = Settings()

        # Assert
        assert settings.full_version is False


class TestSettingsConfigFile:
    """Test TOML config file loading (XDG, cwd, pyproject.toml) and precedence."""

    def test_cwd_toml_file_loaded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """pin-actions.toml in cwd sets field values."""
        # Arrange
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pin-actions.toml").write_text("concurrency = 42\n")

        # Act
        settings = Settings(_cli_parse_args=False)

        # Assert
        assert settings.concurrency == 42

    def test_xdg_config_file_loaded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """XDG_CONFIG_HOME/pin-actions/config.toml sets field values."""
        # Arrange
        xdg = tmp_path / "xdg"
        (xdg / "pin-actions").mkdir(parents=True)
        (xdg / "pin-actions" / "config.toml").write_text("concurrency = 7\n")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
        monkeypatch.chdir(tmp_path)

        # Act
        settings = Settings(_cli_parse_args=False)

        # Assert
        assert settings.concurrency == 7

    def test_cwd_overrides_xdg(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """pin-actions.toml (cwd) takes precedence over XDG config.toml."""
        # Arrange
        xdg = tmp_path / "xdg"
        (xdg / "pin-actions").mkdir(parents=True)
        (xdg / "pin-actions" / "config.toml").write_text("concurrency = 7\n")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pin-actions.toml").write_text("concurrency = 42\n")

        # Act
        settings = Settings(_cli_parse_args=False)

        # Assert
        assert settings.concurrency == 42

    def test_env_var_overrides_toml_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """PIN_ACTIONS_* env var takes precedence over any TOML config file."""
        # Arrange
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pin-actions.toml").write_text("concurrency = 42\n")
        monkeypatch.setenv("PIN_ACTIONS_CONCURRENCY", "3")

        # Act
        settings = Settings(_cli_parse_args=False)

        # Assert
        assert settings.concurrency == 3

    def test_pyproject_toml_tool_table_loaded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """pyproject.toml [tool.pin-actions] table sets field values."""
        # Arrange
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text("[tool.pin-actions]\nconcurrency = 11\n")

        # Act
        settings = Settings(_cli_parse_args=False)

        # Assert
        assert settings.concurrency == 11

    def test_cwd_toml_overrides_pyproject_toml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """pin-actions.toml (cwd) takes precedence over pyproject.toml table."""
        # Arrange
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text("[tool.pin-actions]\nconcurrency = 11\n")
        (tmp_path / "pin-actions.toml").write_text("concurrency = 42\n")

        # Act
        settings = Settings(_cli_parse_args=False)

        # Assert
        assert settings.concurrency == 42

    def test_no_config_file_uses_default(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Missing config files (no pin-actions.toml, no pyproject.toml) fall back to field default."""
        # Arrange
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

        # Act
        settings = Settings(_cli_parse_args=False)

        # Assert
        assert settings.concurrency == 5
