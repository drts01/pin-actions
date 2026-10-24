"""Tests for scripts/update_repos.py fork and PR upsert functionality."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from update_repos import (
    RepoResult,
    UpdateReposSettings,
    _extract_fork_owner,
    _try_fix_injection,
    _try_zizmor,
    _upsert_pr,
)


class TestExtractForkOwner:
    """Test _extract_fork_owner helper."""

    def test_https_url_with_git_suffix(self) -> None:
        """Extract owner from HTTPS URL with .git suffix."""
        url = "https://github.com/octocat/Hello-World.git"
        owner = _extract_fork_owner(url)
        assert owner == "octocat"

    def test_https_url_without_git_suffix(self) -> None:
        """Extract owner from HTTPS URL without .git suffix."""
        url = "https://github.com/myorg/my-repo"
        owner = _extract_fork_owner(url)
        assert owner == "myorg"

    def test_ssh_url_with_git_suffix(self) -> None:
        """Extract owner from SSH URL with .git suffix."""
        url = "git@github.com:octocat/Hello-World.git"
        owner = _extract_fork_owner(url)
        assert owner == "octocat"

    def test_ssh_url_without_git_suffix(self) -> None:
        """Extract owner from SSH URL without .git suffix."""
        url = "git@github.com:myorg/my-repo"
        owner = _extract_fork_owner(url)
        assert owner == "myorg"

    def test_ghe_https_url(self) -> None:
        """Extract owner from GHE HTTPS URL."""
        url = "https://github.example.com/enterprise/internal-repo.git"
        owner = _extract_fork_owner(url)
        assert owner == "enterprise"

    def test_ghe_ssh_url(self) -> None:
        """Extract owner from GHE SSH URL."""
        url = "git@github.example.com:enterprise/internal-repo.git"
        owner = _extract_fork_owner(url)
        assert owner == "enterprise"

    def test_invalid_url_raises_valueerror(self) -> None:
        """Raise ValueError on invalid URL format."""


class TestUpsertPr:
    """Test _upsert_pr function."""

    @patch("update_repos._run")
    def test_reuses_existing_pr(self, mock_run: MagicMock) -> None:
        """Reuse existing PR."""
        repo = "org/repo"
        head = "pinref/org-repo"
        base_branch = "main"
        settings = UpdateReposSettings()
        existing_url = "https://github.com/org/repo/pull/123"
        mock_run.return_value = MagicMock(stdout=existing_url + "\n")
        result = _upsert_pr(repo, head, base_branch, settings, {})
        assert result == existing_url

    @patch("update_repos._run")
    def test_creates_new_pr(self, mock_run: MagicMock) -> None:
        """Create new PR when none exists."""
        repo = "org/repo"
        head = "pinref/org-repo"
        base_branch = "main"
        settings = UpdateReposSettings()
        new_pr_url = "https://github.com/org/repo/pull/789"
        mock_run.side_effect = [
            MagicMock(stdout=""),
            MagicMock(stdout=new_pr_url + "\n"),
        ]
        result = _upsert_pr(repo, head, base_branch, settings, {})
        assert result == new_pr_url

    @patch("update_repos._run")
    def test_opens_new_pr_when_previous_pr_was_merged(self, mock_run: MagicMock) -> None:
        """A merged (non-open) PR for the branch must not be reused; a new PR is created."""
        repo = "org/repo"
        head = "pinref/org-repo"
        base_branch = "main"
        settings = UpdateReposSettings()
        new_pr_url = "https://github.com/org/repo/pull/999"
        # gh pr list --state open finds nothing for a merged PR's now-stale branch.
        mock_run.side_effect = [
            MagicMock(stdout=""),
            MagicMock(stdout=new_pr_url + "\n"),
        ]
        result = _upsert_pr(repo, head, base_branch, settings, {})
        assert result == new_pr_url
        list_call_args = mock_run.call_args_list[0].args
        assert "open" in list_call_args
        assert "all" not in list_call_args


class TestRepoResult:
    """Test RepoResult model."""

    def test_fork_owner_field(self) -> None:
        """RepoResult has fork_owner field."""
        result = RepoResult(repo="org/repo", fork_owner="myuser")
        assert result.fork_owner == "myuser"

        with pytest.raises(ValueError, match="Cannot extract owner"):
            _extract_fork_owner("invalid-url-format")


class TestTryFixInjection:
    """Test _try_fix_injection helper."""

    def test_merges_modified_files_and_tallies_review_count(self, tmp_path: Path) -> None:
        """Fixed files are appended to result.modified; unfixable findings tallied."""
        workflows = tmp_path / ".github" / "workflows"

        workflows.mkdir(parents=True)
        workflow = workflows / "ci.yml"
        workflow.write_text(
            "on: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n"
            '      - run: echo "${{ github.event.issue.title }}"\n'
        )
        settings = UpdateReposSettings()
        result = RepoResult(repo="org/repo")

        _try_fix_injection(tmp_path, settings, result)

        assert workflow in result.modified
        assert result.injection_review == 0


class TestTryZizmor:
    """Test _try_zizmor helper."""

    @patch("update_repos.shutil.which", return_value=None)
    def test_missing_binary_is_a_soft_failure(self, _mock_which: MagicMock, tmp_path: Path) -> None:  # noqa: PT019
        """Missing zizmor binary logs a warning but does not raise."""
        settings = UpdateReposSettings()

        result = RepoResult(repo="org/repo")

        _try_zizmor(tmp_path, settings, result)  # must not raise

        assert result.error is None
