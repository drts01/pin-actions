"""Shared utilities."""


def is_full_sha(ref: str) -> bool:
    """Check if ref is a 40-character hex commit SHA."""
    return len(ref) == 40 and all(c in "0123456789abcdefABCDEF" for c in ref)
