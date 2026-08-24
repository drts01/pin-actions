"""Tests for parsing utilities (uses, SHA detection, local actions)."""

from typing import Any

from hypothesis import given
from hypothesis import strategies as st
from pin_actions._util import git_url_to_repo, is_full_sha
from pin_actions.core import _is_docker_ref, _is_local_action, _parse_uses


class TestIsFullSha:
    """Test SHA detection (pure predicate, great for Hypothesis)."""

    def test_valid_sha_lowercase(self) -> None:
        """Recognize 40-char lowercase hex SHA."""
        assert is_full_sha("abc1234def5678abc1234def5678abc1234def56")
        assert is_full_sha("0123456789abcdef0123456789abcdef01234567")

    def test_valid_sha_uppercase(self) -> None:
        """Recognize 40-char uppercase hex SHA."""
        assert is_full_sha("ABC1234DEF5678ABC1234DEF5678ABC1234DEF56")

    def test_valid_sha_mixed(self) -> None:
        """Recognize 40-char mixed-case hex SHA."""
        assert is_full_sha("aBc1234DeF5678aBc1234DeF5678aBc1234DeF56")

    def test_invalid_short(self) -> None:
        """Reject SHA shorter than 40 chars."""
        assert not is_full_sha("abc1234def5678abc1234def5678abc1234def5")

    def test_invalid_long(self) -> None:
        """Reject SHA longer than 40 chars."""
        assert not is_full_sha("abc1234def5678abc1234def5678abc1234def567")

    def test_invalid_hex_chars(self) -> None:
        """Reject non-hex characters."""
        assert not is_full_sha("g" * 40)
        assert not is_full_sha("z" * 40)
        assert not is_full_sha("abc1234def5678abc1234def5678abc1234def5x")

    @given(st.text(alphabet="0123456789abcdef", min_size=40, max_size=40))
    def test_property_valid_hex_40_chars_is_sha(self, hex_str: str) -> None:
        """Property: any 40-char hex string is recognized as SHA."""
        assert is_full_sha(hex_str)

    @given(st.text(min_size=0, max_size=100).filter(lambda x: len(x) != 40))
    def test_property_non_40_char_is_not_sha(self, s: str) -> None:
        """Property: only 40-char strings can be SHAs."""
        assert not is_full_sha(s)


class TestIsLocalAction:
    """Test local vs remote action detection."""

    def test_local_dot_slash(self) -> None:
        """Detect local actions with ./."""
        # Arrange, Act, Assert
        assert _is_local_action("./path/to/action")
        assert _is_local_action("./__local__")

    def test_not_local_remote_action(self) -> None:
        """Reject remote actions (owner/repo format)."""
        assert not _is_local_action("owner/repo")
        assert not _is_local_action("actions/checkout")

    def test_not_local_with_sha(self) -> None:
        """Reject remote actions even with SHA."""
        assert not _is_local_action("owner/repo@abc1234def5678abc1234def5678abc1234def56")


class TestIsDockerRef:
    """Test docker:// step ref detection (routed to image pinning, not local skip)."""

    def test_docker_ref(self) -> None:
        """Detect docker:// image refs."""
        assert _is_docker_ref("docker://ubuntu:latest")
        assert _is_docker_ref("docker://my-image:v1")

    def test_not_docker_ref(self) -> None:
        """Reject non-docker refs."""
        assert not _is_docker_ref("owner/repo")
        assert not _is_docker_ref("./local-action")


class TestParseUses:
    """Test uses string parsing (repo@ref → tuple or None)."""

    def test_valid_simple(self) -> None:
        """Parse valid uses string."""
        # Arrange
        uses_str = "actions/checkout@v4"
        # Act
        result = _parse_uses(uses_str)
        # Assert
        assert result == ("actions/checkout", "v4")

    def test_valid_with_subpath(self) -> None:
        """Parse uses string with subpath."""
        result = _parse_uses("owner/repo/path/to/action@main")
        assert result == ("owner/repo/path/to/action", "main")

    def test_valid_with_sha(self) -> None:
        """Parse uses string with SHA."""
        sha = "a" * 40
        result = _parse_uses(f"actions/checkout@{sha}")
        assert result == ("actions/checkout", sha)

    def test_invalid_no_at(self) -> None:
        """Return None if no @ present."""
        assert _parse_uses("invalid-uses-string") is None
        assert _parse_uses("owner/repo") is None

    def test_invalid_empty_repo(self) -> None:
        """Return None if repo is empty."""
        assert _parse_uses("@v4") is None
        assert _parse_uses("@") is None

    def test_invalid_empty_ref(self) -> None:
        """Return None if ref is empty."""
        assert _parse_uses("actions/checkout@") is None

    def test_property_parse_uses_round_trip(self) -> None:
        """Property: parsed (repo, ref) can round-trip to uses string."""

        @given(
            repo=st.just("owner/repo"),
            ref=st.text(
                alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-.",
                min_size=1,
                max_size=20,
            ),
        )
        def _test(repo: str, ref: str) -> None:
            uses_str = f"{repo}@{ref}"
            result = _parse_uses(uses_str)
            assert result == (repo, ref)

        _test()

    def test_property_invalid_uses_without_at(self) -> None:
        """Property: uses string without @ always returns None."""

        @given(st.text().filter(lambda x: "@" not in x and x))
        def _test(s: str) -> None:
            assert _parse_uses(s) is None

        _test()


