"""Core parsing and pinning logic."""

import asyncio
import sys
from typing import TYPE_CHECKING, Any

import yamlrocks

from pin_actions.client import GitHubClient
from pin_actions.config import Settings

if TYPE_CHECKING:
    from pathlib import Path


def _is_local_action(repo: str) -> bool:
    """Check if action is local (./...) or docker (docker://)."""
    return repo.startswith("./") or repo.startswith("docker://")


def _is_already_pinned(ref: str) -> bool:
    """Check if ref is already a 40-character commit SHA."""
    return len(ref) == 40 and all(c in "0123456789abcdefABCDEF" for c in ref)


def _parse_uses(uses_str: str) -> tuple[str, str] | None:
    """Parse 'owner/repo[/path]@ref' into (repo, ref) tuple.

    Args:
        uses_str: Uses string (e.g., 'actions/checkout@v4').

    Returns:
        (repo, ref) tuple, or None if parsing fails.
    """
    if "@" not in uses_str:
        return None
    repo, ref = uses_str.rsplit("@", 1)
    return (repo, ref) if repo and ref else None


def _walk_uses_keys(obj: Any, path: str = "") -> list[tuple[Any, str, str]]:  # noqa: ANN401
    """Recursively find all 'uses' keys in a plain-dict YAML structure.

    Used by tests against plain dicts. yamlrocks documents are walked
    separately via ``doc.walk()`` in :func:`pin_file` since their list
    values are ``YAMLRocksDocumentView`` objects, not ``list``.

    Returns:
        List of (parent_obj, key_or_index, current_path) tuples where 'uses' exists.
    """
    results: list[tuple[Any, str, str]] = []

    if isinstance(obj, dict):
        for key, value in obj.items():
            child_path = f"{path}.{key}" if path else key
            if key == "uses" and isinstance(value, str):
                results.append((obj, key, child_path))
            results.extend(_walk_uses_keys(value, child_path))
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            child_path = f"{path}[{idx}]"
            results.extend(_walk_uses_keys(value, child_path))

    return results


def _find_uses_paths(doc: Any) -> list[tuple[tuple[Any, ...], str]]:  # noqa: ANN401
    """Find all 'uses' key paths in a yamlrocks round-trip document.

    Uses ``doc.walk()`` which yields flat (path_tuple, value) pairs,
    correctly traversing list items (returned as YAMLRocksDocumentView,
    not plain list/dict), unlike a manual isinstance-based walk.

    Returns:
        List of (path_tuple, uses_value) where path_tuple[-1] == "uses".
    """
    return [
        (item_path, value)
        for item_path, value in doc.walk()
        if item_path and item_path[-1] == "uses" and isinstance(value, str)
    ]


def _set_path(doc: Any, item_path: tuple[Any, ...], value: str) -> None:  # noqa: ANN401
    """Assign ``value`` at ``item_path`` within ``doc``, writing through to the AST.

    Mutation must be the terminal operation of a single indexing chain
    starting at ``doc`` (yamlrocks intermediate views are not stable
    references across separate ``__getitem__`` calls).
    """
    target = doc
    for key in item_path[:-1]:
        target = target[key]
    target[item_path[-1]] = value


async def pin_file(
    client: GitHubClient,
    path: Path,
    dry_run: bool = False,
) -> bool:
    """Pin mutable action refs in a workflow or action file to their commit SHAs.

    Args:
        client: GitHub API client.
        path: Path to .yaml/.yml file.
        dry_run: If True, don't write changes.

    Returns:
        True if file was modified, False otherwise.

    Raises:
        OSError: If file cannot be read or written.
    """
    content = path.read_bytes()  # noqa: ASYNC240 -- sync IO on Path, no async equivalent needed
    try:
        doc = yamlrocks.loads(content, option=yamlrocks.OPT_ROUND_TRIP)
    except Exception as exc:
        print(f"[WARN] {path}: Failed to parse YAML: {exc}", file=sys.stderr)
        return False

    # Gather all unique mutable refs to resolve, keyed by (repo, ref) -> list of item paths.
    uses_refs: dict[tuple[str, str], list[tuple[Any, ...]]] = {}
    for item_path, uses_str in _find_uses_paths(doc):
        parsed = _parse_uses(uses_str)
        if not parsed:
            continue

        repo, ref = parsed
        if _is_local_action(repo) or _is_already_pinned(ref):
            continue

        uses_refs.setdefault((repo, ref), []).append(item_path)

    # Batch resolve all unique refs
    resolved: dict[tuple[str, str], str] = {}
    for repo, ref in uses_refs:
        try:
            sha = await client.resolve_sha(repo, ref)
            resolved[(repo, ref)] = sha
        except ValueError as exc:
            print(f"[WARN] {path}: {exc}", file=sys.stderr)

    # Rewrite entries with resolved SHAs
    for (repo, ref), sha in resolved.items():
        if not sha:
            continue
        for item_path in uses_refs.get((repo, ref), []):
            _set_path(doc, item_path, f"{repo}@{sha}  # {ref}")

    # Write if changed
    new_content = doc.to_yaml()
    if new_content == content:
        return False

    if not dry_run:
        path.write_bytes(new_content)  # noqa: ASYNC240

    return True


async def run(settings: Settings) -> list[Path]:
    """Scan workflows/actions and pin all mutable refs to commit SHAs.

    Args:
        settings: Configuration (path, token, etc.).

    Returns:
        List of modified file paths.
    """
    if not settings.path.exists():
        raise ValueError(f"Path does not exist: {settings.path}")

    # Gather all workflow and action files
    files = []
    for pattern in ("**/*.yml", "**/*.yaml"):
        files.extend(settings.path.glob(pattern))

    if not files:
        return []

    token = settings.token.get_secret_value() if settings.token else None
    client = GitHubClient(
        token=token,
        base_url=settings.github_api,
        concurrency=settings.concurrency,
        max_retries=settings.max_retries,
    )

    # Process all files concurrently (semaphore in client bounds API calls)
    tasks = [pin_file(client, f, dry_run=settings.dry_run) for f in files]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    return [f for f, r in zip(files, results, strict=True) if r is True]


def main() -> None:
    """CLI entry point."""
    settings = Settings()
    modified = asyncio.run(run(settings))

    if modified:
        print(f"Pinned {len(modified)} file(s):")
        for path in modified:
            print(f"  {path}")
    else:
        print("No files modified.")
