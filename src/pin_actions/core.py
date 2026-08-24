"""Core parsing and pinning logic."""

import asyncio
import difflib
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yamlrocks

from pin_actions._duration import parse_exclude_newer
from pin_actions._util import is_full_sha
from pin_actions.client import GitHubClient
from pin_actions.config import Settings
from pin_actions.errors import PinActionsError, UnsupportedRegistryError, YAMLParseError
from pin_actions.registry import ContainerRegistryClient, is_image_digest, parse_image_ref
from pin_actions.versioning import parse_tag_version, select_latest_tags

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class UpdateOptions:
    """Config for version-constrained tag updates."""

    update: Literal["major", "minor", "patch"]
    full_version: bool = False
    exclude_newer: str | None = None
    cutoff: datetime | None = None


# PEP 695 type aliases for clarity
type UsesWithRefTuple = tuple[tuple[Any, ...], str | None, bool]
type RefsToResolve = dict[tuple[str, str], list[UsesWithRefTuple]]
type ResolvedSHAs = dict[tuple[str, str], str]
type ImageRefsToResolve = dict[tuple[str, str], list[tuple[Any, ...]]]

_SERVICES_IMAGE_MIN_PATH_LEN = 3


def _is_local_action(repo: str) -> bool:
    """Check if action is local (./...)."""
    return repo.startswith("./")


def _is_docker_ref(repo: str) -> bool:
    """Check if a uses: value is a step-level docker:// image reference."""
    return repo.startswith("docker://")


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


def _collect_refs(doc: Any) -> list[tuple[tuple[Any, ...], str, str, bool]]:  # noqa: ANN401
    """Single-pass walk collecting both uses: entries and checkout with.ref entries.

    Returns:
        List of (item_path, repo, ref, is_uses) for every pinnable entry.
        ``is_uses`` distinguishes uses: (write as repo@sha) from with.ref (bare sha).
    """
    step_uses: dict[tuple[Any, ...], str] = {}
    step_repository: dict[tuple[Any, ...], str] = {}
    step_ref: dict[tuple[Any, ...], tuple[tuple[Any, ...], str]] = {}  # step_path -> (ref_path, ref_value)

    results: list[tuple[tuple[Any, ...], str, str, bool]] = []

    for item_path, value in doc.walk():
        if not item_path or not isinstance(value, str):
            continue

        if item_path[-1] == "uses":
            step_uses[item_path[:-1]] = value
            parsed = _parse_uses(value)
            if parsed:
                repo, ref = parsed
                results.append((item_path, repo, ref, True))
        elif item_path[-2:] == ("with", "repository"):
            step_repository[item_path[:-2]] = value
        elif item_path[-2:] == ("with", "ref"):
            step_ref[item_path[:-2]] = (item_path, value)

    for step_path, (ref_path, ref_value) in step_ref.items():
        if step_path not in step_repository or step_path not in step_uses:
            continue
        parsed_uses = _parse_uses(step_uses[step_path])
        if not parsed_uses or not parsed_uses[0].startswith("actions/checkout"):
            continue
        results.append((ref_path, step_repository[step_path], ref_value, False))

    return [r for r in results if not (r[3] and _is_docker_ref(r[1]))]


def _collect_image_refs(doc: Any) -> list[tuple[tuple[Any, ...], str, str]]:  # noqa: ANN401
    """Single-pass walk collecting container image references.

    Covers ``uses: docker://image:tag`` steps, ``jobs.<job>.container.image``,
    and ``jobs.<job>.services.<name>.image``.

    Returns:
        List of (item_path, image, tag_or_digest) for every pinnable image entry.
    """
    results: list[tuple[tuple[Any, ...], str, str]] = []
    for item_path, value in doc.walk():
        if not item_path or not isinstance(value, str):
            continue

        if (item_path[-1] == "uses" and _is_docker_ref(value)) or (
            item_path[-1] == "image"
            and (
                item_path[-2] == "container"
                or (len(item_path) >= _SERVICES_IMAGE_MIN_PATH_LEN and item_path[-3] == "services")
            )
        ):
            parsed = parse_image_ref(value)
            if parsed:
                _registry, name, tag = parsed
                results.append((item_path, name, tag))

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
        for item_path, current_sha, is_uses in refs_to_resolve[(repo, tag)]:
            if new_sha == current_sha:
                continue
            _set_path(doc, item_path, f"{repo}@{new_sha}" if is_uses else new_sha)
            doc.locate(item_path).comment = tag


