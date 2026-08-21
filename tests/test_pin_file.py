"""Tests for pin_file function (workflow file rewriting)."""

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from pin_actions._duration import parse_exclude_newer
from pin_actions.client import GitHubClient
from pin_actions.config import Settings
from pin_actions.core import UpdateOptions, _build_update_options, pin_file
from pin_actions.errors import InvalidRefError, YAMLParseError

if TYPE_CHECKING:
    from pathlib import Path


class TestPinFileRewriting:
    """Test pin_file rewriting mutable refs to pinned SHAs."""

    @pytest.mark.asyncio
    async def test_modifies_mutable_refs(self, tmp_path: Path) -> None:
        """Rewrite mutable refs to pinned SHAs."""
        # Arrange
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

        # Act
        with patch.object(client, "resolve_sha", new=AsyncMock(side_effect=mock_resolve_sha)):
            modified = await pin_file(client, workflow_file, dry_run=False)

        # Assert
        assert modified
        content = workflow_file.read_text()
        assert "actions/checkout@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" in content
        assert "actions/setup-python@bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" in content

    @pytest.mark.asyncio
    async def test_skips_bare_sha_without_comment(self, tmp_path: Path) -> None:
        """Don't rewrite a bare SHA with no '# tag' comment."""
        # Arrange
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

        # Act
        modified = await pin_file(client, workflow_file, dry_run=False)

        # Assert
        assert not modified
        assert workflow_file.read_text() == original_content

    @pytest.mark.asyncio
    async def test_updates_already_pinned_ref_if_moved(self, tmp_path: Path) -> None:
        """Re-resolve already-pinned 'sha  # tag' entry and update if it moved."""
        # Arrange
        client = GitHubClient(token="test", concurrency=1)
        old_sha = "a" * 40
        new_sha = "b" * 40
        workflow_file = tmp_path / "workflow.yml"
        workflow_file.write_text(
            f"name: Test\njobs:\n  build:\n    steps:\n      - uses: actions/checkout@{old_sha}  # v4\n",
        )

        async def mock_resolve_sha(_repo: str, _ref: str) -> str:
            return new_sha

        # Act
        with patch.object(client, "resolve_sha", new=AsyncMock(side_effect=mock_resolve_sha)):
            modified = await pin_file(client, workflow_file, dry_run=False)

        # Assert
        assert modified
        content = workflow_file.read_text()
        assert new_sha in content
        assert old_sha not in content
        assert "# v4" in content

    @pytest.mark.asyncio
    async def test_already_pinned_unchanged_when_sha_same(self, tmp_path: Path) -> None:
        """No modification if re-resolving returns the same SHA."""
        # Arrange
        client = GitHubClient(token="test", concurrency=1)
        sha = "a" * 40
        workflow_file = tmp_path / "workflow.yml"
        original_content = f"name: Test\njobs:\n  build:\n    steps:\n      - uses: actions/checkout@{sha}  # v4\n"
        workflow_file.write_text(original_content)

        async def mock_resolve_sha(_repo: str, _ref: str) -> str:
            return sha

        # Act
        with patch.object(client, "resolve_sha", new=AsyncMock(side_effect=mock_resolve_sha)):
            modified = await pin_file(client, workflow_file, dry_run=False)

        # Assert
        assert not modified
        assert workflow_file.read_text() == original_content


class TestPinFileSkipping:
    """Test pin_file skipping logic (local actions, docker://)."""

    @pytest.mark.asyncio
    async def test_skips_local_actions(self, tmp_path: Path) -> None:
        """Don't process local actions."""
        # Arrange
        client = GitHubClient(token="test")
        workflow_file = tmp_path / "workflow.yml"
        original_content = (
            "name: Test\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: ./path/to/local@v1\n"
        )
        workflow_file.write_text(original_content)

        # Act
        modified = await pin_file(client, workflow_file, dry_run=False)

        # Assert
        assert not modified


