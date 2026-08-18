#!/usr/bin/env -S uv run --with-editable . --script
"""Pin GitHub-hosted pre-commit hook revs to immutable commit SHAs."""

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import yamlrocks
from pin_actions import GitHubClient, git_url_to_repo, resolve_and_rewrite
from pin_actions._util import is_full_sha
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
    token: SecretStr | None = Field(
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


async def pin_precommit_config(
    client: GitHubClient,
    path: Path,
    *,
    host: str = "github.com",
    dry_run: bool = False,
) -> bool:
    """Rewrite each GitHub-hosted repos[].rev to a SHA + '# <original rev>' comment."""
    content = path.read_bytes()  # noqa: ASYNC240 -- sync IO on Path, no async equivalent needed
    doc = yamlrocks.loads(content, option=yamlrocks.OPT_ROUND_TRIP)

    refs_to_resolve: RefsToResolve = {}
    for i, repo_entry in enumerate(doc["repos"]):
        url = repo_entry.get("repo")
        rev = repo_entry.get("rev")
        repo = url and git_url_to_repo(url, host=host)
        if not repo or not rev:
            continue

        rev_path = ("repos", i, "rev")
        if is_full_sha(rev):
            comment = doc.locate(rev_path).comment
            tag = comment.strip() if comment else ""
            if not tag:
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
    token = settings.token.get_secret_value() if settings.token else None
    async with GitHubClient(token=token) as client:
        modified = await pin_precommit_config(client, settings.path, host=settings.host, dry_run=settings.dry_run)
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
