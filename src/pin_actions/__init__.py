"""Pin GitHub Actions to immutable commit SHAs."""

from pin_actions.client import GitHubClient
from pin_actions.config import Settings
from pin_actions.core import pin_file, run
from pin_actions.errors import (
    GitHubAPIError,
    InvalidRefError,
    NetworkError,
    PinActionsError,
    RateLimitExhaustedError,
    YAMLParseError,
)

__version__ = "0.1.0"

__all__ = [
    "GitHubAPIError",
    "GitHubClient",
    "InvalidRefError",
    "NetworkError",
    "PinActionsError",
    "RateLimitExhaustedError",
    "Settings",
    "YAMLParseError",
    "pin_file",
    "run",
]
