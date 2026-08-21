"""Exception hierarchy for pin-actions.

Library callers should catch ``PinActionsError`` (or a more specific
subclass) to handle failures programmatically. The CLI (`main()`) catches
this hierarchy at the top level and converts it to a stderr message + exit code.
"""


class PinActionsError(Exception):
    """Base exception for all pin-actions errors."""


class YAMLParseError(PinActionsError):
    """Raised when a workflow/action file cannot be parsed as YAML."""

    def __init__(self, path: object, reason: str) -> None:
        """Initialize with the offending file path and underlying reason.

        Args:
            path: Path to the file that failed to parse.
            reason: Underlying parser error message.
        """
        self.path = path
        self.reason = reason
        super().__init__(f"Failed to parse YAML in {path}: {reason}")


class GitHubAPIError(PinActionsError):
    """Raised for GitHub API failures (network, auth, rate limits, invalid refs)."""


class AuthError(GitHubAPIError):
    """Raised on 403 responses that are not rate-limit related (bad/missing token)."""

    def __init__(self, path: str) -> None:
        """Initialize with the request path that was rejected.

        Args:
            path: API path that returned 403 with rate limit remaining.
        """
        self.path = path
        super().__init__(f"Authentication/permission error requesting {path} (403, not rate-limited)")


class InvalidRefError(GitHubAPIError):
    """Raised when a ref does not exist on the remote repository (404)."""

    def __init__(self, repo: str, ref: str) -> None:
        """Initialize with the repo and ref that failed to resolve.

        Args:
            repo: Repository in 'owner/repo' format.
            ref: The ref that could not be found.
        """
        self.repo = repo
        self.ref = ref
        super().__init__(f"Ref not found: {repo}@{ref}")


class RateLimitExhaustedError(GitHubAPIError):
    """Raised when retries are exhausted while rate-limited (429/403)."""

    def __init__(self, repo: str, ref: str, attempts: int) -> None:
        """Initialize with the repo/ref and number of attempts made.

        Args:
            repo: Repository in 'owner/repo' format.
            ref: The ref being resolved.
            attempts: Number of retry attempts made before giving up.
        """
        self.repo = repo
        self.ref = ref
        self.attempts = attempts
        super().__init__(f"Failed to resolve {repo}@{ref} after {attempts} retries")


class NetworkError(GitHubAPIError):
    """Raised on unrecoverable network errors (DNS, connection, timeout)."""
