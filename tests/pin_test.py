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
from pin_actions.errors import (
    InvalidRefError,
    RateLimitExhaustedError,
    YAMLParseError,
)
from pin_actions.versioning import parse_tag_version, select_latest_tag

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
        """Raise InvalidRefError on 404."""
        client = GitHubClient(token="test", concurrency=1)

        async def mock_request_with_backoff(repo: str, ref: str) -> str:
            raise InvalidRefError(repo, ref)

        with (
            patch.object(client, "_request_with_backoff", side_effect=mock_request_with_backoff),
            pytest.raises(InvalidRefError, match="Ref not found"),
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
        """Raise RateLimitExhaustedError after max retries on 429."""
        client = GitHubClient(token="test", concurrency=1, max_retries=2)

        async def mock_request_with_backoff(repo: str, ref: str) -> str:
            raise RateLimitExhaustedError(repo, ref, 2)

        with (
            patch.object(client, "_request_with_backoff", side_effect=mock_request_with_backoff),
            pytest.raises(RateLimitExhaustedError, match="Failed to resolve"),
        ):
            await client.resolve_sha("owner/repo", "v4")

    @pytest.mark.asyncio
    async def test_resolve_sha_404_real_backoff_path(self) -> None:
        """Exercise real _request_with_backoff 404 handling via mocked httpx2 client."""
        client = GitHubClient(token="test", concurrency=1)

        mock_resp = MagicMock()
        mock_resp.status_code = 404

        mock_http_client = MagicMock()
        mock_http_client.get = AsyncMock(return_value=mock_resp)
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("pin_actions.client.httpx2.AsyncClient", return_value=mock_http_client),
            pytest.raises(InvalidRefError, match="Ref not found"),
        ):
            await client.resolve_sha("owner/repo", "nonexistent")

    @pytest.mark.asyncio
    async def test_resolve_sha_429_real_backoff_exhausted(self) -> None:
        """Exercise real _request_with_backoff 429-exhausted handling via mocked httpx2 client."""
        client = GitHubClient(token="test", concurrency=1, max_retries=2)

        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {"Retry-After": "0"}

        mock_http_client = MagicMock()
        mock_http_client.get = AsyncMock(return_value=mock_resp)
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("pin_actions.client.httpx2.AsyncClient", return_value=mock_http_client),
            pytest.raises(RateLimitExhaustedError, match="Failed to resolve"),
        ):
            await client.resolve_sha("owner/repo", "v4")

    @pytest.mark.asyncio
    async def test_resolve_sha_composite_action_subpath_strips_subdir(self) -> None:
        """Composite action ('owner/repo/subdir') hits commits API on 'owner/repo' only.

        Regression: previously the full 'owner/repo/subdir' string was used as the repo
        segment of the commits URL, causing a spurious 404 for any 'uses: owner/repo/subdir@ref'.
        """
        client = GitHubClient(token="test", concurrency=1)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"sha": "abc1234def5678abc1234def5678abc1234def56"}

        mock_http_client = MagicMock()
        mock_http_client.get = AsyncMock(return_value=mock_resp)
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=None)

        with patch("pin_actions.client.httpx2.AsyncClient", return_value=mock_http_client):
            result = await client.resolve_sha("uhg-pipelines/epl-jf/saas-setup", "v5")

        assert result == "abc1234def5678abc1234def5678abc1234def56"
        called_url = mock_http_client.get.call_args.args[0]
        assert called_url.endswith("/repos/uhg-pipelines/epl-jf/commits/v5")


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
    async def test_pin_file_skips_bare_sha_without_comment(self, tmp_path: Path) -> None:
        """Don't rewrite a bare SHA that has no '# tag' comment to re-resolve against."""
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
    async def test_pin_file_updates_already_pinned_ref(self, tmp_path: Path) -> None:
        """Re-resolve an already-pinned 'sha  # tag' entry and update the SHA if it moved.

        Mirrors mheap/pin-github-action's default behavior: pinning is not a
        one-way, idempotent operation. Every run re-resolves the tag/branch
        recorded in the trailing comment, so a tag that has since moved to a
        new commit gets its SHA updated on the next run.
        """
        client = GitHubClient(token="test", concurrency=1)

        old_sha = "a" * 40
        new_sha = "b" * 40
        workflow_file = tmp_path / "workflow.yml"
        workflow_file.write_text(
            f"name: Test\njobs:\n  build:\n    steps:\n      - uses: actions/checkout@{old_sha}  # v4\n",
        )

        async def mock_resolve_sha(_repo: str, _ref: str) -> str:
            return new_sha

        with patch.object(client, "resolve_sha", new=AsyncMock(side_effect=mock_resolve_sha)):
            modified = await pin_file(client, workflow_file, dry_run=False)
            assert modified

        content = workflow_file.read_text()
        assert new_sha in content
        assert old_sha not in content
        assert "# v4" in content

    @pytest.mark.asyncio
    async def test_pin_file_already_pinned_ref_unchanged_when_sha_same(self, tmp_path: Path) -> None:
        """No file modification if re-resolving an already-pinned tag returns the same SHA."""
        client = GitHubClient(token="test", concurrency=1)

        sha = "a" * 40
        workflow_file = tmp_path / "workflow.yml"
        original_content = f"name: Test\njobs:\n  build:\n    steps:\n      - uses: actions/checkout@{sha}  # v4\n"
        workflow_file.write_text(original_content)

        async def mock_resolve_sha(_repo: str, _ref: str) -> str:
            return sha

        with patch.object(client, "resolve_sha", new=AsyncMock(side_effect=mock_resolve_sha)):
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

    @pytest.mark.asyncio
    async def test_pin_file_malformed_yaml_raises(self, tmp_path: Path) -> None:
        """Raise YAMLParseError on malformed YAML."""
        client = GitHubClient(token="test")

        workflow_file = tmp_path / "workflow.yml"
        workflow_file.write_text("jobs:\n  build:\n    steps:\n    - uses: actions/checkout@v4\n  bad indent: [\n")

        with pytest.raises(YAMLParseError, match="Failed to parse YAML"):
            await pin_file(client, workflow_file, dry_run=False)

    @pytest.mark.asyncio
    async def test_pin_file_propagates_github_api_error(self, tmp_path: Path) -> None:
        """Propagate GitHubAPIError from client.resolve_sha without swallowing."""
        client = GitHubClient(token="test", concurrency=1)

        workflow_file = tmp_path / "workflow.yml"
        workflow_file.write_text("jobs:\n  build:\n    steps:\n      - uses: actions/checkout@nonexistent\n")

        async def mock_resolve_sha(repo: str, ref: str) -> str:
            raise InvalidRefError(repo, ref)

        with (
            patch.object(client, "resolve_sha", new=AsyncMock(side_effect=mock_resolve_sha)),
            pytest.raises(InvalidRefError, match="Ref not found"),
        ):
            await pin_file(client, workflow_file, dry_run=False)

    @pytest.mark.asyncio
    async def test_pin_file_with_ref_new_pin(self, tmp_path: Path) -> None:
        """Pin a fresh with.ref: v3.0.0 (no SHA yet) → resolves and writes bare sha + comment."""
        client = GitHubClient(token="test", concurrency=1)

        workflow_file = tmp_path / "workflow.yml"
        workflow_file.write_text(
            "name: Test\n"
            "jobs:\n"
            "  build:\n"
            "    steps:\n"
            "      - name: Checkout other repo\n"
            "        uses: actions/checkout@v4\n"
            "        with:\n"
            "          repository: other/repo\n"
            "          ref: v3.0.0\n"
        )

        async def mock_resolve_sha(repo: str, ref: str) -> str:
            if repo == "other/repo" and ref == "v3.0.0":
                return "cccccccccccccccccccccccccccccccccccccccc"
            return "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

        with patch.object(client, "resolve_sha", new=AsyncMock(side_effect=mock_resolve_sha)):
            modified = await pin_file(client, workflow_file, dry_run=False)
            assert modified

        content = workflow_file.read_text()
        assert "ref: cccccccccccccccccccccccccccccccccccccccc # v3.0.0" in content
        assert "repository: other/repo" in content

    @pytest.mark.asyncio
    async def test_pin_file_with_ref_already_pinned_updates_if_moved(self, tmp_path: Path) -> None:
        """Re-resolve already-pinned with.ref with comment; update SHA if tag moved."""
        client = GitHubClient(token="test", concurrency=1)

        old_sha = "d" * 40
        new_sha = "e" * 40
        workflow_file = tmp_path / "workflow.yml"
        workflow_file.write_text(
            "name: Test\n"
            "jobs:\n"
            "  build:\n"
            "    steps:\n"
            "      - name: Checkout prek\n"
            "        uses: actions/checkout@v4\n"
            "        with:\n"
            f"          repository: j178/prek-action\n"
            f"          ref: {old_sha}  # v3.0.0\n"
        )

        async def mock_resolve_sha(_repo: str, _ref: str) -> str:
            return new_sha

        with patch.object(client, "resolve_sha", new=AsyncMock(side_effect=mock_resolve_sha)):
            modified = await pin_file(client, workflow_file, dry_run=False)
            assert modified

        content = workflow_file.read_text()
        assert f"ref: {new_sha} # v3.0.0" in content
        assert old_sha not in content

    @pytest.mark.asyncio
    async def test_pin_file_with_ref_missing_repository_skipped(self, tmp_path: Path) -> None:
        """Skip with.ref if no with.repository sibling (can't resolve without knowing repo)."""
        client = GitHubClient(token="test")

        workflow_file = tmp_path / "workflow.yml"
        pinned_sha = "a" * 40
        original_content = (
            "name: Test\n"
            "jobs:\n"
            "  build:\n"
            "    steps:\n"
            "      - name: Checkout current repo\n"
            f"        uses: actions/checkout@{pinned_sha}\n"
            "        with:\n"
            "          ref: v3.0.0\n"
        )
        workflow_file.write_text(original_content)

        modified = await pin_file(client, workflow_file, dry_run=False)
        assert not modified
        assert workflow_file.read_text() == original_content

    @pytest.mark.asyncio
    async def test_pin_file_with_ref_non_checkout_action_skipped(self, tmp_path: Path) -> None:
        """Skip with.ref on non-checkout actions (only checkout has meaningful with.ref)."""
        client = GitHubClient(token="test")

        workflow_file = tmp_path / "workflow.yml"
        pinned_sha = "b" * 40
        original_content = (
            "name: Test\n"
            "jobs:\n"
            "  build:\n"
            "    steps:\n"
            "      - name: Setup Python\n"
            f"        uses: actions/setup-python@{pinned_sha}\n"
            "        with:\n"
            "          repository: other/repo\n"
            "          ref: v3.0.0\n"
        )
        workflow_file.write_text(original_content)

        modified = await pin_file(client, workflow_file, dry_run=False)
        assert not modified
        assert workflow_file.read_text() == original_content

    @pytest.mark.asyncio
    async def test_pin_file_with_ref_version_constraint_major(self, tmp_path: Path) -> None:
        """Apply version-constraint flags to with.ref (--update-to-latest-major)."""
        client = GitHubClient(token="test", concurrency=1)

        old_sha = "f" * 40
        new_sha = "c" * 40
        checkout_sha = "e" * 40
        workflow_file = tmp_path / "workflow.yml"
        workflow_file.write_text(
            "name: Test\n"
            "jobs:\n"
            "  build:\n"
            "    steps:\n"
            f"      - uses: actions/checkout@{checkout_sha}\n"
            "        with:\n"
            f"          repository: other/repo\n"
            f"          ref: {old_sha}  # v3.0.0\n"
        )

        async def mock_list_tags(repo: str) -> list[tuple[str, str]]:
            if repo == "other/repo":
                return [("v3.0.0", old_sha), ("v9.0.0", new_sha)]
            return []

        async def mock_resolve_sha(_repo: str, _ref: str) -> str:
            return old_sha  # Only used for non-version-constraint paths

        with (
            patch.object(client, "list_tags", new=AsyncMock(side_effect=mock_list_tags)),
            patch.object(client, "resolve_sha", new=AsyncMock(side_effect=mock_resolve_sha)),
        ):
            modified = await pin_file(client, workflow_file, dry_run=False, update="major")
            assert modified

        content = workflow_file.read_text()
        assert f"ref: {new_sha} # v9" in content
        assert old_sha not in content


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

        settings = Settings(path=workflows_dir, github_token=None, dry_run=False)
        modified = await run(settings)

        assert modified == []

    @pytest.mark.asyncio
    async def test_run_missing_path_raises(self, tmp_path: Path) -> None:
        """Raise ValueError if path doesn't exist."""
        from pin_actions.config import Settings

        nonexistent = tmp_path / "nonexistent"
        settings = Settings(path=nonexistent, github_token=None)

        with pytest.raises(ValueError, match="Path does not exist"):
            await run(settings)

    @pytest.mark.asyncio
    async def test_run_raises_exception_group_on_partial_failure(self, tmp_path: Path) -> None:
        """Raise ExceptionGroup[PinActionsError] when one file fails but others succeed."""
        workflows_dir = tmp_path / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)

        good_file = workflows_dir / "ci.yml"
        good_file.write_text("name: CI\njobs:\n  test:\n    steps:\n      - uses: actions/checkout@v4\n")

        bad_file = workflows_dir / "broken.yml"
        bad_file.write_text("jobs:\n  build:\n    steps:\n    - uses: actions/checkout@v4\n  bad: [\n")

        from pin_actions.config import Settings

        settings = Settings(path=workflows_dir, github_token=None, dry_run=False, concurrency=1)

        async def mock_resolve_sha(_repo: str, ref: str) -> str:
            return "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" if ref == "v4" else ref

        with patch("pin_actions.core.GitHubClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.resolve_sha = AsyncMock(side_effect=mock_resolve_sha)
            mock_client_class.return_value = mock_client

            with pytest.raises(ExceptionGroup) as exc_info:
                await run(settings)

        assert len(exc_info.value.exceptions) == 1
        assert isinstance(exc_info.value.exceptions[0], YAMLParseError)


class TestVersioning:
    """Test semver tag selection logic."""

    def test_select_latest_tag_patch_downgrade_regression(self) -> None:
        """Patch constraint on major-only comment should not downgrade to minor==0.

        Regression: `# v4` with `--update patch` should pick the true latest
        v4.x tag (e.g. v4.9.0), not spuriously narrow to v4.0.x by treating
        minor as a fixed constraint. The issue: v4 parses to Version('4') with
        release=(4,), so precision=1; the old code checked `version.minor != 0`
        (failing to match v4.9.0), even though minor is meaningless for a
        major-only comment.
        """
        tags = [
            ("v4.0.1", "sha_v4_0_1"),
            ("v4.9.0", "sha_v4_9_0"),
            ("v5.1.0", "sha_v5_1_0"),
        ]
        result = select_latest_tag(tags, "v4", latest_patch=True)
        assert result is not None
        tag_name, sha = result
        # Should pick v4.9.0 (rendered as v4 to match precision)
        assert tag_name == "v4"
        assert sha == "sha_v4_9_0"

    def test_select_latest_tag_patch_with_full_precision(self) -> None:
        """Patch constraint with full major.minor.patch precision works correctly."""
        tags = [
            ("v4.2.1", "sha_v4_2_1"),
            ("v4.2.9", "sha_v4_2_9"),
            ("v4.3.0", "sha_v4_3_0"),
        ]
        result = select_latest_tag(tags, "v4.2.3", latest_patch=True)
        assert result is not None
        tag_name, sha = result
        # Should pick v4.2.9 (constrained to v4.2.x)
        assert tag_name == "v4.2.9"
        assert sha == "sha_v4_2_9"

    def test_select_latest_tag_minor_only(self) -> None:
        """Minor constraint picks highest v4.x but not v5.x."""
        tags = [
            ("v4.0.1", "sha_v4_0_1"),
            ("v4.9.5", "sha_v4_9_5"),
            ("v5.0.0", "sha_v5_0_0"),
        ]
        result = select_latest_tag(tags, "v4", latest_minor=True)
        assert result is not None
        tag_name, sha = result
        # Should pick v4.9.5 (rendered as v4)
        assert tag_name == "v4"
        assert sha == "sha_v4_9_5"

    def test_select_latest_tag_major_no_constraint(self) -> None:
        """Major constraint picks globally highest tag."""
        tags = [
            ("v4.0.1", "sha_v4_0_1"),
            ("v4.9.5", "sha_v4_9_5"),
            ("v9.0.0", "sha_v9_0_0"),
        ]
        result = select_latest_tag(tags, "v4", latest_major=True)
        assert result is not None
        tag_name, sha = result
        # Should pick v9.0.0 (rendered as v9)
        assert tag_name == "v9"
        assert sha == "sha_v9_0_0"

    def test_select_latest_tag_full_version_preserves_precision(self) -> None:
        """With full_version=True, preserve full resolved tag precision instead of truncating."""
        tags = [
            ("v4.0.1", "sha_v4_0_1"),
            ("v4.9.2", "sha_v4_9_2"),
            ("v5.0.0", "sha_v5_0_0"),
        ]
        # Without full_version: v4 -> picks v4.9.2 but renders as v4 (original precision)
        result = select_latest_tag(tags, "v4", latest_minor=True, full_version=False)
        assert result is not None
        tag_name, sha = result
        assert tag_name == "v4"
        assert sha == "sha_v4_9_2"

        # With full_version: v4 -> picks v4.9.2 and renders as v4.9.2 (full precision)
        result = select_latest_tag(tags, "v4", latest_minor=True, full_version=True)
        assert result is not None
        tag_name, sha = result
        assert tag_name == "v4.9.2"
        assert sha == "sha_v4_9_2"

    def test_parse_tag_version_calver_dot_separated(self) -> None:
        """Parse CalVer with dot separators (2023.10.15)."""
        v = parse_tag_version("2023.10.15")
        assert v is not None
        assert v.release == (2023, 10, 15)

    def test_parse_tag_version_calver_zero_padded(self) -> None:
        """Parse CalVer with zero-padded month/day (2023.01.05)."""
        v = parse_tag_version("2023.01.05")
        assert v is not None
        assert v.release == (2023, 1, 5)

    def test_parse_tag_version_calver_dash_separated(self) -> None:
        """Parse CalVer with dash separators (2024-05-01) by normalizing to dots."""
        v = parse_tag_version("2024-05-01")
        assert v is not None
        assert v.release == (2024, 5, 1)

    def test_parse_tag_version_calver_v_prefix_with_dash(self) -> None:
        """Parse CalVer with 'v' prefix and dashes (v2024-05-01)."""
        v = parse_tag_version("v2024-05-01")
        assert v is not None
        assert v.release == (2024, 5, 1)

    def test_parse_tag_version_unparseable_branch_name(self) -> None:
        """Return None for branch names like 'main', 'nightly', etc."""
        assert parse_tag_version("main") is None
        assert parse_tag_version("nightly") is None
        assert parse_tag_version("develop") is None

    def test_select_latest_tag_calver_dot_separated(self) -> None:
        """CalVer with dot separators: latest_major picks highest date."""
        tags = [
            ("2023.01.05", "sha_2023_01_05"),
            ("2023.09.30", "sha_2023_09_30"),
            ("2024.01.02", "sha_2024_01_02"),
        ]
        result = select_latest_tag(tags, "2023.01.05", latest_major=True)
        assert result is not None
        tag_name, sha = result
        # Rendered to match original precision (3 components)
        assert tag_name == "2024.1.2"
        assert sha == "sha_2024_01_02"

    def test_select_latest_tag_calver_dash_separated(self) -> None:
        """CalVer with dash separators: latest_minor picks within same year."""
        tags = [
            ("2024-01-05", "sha_2024_01_05"),
            ("2024-09-30", "sha_2024_09_30"),
            ("2025-01-02", "sha_2025_01_02"),
        ]
        result = select_latest_tag(tags, "2024-01-05", latest_minor=True)
        assert result is not None
        tag_name, sha = result
        # Rendered to match original precision (3 components), dash-normalized to dot
        assert tag_name == "2024.9.30"
        assert sha == "sha_2024_09_30"

    def test_select_latest_tag_calver_patch_constraint(self) -> None:
        """CalVer with patch constraint: latest_patch picks within same year.month."""
        tags = [
            ("2024.05.01", "sha_2024_05_01"),
            ("2024.05.15", "sha_2024_05_15"),
            ("2024.06.01", "sha_2024_06_01"),
        ]
        result = select_latest_tag(tags, "2024.05.05", latest_patch=True)
        assert result is not None
        tag_name, sha = result
        # Constrained to 2024.05.x, so picks 2024.05.15
        assert tag_name == "2024.5.15"
        assert sha == "sha_2024_05_15"

    @pytest.mark.asyncio
    async def test_pin_file_calver_already_pinned_updates_if_moved(self, tmp_path: Path) -> None:
        """Re-resolve CalVer-tagged action; update SHA if date tag moved."""
        client = GitHubClient(token="test", concurrency=1)

        old_sha = "a" * 40
        new_sha = "b" * 40
        workflow_file = tmp_path / "workflow.yml"
        workflow_file.write_text(
            f"name: Test\njobs:\n  build:\n    steps:\n      - uses: some-action@{old_sha}  # 2024.01.15\n"
        )

        async def mock_resolve_sha(_repo: str, _ref: str) -> str:
            return new_sha

        with patch.object(client, "resolve_sha", new=AsyncMock(side_effect=mock_resolve_sha)):
            modified = await pin_file(client, workflow_file, dry_run=False)
            assert modified

        content = workflow_file.read_text()
        # YAML normalization may alter spacing, so check key parts separately
        assert f"@{new_sha}" in content
        assert "# 2024.01.15" in content
        assert old_sha not in content

    @pytest.mark.asyncio
    async def test_pin_file_branch_name_fallback_no_update(self, tmp_path: Path) -> None:
        """Unparseable tag (e.g., 'nightly' branch): re-resolve hash only, leave comment untouched."""
        client = GitHubClient(token="test", concurrency=1)

        old_sha = "c" * 40
        new_sha = "d" * 40
        workflow_file = tmp_path / "workflow.yml"
        workflow_file.write_text(
            f"name: Test\njobs:\n  build:\n    steps:\n      - uses: some-action@{old_sha}  # nightly\n"
        )

        async def mock_resolve_sha(_repo: str, _ref: str) -> str:
            return new_sha

        with patch.object(client, "resolve_sha", new=AsyncMock(side_effect=mock_resolve_sha)):
            # No --update flag means always re-resolve, even 'nightly' branch
            modified = await pin_file(client, workflow_file, dry_run=False)
            assert modified

        content = workflow_file.read_text()
        # YAML normalization may alter spacing
        assert f"@{new_sha}" in content
        assert "# nightly" in content
        assert old_sha not in content
