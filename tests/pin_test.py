"""Test suite for pin-actions."""

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pin_actions.client import GitHubClient
from pin_actions.core import (
    _is_already_pinned,
    _is_local_action,
    _parse_uses,
    _walk_uses_keys,
    pin_file,
    run,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestHelpers:
    """Test helper functions."""

    def test_is_local_action_dot_slash(self) -> None:
        """Detect local actions with ./."""
        assert _is_local_action("./path/to/action")
        assert not _is_local_action("owner/repo")

    def test_is_local_action_docker(self) -> None:
        """Detect docker:// actions."""
        assert _is_local_action("docker://image:tag")
        assert not _is_local_action("owner/repo")

    def test_is_already_pinned_valid_sha(self) -> None:
        """Recognize 40-char hex SHA."""
        assert _is_already_pinned("abc1234def5678abc1234def5678abc1234def56")
        assert _is_already_pinned("0123456789abcdef0123456789abcdef01234567")

    def test_is_already_pinned_invalid(self) -> None:
        """Reject non-SHA refs."""
        assert not _is_already_pinned("v4")
        assert not _is_already_pinned("main")
        assert not _is_already_pinned("abc1234")  # Too short
        assert not _is_already_pinned("g" * 40)  # Invalid hex

    def test_parse_uses_valid(self) -> None:
        """Parse valid uses string."""
        result = _parse_uses("actions/checkout@v4")
        assert result == ("actions/checkout", "v4")

    def test_parse_uses_with_subpath(self) -> None:
        """Parse uses string with subpath."""
        result = _parse_uses("owner/repo/path/to/action@main")
        assert result == ("owner/repo/path/to/action", "main")

    def test_parse_uses_no_at(self) -> None:
        """Return None if no @ present."""
        assert _parse_uses("invalid-uses-string") is None

    def test_parse_uses_empty_parts(self) -> None:
        """Return None if repo or ref is empty."""
        assert _parse_uses("@v4") is None
        assert _parse_uses("actions/checkout@") is None

    def test_walk_uses_keys_dict(self) -> None:
        """Find uses keys in nested dict."""
        doc = {
            "jobs": {
                "test": {
                    "steps": [
                        {"uses": "actions/checkout@v4"},
                        {"run": "echo hello"},
                    ],
                },
            },
        }
        results = _walk_uses_keys(doc)
        assert len(results) == 1
        parent_obj, key, _path = results[0]
        assert parent_obj[key] == "actions/checkout@v4"
        assert key == "uses"

    def test_walk_uses_keys_multiple(self) -> None:
        """Find multiple uses keys."""
        doc = {
            "jobs": {
                "test": {
                    "steps": [
                        {"uses": "actions/checkout@v4"},
                        {"uses": "actions/setup-python@v4"},
                    ],
                },
            },
        }
        results = _walk_uses_keys(doc)
        assert len(results) == 2
        uses_values = [r[0][r[1]] for r in results]
        assert "actions/checkout@v4" in uses_values
        assert "actions/setup-python@v4" in uses_values


class TestGitHubClient:
    """Test GitHubClient with async fixtures."""

    @pytest.mark.asyncio
    async def test_resolve_sha_already_pinned(self) -> None:
        """Skip API call if ref is already SHA."""
        client = GitHubClient(token="test")
        sha = "abc1234def5678abc1234def5678abc1234def56"
        result = await client.resolve_sha("owner/repo", sha)
        assert result == sha

    @pytest.mark.asyncio
    async def test_resolve_sha_cache_hit(self) -> None:
        """Return cached SHA without second request."""
        client = GitHubClient(token="test", concurrency=1)

        # Manually populate cache
        client._cache[("owner/repo", "v4")] = "abc1234def5678abc1234def5678abc1234def56"

        result = await client.resolve_sha("owner/repo", "v4")
        assert result == "abc1234def5678abc1234def5678abc1234def56"

    @pytest.mark.asyncio
    async def test_resolve_sha_api_call(self) -> None:
        """Mock API response via patch."""
        client = GitHubClient(token="test", concurrency=1)

        async def mock_request_with_backoff(_repo: str, _ref: str) -> str:
            return "abc1234def5678abc1234def5678abc1234def56"

        with patch.object(client, "_request_with_backoff", side_effect=mock_request_with_backoff):
            result = await client.resolve_sha("owner/repo", "v4")
            assert result == "abc1234def5678abc1234def5678abc1234def56"
            assert client._cache[("owner/repo", "v4")] == "abc1234def5678abc1234def5678abc1234def56"

    @pytest.mark.asyncio
    async def test_resolve_sha_404_raises(self) -> None:
        """Raise ValueError on 404."""
        client = GitHubClient(token="test", concurrency=1)

        async def mock_request_with_backoff(repo: str, ref: str) -> str:
            raise ValueError(f"Ref not found: {repo}@{ref}")

        with (
            patch.object(client, "_request_with_backoff", side_effect=mock_request_with_backoff),
            pytest.raises(ValueError, match="Ref not found"),
        ):
            await client.resolve_sha("owner/repo", "nonexistent")

    @pytest.mark.asyncio
    async def test_resolve_sha_429_retry(self) -> None:
        """Retry logic tested via mock."""
        client = GitHubClient(token="test", concurrency=1, max_retries=3)

        async def mock_request_with_backoff(_repo: str, _ref: str) -> str:
            return "abc1234def5678abc1234def5678abc1234def56"

        with patch.object(client, "_request_with_backoff", side_effect=mock_request_with_backoff):
            result = await client.resolve_sha("owner/repo", "v4")
            assert result == "abc1234def5678abc1234def5678abc1234def56"

    @pytest.mark.asyncio
    async def test_resolve_sha_429_exhausted(self) -> None:
        """Raise ValueError after max retries on 429."""
        client = GitHubClient(token="test", concurrency=1, max_retries=2)

        async def mock_request_with_backoff(repo: str, ref: str) -> str:
            raise ValueError(f"Failed to resolve {repo}@{ref}")

        with (
            patch.object(client, "_request_with_backoff", side_effect=mock_request_with_backoff),
            pytest.raises(ValueError, match="Failed to resolve"),
        ):
            await client.resolve_sha("owner/repo", "v4")


class TestPinFile:
    """Test file pinning logic."""

    @pytest.mark.asyncio
    async def test_pin_file_modifies_mutable_refs(self, tmp_path: Path) -> None:
        """Rewrite mutable refs to pinned SHAs."""
        client = GitHubClient(token="test", concurrency=1)

        workflow_file = tmp_path / "workflow.yml"
        workflow_file.write_text(
            "name: Test\n"
            "jobs:\n"
            "  build:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - uses: actions/checkout@v4\n"
            "      - uses: actions/setup-python@v4\n",
        )

        async def mock_resolve_sha(repo: str, ref: str) -> str:
            shas = {
                ("actions/checkout", "v4"): "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                ("actions/setup-python", "v4"): "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            }
            return shas.get((repo, ref), ref)

        with patch.object(client, "resolve_sha", new=AsyncMock(side_effect=mock_resolve_sha)):
            modified = await pin_file(client, workflow_file, dry_run=False)
            assert modified

        content = workflow_file.read_text()
        assert "actions/checkout@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" in content
        assert "actions/setup-python@bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" in content

    @pytest.mark.asyncio
    async def test_pin_file_skips_already_pinned(self, tmp_path: Path) -> None:
        """Don't rewrite already-pinned refs."""
        client = GitHubClient(token="test")

        workflow_file = tmp_path / "workflow.yml"
        original_content = (
            "name: Test\n"
            "jobs:\n"
            "  build:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - uses: actions/checkout@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        )
        workflow_file.write_text(original_content)

        modified = await pin_file(client, workflow_file, dry_run=False)
        assert not modified
        assert workflow_file.read_text() == original_content

    @pytest.mark.asyncio
    async def test_pin_file_skips_local_actions(self, tmp_path: Path) -> None:
        """Don't process local actions."""
        client = GitHubClient(token="test")

        workflow_file = tmp_path / "workflow.yml"
        original_content = (
            "name: Test\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: ./path/to/local@v1\n"
        )
        workflow_file.write_text(original_content)

        modified = await pin_file(client, workflow_file, dry_run=False)
        assert not modified

    @pytest.mark.asyncio
    async def test_pin_file_dry_run_no_write(self, tmp_path: Path) -> None:
        """Don't write file in dry_run mode."""
        client = GitHubClient(token="test", concurrency=1)

        workflow_file = tmp_path / "workflow.yml"
        original_content = "name: Test\njobs:\n  build:\n    steps:\n      - uses: actions/checkout@v4\n"
        workflow_file.write_text(original_content)

        async def mock_resolve_sha(_repo: str, _ref: str) -> str:
            return "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

        with patch.object(client, "resolve_sha", new=AsyncMock(side_effect=mock_resolve_sha)):
            modified = await pin_file(client, workflow_file, dry_run=True)
            assert modified
        # File should remain unchanged
        assert workflow_file.read_text() == original_content

    @pytest.mark.asyncio
    async def test_pin_file_preserves_formatting(self, tmp_path: Path) -> None:
        """Preserve YAML formatting and comments on unchanged lines."""
        client = GitHubClient(token="test", concurrency=1)

        workflow_file = tmp_path / "workflow.yml"
        original_content = (
            "name: Test Workflow  # workflow name\n"
            "# Configuration\n"
            "jobs:\n"
            "  build:  # build job\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      # First step\n"
            "      - uses: actions/checkout@v4\n"
            "      - run: echo hello\n"
        )
        workflow_file.write_text(original_content)

        async def mock_resolve_sha(_repo: str, _ref: str) -> str:
            return "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

        with patch.object(client, "resolve_sha", new=AsyncMock(side_effect=mock_resolve_sha)):
            modified = await pin_file(client, workflow_file, dry_run=False)
            assert modified

        content = workflow_file.read_text()
        # Original comments should still be present
        assert "# workflow name" in content
        assert "# Configuration" in content
        assert "# build job" in content
        # Pinned ref should be there
        assert "actions/checkout@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" in content


class TestRun:
    """Test main run logic."""

    @pytest.mark.asyncio
    async def test_run_processes_all_workflows(self, tmp_path: Path) -> None:
        """Process all .yml/.yaml files in path."""
        workflows_dir = tmp_path / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)

        workflow1 = workflows_dir / "ci.yml"
        workflow1.write_text("name: CI\njobs:\n  test:\n    steps:\n      - uses: actions/checkout@v4\n")

        workflow2 = workflows_dir / "release.yaml"
        workflow2.write_text("name: Release\njobs:\n  deploy:\n    steps:\n      - uses: actions/upload-artifact@v3\n")

        from pin_actions.config import Settings

        settings = Settings(
            path=workflows_dir,
            token=None,
            dry_run=False,
            concurrency=1,
        )

        async def mock_resolve_sha(repo: str, ref: str) -> str:
            shas = {
                ("actions/checkout", "v4"): "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                ("actions/upload-artifact", "v3"): "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            }
            return shas.get((repo, ref), ref)

        with patch("pin_actions.core.GitHubClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.resolve_sha = AsyncMock(side_effect=mock_resolve_sha)
            mock_client_class.return_value = mock_client

            modified = await run(settings)

            assert len(modified) == 2
            assert workflow1 in modified
            assert workflow2 in modified

    @pytest.mark.asyncio
    async def test_run_no_files(self, tmp_path: Path) -> None:
        """Handle empty workflows directory gracefully."""
        from pin_actions.config import Settings

        workflows_dir = tmp_path / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)

        settings = Settings(path=workflows_dir, token=None, dry_run=False)
        modified = await run(settings)

        assert modified == []

    @pytest.mark.asyncio
    async def test_run_missing_path_raises(self, tmp_path: Path) -> None:
        """Raise ValueError if path doesn't exist."""
        from pin_actions.config import Settings

        nonexistent = tmp_path / "nonexistent"
        settings = Settings(path=nonexistent, token=None)

        with pytest.raises(ValueError, match="Path does not exist"):
            await run(settings)
