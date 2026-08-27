"""Integration tests for --provenance (off/warn/strict) end-to-end behavior."""

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pin_actions.config import Settings
from pin_actions.core import run
from pin_actions.errors import UnverifiedProvenanceError

if TYPE_CHECKING:
    from pathlib import Path


def _patched_client(*, resolve_sha_map: dict[tuple[str, str], str], provenance_result: str) -> MagicMock:
    """Build a MagicMock GitHubClient with resolve_sha/verify_provenance/list_tags stubbed."""
    mock_client = MagicMock()

    async def mock_resolve_sha(repo: str, ref: str) -> str:
        return resolve_sha_map.get((repo, ref), ref)

    mock_client.resolve_sha = AsyncMock(side_effect=mock_resolve_sha)
    mock_client.verify_provenance = AsyncMock(return_value=provenance_result)
    mock_client.aclose = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


class TestProvenanceOff:
    """Default 'off' mode: zero behavior change, verify_provenance never called."""

    @pytest.mark.asyncio
    async def test_off_never_calls_verify_provenance(self, tmp_path: Path) -> None:
        # Arrange
        workflows_dir = tmp_path / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)
        workflow = workflows_dir / "ci.yml"
        workflow.write_text("name: CI\njobs:\n  test:\n    steps:\n      - uses: actions/checkout@v4\n")
        settings = Settings(paths=[workflows_dir], github_token=None, dry_run=False, concurrency=1)
        assert settings.provenance == "off"

        sha = "a" * 40
        mock_client = _patched_client(resolve_sha_map={("actions/checkout", "v4"): sha}, provenance_result="unverified")

        # Act
        with patch("pin_actions.core.GitHubClient", return_value=mock_client):
            modified = await run(settings)

        # Assert
        mock_client.verify_provenance.assert_not_called()
        assert modified == [workflow]
        assert sha in workflow.read_text()


class TestProvenanceWarn:
    """'warn' mode: unverifiable SHAs are logged but the file is still written."""

    @pytest.mark.asyncio
    async def test_warn_logs_and_still_writes(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        # Arrange
        workflows_dir = tmp_path / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)
        workflow = workflows_dir / "ci.yml"
        workflow.write_text("name: CI\njobs:\n  test:\n    steps:\n      - uses: actions/checkout@v4\n")
        settings = Settings(paths=[workflows_dir], github_token=None, dry_run=False, concurrency=1, provenance="warn")

        sha = "b" * 40
        mock_client = _patched_client(resolve_sha_map={("actions/checkout", "v4"): sha}, provenance_result="unverified")

        # Act
        with patch("pin_actions.core.GitHubClient", return_value=mock_client), caplog.at_level("WARNING"):
            modified = await run(settings)

        # Assert
        mock_client.verify_provenance.assert_called_once_with("actions/checkout", sha)
        assert "Unverified provenance" in caplog.text
        assert modified == [workflow]
        assert sha in workflow.read_text()


class TestProvenanceStrict:
    """'strict' mode: unverifiable SHAs raise, wrapped in run()'s ExceptionGroup."""

    @pytest.mark.asyncio
    async def test_strict_raises_exception_group(self, tmp_path: Path) -> None:
        # Arrange
        workflows_dir = tmp_path / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)
        workflow = workflows_dir / "ci.yml"
        workflow.write_text("name: CI\njobs:\n  test:\n    steps:\n      - uses: actions/checkout@v4\n")
        settings = Settings(paths=[workflows_dir], github_token=None, dry_run=False, concurrency=1, provenance="strict")

        sha = "c" * 40
        mock_client = _patched_client(resolve_sha_map={("actions/checkout", "v4"): sha}, provenance_result="unverified")

        # Act / Assert
        with (
            patch("pin_actions.core.GitHubClient", return_value=mock_client),
            pytest.raises(ExceptionGroup) as exc_info,
        ):
            await run(settings)

        assert any(isinstance(exc, UnverifiedProvenanceError) for exc in exc_info.value.exceptions)
        assert workflow.read_text() == "name: CI\njobs:\n  test:\n    steps:\n      - uses: actions/checkout@v4\n"

    @pytest.mark.asyncio
    async def test_strict_passes_when_verified(self, tmp_path: Path) -> None:
        # Arrange
        workflows_dir = tmp_path / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)
        workflow = workflows_dir / "ci.yml"
        workflow.write_text("name: CI\njobs:\n  test:\n    steps:\n      - uses: actions/checkout@v4\n")
        settings = Settings(paths=[workflows_dir], github_token=None, dry_run=False, concurrency=1, provenance="strict")

        sha = "d" * 40
        mock_client = _patched_client(resolve_sha_map={("actions/checkout", "v4"): sha}, provenance_result="verified")

        # Act
        with patch("pin_actions.core.GitHubClient", return_value=mock_client):
            modified = await run(settings)

        # Assert
        assert modified == [workflow]
        assert sha in workflow.read_text()
