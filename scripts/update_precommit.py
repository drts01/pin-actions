#!/usr/bin/env -S uv run --with-editable . --script
"""Pin GitHub-hosted pre-commit hook revs to immutable commit SHAs."""

import asyncio
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import yamlrocks
from pin_actions import GitHubClient, git_url_to_repo, resolve_and_rewrite
from pin_actions._util import is_full_sha

if TYPE_CHECKING:
    from pin_actions.core import RefsToResolve


async def pin_precommit_config(client: GitHubClient, path: Path, *, dry_run: bool = False) -> bool:
    """Rewrite each GitHub-hosted repos[].rev to a SHA + '# <original rev>' comment."""
    content = path.read_bytes()
    doc = yamlrocks.loads(content, option=yamlrocks.OPT_ROUND_TRIP)

    refs_to_resolve: RefsToResolve = {}
    for i, repo_entry in enumerate(doc["repos"]):
        url = repo_entry.get("repo")
        rev = repo_entry.get("rev")
        repo = url and git_url_to_repo(url)
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
        path.write_bytes(new_content)
    return True


async def main() -> None:
    """Execute main business logic."""
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".pre-commit-config.yaml")
    dry_run = "--dry-run" in sys.argv
    async with GitHubClient() as client:
        modified = await pin_precommit_config(client, path, dry_run=dry_run)
    status = "Would modify" if dry_run else "Modified"
    msg = f"{status}: {path}" if modified else "No changes."
    print(msg)


if __name__ == "__main__":
    asyncio.run(main())