async def apply_version_constrained_tag(
    doc: Any,  # noqa: ANN401
    client: GitHubClient,
    item_path: tuple[Any, ...],
    repo: str,
    tag: str,
    current_sha: str,
    *,
    is_uses: bool = True,
    options: UpdateOptions,
) -> None:
    """Rewrite a single already-pinned semver tag to the latest version within constraint.

    Warns to stderr (and leaves the entry untouched) if no tag on the remote
    satisfies the constraint relative to ``tag`` or if cool-off period excludes all candidates.

    Args:
        doc: YAML document to mutate.
        client: GitHub API client for fetching tags.
        item_path: Path tuple to the item to rewrite.
        repo: Repository in 'owner/repo' format.
        tag: Current tag recorded in the comment.
        current_sha: Current SHA already in the file.
        is_uses: If True, write as 'repo@sha' (uses:); if False, write as bare 'sha' (with.ref).
        options: Version update config (update mode, full_version, pre-parsed cutoff).
    """
    tags = await client.list_tags(repo)
    candidates = select_latest_tags(
        tags,
        tag,
        latest_patch=(options.update == "patch"),
        latest_minor=(options.update == "minor"),
        latest_major=(options.update == "major"),
        full_version=options.full_version,
    )
    if not candidates:
        logger.warning("no tag matching version constraint for %s@%s; leaving pinned as-is", repo, tag)
        return

    chosen: tuple[str, str] | None = None
    if options.cutoff:
        # Prefetch all candidate dates concurrently rather than awaiting serially
        # until one passes the cutoff.
        dates = await asyncio.gather(
            *(client.get_commit_date(repo, sha) for _, sha in candidates),
            return_exceptions=True,
        )
        for (candidate_tag, candidate_sha), date_result in zip(candidates, dates, strict=True):
            if isinstance(date_result, BaseException):
                logger.warning("failed to check commit date for %s@%s: %s; skipping", repo, candidate_sha, date_result)
                continue
            if datetime.fromisoformat(date_result) < options.cutoff:
                chosen = (candidate_tag, candidate_sha)
                break
        if chosen is None:
            logger.warning("all candidates for %s@%s are younger than cool-off cutoff; leaving pinned as-is", repo, tag)
            return
    else:
        chosen = candidates[0]

    new_tag, new_sha = chosen
    if new_sha == current_sha and new_tag == tag:
        return

    _set_path(doc, item_path, f"{repo}@{new_sha}" if is_uses else new_sha)
    doc.locate(item_path).comment = new_tag


async def _resolve_pinned_ref(
    doc: Any,  # noqa: ANN401
    client: GitHubClient,
    item_path: tuple[Any, ...],
    repo: str,
    ref: str,
    *,
    is_uses: bool,
    update_options: UpdateOptions | None,
    refs_to_resolve: RefsToResolve,
) -> None:
    """Handle re-resolve logic for an already-pinned uses:/with.ref entry.

    Extracts the common resolution logic for pinned entries that need re-resolution
    against their recorded tag/branch or version update constraints. Version-constrained
    updates are awaited directly (caller gathers these concurrently); plain re-resolves
    are accumulated into ``refs_to_resolve`` for batch resolution.

    Args:
        doc: yamlrocks round-trip document to mutate.
        client: GitHub API client.
        item_path: Path to the entry in the document.
        repo: Repository identifier (owner/repo).
        ref: Current ref value (SHA for pinned entries).
        is_uses: True if this is a uses: entry, False if with.ref.
        update_options: Version update config, or None for re-resolve.
        refs_to_resolve: Mutable dict to accumulate refs needing resolution.
    """
    node = doc.locate(item_path)
    assert node is not None, f"item_path {item_path} exists in doc"  # noqa: S101
    comment = node.comment
    tag = comment.strip() if comment else ""
    if not tag:
        return

    if update_options and parse_tag_version(tag) is not None:
        await apply_version_constrained_tag(
            doc,
            client,
            item_path,
            repo,
            tag,
            ref,
            is_uses=is_uses,
            options=update_options,
        )
        return

    refs_to_resolve.setdefault((repo, tag), []).append((item_path, ref, is_uses))


