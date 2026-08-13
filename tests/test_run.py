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


class TestRunSharedClient:
    """Test run with pre-built shared GitHubClient."""

    @pytest.mark.asyncio
    async def test_uses_provided_client_without_creating_new_one(self, tmp_path: Path) -> None:
        """Use provided client without instantiating GitHubClient internally."""
        # Arrange
        workflows_dir = tmp_path / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)

        workflow = workflows_dir / "ci.yml"
        workflow.write_text("name: CI\njobs:\n  test:\n    steps:\n      - uses: actions/checkout@v4\n")

        settings = Settings(path=workflows_dir, github_token=None, dry_run=False)

        # Mock the client and verify GitHubClient constructor is never called
        async def mock_resolve_sha(_repo: str, ref: str) -> str:
            return "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" if ref == "v4" else ref

        provided_client = MagicMock()
        provided_client.resolve_sha = AsyncMock(side_effect=mock_resolve_sha)

        # Act
        with patch("pin_actions.core.GitHubClient") as mock_client_class:
            modified = await run(settings, client=provided_client)

            # Assert: GitHubClient constructor should never be called
            mock_client_class.assert_not_called()

        assert len(modified) == 1
        assert workflow in modified
        # Verify client method was called
        provided_client.resolve_sha.assert_called()

    @pytest.mark.asyncio
    async def test_shared_client_across_multiple_settings(self, tmp_path: Path) -> None:
        """Reuse one client across multiple run() calls."""
        # Arrange: create two separate workflow directories
        dir_a = tmp_path / "repo_a" / ".github" / "workflows"
        dir_a.mkdir(parents=True)
        workflow_a = dir_a / "ci.yml"
        workflow_a.write_text("name: CI\njobs:\n  test:\n    steps:\n      - uses: actions/checkout@v4\n")

        dir_b = tmp_path / "repo_b" / ".github" / "workflows"
        dir_b.mkdir(parents=True)
        workflow_b = dir_b / "release.yaml"
        workflow_b.write_text("name: Release\njobs:\n  deploy:\n    steps:\n      - uses: actions/upload-artifact@v3\n")

        settings_a = Settings(path=dir_a, github_token=None, dry_run=False)
        settings_b = Settings(path=dir_b, github_token=None, dry_run=False)

        # Mock resolve_sha to track calls
        resolve_calls = []

        async def mock_resolve_sha(repo: str, ref: str) -> str:
            resolve_calls.append((repo, ref))
            shas = {
                ("actions/checkout", "v4"): "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                ("actions/upload-artifact", "v3"): "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            }
            return shas.get((repo, ref), ref)

        provided_client = MagicMock()
        provided_client.resolve_sha = AsyncMock(side_effect=mock_resolve_sha)

        # Act: call run twice with the same client
        with patch("pin_actions.core.GitHubClient") as mock_client_class:
            modified_a = await run(settings_a, client=provided_client)
            modified_b = await run(settings_b, client=provided_client)

            # Assert: GitHubClient constructor should never be called
            mock_client_class.assert_not_called()

        assert len(modified_a) == 1
        assert workflow_a in modified_a
        assert len(modified_b) == 1
        assert workflow_b in modified_b

        # Both resolve calls should have used the same client instance
        assert provided_client.resolve_sha.call_count == 2
        assert ("actions/checkout", "v4") in resolve_calls
        assert ("actions/upload-artifact", "v3") in resolve_calls

    @pytest.mark.asyncio
    async def test_run_without_client_still_works(self, tmp_path: Path) -> None:
        """Ensure backward compatibility: calling run() without client kwarg works as before."""
        # Arrange
        workflows_dir = tmp_path / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)

        workflow = workflows_dir / "ci.yml"
        workflow.write_text("name: CI\njobs:\n  test:\n    steps:\n      - uses: actions/checkout@v4\n")

        settings = Settings(path=workflows_dir, github_token=None, dry_run=False, concurrency=1)

        async def mock_resolve_sha(_repo: str, ref: str) -> str:
            return "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" if ref == "v4" else ref

        # Act
        with patch("pin_actions.core.GitHubClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.resolve_sha = AsyncMock(side_effect=mock_resolve_sha)
            mock_client.aclose = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            modified = await run(settings)

        # Assert: GitHubClient constructor should be called (default branch)
        mock_client_class.assert_called_once()
        assert len(modified) == 1
        assert workflow in modified
