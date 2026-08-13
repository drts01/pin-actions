"""Shared utilities."""


def is_full_sha(ref: str) -> bool:
    """Check if ref is a full 40-character hexadecimal commit SHA.

    Args:
        ref: Git ref string (branch, tag, or SHA).

    Returns:
        True if ``ref`` is exactly 40 hex characters (case-insensitive), False otherwise.
    """
    return len(ref) == 40 and all(c in "0123456789abcdefABCDEF" for c in ref)
