#!/usr/bin/env -S uv run --with-editable . --script
"""Pin GitHub-hosted pre-commit hook revs to immutable commit SHAs."""

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import yamlrocks
from pin_actions import GitHubClient, UpdateOptions, apply_version_constrained_tag, git_url_to_repo, resolve_and_rewrite
from pin_actions._util import is_full_sha
from pin_actions.versioning import parse_tag_version
from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from pin_actions.core import RefsToResolve


class UpdatePrecommitSettings(BaseSettings):
    """CLI & environment configuration for update-precommit."""

    model_config = SettingsConfigDict(
        env_prefix="UPDATE_PRECOMMIT_",
        case_sensitive=False,
        populate_by_name=True,
    )

    path: Path = Field(
        default=Path(".pre-commit-config.yaml"),
        description="Path to .pre-commit-config.yaml file",
    )
    github_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("UPDATE_PRECOMMIT_TOKEN", "GITHUB_TOKEN"),
        description="GitHub API token (env: GITHUB_TOKEN or UPDATE_PRECOMMIT_TOKEN)",
    )
    host: str = Field(
        default="github.com",
        description="GitHub hostname for clone-URL parsing (e.g. 'github.example.com' for GHE Server)",
    )
    dry_run: bool = Field(
        default=False,
        description="Print changes without writing",
    )
    update: Literal["major", "minor", "patch"] | None = Field(
        default=None,
        description="Update strategy for pinned semver tags: 'major', 'minor', or 'patch'",
    )
    full_version: bool = Field(
        default=False,
        description="Record full tag version instead of truncated precision",
    )
    exclude_newer: str | None = Field(
        default=None,
        description=(
            "Exclude tags newer than this cutoff (cool-off period). "
            "Accepted: RFC 3339 timestamp, ISO 8601 duration (e.g., P7D), "
            "or friendly duration (e.g., '7 days'). Only applies with --update"
        ),
    )


async def pin_precommit_config(
    client: GitHubClient,
    path: Path,
    *,
    host: str = "github.com",
    dry_run: bool = False,
    update: Literal["major", "minor", "patch"] | None = None,
    full_version: bool = False,
    exclude_newer: str | None = None,
) -> bool:
    """Rewrite each GitHub-hosted repos[].rev to a SHA + '# <original rev>' comment."""
    content = path.read_bytes()  # noqa: ASYNC240 -- sync IO on Path, no async equivalent needed
    doc = yamlrocks.loads(content, option=yamlrocks.OPT_ROUND_TRIP)
    if not isinstance(doc, yamlrocks.YAMLRocksDocument):
        msg = "expected a round-trip YAMLRocksDocument"
        raise TypeError(msg)

    refs_to_resolve: RefsToResolve = {}
    for i, repo_entry in enumerate(doc["repos"]):
        url = repo_entry.get("repo")
        rev = repo_entry.get("rev")
        repo = url and git_url_to_repo(url, host=host)
        if not repo or not rev:
            continue

        rev_path = ("repos", i, "rev")
        if is_full_sha(rev):
            node = doc.locate(rev_path)
            assert node is not None, f"rev_path {rev_path} exists in doc"  # noqa: S101
            comment = node.comment
            tag = comment.strip() if comment else ""
            if not tag:
                continue
            if update and parse_tag_version(tag) is not None:
                opts = UpdateOptions(update=update, full_version=full_version, exclude_newer=exclude_newer)
                await apply_version_constrained_tag(doc, client, rev_path, repo, tag, rev, is_uses=False, options=opts)
                continue
            refs_to_resolve.setdefault((repo, tag), []).append((rev_path, rev, False))
        else:
            refs_to_resolve.setdefault((repo, rev), []).append((rev_path, None, False))

    if refs_to_resolve:
        await resolve_and_rewrite(doc, client, refs_to_resolve)

    new_content = doc.to_yaml()
    if new_content == content:
        return False
    if not dry_run:
        path.write_bytes(new_content)  # noqa: ASYNC240 -- sync IO on Path, no async equivalent needed
    return True


async def _amain(settings: UpdatePrecommitSettings) -> None:
    """Execute main business logic."""
    token = settings.github_token.get_secret_value() if settings.github_token else None
    async with GitHubClient(token=token) as client:
        modified = await pin_precommit_config(
            client,
            settings.path,
            host=settings.host,
            dry_run=settings.dry_run,
            update=settings.update,
            full_version=settings.full_version,
            exclude_newer=settings.exclude_newer,
        )
    status = "Would modify" if settings.dry_run else "Modified"
    msg = f"{status}: {settings.path}" if modified else "No changes."
    print(msg)


def main() -> None:
    """CLI entry point."""
    settings = UpdatePrecommitSettings(
        _cli_parse_args=True,
        _cli_kebab_case=True,
        _cli_implicit_flags=True,
        _cli_prog_name="update-precommit",
    )
    asyncio.run(_amain(settings))


if __name__ == "__main__":
    main()