class TestPinFileDryRun:
    """Test pin_file dry_run mode."""

    @pytest.mark.asyncio
    async def test_dry_run_no_write(self, tmp_path: Path) -> None:
        """Don't write file in dry_run mode."""
        # Arrange
        client = GitHubClient(token="test", concurrency=1)
        workflow_file = tmp_path / "workflow.yml"
        original_content = "name: Test\njobs:\n  build:\n    steps:\n      - uses: actions/checkout@v4\n"
        workflow_file.write_text(original_content)

        async def mock_resolve_sha(_repo: str, _ref: str) -> str:
            return "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

        # Act
        with patch.object(client, "resolve_sha", new=AsyncMock(side_effect=mock_resolve_sha)):
            modified = await pin_file(client, workflow_file, dry_run=True)

        # Assert
        assert modified
        assert workflow_file.read_text() == original_content


class TestPinFileFormatting:
    """Test pin_file preserves formatting."""

    @pytest.mark.asyncio
    async def test_preserves_formatting(self, tmp_path: Path) -> None:
        """Preserve YAML formatting and comments on unchanged lines."""
        # Arrange
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

        # Act
        with patch.object(client, "resolve_sha", new=AsyncMock(side_effect=mock_resolve_sha)):
            modified = await pin_file(client, workflow_file, dry_run=False)

        # Assert
        assert modified
        content = workflow_file.read_text()
        assert "# workflow name" in content
        assert "# Configuration" in content
        assert "# build job" in content
        assert "actions/checkout@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" in content


class TestPinFileErrors:
    """Test pin_file error handling."""

    @pytest.mark.asyncio
    async def test_malformed_yaml_raises(self, tmp_path: Path) -> None:
        """Raise YAMLParseError on malformed YAML."""
        # Arrange
        client = GitHubClient(token="test")
        workflow_file = tmp_path / "workflow.yml"
        workflow_file.write_text("jobs:\n  build:\n    steps:\n    - uses: actions/checkout@v4\n  bad indent: [\n")

        # Act, Assert
        with pytest.raises(YAMLParseError, match="Failed to parse YAML"):
            await pin_file(client, workflow_file, dry_run=False)

    @pytest.mark.asyncio
    async def test_propagates_github_api_error(self, tmp_path: Path) -> None:
        """Propagate GitHubAPIError from client.resolve_sha."""
        # Arrange
        client = GitHubClient(token="test", concurrency=1)
        workflow_file = tmp_path / "workflow.yml"
        workflow_file.write_text("jobs:\n  build:\n    steps:\n      - uses: actions/checkout@nonexistent\n")

        async def mock_resolve_sha(repo: str, ref: str) -> str:
            raise InvalidRefError(repo, ref)

        # Act, Assert
        with (
            patch.object(client, "resolve_sha", new=AsyncMock(side_effect=mock_resolve_sha)),
            pytest.raises(InvalidRefError, match="Ref not found"),
        ):
            await pin_file(client, workflow_file, dry_run=False)


