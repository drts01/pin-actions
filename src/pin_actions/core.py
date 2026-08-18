"""Core parsing and pinning logic."""

import asyncio
import logging
import sys
from typing import TYPE_CHECKING, Any, Literal

import yamlrocks

from pin_actions._util import is_full_sha
from pin_actions.client import GitHubClient
from pin_actions.config import Settings
from pin_actions.errors import PinActionsError, YAMLParseError
from pin_actions.versioning import parse_tag_version, select_latest_tag

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from pathlib import Path

# PEP 695 type aliases for clarity
type UsesWithRefTuple = tuple[tuple[Any, ...], str | None, bool]
type RefsToResolve = dict[tuple[str, str], list[UsesWithRefTuple]]
type ResolvedSHAs = dict[tuple[str, str], str]


def _is_local_action(repo: str) -> bool:
    """Check if action is local (./...) or docker (docker://)."""
    return repo.startswith(("./", "docker://"))


def _is_already_pinned(ref: str) -> bool:
    """Check if ref is already a 40-character commit SHA."""
    return is_full_sha(ref)


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


def _find_with_ref_paths(doc: Any) -> list[tuple[tuple[Any, ...], str, str, bool]]:  # noqa: ANN401
    """Find all with.ref + with.repository pairs for actions/checkout.

    Scans for steps using actions/checkout, then checks if they have both
    with.repository (string) and with.ref (string) siblings. Only returns
    results for checkout actions with both fields present.

    Returns:
        List of (ref_path_tuple, repo, ref, is_uses=False) where ref_path_tuple[-1] == "ref".
    """
    # Collect all uses/with.repository/with.ref by step container
    step_uses: dict[tuple[Any, ...], str] = {}
    step_repository: dict[tuple[Any, ...], str] = {}
    step_ref: dict[tuple[Any, ...], tuple[tuple[Any, ...], str]] = {}  # step_path -> (ref_path, ref_value)

    for item_path, value in doc.walk():
        if not item_path:
            continue

        if item_path[-1] == "uses" and isinstance(value, str):
            step_uses[item_path[:-1]] = value
        elif item_path[-2:] == ("with", "repository") and isinstance(value, str):
            step_repository[item_path[:-2]] = value
        elif item_path[-2:] == ("with", "ref") and isinstance(value, str):
            step_ref[item_path[:-2]] = (item_path, value)

    results: list[tuple[tuple[Any, ...], str, str, bool]] = []

    # For each step with with.ref, check if it has both with.repository and uses=checkout
    for step_path, (ref_path, ref_value) in step_ref.items():
        if step_path not in step_repository or step_path not in step_uses:
            continue

        # Verify uses is actions/checkout
        uses_value = step_uses[step_path]
        parsed_uses = _parse_uses(uses_value)
        if not parsed_uses or not parsed_uses[0].startswith("actions/checkout"):
            continue

        repo = step_repository[step_path]
        results.append((ref_path, repo, ref_value, False))

    return results


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


async def resolve_and_rewrite(
    doc: Any,  # noqa: ANN401
    client: GitHubClient,
    refs_to_resolve: RefsToResolve,
) -> None:
    """Batch-resolve unique (repo, ref) pairs and rewrite matching doc entries in place.

    Schema-agnostic: caller supplies refs_to_resolve from whatever YAML shape
    it walked (GH Actions uses:, pre-commit repos[].rev, etc.).

    Args:
        doc: yamlrocks round-trip document to mutate.
        client: GitHub API client.
        refs_to_resolve: Map of (repo, tag_or_ref) -> list of (item_path,
            current_sha, is_uses) needing that resolution.
    """
    keys = list(refs_to_resolve)
    values = await asyncio.gather(*(client.resolve_sha(repo, tag) for repo, tag in keys))
    resolved: ResolvedSHAs = dict(zip(keys, values, strict=True))

    for (repo, tag), new_sha in resolved.items():
        for item_path, current_sha, is_uses in refs_to_resolve.get((repo, tag), []):
            if new_sha == current_sha:
                continue
            _set_path(doc, item_path, f"{repo}@{new_sha}" if is_uses else new_sha)
            doc.locate(item_path).comment = tag