type CollectFn = Any  # (doc) -> list[tuple[tuple[Any, ...], str, str, bool]]


async def _resolve_and_rewrite_images(
    doc: Any,  # noqa: ANN401
    registry_client: ContainerRegistryClient,
    image_refs: list[tuple[tuple[Any, ...], str, str]],
) -> None:
    """Resolve container image tags to digests and rewrite matching doc entries in place.

    Unresolvable registries (non-Bearer auth, e.g. ECR/GCR) are logged as a
    warning and left untouched rather than failing the whole file.

    Args:
        doc: yamlrocks round-trip document to mutate.
        registry_client: Container registry client.
        image_refs: (item_path, image, tag_or_digest) tuples to resolve.
    """
    to_resolve = [(item_path, image, ref) for item_path, image, ref in image_refs if not is_image_digest(ref)]
    if not to_resolve:
        return

    async def _resolve(image: str, ref: str) -> str | UnsupportedRegistryError:
        try:
            return await registry_client.resolve_digest(image, ref)
        except UnsupportedRegistryError as exc:
            logger.warning("skipping unsupported registry for %s:%s: %s", image, ref, exc)
            return exc

    results = await asyncio.gather(*(_resolve(image, ref) for _, image, ref in to_resolve))

    for (item_path, image, ref), result in zip(to_resolve, results, strict=True):
        if isinstance(result, UnsupportedRegistryError):
            continue
        prefix = "docker://" if item_path[-1] == "uses" else ""
        _set_path(doc, item_path, f"{prefix}{image}@{result}")
        doc.locate(item_path).comment = ref


