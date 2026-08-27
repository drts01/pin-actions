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


class UnverifiedProvenanceError(GitHubAPIError):
    """Raised (in --provenance strict mode) when a SHA's provenance can't be confirmed.

    GitHub's fork-network object storage lets a repository resolve/serve a SHA
    that was only ever committed to an unrelated fork of that repository
    (see docs/explanation/threat-model.md, section 3.1). This error means the SHA
    could not be confirmed reachable from any real branch, tag, or PR on the
    named repository -- it may be a legitimate but orphaned commit, or an
    impostor commit from a malicious fork.
    """

    def __init__(self, repo: str, sha: str, reason: str) -> None:
        """Initialize with the repo/SHA that failed verification and why.

        Args:
            repo: Repository in 'owner/repo' format.
            sha: The commit SHA that could not be verified.
            reason: Human-readable explanation of what was checked.
        """
        self.repo = repo
        self.sha = sha
        self.reason = reason
        super().__init__(f"Could not verify provenance of {repo}@{sha}: {reason}")


class UnsupportedRegistryError(PinActionsError):
    """Raised when a container registry doesn't support anonymous Bearer auth (e.g. ECR, GCR)."""

    def __init__(self, registry: str, reason: str) -> None:
        """Initialize with the registry host and underlying reason.

        Args:
            registry: Registry hostname that could not be resolved.
            reason: Human-readable explanation.
        """
        self.registry = registry
        self.reason = reason
        super().__init__(reason)