async def pin_file(
    client: GitHubClient,
    path: Path,
    dry_run: bool = False,
    update: Literal["major", "minor", "patch"] | None = None,
    full_version: bool = False,
) -> bool:
    """Pin mutable action refs in a workflow or action file to their commit SHAs.

    Args:
        client: GitHub API client.
        path: Path to .yaml/.yml file.
        dry_run: If True, don't write changes.
        update: Update strategy for pinned semver tags: 'major' (absolute latest,
            crossing majors, e.g. v4.0.5 -> v9.1.2), 'minor' (same major, e.g.
            v4.0.5 -> v4.9.0), 'patch' (same major.minor, e.g. v4.2.3 -> v4.2.9),
            or None (re-resolve exact tag/branch recorded in the comment).
        full_version: If True, record the full resolved tag version in the comment
            instead of truncating to match the original precision.

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

    # Gather all unique refs to resolve, keyed by (repo, tag) -> list of (item_path, current_sha, is_uses).
    # ``current_sha`` is the SHA already in the file (None if this entry isn't pinned yet), so
    # we can tell after resolution whether the tag has moved and a rewrite is actually needed.
    # ``is_uses`` distinguishes uses: (write as repo@sha) from with.ref (write as bare sha).
    refs_to_resolve: RefsToResolve = {}

    # Process uses: entries
    for item_path, uses_str in _find_uses_paths(doc):
        parsed = _parse_uses(uses_str)
        if not parsed:
            continue

        repo, ref = parsed
        if _is_local_action(repo):
            continue

        if not _is_already_pinned(ref):
            refs_to_resolve.setdefault((repo, ref), []).append((item_path, None, True))
            continue

        # Already-pinned entry: re-resolve against the tag/branch recorded in the
        # trailing comment (mirrors mheap/pin-github-action's default behavior). A
        # bare SHA with no comment has nothing to re-resolve against, so it's skipped.
        comment = doc.locate(item_path).comment
        tag = comment.strip() if comment else ""
        if not tag:
            continue

        if update and parse_tag_version(tag) is not None:
            await _apply_version_constrained_tag(
                doc,
                client,
                item_path,
                repo,
                tag,
                ref,
                update=update,
                is_uses=True,
                full_version=full_version,
            )
            continue

        # Regardless of update mode, always re-resolve any non-semver comment (branch ref)
        refs_to_resolve.setdefault((repo, tag), []).append((item_path, ref, True))

    # Process with.ref entries (checkout-only, requires with.repository)
    for ref_path, repo, ref, _is_uses in _find_with_ref_paths(doc):
        if not _is_already_pinned(ref):
            refs_to_resolve.setdefault((repo, ref), []).append((ref_path, None, False))
            continue

        # Already-pinned with.ref: same re-resolve logic
        comment = doc.locate(ref_path).comment
        tag = comment.strip() if comment else ""
        if not tag:
            continue

        if update and parse_tag_version(tag) is not None:
            await _apply_version_constrained_tag(
                doc,
                client,
                ref_path,
                repo,
                tag,
                ref,
                update=update,
                is_uses=False,
                full_version=full_version,
            )
            continue

        refs_to_resolve.setdefault((repo, tag), []).append((ref_path, ref, False))

    await resolve_and_rewrite(doc, client, refs_to_resolve)

    # Write if changed
    new_content = doc.to_yaml()
    if new_content == content:
        return False

    if not dry_run:
        path.write_bytes(new_content)  # noqa: ASYNC240 -- sync IO on Path, no async equivalent needed

    return True


async def _apply_version_constrained_tag(
    doc: Any,  # noqa: ANN401
    client: GitHubClient,
    item_path: tuple[Any, ...],
    repo: str,
    tag: str,
    current_sha: str,
    *,
    update: Literal["major", "minor", "patch"],
    is_uses: bool = True,
    full_version: bool = False,
) -> None:
    """Rewrite a single already-pinned semver tag to the latest version within constraint.

    Warns to stderr (and leaves the entry untouched) if no tag on the remote
    satisfies the constraint relative to ``tag``.

    Args:
        doc: YAML document to mutate.
        client: GitHub API client for fetching tags.
        item_path: Path tuple to the item to rewrite.
        repo: Repository in 'owner/repo' format.
        tag: Current tag recorded in the comment.
        current_sha: Current SHA already in the file.
        update: Version constraint mode ('major', 'minor', 'patch').
        is_uses: If True, write as 'repo@sha' (uses:); if False, write as bare 'sha' (with.ref).
        full_version: If True, use the full precision of the winning tag instead of
            truncating to match the original tag's precision.
    """
    tags = await client.list_tags(repo)
    match = select_latest_tag(
        tags,
        tag,
        latest_patch=(update == "patch"),
        latest_minor=(update == "minor"),
        latest_major=(update == "major"),
        full_version=full_version,
    )
    if match is None:
        logger.warning("no tag matching version constraint for %s@%s; leaving pinned as-is", repo, tag)
        return

    new_tag, new_sha = match
    if new_sha == current_sha and new_tag == tag:
        return

    if is_uses:
        _set_path(doc, item_path, f"{repo}@{new_sha}")
    else:
        _set_path(doc, item_path, new_sha)
    doc.locate(item_path).comment = new_tag


async def run(settings: Settings, *, client: GitHubClient | None = None) -> list[Path]:
    """Scan workflows/actions and pin all mutable refs to commit SHAs.

    Per-file errors (YAML parse failures, unresolvable refs, I/O errors) are
    collected rather than aborting the whole batch; callers that need
    per-file detail should inspect the raised ``ExceptionGroup`` or call
    :func:`pin_file` directly for single-file control.

    Args:
        settings: Configuration (path, token, etc.).
        client: Optional pre-built GitHubClient. When provided, the client is
            reused without closing it (caller retains ownership). When None,
            a new client is created internally and closed after processing.
            Provide a shared client to reuse connection pooling, in-memory
            caching, and rate-limit bookkeeping across multiple run() calls
            (e.g. processing multiple repositories).

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
        msg = f"Path does not exist: {settings.path}"
        raise ValueError(msg)

    # Gather all workflow and action files
    files = []
    for pattern in ("**/*.yml", "**/*.yaml"):
        files.extend(settings.path.glob(pattern))

    if not files:
        return []

    if client is not None:
        return await _process_files(client, files, settings)

    token = settings.github_token.get_secret_value() if settings.github_token else None

    # Initialize disk cache if enabled (can be disabled via --no-cache)
    disk_cache = None
    if settings.cache:
        try:
            from diskcache_rs import Cache  # type: ignore[import-not-found]  # noqa: PLC0415
        except ImportError:
            logger.warning("diskcache-rs not installed; persistent caching disabled (disable warning with --no-cache)")
        else:
            settings.cache_dir.mkdir(parents=True, exist_ok=True)
            disk_cache = Cache(str(settings.cache_dir))

    async with GitHubClient(
        token=token,
        base_url=settings.api_base_url,
        concurrency=settings.concurrency,
        max_retries=settings.max_retries,
        disk_cache=disk_cache,
        cache_ttl=settings.cache_ttl,
    ) as gh_client:
        return await _process_files(gh_client, files, settings)


