"""Shared utilities."""

_SHA_LENGTH = 40
_URL_OWNER_REPO_PARTS = 2
_HEX = frozenset("0123456789abcdefABCDEF")


def is_full_sha(ref: str) -> bool:
    """Check if ref is a full 40-character hexadecimal commit SHA.

    Args:
        ref: Git ref string (branch, tag, or SHA).

    Returns:
        True if ``ref`` is exactly 40 hex characters (case-insensitive), False otherwise.

    Example:
        >>> is_full_sha("a" * 40)
        True
        >>> is_full_sha("v4")
        False
        >>> is_full_sha("a" * 39)
        False
    """
    return len(ref) == _SHA_LENGTH and _HEX.issuperset(ref)


def git_url_to_repo(url: str, host: str = "github.com") -> str | None:
    """Extract 'owner/repo' from a git clone URL for a given host.

    Supports https://{host}/owner/repo(.git), git@{host}:owner/repo(.git),
    and ssh://git@{host}/owner/repo(.git) URLs.

    Args:
        url: Git clone URL (as found in .pre-commit-config.yaml repos[].repo).
        host: Hostname to match (default 'github.com' for public GitHub; use
            'github.example.com' for GitHub Enterprise Server).

    Returns:
        'owner/repo', or None if url isn't a recognizable URL for the given host.

    Example:
        >>> git_url_to_repo("https://github.com/astral-sh/ruff-pre-commit")
        'astral-sh/ruff-pre-commit'
        >>> git_url_to_repo("git@github.com:astral-sh/ruff-pre-commit.git")
        'astral-sh/ruff-pre-commit'
        >>> git_url_to_repo("https://gitlab.com/owner/repo") is None
        True
    """
    url = url.strip().removesuffix("/").removesuffix(".git")
    for prefix in (f"https://{host}/", f"git@{host}:", f"ssh://git@{host}/"):
        if url.startswith(prefix):
            parts = url[len(prefix) :].split("/")
            if len(parts) == _URL_OWNER_REPO_PARTS and all(parts):
                return "/".join(parts)
    return None
