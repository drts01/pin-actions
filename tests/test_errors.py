"""Tests for exception hierarchy (attributes, messages, inheritance)."""

from pin_actions.errors import (
    GitHubAPIError,
    InvalidRefError,
    NetworkError,
    PinActionsError,
    RateLimitExhaustedError,
    YAMLParseError,
)


class TestPinActionsErrorBase:
    """Test base PinActionsError."""

    def test_is_exception(self) -> None:
        """PinActionsError is an Exception."""
        # Arrange, Act
        error = PinActionsError("test message")

        # Assert
        assert isinstance(error, Exception)
        assert str(error) == "test message"


class TestYAMLParseError:
    """Test YAMLParseError."""

    def test_attributes(self) -> None:
        """YAMLParseError stores path and reason."""
        # Arrange, Act
        error = YAMLParseError("/path/to/file.yml", "invalid syntax")

        # Assert
        assert error.path == "/path/to/file.yml"
        assert error.reason == "invalid syntax"
        assert isinstance(error, PinActionsError)
        assert "Failed to parse YAML" in str(error)

    def test_message_format(self) -> None:
        """YAMLParseError formats message with path and reason."""
        # Arrange, Act
        error = YAMLParseError("/path/to/workflow.yml", "expected ':' but got EOF")

        # Assert
        assert "/path/to/workflow.yml" in str(error)
        assert "expected ':' but got EOF" in str(error)


class TestGitHubAPIError:
    """Test GitHubAPIError base class."""

    def test_is_pin_actions_error(self) -> None:
        """GitHubAPIError is a PinActionsError."""
        # Arrange, Act
        error = GitHubAPIError("API error")

        # Assert
        assert isinstance(error, PinActionsError)
        assert str(error) == "API error"


class TestInvalidRefError:
    """Test InvalidRefError."""

    def test_attributes(self) -> None:
        """InvalidRefError stores repo and ref."""
        # Arrange, Act
        error = InvalidRefError("owner/repo", "nonexistent-tag")

        # Assert
        assert error.repo == "owner/repo"
        assert error.ref == "nonexistent-tag"
        assert isinstance(error, GitHubAPIError)

    def test_message_format(self) -> None:
        """InvalidRefError formats message with repo and ref."""
        # Arrange, Act
        error = InvalidRefError("actions/checkout", "v999")

        # Assert
        assert "Ref not found" in str(error)
        assert "actions/checkout" in str(error)
        assert "v999" in str(error)

    def test_inheritance(self) -> None:
        """InvalidRefError inherits from GitHubAPIError."""
        # Arrange, Act
        error = InvalidRefError("owner/repo", "ref")

        # Assert
        assert isinstance(error, GitHubAPIError)
        assert isinstance(error, PinActionsError)


class TestRateLimitExhaustedError:
    """Test RateLimitExhaustedError."""

    def test_attributes(self) -> None:
        """RateLimitExhaustedError stores repo, ref, and attempts."""
        # Arrange, Act
        error = RateLimitExhaustedError("owner/repo", "v4", 5)

        # Assert
        assert error.repo == "owner/repo"
        assert error.ref == "v4"
        assert error.attempts == 5
        assert isinstance(error, GitHubAPIError)

    def test_message_format(self) -> None:
        """RateLimitExhaustedError formats message with details."""
        # Arrange, Act
        error = RateLimitExhaustedError("actions/setup-python", "v3", 3)

        # Assert
        assert "Failed to resolve" in str(error)
        assert "actions/setup-python" in str(error)
        assert "v3" in str(error)
        assert "3 retries" in str(error)

    def test_inheritance(self) -> None:
        """RateLimitExhaustedError inherits from GitHubAPIError."""
        # Arrange, Act
        error = RateLimitExhaustedError("owner/repo", "ref", 2)

        # Assert
        assert isinstance(error, GitHubAPIError)
        assert isinstance(error, PinActionsError)


class TestNetworkError:
    """Test NetworkError."""

    def test_is_github_api_error(self) -> None:
        """NetworkError is a GitHubAPIError."""
        # Arrange, Act
        error = NetworkError("Connection timeout")

        # Assert
        assert isinstance(error, GitHubAPIError)
        assert isinstance(error, PinActionsError)
        assert str(error) == "Connection timeout"

    def test_message(self) -> None:
        """NetworkError stores and formats message."""
        # Arrange, Act
        error = NetworkError("DNS lookup failed for api.github.com")

        # Assert
        assert "DNS lookup failed" in str(error)
