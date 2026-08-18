"""Shared utilities."""

import re

_GITHUB_URL_RE = re.compile(
    r"^(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
    r"(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$",
)


def is_full_sha(ref: str) -> bool:
    """Check if ref is a full 40-character hexadecimal commit SHA.

    Args:
        ref: Git ref string (branch, tag, or SHA).

    Returns:
        True if ``ref`` is exactly 40 hex characters (case-insensitive), False otherwise.
    """
    return len(ref) == 40 and all(c in "0123456789abcdefABCDEF" for c in ref)


def git_url_to_repo(url: str) -> str | None:
    """Extract 'owner/repo' from a GitHub clone URL; None for non-GitHub hosts.

    Supports https://github.com/owner/repo(.git), git@github.com:owner/repo(.git),
    and ssh://git@github.com/owner/repo(.git) URLs.

    Args:
        url: Git clone URL (as found in .pre-commit-config.yaml repos[].repo).

    Returns:
        'owner/repo', or None if url isn't a recognizable GitHub URL.
    """
    match = _GITHUB_URL_RE.match(url.strip())
    return f"{match['owner']}/{match['repo']}" if match else None