async def _process_files(client: GitHubClient, files: list[Path], settings: Settings) -> list[Path]:
    """Process all workflow files using the provided client.

    Args:
        client: GitHub API client (caller retains ownership/closing responsibility).
        files: List of workflow/action files to process.
        settings: Configuration (for dry_run, update mode, etc.).

    Returns:
        List of modified file paths.

    Raises:
        ExceptionGroup[PinActionsError]: If one or more files failed.
    """
    # Process all files concurrently (semaphore in client bounds API calls)
    tasks = [
        pin_file(
            client,
            f,
            dry_run=settings.dry_run,
            update=settings.update,
            full_version=settings.full_version,
        )
        for f in files
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    errors = [(f, r) for f, r in zip(files, results, strict=True) if isinstance(r, Exception)]
    if errors:
        msg = f"{len(errors)} file(s) failed to process"
        raise ExceptionGroup(
            msg,
            [PinActionsError(f"{f}: {exc}") if not isinstance(exc, PinActionsError) else exc for f, exc in errors],
        )

    return [f for f, r in zip(files, results, strict=True) if r is True]


# Verbosity → per-namespace logging levels
# 0 (default): pin_actions=WARNING, httpx2/httpcore=WARNING
# 1 (-v):      pin_actions=INFO, httpx2/httpcore=WARNING
# 2 (-vv):     pin_actions=DEBUG, httpx2/httpcore=INFO
# 3+ (-vvv):   pin_actions=DEBUG, httpx2/httpcore=DEBUG
_LEVELS_BY_VERBOSITY: list[dict[str, int]] = [
    {"pin_actions": logging.WARNING, "httpx2": logging.WARNING, "httpcore": logging.WARNING},
    {"pin_actions": logging.INFO, "httpx2": logging.WARNING, "httpcore": logging.WARNING},
    {"pin_actions": logging.DEBUG, "httpx2": logging.INFO, "httpcore": logging.INFO},
    {"pin_actions": logging.DEBUG, "httpx2": logging.DEBUG, "httpcore": logging.DEBUG},
]

# Dedicated always-on CLI loggers for user-facing output (independent of -v verbosity)
_cli_out = logging.getLogger("pin_actions.cli.out")
_cli_err = logging.getLogger("pin_actions.cli.err")
for _log in (_cli_out, _cli_err):
    _log.propagate = False
    _log.setLevel(logging.INFO)


def _configure_logging(verbose: int) -> None:
    """Configure logging levels per namespace based on verbosity count.

    Args:
        verbose: Verbosity count (0-3+).
    """
    logging.basicConfig(format="%(levelname)s:%(name)s: %(message)s", force=True)
    levels = _LEVELS_BY_VERBOSITY[min(verbose, 3)]
    for namespace, level in levels.items():
        logging.getLogger(namespace).setLevel(level)

    # Rebuild CLI loggers' handlers for test isolation (capsys-safe: fresh stream references).
    for log, stream in ((_cli_out, sys.stdout), (_cli_err, sys.stderr)):
        log.handlers.clear()
        log.addHandler(logging.StreamHandler(stream))


def main() -> None:
    """CLI entry point.

    Parses ``sys.argv`` via pydantic-settings (supports ``--help``), runs the
    pin operation, and reports results. Exits with status 1 on any error.
    """
    try:
        settings = Settings(
            _cli_parse_args=True,
            _cli_kebab_case=True,
            _cli_implicit_flags=True,
            _cli_prog_name="pin-actions",
        )
        _configure_logging(settings.verbose)
        modified = asyncio.run(run(settings))
    except PinActionsError as exc:
        _cli_err.error(f"Error: {exc}")
        sys.exit(1)
    except ExceptionGroup as eg:
        _cli_err.error(f"Error: {eg}")
        for exc in eg.exceptions:
            _cli_err.error(f"  - {exc}")
        sys.exit(1)
    except ValueError as exc:
        _cli_err.error(f"Error: {exc}")
        sys.exit(1)

    if modified:
        _cli_out.info(f"Pinned {len(modified)} file(s):")
        for path in modified:
            _cli_out.info(f"  {path}")
    else:
        _cli_out.info("No files modified.")
