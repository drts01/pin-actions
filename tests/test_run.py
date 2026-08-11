"""Tests for run function (orchestration, error handling, ExceptionGroup)."""

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pin_actions.config import Settings
from pin_actions.core import run
from pin_actions.errors import YAMLParseError

if TYPE_CHECKING:
    from pathlib import Path


class TestRunBasic:
    """Test run function orchestration."""

    @pytest.mark.asyncio
    async def test_processes_all_workflows(self, tmp_path: Path) -> None:
        """Process all .yml/.yaml files in path."""
        # Arrange
        workflows_dir = tmp_path / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)

        workflow1 = workflows_dir / "ci.yml"
        workflow1.write_text("name: CI\njobs:\n  test:\n    steps:\n      - uses: actions/checkout@v4\n")

        workflow2 = workflows_dir / "release.yaml"
        workflow2.write_text("name: Release\njobs:\n  deploy:\n    steps:\n      - uses: actions/upload-artifact@v3\n")

        settings = Settings(
            path=workflows_dir,
            github_token=None,
            dry_run=False,
            concurrency=1,
        )

        async def mock_resolve_sha(repo: str, ref: str) -> str:
            shas = {
                ("actions/checkout", "v4"): "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                ("actions/upload-artifact", "v3"): "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            }
            return shas.get((repo, ref), ref)

        # Act
        with patch("pin_actions.core.GitHubClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.resolve_sha = AsyncMock(side_effect=mock_resolve_sha)
            mock_client_class.return_value = mock_client

            modified = await run(settings)

        # Assert
        assert len(modified) == 2
        assert workflow1 in modified
        assert workflow2 in modified


class TestRunEmpty:
    """Test run with empty directory."""

    @pytest.mark.asyncio
    async def test_no_files(self, tmp_path: Path) -> None:
        """Handle empty workflows directory gracefully."""
        # Arrange
        workflows_dir = tmp_path / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)

        settings = Settings(path=workflows_dir, github_token=None, dry_run=False)

        # Act
        modified = await run(settings)

        # Assert
        assert modified == []


class TestRunErrors:
    """Test run error handling."""

    @pytest.mark.asyncio
    async def test_missing_path_raises(self, tmp_path: Path) -> None:
        """Raise ValueError if path doesn't exist."""
        # Arrange
        nonexistent = tmp_path / "nonexistent"
        settings = Settings(path=nonexistent, github_token=None)

        # Act, Assert
        with pytest.raises(ValueError, match="Path does not exist"):
            await run(settings)

    @pytest.mark.asyncio
    async def test_partial_failure_raises_exception_group(self, tmp_path: Path) -> None:
        """Raise ExceptionGroup when one file fails but others succeed."""
        # Arrange
        workflows_dir = tmp_path / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)

        good_file = workflows_dir / "ci.yml"
        good_file.write_text("name: CI\njobs:\n  test:\n    steps:\n      - uses: actions/checkout@v4\n")

        bad_file = workflows_dir / "broken.yml"
        bad_file.write_text("jobs:\n  build:\n    steps:\n    - uses: actions/checkout@v4\n  bad: [\n")

        settings = Settings(path=workflows_dir, github_token=None, dry_run=False, concurrency=1)

        async def mock_resolve_sha(_repo: str, ref: str) -> str:
            return "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" if ref == "v4" else ref

        # Act, Assert
        with patch("pin_actions.core.GitHubClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.resolve_sha = AsyncMock(side_effect=mock_resolve_sha)
            mock_client_class.return_value = mock_client

            with pytest.raises(ExceptionGroup) as exc_info:
                await run(settings)

        assert len(exc_info.value.exceptions) == 1
        assert isinstance(exc_info.value.exceptions[0], YAMLParseError)
