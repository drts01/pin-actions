"""Core parsing and pinning logic."""

import asyncio
from typing import TYPE_CHECKING, Any

import yamlrocks

from pin_actions.client import GitHubClient
from pin_actions.config import Settings
from pin_actions.errors import PinActionsError, YAMLParseError

if TYPE_CHECKING:
    from pathlib import Path


def _is_local_action(repo: str) -> bool:
    """Check if action is local (./...) or docker (docker://)."""
    return repo.startswith("./") or repo.startswith("docker://")


def _is_already_pinned(ref: str) -> bool:
    """Check if ref is already a 40-character commit SHA."""
    return len(ref) == 40 and all(c in "0123456789abcdefABCDEF" for c in ref)


def _parse_uses(uses_str: str) -> tuple[str, str] | None:
    """Parse 'owner/repo[/path]@ref' into (repo, ref).

    ``uses_str`` is the bare scalar value as returned by ``doc.walk()``,
    which never includes a genuine trailing YAML comment (yamlrocks strips
    those from the walked value; see ``doc.locate(path).comment`` in
    :func:`pin_file` for the tag recorded on an already-pinned entry).

    Args:
        uses_str: Uses string (e.g., 'actions/checkout@v4' or
            'actions/checkout@<sha>').

    Returns:
        (repo, ref) tuple, or None if parsing fails.
    """
    if "@" not in uses_str:
        return None
    repo, ref = uses_str.rsplit("@", 1)
    if not repo or not ref:
        return None
    return repo, ref


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
        YAMLParseError: If the file cannot be parsed as YAML.
        GitHubAPIError: If a ref cannot be resolved (invalid ref, rate limit
            exhausted, or network failure). Subclass of ``PinActionsError``.
        OSError: If the file cannot be read or written.
    """
    content = path.read_bytes()  # noqa: ASYNC240 -- sync IO on Path, no async equivalent needed

    try:
        doc = yamlrocks.loads(content, option=yamlrocks.OPT_ROUND_TRIP)
    except Exception as exc:
        raise YAMLParseError(path, str(exc)) from exc

    # Gather all unique refs to resolve, keyed by (repo, tag) -> list of (item_path, current_sha).
    # ``current_sha`` is the SHA already in the file (None if this entry isn't pinned yet), so
    # we can tell after resolution whether the tag has moved and a rewrite is actually needed.
    uses_refs: dict[tuple[str, str], list[tuple[tuple[Any, ...], str | None]]] = {}
    for item_path, uses_str in _find_uses_paths(doc):
        parsed = _parse_uses(uses_str)
        if not parsed:
            continue

        repo, ref = parsed
        if _is_local_action(repo):
            continue

        if _is_already_pinned(ref):
            # Already-pinned entry: re-resolve against the tag/branch recorded in the
            # trailing comment (mirrors mheap/pin-github-action's default behavior). A
            # bare SHA with no comment has nothing to re-resolve against, so it's skipped.
            comment = doc.locate(item_path).comment
            tag = comment.strip() if comment else ""
            if not tag:
                continue
            uses_refs.setdefault((repo, tag), []).append((item_path, ref))
        else:
            uses_refs.setdefault((repo, ref), []).append((item_path, None))

    # Batch resolve all unique refs. Any GitHubAPIError propagates to the caller,
    # who decides whether to skip, retry, or abort (library-friendly: no swallowing).
    resolved: dict[tuple[str, str], str] = {}
    for repo, tag in uses_refs:
        resolved[(repo, tag)] = await client.resolve_sha(repo, tag)

    # Rewrite entries whose resolved SHA differs from what's already there (new pins
    # always differ; already-pinned entries only differ if the tag has moved).
    for (repo, tag), new_sha in resolved.items():
        for item_path, current_sha in uses_refs.get((repo, tag), []):
            if new_sha == current_sha:
                continue
            _set_path(doc, item_path, f"{repo}@{new_sha}")
            doc.locate(item_path).comment = tag

    # Write if changed
    new_content = doc.to_yaml()
    if new_content == content:
        return False

    if not dry_run:
        path.write_bytes(new_content)  # noqa: ASYNC240 -- sync IO on Path, no async equivalent needed

    return True


async def run(settings: Settings) -> list[Path]:
    """Scan workflows/actions and pin all mutable refs to commit SHAs.

    Per-file errors (YAML parse failures, unresolvable refs, I/O errors) are
    collected rather than aborting the whole batch; callers that need
    per-file detail should inspect the raised ``ExceptionGroup`` or call
    :func:`pin_file` directly for single-file control.

    Args:
        settings: Configuration (path, token, etc.).

    Returns:
        List of modified file paths.

    Raises:
        ValueError: If ``settings.path`` does not exist.
        ExceptionGroup[PinActionsError]: If one or more files failed to
            process; no partial results are returned in that case. Callers
            needing per-file results despite failures should call
            :func:`pin_file` directly for each file.
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

    errors = [(f, r) for f, r in zip(files, results, strict=True) if isinstance(r, Exception)]
    if errors:
        raise ExceptionGroup(
            f"{len(errors)} file(s) failed to process",
            [PinActionsError(f"{f}: {exc}") if not isinstance(exc, PinActionsError) else exc for f, exc in errors],
        )

    return [f for f, r in zip(files, results, strict=True) if r is True]


def main() -> None:
    """CLI entry point.

    Parses ``sys.argv`` via pydantic-settings (supports ``--help``), runs the
    pin operation, and reports results. Exits with status 1 on any error.
    """
    import sys

    try:
        settings = Settings(
            _cli_parse_args=True,
            _cli_kebab_case=True,
            _cli_implicit_flags=True,
            _cli_prog_name="pin-actions",
        )
        modified = asyncio.run(run(settings))
    except PinActionsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except ExceptionGroup as eg:
        print(f"Error: {eg}", file=sys.stderr)
        for exc in eg.exceptions:
            print(f"  - {exc}", file=sys.stderr)
        sys.exit(1)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if modified:
        print(f"Pinned {len(modified)} file(s):")
        for path in modified:
            print(f"  {path}")
    else:
        print("No files modified.")