class TestPinFileWithRef:
    """Test pin_file with.ref handling (checkout-only)."""

    @pytest.mark.asyncio
    async def test_with_ref_new_pin(self, tmp_path: Path) -> None:
        """Pin fresh with.ref: v3.0.0 (no SHA yet)."""
        # Arrange
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
            "          ref: v3.0.0\n",
        )

        async def mock_resolve_sha(repo: str, ref: str) -> str:
            if repo == "other/repo" and ref == "v3.0.0":
                return "cccccccccccccccccccccccccccccccccccccccc"
            return "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

        # Act
        with patch.object(client, "resolve_sha", new=AsyncMock(side_effect=mock_resolve_sha)):
            modified = await pin_file(client, workflow_file, dry_run=False)

        # Assert
        assert modified
        content = workflow_file.read_text()
        assert "ref: cccccccccccccccccccccccccccccccccccccccc # v3.0.0" in content
        assert "repository: other/repo" in content

    @pytest.mark.asyncio
    async def test_with_ref_already_pinned_updates_if_moved(self, tmp_path: Path) -> None:
        """Re-resolve already-pinned with.ref with comment; update SHA if tag moved."""
        # Arrange
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
            f"          ref: {old_sha}  # v3.0.0\n",
        )

        async def mock_resolve_sha(_repo: str, _ref: str) -> str:
            return new_sha

        # Act
        with patch.object(client, "resolve_sha", new=AsyncMock(side_effect=mock_resolve_sha)):
            modified = await pin_file(client, workflow_file, dry_run=False)

        # Assert
        assert modified
        content = workflow_file.read_text()
        assert f"ref: {new_sha} # v3.0.0" in content
        assert old_sha not in content

    @pytest.mark.asyncio
    async def test_with_ref_missing_repository_skipped(self, tmp_path: Path) -> None:
        """Skip with.ref if no with.repository sibling."""
        # Arrange
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

        # Act
        modified = await pin_file(client, workflow_file, dry_run=False)

        # Assert
        assert not modified
        assert workflow_file.read_text() == original_content

    @pytest.mark.asyncio
    async def test_with_ref_non_checkout_action_skipped(self, tmp_path: Path) -> None:
        """Skip with.ref on non-checkout actions."""
        # Arrange
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

        # Act
        modified = await pin_file(client, workflow_file, dry_run=False)

        # Assert
        assert not modified
        assert workflow_file.read_text() == original_content


class TestPinFileVersionConstraints:
    """Test pin_file with version-constraint flags."""

    @pytest.mark.asyncio
    async def test_with_ref_version_constraint_major(self, tmp_path: Path) -> None:
        """Apply version-constraint flags to with.ref (--update-to-latest-major)."""
        # Arrange
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
            f"          ref: {old_sha}  # v3.0.0\n",
        )

        async def mock_list_tags(repo: str) -> list[tuple[str, str]]:
            if repo == "other/repo":
                return [("v3.0.0", old_sha), ("v9.0.0", new_sha)]
            return []

        async def mock_resolve_sha(_repo: str, _ref: str) -> str:
            return old_sha

        # Act
        with (
            patch.object(client, "list_tags", new=AsyncMock(side_effect=mock_list_tags)),
            patch.object(client, "resolve_sha", new=AsyncMock(side_effect=mock_resolve_sha)),
        ):
            modified = await pin_file(client, workflow_file, dry_run=False, options=UpdateOptions(update="major"))

        # Assert
        assert modified
        content = workflow_file.read_text()
        assert f"ref: {new_sha} # v9" in content
        assert old_sha not in content


class TestPinFileCalVer:
    """Test pin_file with CalVer tags."""

    @pytest.mark.asyncio
    async def test_calver_already_pinned_updates_if_moved(self, tmp_path: Path) -> None:
        """Re-resolve CalVer-tagged action; update SHA if date tag moved."""
        # Arrange
        client = GitHubClient(token="test", concurrency=1)
        old_sha = "a" * 40
        new_sha = "b" * 40
        workflow_file = tmp_path / "workflow.yml"
        workflow_file.write_text(
            f"name: Test\njobs:\n  build:\n    steps:\n      - uses: some-action@{old_sha}  # 2024.01.15\n",
        )

        async def mock_resolve_sha(_repo: str, _ref: str) -> str:
            return new_sha

        # Act
        with patch.object(client, "resolve_sha", new=AsyncMock(side_effect=mock_resolve_sha)):
            modified = await pin_file(client, workflow_file, dry_run=False)

        # Assert
        assert modified
        content = workflow_file.read_text()
        assert f"@{new_sha}" in content
        assert "# 2024.01.15" in content
        assert old_sha not in content

    @pytest.mark.asyncio
    async def test_branch_name_fallback_no_update(self, tmp_path: Path) -> None:
        """Unparseable tag (e.g., 'nightly' branch): re-resolve hash only, leave comment untouched."""
        # Arrange
        client = GitHubClient(token="test", concurrency=1)
        old_sha = "c" * 40
        new_sha = "d" * 40
        workflow_file = tmp_path / "workflow.yml"
        workflow_file.write_text(
            f"name: Test\njobs:\n  build:\n    steps:\n      - uses: some-action@{old_sha}  # nightly\n",
        )

        async def mock_resolve_sha(_repo: str, _ref: str) -> str:
            return new_sha

        # Act
        with patch.object(client, "resolve_sha", new=AsyncMock(side_effect=mock_resolve_sha)):
            modified = await pin_file(client, workflow_file, dry_run=False)

        # Assert
        assert modified
        content = workflow_file.read_text()
        assert f"@{new_sha}" in content
        assert "# nightly" in content
        assert old_sha not in content