class TestWalkUsesKeys:
    """Test recursive 'uses' key discovery in YAML dicts (local test helper)."""

    def _walk_uses_keys(self, obj: Any, path: str = "") -> list[tuple[Any, str, str]]:
        """Local helper: recursively find 'uses' keys in plain-dict YAML structure."""
        results: list[tuple[Any, str, str]] = []

        if isinstance(obj, dict):
            for key, value in obj.items():
                child_path = f"{path}.{key}" if path else key
                if key == "uses" and isinstance(value, str):
                    results.append((obj, key, child_path))
                results.extend(self._walk_uses_keys(value, child_path))
        elif isinstance(obj, list):
            for idx, value in enumerate(obj):
                child_path = f"{path}[{idx}]"
                results.extend(self._walk_uses_keys(value, child_path))

        return results

    def test_find_single_uses(self) -> None:
        """Find single uses key in nested dict."""
        # Arrange
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
        # Act
        results = self._walk_uses_keys(doc)
        # Assert
        assert len(results) == 1
        parent_obj, key, _path = results[0]
        assert parent_obj[key] == "actions/checkout@v4"
        assert key == "uses"

    def test_find_multiple_uses(self) -> None:
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
        results = self._walk_uses_keys(doc)
        assert len(results) == 2
        uses_values = [r[0][r[1]] for r in results]
        assert "actions/checkout@v4" in uses_values
        assert "actions/setup-python@v4" in uses_values

    def test_skip_non_string_uses(self) -> None:
        """Skip uses keys that aren't strings."""
        doc = {
            "jobs": {
                "test": {
                    "steps": [
                        {"uses": "actions/checkout@v4"},
                        {"uses": 123},  # Skip non-string
                        {"uses": None},  # Skip None
                    ],
                },
            },
        }
        results = self._walk_uses_keys(doc)
        assert len(results) == 1
        assert results[0][0][results[0][1]] == "actions/checkout@v4"

    def test_empty_structure(self) -> None:
        """Handle empty structure."""
        assert self._walk_uses_keys({}) == []
        assert self._walk_uses_keys([]) == []
        assert self._walk_uses_keys({"jobs": {}}) == []


class TestGitUrlToRepo:
    """Test git URL → owner/repo extraction (configurable host)."""

    @given(
        st.sampled_from(
            [
                ("https://github.com/pre-commit/pre-commit-hooks", "pre-commit/pre-commit-hooks"),
                ("https://github.com/pre-commit/pre-commit-hooks.git", "pre-commit/pre-commit-hooks"),
                ("git@github.com:pre-commit/pre-commit-hooks.git", "pre-commit/pre-commit-hooks"),
                ("ssh://git@github.com/pre-commit/pre-commit-hooks.git", "pre-commit/pre-commit-hooks"),
                ("https://gitlab.com/foo/bar", None),
                ("local", None),
                ("meta", None),
            ],
        ),
    )
    def test_github_url_extraction(self, url_and_expected: tuple[str, str | None]) -> None:
        """Extract owner/repo from GitHub URLs; return None for non-GitHub."""
        url, expected = url_and_expected
        assert git_url_to_repo(url) == expected

    def test_ghe_server_https_url(self) -> None:
        """Extract owner/repo from GitHub Enterprise Server HTTPS URL."""
        url = "https://github.example.com/myorg/myrepo"
        assert git_url_to_repo(url, host="github.example.com") == "myorg/myrepo"

    def test_ghe_server_ssh_url(self) -> None:
        """Extract owner/repo from GitHub Enterprise Server SSH URL."""
        url = "git@github.example.com:myorg/myrepo.git"
        assert git_url_to_repo(url, host="github.example.com") == "myorg/myrepo"

    def test_ghe_server_ssh_protocol_url(self) -> None:
        """Extract owner/repo from GitHub Enterprise Server SSH protocol URL."""
        url = "ssh://git@github.example.com/myorg/myrepo"
        assert git_url_to_repo(url, host="github.example.com") == "myorg/myrepo"

    def test_ghe_url_with_different_host_returns_none(self) -> None:
        """Return None if URL host doesn't match the specified host."""
        url = "https://github.com/owner/repo"
        assert git_url_to_repo(url, host="github.example.com") is None

    def test_git_url_strips_trailing_slash(self) -> None:
        """Strip trailing slash from URL."""
        url = "https://github.com/owner/repo/"
        assert git_url_to_repo(url) == "owner/repo"

    def test_git_url_double_suffix_removal(self) -> None:
        """Handle both trailing slash and .git suffix."""
        url = "https://github.com/owner/repo.git/"
        assert git_url_to_repo(url) == "owner/repo"
