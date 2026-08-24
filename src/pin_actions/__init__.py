"""Pin GitHub Actions to immutable commit SHAs."""

from importlib.metadata import version

from pin_actions._util import git_url_to_repo
from pin_actions.client import GitHubClient
from pin_actions.config import Settings
from pin_actions.core import (
    LEVELS_BY_VERBOSITY,
    UpdateOptions,
    apply_version_constrained_tag,
    build_update_options,
    configure_logging,
    pin_file,
    resolve_and_rewrite,
    run,
)
from pin_actions.errors import (
    GitHubAPIError,
    InvalidRefError,
    NetworkError,
    PinActionsError,
    RateLimitExhaustedError,
    YAMLParseError,
)

__version__ = version("pin-actions")

__all__ = [
    "LEVELS_BY_VERBOSITY",
    "GitHubAPIError",
    "GitHubClient",
    "InvalidRefError",
    "NetworkError",
    "PinActionsError",
    "RateLimitExhaustedError",
    "Settings",
    "UpdateOptions",
    "YAMLParseError",
    "apply_version_constrained_tag",
    "build_update_options",
    "configure_logging",
    "git_url_to_repo",
    "pin_file",
    "resolve_and_rewrite",
    "run",
]