class TestPinFileVersionConstraintsUses:
    """Test pin_file version-constrained updates on already-pinned uses entries."""

    @pytest.mark.asyncio
    async def test_uses_version_constraint_patch_on_already_pinned(self, tmp_path: Path) -> None:
        """Update already-pinned uses with --update-to-latest-patch."""
        # Arrange
        client = GitHubClient(token="test", concurrency=1)
        old_sha = "a" * 40
        new_sha = "b" * 40
        workflow_file = tmp_path / "workflow.yml"
        workflow_file.write_text(
            f"name: Test\njobs:\n  build:\n    steps:\n      - uses: actions/checkout@{old_sha}  # v4.2.1\n",
        )

        async def mock_list_tags(repo: str) -> list[tuple[str, str]]:
            if repo == "actions/checkout":
                return [("v4.2.1", old_sha), ("v4.2.9", new_sha), ("v4.3.0", "c" * 40)]
            return []

        async def mock_resolve_sha(repo: str, ref: str) -> str:
            if repo == "actions/checkout" and ref == "v4.2.1":
                return old_sha
            return ref

        # Act
        with (
            patch.object(client, "list_tags", new=AsyncMock(side_effect=mock_list_tags)),
            patch.object(client, "resolve_sha", new=AsyncMock(side_effect=mock_resolve_sha)),
        ):
            modified = await pin_file(client, workflow_file, dry_run=False, options=UpdateOptions(update="patch"))

        # Assert
        assert modified
        content = workflow_file.read_text()
        assert f"@{new_sha}" in content
        assert "# v4.2.9" in content
        assert old_sha not in content

    @pytest.mark.asyncio
    async def test_uses_version_constraint_minor_on_already_pinned(self, tmp_path: Path) -> None:
        """Update already-pinned uses with --update-to-latest-minor."""
        # Arrange
        client = GitHubClient(token="test", concurrency=1)
        old_sha = "d" * 40
        new_sha = "e" * 40
        workflow_file = tmp_path / "workflow.yml"
        workflow_file.write_text(
            f"name: Test\njobs:\n  build:\n    steps:\n      - uses: actions/setup-python@{old_sha}  # v4\n",
        )

        async def mock_list_tags(repo: str) -> list[tuple[str, str]]:
            if repo == "actions/setup-python":
                return [("v4.0.0", old_sha), ("v4.9.5", new_sha), ("v5.0.0", "f" * 40)]
            return []

        async def mock_resolve_sha(repo: str, ref: str) -> str:
            if repo == "actions/setup-python" and ref == "v4":
                return old_sha
            return ref

        # Act
        with (
            patch.object(client, "list_tags", new=AsyncMock(side_effect=mock_list_tags)),
            patch.object(client, "resolve_sha", new=AsyncMock(side_effect=mock_resolve_sha)),
        ):
            modified = await pin_file(client, workflow_file, dry_run=False, options=UpdateOptions(update="minor"))

        # Assert
        assert modified
        content = workflow_file.read_text()
        assert f"@{new_sha}" in content
        assert "# v4" in content
        assert old_sha not in content


