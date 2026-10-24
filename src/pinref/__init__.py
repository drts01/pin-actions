"""Pin GitHub Actions to immutable commit SHAs."""

from importlib.metadata import version

from pinref._util import git_url_to_repo
from pinref.client import GitHubClient
from pinref.config import Settings
from pinref.core import (
    LEVELS_BY_VERBOSITY,
    UpdateOptions,
    apply_version_constrained_tag,
    build_update_options,
    configure_logging,
    pin_file,
    resolve_and_rewrite,
    run,
)
from pinref.errors import (
    GitHubAPIError,
    InvalidRefError,
    NetworkError,
    PinActionsError,
    RateLimitExhaustedError,
    YAMLParseError,
)
from pinref.precommit import pin_precommit_file

__version__ = version("pinref")

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
    "pin_precommit_file",
    "resolve_and_rewrite",
    "run",
]