async def _pin_doc(
    client: GitHubClient,
    path: Path,
    collect_fn: CollectFn,
    *,
    dry_run: bool = False,
    diff: bool = False,
    options: UpdateOptions | None = None,
    registry_client: ContainerRegistryClient | None = None,
    collect_images_fn: CollectFn | None = None,
) -> bool:
    """Load, resolve, and rewrite pinnable refs in a YAML doc; shared by pin_file/pin_precommit_file.

    Args:
        client: GitHub API client.
        path: Path to the YAML file (workflow, action, or pre-commit config).
        collect_fn: Callable taking the parsed doc and returning
            (item_path, repo, ref, is_uses) tuples for every pinnable entry.
        dry_run: If True, don't write changes.
        diff: If True, print a unified diff of changes to stdout (implies dry_run).
        options: Version update config, or None to re-resolve exact tags/branches
            recorded in comments.
        registry_client: Container registry client for image pinning, or None to skip.
        collect_images_fn: Callable taking the parsed doc and returning
            (item_path, image, tag) tuples for every pinnable image entry.

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

    if not isinstance(doc, yamlrocks.YAMLRocksDocument):
        raise YAMLParseError(path, "expected a round-trip YAMLRocksDocument")

    # Gather all unique refs to resolve, keyed by (repo, tag) -> list of (item_path, current_sha, is_uses).
    # ``current_sha`` is the SHA already in the file (None if this entry isn't pinned yet), so
    # we can tell after resolution whether the tag has moved and a rewrite is actually needed.
    # ``is_uses`` distinguishes uses: (write as repo@sha) from with.ref (write as bare sha).
    refs_to_resolve: RefsToResolve = {}
    version_constrained: list[Any] = []

    for item_path, repo, ref, is_uses in collect_fn(doc):
        if is_uses and _is_local_action(repo):
            continue

        if not is_full_sha(ref):
            refs_to_resolve.setdefault((repo, ref), []).append((item_path, None, is_uses))
            continue

        version_constrained.append(
            _resolve_pinned_ref(
                doc,
                client,
                item_path,
                repo,
                ref,
                is_uses=is_uses,
                update_options=options,
                refs_to_resolve=refs_to_resolve,
            ),
        )

    # Version-constrained updates each make their own API calls (list_tags, get_commit_date);
    # run them concurrently rather than serially awaiting one pin at a time.
    await asyncio.gather(*version_constrained)
    await resolve_and_rewrite(doc, client, refs_to_resolve)

    if registry_client is not None and collect_images_fn is not None:
        await _resolve_and_rewrite_images(doc, registry_client, collect_images_fn(doc))

    new_content = doc.to_yaml()
    if new_content == content:
        return False

    if diff:
        sys.stdout.writelines(
            line + "\n"
            for line in difflib.unified_diff(
                content.decode().splitlines(),
                new_content.decode().splitlines(),
                fromfile=str(path),
                tofile=str(path),
                lineterm="",
            )
        )

    if not dry_run:
        path.write_bytes(new_content)  # noqa: ASYNC240 -- sync IO on Path, no async equivalent needed

    return True


async def pin_file(
    client: GitHubClient,
    path: Path,
    *,
    dry_run: bool = False,
    diff: bool = False,
    options: UpdateOptions | None = None,
    registry_client: ContainerRegistryClient | None = None,
) -> bool:
    """Pin mutable action refs in a workflow or action file to their commit SHAs.

    Args:
        client: GitHub API client.
        path: Path to .yaml/.yml file.
        dry_run: If True, don't write changes.
        diff: If True, print a unified diff of changes to stdout (implies dry_run).
        options: Version update config (``update`` strategy, ``full_version``,
            pre-parsed ``cutoff``), or None to re-resolve exact tags/branches
            recorded in comments.
        registry_client: Container registry client for pinning container images
            (``uses: docker://``, ``container.image``, ``services[*].image``),
            or None to skip image pinning entirely.

    Returns:
        True if file was modified, False otherwise.

    Raises:
        YAMLParseError: If the file cannot be parsed as YAML.
        GitHubAPIError: If a ref cannot be resolved (invalid ref, rate limit
            exhausted, or network failure). Subclass of ``PinActionsError``.
        OSError: If the file cannot be read or written.
    """
    return await _pin_doc(
        client,
        path,
        _collect_refs,
        dry_run=dry_run,
        diff=diff,
        options=options,
        registry_client=registry_client,
        collect_images_fn=_collect_image_refs if registry_client is not None else None,
    )


def _build_update_options(settings: Settings) -> UpdateOptions | None:
    """Build ``UpdateOptions`` from settings, pre-parsing the cool-off cutoff once.

    Raises:
        ValueError: If ``settings.exclude_newer`` is set but not a valid duration/timestamp.
    """
    if not settings.update:
        return None
    cutoff = parse_exclude_newer(settings.exclude_newer) if settings.exclude_newer else None
    return UpdateOptions(
        update=settings.update,
        full_version=settings.full_version,
        exclude_newer=settings.exclude_newer,
        cutoff=cutoff,
    )


async def run(settings: Settings, *, client: GitHubClient | None = None, cwd: Path | None = None) -> list[Path]:
    """Scan workflows/actions and pin all mutable refs to commit SHAs.

    Per-file errors (YAML parse failures, unresolvable refs, I/O errors) are
    collected rather than aborting the whole batch; callers that need
    per-file detail should inspect the raised ``ExceptionGroup`` or call
    :func:`pin_file` directly for single-file control.

    Args:
        settings: Configuration (paths, token, etc.).
        client: Optional pre-built GitHubClient. When provided, the client is
            reused without closing it (caller retains ownership). When None,
            a new client is created internally and closed after processing.
            Provide a shared client to reuse connection pooling, in-memory
            caching, and rate-limit bookkeeping across multiple run() calls
            (e.g. processing multiple repositories).
        cwd: Working directory for resolving relative paths and glob patterns;
            defaults to current directory. Glob patterns in paths are resolved
            relative to this directory.

    Returns:
        List of modified file paths.

    Raises:
        ValueError: If ``exclude_newer`` is set but not a valid duration/timestamp.
        ExceptionGroup[PinActionsError]: If one or more files failed to
            process; no partial results are returned in that case. Callers
            needing per-file results despite failures should call
            :func:`pin_file` directly for each file.
    """
    _cwd = cwd or Path()
    files: list[Path] = []
    for p in settings.paths:
        # Check if p is a glob pattern
        if any(c in str(p) for c in ("*", "?", "[")):
            files.extend(_cwd.glob(str(p)))
        elif not (_cwd / p).exists():
            continue
        elif (_cwd / p).is_file():
            files.append(_cwd / p)
        else:
            files.extend(f for pattern in ("**/*.yml", "**/*.yaml") for f in (_cwd / p).glob(pattern))

    if not files:
        return []

    options = _build_update_options(settings)
    token = settings.github_token.get_secret_value() if settings.github_token else None
    registry_client = (
        ContainerRegistryClient(github_token=token, concurrency=settings.concurrency) if settings.image_pin else None
    )

    try:
        if client is not None:
            return await _process_files(client, files, settings, options, registry_client)

        async with GitHubClient(
            token=token,
            base_url=settings.api_base_url,
            concurrency=settings.concurrency,
            max_retries=settings.max_retries,
        ) as gh_client:
            return await _process_files(gh_client, files, settings, options, registry_client)
    finally:
        if registry_client is not None:
            await registry_client.aclose()


async def _process_files(
    client: GitHubClient,
    files: list[Path],
    settings: Settings,
    options: UpdateOptions | None,
    registry_client: ContainerRegistryClient | None = None,
) -> list[Path]:
    """Process all workflow files concurrently using the provided client.

    Args:
        client: GitHub API client (caller retains ownership/closing responsibility).
        files: List of workflow/action files to process.
        settings: Configuration (for dry_run and diff).
        options: Pre-built version-update config, or None.
        registry_client: Container registry client for image pinning, or None to skip.

    Returns:
        List of modified file paths.

    Raises:
        ExceptionGroup[PinActionsError]: If one or more files failed.
    """
    tasks = [
        pin_file(
            client, f, dry_run=settings.dry_run, diff=settings.diff, options=options, registry_client=registry_client
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


"""Verbosity count → per-namespace logging level mapping.

Maps verbosity levels (0-3+) to logging level dicts for core libraries:
- 0 (default): pin_actions=WARNING, httpx2/httpcore=WARNING
- 1 (-v):      pin_actions=INFO, httpx2/httpcore=WARNING
- 2 (-vv):     pin_actions=DEBUG, httpx2/httpcore=INFO
- 3+ (-vvv):   pin_actions=DEBUG, httpx2/httpcore=DEBUG
"""
LEVELS_BY_VERBOSITY: list[dict[str, int]] = [
    {"pin_actions": logging.WARNING, "httpx2": logging.WARNING, "httpcore": logging.WARNING},
    {"pin_actions": logging.INFO, "httpx2": logging.WARNING, "httpcore": logging.WARNING},
    {"pin_actions": logging.DEBUG, "httpx2": logging.INFO, "httpcore": logging.INFO},
    {"pin_actions": logging.DEBUG, "httpx2": logging.DEBUG, "httpcore": logging.DEBUG},
]


def configure_logging(verbose: int) -> None:
    """Configure diagnostic logging levels per namespace based on verbosity count.

    User-facing CLI output (results/errors) goes through ``print()``, not
    logging, so it's independent of ``-v`` and works correctly under
    ``capsys``/output redirection without any handler bookkeeping.

    Args:
        verbose: Verbosity count (0-3+).
    """
    logging.basicConfig(format="%(levelname)s:%(name)s: %(message)s", force=True)
    levels = LEVELS_BY_VERBOSITY[min(verbose, 3)]
    for namespace, level in levels.items():
        logging.getLogger(namespace).setLevel(level)


def main() -> None:
    """CLI entry point.

    Parses ``sys.argv`` via pydantic-settings (supports ``--help``), runs the
    pin operation, and reports results. Exits with status 1 on any error.
    """
    if "--version" in sys.argv:
        from pin_actions import __version__  # noqa: PLC0415 -- deferred to avoid import cost when unused

        print(f"pin-actions {__version__}")
        return

    try:
        settings = Settings(
            _cli_parse_args=True,
            _cli_kebab_case=True,
            _cli_implicit_flags=True,
            _cli_prog_name="pin-actions",
        )
        configure_logging(settings.verbose)
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