class TestPinFileExcludeNewer:
    """Test pin_file with --exclude-newer cool-off period."""

    @pytest.mark.asyncio
    async def test_exclude_newer_skips_newest_falls_back(self, tmp_path: Path) -> None:
        """Cutoff excludes the newest candidate; falls back to next-oldest passing candidate."""
        # Arrange
        client = GitHubClient(token="test", concurrency=1)
        old_sha = "a" * 40
        mid_sha = "b" * 40
        new_sha = "c" * 40
        workflow_file = tmp_path / "workflow.yml"
        workflow_file.write_text(
            f"name: Test\njobs:\n  build:\n    steps:\n      - uses: actions/checkout@{old_sha}  # v4.0.0\n",
        )

        async def mock_list_tags(repo: str) -> list[tuple[str, str]]:
            if repo == "actions/checkout":
                return [("v4.0.0", old_sha), ("v4.5.0", mid_sha), ("v4.9.0", new_sha)]
            return []

        async def mock_get_commit_date(_repo: str, sha: str) -> str:
            # new_sha is "too new" (after cutoff); mid_sha and old_sha are old enough
            dates = {
                new_sha: "2024-06-01T00:00:00Z",
                mid_sha: "2024-01-01T00:00:00Z",
                old_sha: "2023-01-01T00:00:00Z",
            }
            return dates[sha]

        async def mock_resolve_sha(_repo: str, _ref: str) -> str:
            return old_sha

        # Act
        with (
            patch.object(client, "list_tags", new=AsyncMock(side_effect=mock_list_tags)),
            patch.object(client, "get_commit_date", new=AsyncMock(side_effect=mock_get_commit_date)),
            patch.object(client, "resolve_sha", new=AsyncMock(side_effect=mock_resolve_sha)),
        ):
            modified = await pin_file(
                client,
                workflow_file,
                dry_run=False,
                options=UpdateOptions(update="minor", cutoff=parse_exclude_newer("2024-03-01T00:00:00Z")),
            )

        # Assert
        assert modified
        content = workflow_file.read_text()
        assert f"@{mid_sha}" in content
        assert "# v4.5.0" in content
        assert new_sha not in content

    @pytest.mark.asyncio
    async def test_exclude_newer_all_candidates_too_new(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """All candidates newer than cutoff; file left untouched, warning logged."""
        # Arrange
        client = GitHubClient(token="test", concurrency=1)
        old_sha = "a" * 40
        new_sha = "b" * 40
        workflow_file = tmp_path / "workflow.yml"
        original_content = (
            f"name: Test\njobs:\n  build:\n    steps:\n      - uses: actions/checkout@{old_sha}  # v4.0.0\n"
        )
        workflow_file.write_text(original_content)

        async def mock_list_tags(repo: str) -> list[tuple[str, str]]:
            if repo == "actions/checkout":
                return [("v4.0.0", old_sha), ("v4.9.0", new_sha)]
            return []

        async def mock_get_commit_date(_repo: str, _sha: str) -> str:
            return "2024-06-01T00:00:00Z"  # everything is too new

        # Act
        with (
            patch.object(client, "list_tags", new=AsyncMock(side_effect=mock_list_tags)),
            patch.object(client, "get_commit_date", new=AsyncMock(side_effect=mock_get_commit_date)),
        ):
            modified = await pin_file(
                client,
                workflow_file,
                dry_run=False,
                options=UpdateOptions(update="minor", cutoff=parse_exclude_newer("2024-03-01T00:00:00Z")),
            )

        # Assert
        assert not modified
        assert workflow_file.read_text() == original_content
        assert "younger than cool-off cutoff" in caplog.text

    def test_exclude_newer_invalid_value_raises(self) -> None:
        """Invalid exclude_newer string raises ValueError from _build_update_options."""
        settings = Settings(update="minor", exclude_newer="not-a-valid-duration")
        with pytest.raises(ValueError, match="Invalid exclude-newer format"):
            _build_update_options(settings)
