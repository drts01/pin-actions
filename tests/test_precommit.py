"""Tests for pin_precommit_file (pre-commit config rev pinning)."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from pin_actions.client import GitHubClient
from pin_actions.errors import YAMLParseError
from pin_actions.precommit import PrecommitSettings, pin_precommit_file


class TestPrecommitDefaults:
    """Test PrecommitSettings defaults."""

    def test_default_paths(self) -> None:
        """Default paths is .pre-commit-config.yaml."""
        assert PrecommitSettings().paths == [Path(".pre-commit-config.yaml")]


class TestPinPrecommitFile:
    """Test pin_precommit_file rewriting repos[].rev to pinned SHAs."""

    @pytest.mark.asyncio
    async def test_new_pin(self, tmp_path: Path) -> None:
        """Pin a fresh (unpinned) rev to a commit SHA."""
        # Arrange
        client = GitHubClient(token="test", concurrency=1)
        config_file = tmp_path / ".pre-commit-config.yaml"
        config_file.write_text(
            "repos:\n  - repo: https://github.com/astral-sh/ruff-pre-commit\n    rev: v0.5.0\n",
        )

        async def mock_resolve_sha(repo: str, ref: str) -> str:
            assert repo == "astral-sh/ruff-pre-commit"
            assert ref == "v0.5.0"
            return "a" * 40

        # Act
        with patch.object(client, "resolve_sha", new=AsyncMock(side_effect=mock_resolve_sha)):
            modified = await pin_precommit_file(client, config_file, dry_run=False)

        # Assert
        assert modified
        content = config_file.read_text()
        assert "a" * 40 in content
        assert "# v0.5.0" in content

    @pytest.mark.asyncio
    async def test_already_pinned_updates_if_moved(self, tmp_path: Path) -> None:
        """Re-resolve already-pinned rev; update SHA if tag moved."""
        # Arrange
        client = GitHubClient(token="test", concurrency=1)
        old_sha = "b" * 40
        new_sha = "c" * 40
        config_file = tmp_path / ".pre-commit-config.yaml"
        config_file.write_text(
            f"repos:\n  - repo: https://github.com/astral-sh/ruff-pre-commit\n    rev: {old_sha}  # v0.5.0\n",
        )

        async def mock_resolve_sha(_repo: str, _ref: str) -> str:
            return new_sha

        # Act
        with patch.object(client, "resolve_sha", new=AsyncMock(side_effect=mock_resolve_sha)):
            modified = await pin_precommit_file(client, config_file, dry_run=False)

        # Assert
        assert modified
        content = config_file.read_text()
        assert new_sha in content
        assert old_sha not in content

    @pytest.mark.asyncio
    async def test_non_github_url_skipped(self, tmp_path: Path) -> None:
        """Skip repos[] entries whose repo URL isn't a recognizable GitHub clone URL."""
        # Arrange
        client = GitHubClient(token="test")
        config_file = tmp_path / ".pre-commit-config.yaml"
        original_content = "repos:\n  - repo: local\n    hooks:\n      - id: check-yaml\n"
        config_file.write_text(original_content)

        # Act
        modified = await pin_precommit_file(client, config_file, dry_run=False)

        # Assert
        assert not modified
        assert config_file.read_text() == original_content

    @pytest.mark.asyncio
    async def test_malformed_yaml_raises(self, tmp_path: Path) -> None:
        """Raise YAMLParseError on malformed YAML."""
        # Arrange
        client = GitHubClient(token="test")
        config_file = tmp_path / ".pre-commit-config.yaml"
        config_file.write_text("repos:\n  - repo: [\n")

        # Act, Assert
        with pytest.raises(YAMLParseError, match="Failed to parse YAML"):
            await pin_precommit_file(client, config_file, dry_run=False)

    @pytest.mark.asyncio
    async def test_dry_run_no_write(self, tmp_path: Path) -> None:
        """Don't write file in dry_run mode."""
        # Arrange
        client = GitHubClient(token="test", concurrency=1)
        config_file = tmp_path / ".pre-commit-config.yaml"
        original_content = "repos:\n  - repo: https://github.com/astral-sh/ruff-pre-commit\n    rev: v0.5.0\n"
        config_file.write_text(original_content)

        async def mock_resolve_sha(_repo: str, _ref: str) -> str:
            return "d" * 40

        # Act
        with patch.object(client, "resolve_sha", new=AsyncMock(side_effect=mock_resolve_sha)):
            modified = await pin_precommit_file(client, config_file, dry_run=True)

        # Assert
        assert modified
        assert config_file.read_text() == original_content
