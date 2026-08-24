#!/usr/bin/env -S uv run --with-editable . --script
"""Pin GitHub-hosted pre-commit hook revs to immutable commit SHAs."""

import asyncio
import sys
from pathlib import Path
from typing import Any

from pin_actions._util import git_url_to_repo
from pin_actions.client import GitHubClient
from pin_actions.config import Settings
from pin_actions.core import _build_update_options, _pin_doc
from pin_actions.errors import PinActionsError
from pydantic import Field


class PrecommitSettings(Settings):
    """CLI & environment configuration for pin-precommit."""

    paths: list[Path] = Field(default_factory=lambda: [Path(".pre-commit-config.yaml")])


def _collect_precommit_refs(doc: Any, *, host: str) -> list[tuple[tuple[Any, ...], str, str, bool]]:  # noqa: ANN401
    """Collect repos[].rev entries with a resolvable repos[].repo sibling for ``host``.

    Returns:
        List of (rev_path, repo, rev, is_uses=False) for every hook hosted on ``host``.
    """
    results: list[tuple[tuple[Any, ...], str, str, bool]] = []
    try:
        repos = doc["repos"]
    except KeyError, TypeError:
        return results

    for i, repo_entry in enumerate(repos):
        url = repo_entry.get("repo", None)
        rev = repo_entry.get("rev", None)
        repo = url and git_url_to_repo(url, host=host)
        if repo and rev:
            results.append((("repos", i, "rev"), repo, rev, False))
    return results


async def pin_precommit_file(
    client: GitHubClient,
    path: Path,
    *,
    host: str = "github.com",
    dry_run: bool = False,
    diff: bool = False,
    options: Any = None,  # noqa: ANN401
) -> bool:
    """Pin GitHub-hosted repos[].rev entries in a pre-commit config to their commit SHAs.

    Args:
        client: GitHub API client.
        path: Path to .pre-commit-config.yaml.
        host: GitHub hostname used to match repos[].repo clone URLs.
        dry_run: If True, don't write changes.
        diff: If True, print a unified diff of changes to stdout (implies dry_run).
        options: Version update config, or None to re-resolve exact tags/branches
            recorded in comments.

    Returns:
        True if file was modified, False otherwise.
    """

    def _collect(doc: Any) -> list[tuple[tuple[Any, ...], str, str, bool]]:  # noqa: ANN401
        return _collect_precommit_refs(doc, host=host)

    return await _pin_doc(client, path, _collect, dry_run=dry_run, diff=diff, options=options)


def main() -> None:
    """CLI entry point for pin-precommit."""
    if "--version" in sys.argv:
        from pin_actions import __version__  # noqa: PLC0415 -- deferred to avoid import cost when unused

        print(f"pin-precommit {__version__}")
        return

    try:
        settings = PrecommitSettings(
            _cli_parse_args=True,
            _cli_kebab_case=True,
            _cli_implicit_flags=True,
            _cli_prog_name="pin-precommit",
        )

        # Resolve files from paths (glob patterns + literal files)
        _cwd = Path()
        files: list[Path] = []
        for p in settings.paths:
            # Check if p is a glob pattern
            if any(c in str(p) for c in ("*", "?", "[")):
                files.extend(_cwd.glob(str(p)))
            elif (_cwd / p).is_file():
                files.append(_cwd / p)
            # Directories: skip (pre-commit configs are files, not discovered recursively)

        options = _build_update_options(settings)
        token = settings.github_token.get_secret_value() if settings.github_token else None

        async def _run() -> list[Path]:
            async with GitHubClient(
                token=token,
                base_url=settings.api_base_url,
                concurrency=settings.concurrency,
                max_retries=settings.max_retries,
            ) as client:
                modified_files: list[Path] = []
                for config_file in files:
                    modified = await pin_precommit_file(
                        client,
                        config_file,
                        host=settings.host,
                        dry_run=settings.dry_run,
                        diff=settings.diff,
                        options=options,
                    )
                    if modified:
                        modified_files.append(config_file)
                return modified_files

        modified_files = asyncio.run(_run())
    except PinActionsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if modified_files:
        print(f"Pinned {len(modified_files)} file(s):")
        for path in modified_files:
            print(f"  {path}")
    else:
        print("No files modified.")


if __name__ == "__main__":
    main()
