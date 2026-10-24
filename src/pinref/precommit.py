"""Pin GitHub-hosted pre-commit hook refs to immutable commit SHAs."""

import asyncio
import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from pinref._util import git_url_to_repo
from pinref.client import GitHubClient
from pinref.config import Settings
from pinref.core import UpdateOptions, _pin_doc, build_update_options, configure_logging
from pinref.errors import PinActionsError


class PrecommitSettings(Settings):
    """CLI and environment configuration for ``pin-precommit``."""

    paths: list[Path] = Field(default_factory=lambda: [Path(".pre-commit-config.yaml")])


def _collect_precommit_refs(doc: Any, *, host: str) -> list[tuple[tuple[Any, ...], str, str, bool]]:  # noqa: ANN401
    """Collect GitHub-hosted ``repos[].rev`` entries.

    Args:
        doc: Parsed pre-commit YAML document.
        host: GitHub hostname used to match repository clone URLs.

    Returns:
        Tuples containing the YAML path, repository, ref, and ``is_uses=False``.
    """
    results: list[tuple[tuple[Any, ...], str, str, bool]] = []
    try:
        repos = enumerate(doc["repos"])
    except KeyError, TypeError, IndexError:
        return results

    for index, repo_entry in repos:
        try:
            url = repo_entry.get("repo", None)
            ref = repo_entry.get("rev", None)
        except AttributeError, TypeError:
            continue
        if not isinstance(url, str) or not isinstance(ref, str):
            continue
        repo = git_url_to_repo(url, host=host)
        if repo and ref:
            results.append((("repos", index, "rev"), repo, ref, False))
    return results


async def pin_precommit_file(
    client: GitHubClient,
    path: Path,
    *,
    host: str = "github.com",
    dry_run: bool = False,
    diff: bool = False,
    options: UpdateOptions | None = None,
    provenance_mode: Literal["off", "warn", "strict"] = "off",
) -> bool:
    """Pin GitHub-hosted pre-commit hook refs to commit SHAs.

    Args:
        client: GitHub API client.
        path: Path to a pre-commit configuration file.
        host: GitHub hostname used to match repository clone URLs.
        dry_run: Do not write changes when true.
        diff: Print a unified diff and imply dry-run behavior when true.
        options: Version update configuration, or ``None`` to re-resolve the
            exact tags or branches recorded in comments.
        provenance_mode: Provenance verification mode for resolved SHAs.

    Returns:
        Whether the file content would change.

    Raises:
        PinActionsError: If parsing, resolution, or provenance verification fails.
    """

    def collect(doc: Any) -> list[tuple[tuple[Any, ...], str, str, bool]]:  # noqa: ANN401
        """Collect refs for the configured GitHub host."""
        return _collect_precommit_refs(doc, host=host)

    return await _pin_doc(
        client,
        path,
        collect,
        dry_run=dry_run,
        diff=diff,
        options=options,
        provenance_mode=provenance_mode,
    )


async def _run(settings: PrecommitSettings, files: list[Path]) -> list[Path]:
    """Pin all selected pre-commit configuration files."""
    options = build_update_options(settings)
    token = settings.github_token.get_secret_value() if settings.github_token else None

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
                provenance_mode=settings.provenance,
            )
            if modified:
                modified_files.append(config_file)
        return modified_files


def main() -> None:
    """Run the ``pin-precommit`` CLI."""
    if "--version" in sys.argv:
        from pinref import __version__  # noqa: PLC0415 -- deferred to avoid import cost when unused

        print(f"pin-precommit {__version__}")
        return

    try:
        cli_options: dict[str, Any] = {
            "_cli_parse_args": True,
            "_cli_kebab_case": True,
            "_cli_implicit_flags": True,
            "_cli_prog_name": "pin-precommit",
        }
        settings = PrecommitSettings(**cli_options)
        configure_logging(settings.verbose)

        cwd = Path()
        files: list[Path] = []
        for path in settings.paths:
            if any(character in str(path) for character in ("*", "?", "[")):
                files.extend(cwd.glob(str(path)))
            elif (cwd / path).is_file():
                files.append(cwd / path)

        modified_files = asyncio.run(_run(settings, files))
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
