#!/usr/bin/env -S uv run --with-editable . --script
"""Corpus scanner for the SCaLE 24x talk, Part 1 — "the surface is bigger than ``uses:``".

Measures what fraction of fully ``uses:``-pinned repositories still carry mutable
container images, cross-repository checkout refs, or pre-commit hook revisions.

Four resumable stages, each writing its artifact to disk so the published numbers
are reproducible from the published inputs:

1. ``frame``  — build the sampling frame from the GitHub repository search API.
2. ``fetch``  — blobless sparse-clone every repo in the frame, recording its HEAD SHA.
3. ``scan``   — classify each clone into one CSV row.
4. ``report`` — aggregate the CSV into the headline percentages.

Classification reuses the production collectors (``_collect_refs``,
``_collect_image_refs``, ``_collect_precommit_refs``) instead of re-implementing them,
so the measurement cannot drift from what ``pin-actions`` actually pins.

Research code for ``notes/scale-24x-talk.md``. Not part of the published package.

Example:
    ./notes/scan_corpus.py frame --min-stars 100 --pushed-since 2026-04-01 --out notes/corpus/frame.jsonl
    ./notes/scan_corpus.py fetch --frame notes/corpus/frame.jsonl --cache notes/corpus/repos
    ./notes/scan_corpus.py scan --cache notes/corpus/repos --out notes/corpus/corpus.csv
    ./notes/scan_corpus.py report --csv notes/corpus/corpus.csv
"""

import asyncio
import csv
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, fields
from datetime import date  # noqa: TC003 -- runtime-required: pydantic resolves field annotations
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self, TextIO

import yamlrocks
from pin_actions._util import is_full_sha
from pin_actions.client import GitHubClient
from pin_actions.core import (
    LEVELS_BY_VERBOSITY,
    _collect_image_refs,
    _collect_refs,
    _is_local_action,
    configure_logging,
)
from pin_actions.errors import PinActionsError
from pin_actions.precommit import _collect_precommit_refs
from pin_actions.registry import is_image_digest
from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, CliApp, CliSubCommand, SettingsConfigDict

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence


logger = logging.getLogger("scan_corpus")

_SEARCH_PAGE_SIZE = 100
_SEARCH_RESULT_CAP = 1000
_SEARCH_THROTTLE_SECONDS = 2.1  # GitHub search allows 30 requests/minute authenticated.

_SPARSE_PATHS = (".github/workflows", ".github/actions")
_GIT_ENV = {"GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "/bin/echo", "GIT_CONFIG_NOSYSTEM": "1"}
_YAML_SUFFIXES = frozenset({".yml", ".yaml"})
_PRECOMMIT_NAMES = (".pre-commit-config.yaml", ".pre-commit-config.yml")
_PRECOMMIT_CI_MARKERS = (b"pre-commit/action@", b"pre-commit run", b"prek run", b"prek-action@")
_ERROR_EXCERPT_CHARS = 200


# --------------------------------------------------------------------------------------
# Stage 1: sampling frame
# --------------------------------------------------------------------------------------


async def _search_page(client: GitHubClient, query: str, page: int) -> dict[str, Any]:
    """Fetch one page of ``GET /search/repositories`` and throttle to the search quota.

    Args:
        client: GitHub API client.
        query: Search qualifier string.
        page: 1-based page number.

    Returns:
        Parsed search response body.
    """
    # Reuses the package's retry/backoff handling rather than reimplementing it.
    data = await client._get_json(
        "/search/repositories",
        params={"q": query, "sort": "stars", "order": "desc", "per_page": _SEARCH_PAGE_SIZE, "page": page},
    )
    await asyncio.sleep(_SEARCH_THROTTLE_SECONDS)
    return data


def _write_frame_items(handle: TextIO, items: Iterable[dict[str, Any]], seen: set[str]) -> int:
    """Append unseen search results to the frame file as JSON lines.

    Args:
        handle: Open frame file.
        items: Search API ``items`` entries.
        seen: Repository full names already written; mutated in place.

    Returns:
        Number of newly written rows.
    """
    written = 0
    for item in items:
        name = item["full_name"]
        if name in seen:
            continue
        seen.add(name)
        handle.write(json.dumps({"repo": name, "stars": item["stargazers_count"]}) + "\n")
        written += 1
    return written


async def build_frame(client: GitHubClient, out: Path, *, min_stars: int, max_stars: int, pushed_since: str) -> int:
    """Enumerate the sampling frame by bisecting star bands around the 1000-result cap.

    GitHub returns at most 1000 results per query, so any band wider than that is split
    in half until it fits. Bands that cannot be split further are truncated and logged.

    Args:
        client: GitHub API client.
        out: Destination JSON Lines file; a sibling ``.meta.json`` records the query.
        min_stars: Inclusive lower star bound of the frame.
        max_stars: Inclusive upper star bound of the frame.
        pushed_since: ISO date; only repos pushed after this are included.

    Returns:
        Number of distinct repositories written.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    bands = [(min_stars, max_stars)]
    seen: set[str] = set()

    with out.open("w", encoding="utf-8") as handle:
        while bands:
            lo, hi = bands.pop()
            query = f"stars:{lo}..{hi} pushed:>{pushed_since} fork:false archived:false"
            first = await _search_page(client, query, 1)
            total = first["total_count"]

            if total > _SEARCH_RESULT_CAP and lo < hi:
                mid = (lo + hi) // 2
                bands.extend([(lo, mid), (mid + 1, hi)])
                continue
            if total > _SEARCH_RESULT_CAP:
                logger.warning("band stars:%d..%d holds %d repos; truncating to %d", lo, hi, total, _SEARCH_RESULT_CAP)

            _write_frame_items(handle, first["items"], seen)
            last_page = min(total, _SEARCH_RESULT_CAP) // _SEARCH_PAGE_SIZE
            for page in range(2, last_page + 1):
                items = (await _search_page(client, query, page))["items"]
                if not items:
                    break
                _write_frame_items(handle, items, seen)
            logger.info("band stars:%d..%d -> %d repos (frame now %d)", lo, hi, total, len(seen))

    meta = {
        "min_stars": min_stars,
        "max_stars": max_stars,
        "pushed_since": pushed_since,
        "qualifiers": "fork:false archived:false",
        "repos": len(seen),
    }
    out.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return len(seen)


# --------------------------------------------------------------------------------------
# Stage 2: corpus fetch
# --------------------------------------------------------------------------------------


async def _git(*args: str, timeout: float) -> tuple[int, str, str]:  # noqa: ASYNC109 -- see below
    """Run ``git`` with prompts disabled and return (returncode, stdout, stderr).

    The timeout is applied inside rather than by an outer ``asyncio.timeout``; the
    process must be killed explicitly or a hung clone leaks a child process.

    Args:
        *args: Arguments passed to ``git``.
        timeout: Seconds before the process is killed.

    Returns:
        Exit code, decoded stdout, decoded stderr.

    Raises:
        TimeoutError: If the process exceeds ``timeout``; the process is killed first.
    """
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        env={**os.environ, **_GIT_ENV},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return proc.returncode or 0, stdout.decode(errors="replace"), stderr.decode(errors="replace")


async def fetch_repo(repo: str, cache: Path, *, timeout: float) -> dict[str, Any]:  # noqa: ASYNC109 -- see _git
    """Blobless sparse-clone ``repo`` into ``cache`` and record its HEAD SHA.

    Cone-mode sparse checkout always includes top-level files, so
    ``.pre-commit-config.yaml`` and a root ``action.yml`` arrive without an explicit
    pattern. Re-running against an existing clone only re-reads HEAD.

    Args:
        repo: ``owner/name``.
        cache: Root directory holding clones.
        timeout: Per-git-invocation timeout in seconds.

    Returns:
        Manifest row with ``repo``, ``ok``, and either ``head_sha`` or ``error``.
    """
    dest = cache / repo
    try:
        if not (dest / ".git").is_dir():
            dest.parent.mkdir(parents=True, exist_ok=True)
            url = f"https://github.com/{repo}.git"
            code, _, err = await _git(
                "clone",
                "--filter=blob:none",
                "--sparse",
                "--depth=1",
                "--no-tags",
                "--quiet",
                url,
                str(dest),
                timeout=timeout,
            )
            if code != 0:
                return {"repo": repo, "ok": False, "error": err.strip()[:_ERROR_EXCERPT_CHARS]}
            code, _, err = await _git("-C", str(dest), "sparse-checkout", "set", *_SPARSE_PATHS, timeout=timeout)
            if code != 0:
                return {"repo": repo, "ok": False, "error": err.strip()[:_ERROR_EXCERPT_CHARS]}
        code, out, err = await _git("-C", str(dest), "rev-parse", "HEAD", timeout=timeout)
    except (TimeoutError, OSError) as exc:
        return {"repo": repo, "ok": False, "error": f"{type(exc).__name__}: {exc}"[:_ERROR_EXCERPT_CHARS]}

    if code != 0:
        return {"repo": repo, "ok": False, "error": err.strip()[:_ERROR_EXCERPT_CHARS]}
    return {"repo": repo, "ok": True, "head_sha": out.strip()}


async def fetch_corpus(repos: Sequence[str], cache: Path, *, concurrency: int, timeout: float) -> Path:  # noqa: ASYNC109 -- see _git
    """Clone every repository in ``repos``, writing a manifest as results land.

    Args:
        repos: Repository full names.
        cache: Root directory for clones; the manifest is written to ``cache/manifest.jsonl``.
        concurrency: Maximum simultaneous clones.
        timeout: Per-git-invocation timeout in seconds.

    Returns:
        Path to the manifest file.
    """
    cache.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240 -- sync IO on Path, no async equivalent needed
    manifest = cache / "manifest.jsonl"
    semaphore = asyncio.Semaphore(concurrency)

    async def _bounded(repo: str) -> dict[str, Any]:
        async with semaphore:
            return await fetch_repo(repo, cache, timeout=timeout)

    done = failed = 0
    with manifest.open("w", encoding="utf-8") as handle:
        for coro in asyncio.as_completed([_bounded(repo) for repo in repos]):
            row = await coro
            handle.write(json.dumps(row) + "\n")
            done += 1
            failed += not row["ok"]
            if done % 100 == 0:
                logger.info("fetched %d/%d (%d failed)", done, len(repos), failed)
    logger.info("fetched %d/%d (%d failed)", done, len(repos), failed)
    return manifest


# --------------------------------------------------------------------------------------
# Stage 3: classification
# --------------------------------------------------------------------------------------


@dataclass(slots=True)
class _Counts:
    """Mutable per-repository accumulator folded into a :class:`RepoStats`."""

    workflow_files: int = 0
    parse_errors: int = 0
    uses_total: int = 0
    uses_pinned: int = 0
    uses_dynamic: int = 0
    uses_local: int = 0
    image_total: int = 0
    image_mutable: int = 0
    image_dynamic: int = 0
    withref_total: int = 0
    withref_mutable: int = 0
    withref_dynamic: int = 0
    precommit_in_ci: bool = False
    precommit_total: int = 0
    precommit_mutable: int = 0


@dataclass(frozen=True, slots=True)
class RepoStats:
    """One scanned repository; serialized as one row of the corpus CSV.

    ``*_total`` counts exclude expression-valued (``${{ ... }}``) references, which are
    tallied under ``*_dynamic`` because they are neither pinned nor statically mutable.
    """

    repo: str
    head_sha: str
    workflow_files: int
    parse_errors: int
    uses_total: int
    uses_pinned: int
    uses_dynamic: int
    uses_local: int
    fully_pinned: bool
    image_total: int
    image_mutable: int
    image_dynamic: int
    withref_total: int
    withref_mutable: int
    withref_dynamic: int
    precommit_in_ci: bool
    precommit_total: int
    precommit_mutable: int


def _is_dynamic(value: str) -> bool:
    """Check whether ``value`` contains a GitHub Actions expression."""
    return "${{" in value


def _load_doc(path: Path) -> Any | None:  # noqa: ANN401
    """Round-trip parse ``path``, returning None when it is not a usable YAML document.

    Args:
        path: YAML file to parse.

    Returns:
        A ``YAMLRocksDocument``, or None on any parse failure.
    """
    try:
        doc = yamlrocks.loads(path.read_bytes(), option=yamlrocks.OPT_ROUND_TRIP)
    except Exception:  # noqa: BLE001 -- corpus files are arbitrary; any failure is just "unparsable"
        return None
    return doc if isinstance(doc, yamlrocks.YAMLRocksDocument) else None


def _count_local_uses(doc: Any) -> int:  # noqa: ANN401
    """Count ``uses: ./...`` local action references, which are out of scope, not unpinned."""
    return sum(
        1
        for item_path, value in doc.walk()
        if item_path and item_path[-1] == "uses" and isinstance(value, str) and value.startswith("./")
    )


def _scan_workflow(doc: Any, counts: _Counts) -> None:  # noqa: ANN401
    """Fold one workflow or action definition into ``counts``.

    Args:
        doc: Parsed round-trip document.
        counts: Accumulator mutated in place.
    """
    counts.uses_local += _count_local_uses(doc)

    for _path, repo, ref, is_uses in _collect_refs(doc):
        if is_uses:
            if _is_local_action(repo):
                continue
            if _is_dynamic(repo) or _is_dynamic(ref):
                counts.uses_dynamic += 1
            else:
                counts.uses_total += 1
                if is_full_sha(ref):
                    counts.uses_pinned += 1
        elif _is_dynamic(ref):
            counts.withref_dynamic += 1
        else:
            counts.withref_total += 1
            if not is_full_sha(ref):
                counts.withref_mutable += 1

    for _path, image, tag in _collect_image_refs(doc):
        if _is_dynamic(image) or _is_dynamic(tag):
            counts.image_dynamic += 1
        else:
            counts.image_total += 1
            if not is_image_digest(tag):
                counts.image_mutable += 1


def _scan_precommit(doc: Any, counts: _Counts) -> None:  # noqa: ANN401
    """Fold one ``.pre-commit-config.yaml`` into ``counts``.

    Args:
        doc: Parsed round-trip document.
        counts: Accumulator mutated in place.
    """
    for _path, _repo, rev, _is_uses in _collect_precommit_refs(doc, host="github.com"):
        counts.precommit_total += 1
        if not is_full_sha(rev):
            counts.precommit_mutable += 1


def _workflow_paths(root: Path) -> list[Path]:
    """Collect workflow files and action definitions under ``root``."""
    paths: list[Path] = []
    workflows = root / ".github" / "workflows"
    if workflows.is_dir():
        paths.extend(sorted(p for p in workflows.iterdir() if p.is_file() and p.suffix in _YAML_SUFFIXES))
    actions = root / ".github" / "actions"
    if actions.is_dir():
        paths.extend(sorted(p for p in actions.rglob("action.*") if p.is_file() and p.suffix in _YAML_SUFFIXES))
    paths.extend(sorted(p for p in root.glob("action.*") if p.is_file() and p.suffix in _YAML_SUFFIXES))
    return paths


def scan_repo(repo: str, head_sha: str, root: Path) -> RepoStats:
    """Classify one cloned repository into a single corpus row.

    Args:
        repo: ``owner/name``.
        head_sha: Default-branch commit the clone was taken at.
        root: Clone directory.

    Returns:
        Per-repository counts, with ``fully_pinned`` set when every in-scope,
        non-expression ``uses:`` reference is already a 40-character commit SHA.
    """
    counts = _Counts()
    workflow_blobs: list[bytes] = []

    for path in _workflow_paths(root):
        counts.workflow_files += 1
        doc = _load_doc(path)
        if doc is None:
            counts.parse_errors += 1
            continue
        workflow_blobs.append(path.read_bytes())
        _scan_workflow(doc, counts)

    counts.precommit_in_ci = any(marker in blob for blob in workflow_blobs for marker in _PRECOMMIT_CI_MARKERS)

    precommit = next((root / name for name in _PRECOMMIT_NAMES if (root / name).is_file()), None)
    if precommit is not None:
        doc = _load_doc(precommit)
        if doc is None:
            counts.parse_errors += 1
        else:
            _scan_precommit(doc, counts)

    return RepoStats(
        repo=repo,
        head_sha=head_sha,
        fully_pinned=counts.uses_total > 0 and counts.uses_pinned == counts.uses_total,
        workflow_files=counts.workflow_files,
        parse_errors=counts.parse_errors,
        uses_total=counts.uses_total,
        uses_pinned=counts.uses_pinned,
        uses_dynamic=counts.uses_dynamic,
        uses_local=counts.uses_local,
        image_total=counts.image_total,
        image_mutable=counts.image_mutable,
        image_dynamic=counts.image_dynamic,
        withref_total=counts.withref_total,
        withref_mutable=counts.withref_mutable,
        withref_dynamic=counts.withref_dynamic,
        precommit_in_ci=counts.precommit_in_ci,
        precommit_total=counts.precommit_total,
        precommit_mutable=counts.precommit_mutable,
    )


def scan_corpus(manifest: Path, cache: Path, out: Path, *, limit: int | None = None) -> int:
    """Scan every successfully cloned repository in ``manifest`` into a CSV.

    Args:
        manifest: JSON Lines manifest produced by :func:`fetch_corpus`.
        cache: Root directory holding the clones.
        out: Destination CSV path.
        limit: Optional cap on repositories scanned, for pilot runs.

    Returns:
        Number of rows written.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    field_names = [f.name for f in fields(RepoStats)]
    written = 0

    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=field_names)
        writer.writeheader()
        for row in _read_jsonl(manifest):
            if not row.get("ok"):
                continue
            stats = scan_repo(row["repo"], row["head_sha"], cache / row["repo"])
            writer.writerow({k: int(v) if isinstance(v, bool) else v for k, v in asdict(stats).items()})
            written += 1
            if limit is not None and written >= limit:
                break
    return written


# --------------------------------------------------------------------------------------
# Stage 4: aggregation
# --------------------------------------------------------------------------------------


def _pct(numerator: int, denominator: int) -> str:
    """Format ``numerator/denominator`` as a one-decimal percentage, or ``n/a`` when empty."""
    return f"{100 * numerator / denominator:.1f}%" if denominator else "n/a"


def report(csv_path: Path, *, exclude_dynamic: bool) -> str:
    """Aggregate the corpus CSV into the Part 1 headline numbers.

    Args:
        csv_path: CSV produced by :func:`scan_corpus`.
        exclude_dynamic: Drop repositories containing expression-valued ``uses:`` refs
            from the denominator instead of counting them as fully pinned.

    Returns:
        A Markdown report ready to paste into the talk notes.
    """
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8", newline="")))
    scanned = len(rows)
    with_workflows = [r for r in rows if int(r["workflow_files"]) > 0]

    pinned = [
        r for r in with_workflows if int(r["fully_pinned"]) and not (exclude_dynamic and int(r["uses_dynamic"]) > 0)
    ]
    denominator = len(pinned)

    def _has_precommit_gap(row: dict[str, str]) -> bool:
        return bool(int(row["precommit_in_ci"]) and int(row["precommit_mutable"]))

    image_gap = sum(1 for r in pinned if int(r["image_mutable"]))
    withref_gap = sum(1 for r in pinned if int(r["withref_mutable"]))
    precommit_frame = [r for r in pinned if int(r["precommit_in_ci"]) and int(r["precommit_total"])]
    precommit_gap = sum(1 for r in precommit_frame if int(r["precommit_mutable"]))
    any_gap = sum(1 for r in pinned if int(r["image_mutable"]) or int(r["withref_mutable"]) or _has_precommit_gap(r))

    table = (
        ("Any of the three (headline)", any_gap, denominator),
        ("Mutable container image (`X`)", image_gap, denominator),
        ("Unpinned cross-repo `with.ref` (`Y`)", withref_gap, denominator),
        ("Unpinned pre-commit rev in CI (`Z`)", precommit_gap, len(precommit_frame)),
    )
    dynamic_note = (
        "Excluded from the numerators as neither pinned nor statically mutable: "
        f"{sum(int(r['uses_dynamic']) for r in pinned)} expression-valued `uses:`, "
        f"{sum(int(r['withref_dynamic']) for r in pinned)} expression-valued `with.ref`, "
        f"{sum(int(r['image_dynamic']) for r in pinned)} expression-valued image refs. "
        f"Local `uses: ./...` actions ({sum(int(r['uses_local']) for r in pinned)}) are out of scope."
    )

    lines = [
        "## Part 1 corpus results",
        "",
        f"- Repositories scanned: **{scanned}**",
        f"- With at least one workflow or action file: **{len(with_workflows)}**",
        f"- Fully `uses:`-pinned (denominator `N`): **{denominator}**"
        + ("  _(expression-valued `uses:` excluded)_" if exclude_dynamic else ""),
        f"- Unparsable YAML files encountered: **{sum(int(r['parse_errors']) for r in rows)}**",
        "",
        "| Residual mutable surface | Count | Denominator | Share |",
        "| --- | --- | --- | --- |",
    ]
    lines.extend(f"| {label} | {hits} | {total} | **{_pct(hits, total)}** |" for label, hits, total in table)
    lines.extend(("", dynamic_note))
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def _read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """Yield each non-empty line of ``path`` as a parsed JSON object."""
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


class FrameStage(BaseSettings):
    """Build the sampling frame from the GitHub repository search API."""

    out: Path = Field(
        default=Path("notes/corpus/frame.jsonl"),
        description="Destination JSON Lines frame; the query is recorded in a sibling .meta.json",
    )
    min_stars: int = Field(default=100, ge=0, description="Inclusive lower star bound of the frame")
    max_stars: int = Field(default=500_000, ge=0, description="Inclusive upper star bound of the frame")
    pushed_since: date = Field(
        description="Only include repos pushed after this ISO date (e.g. 2026-04-01); state it in the methodology",
    )
    github_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("PIN_ACTIONS_TOKEN", "GITHUB_TOKEN"),
        description="GitHub API token; search is 10 req/min unauthenticated, 30 req/min authenticated",
    )

    @model_validator(mode="after")
    def _check_star_band(self) -> Self:
        """Reject an inverted star band, which would otherwise yield an empty frame silently.

        Returns:
            The validated model.

        Raises:
            ValueError: If ``min_stars`` exceeds ``max_stars``.
        """
        if self.min_stars > self.max_stars:
            msg = f"min_stars ({self.min_stars}) must not exceed max_stars ({self.max_stars})"
            raise ValueError(msg)
        return self

    def cli_cmd(self) -> None:
        """Run the frame stage."""
        if self.github_token is None:
            logger.warning("no GitHub token; unauthenticated search is capped at 10 requests/minute")

        async def _run() -> int:
            token = self.github_token.get_secret_value() if self.github_token else None
            async with GitHubClient(token=token, concurrency=1) as client:
                return await build_frame(
                    client,
                    self.out,
                    min_stars=self.min_stars,
                    max_stars=self.max_stars,
                    pushed_since=self.pushed_since.isoformat(),
                )

        print(f"frame: {asyncio.run(_run())} repositories -> {self.out}")


class FetchStage(BaseSettings):
    """Blobless sparse-clone every repository in the frame."""

    frame: Path = Field(default=Path("notes/corpus/frame.jsonl"), description="Frame file to read")
    cache: Path = Field(default=Path("notes/corpus/repos"), description="Root directory for clones")
    concurrency: int = Field(default=16, ge=1, description="Max simultaneous clones")
    timeout: float = Field(default=120.0, gt=0, description="Per-git-invocation timeout in seconds")
    limit: int | None = Field(default=None, ge=1, description="Clone only the first N repositories")

    def cli_cmd(self) -> None:
        """Run the fetch stage."""
        repos = [row["repo"] for row in _read_jsonl(self.frame)][: self.limit]
        manifest = asyncio.run(fetch_corpus(repos, self.cache, concurrency=self.concurrency, timeout=self.timeout))
        print(f"fetch: {len(repos)} repositories -> {manifest}")


class ScanStage(BaseSettings):
    """Classify the clones into the corpus CSV."""

    cache: Path = Field(default=Path("notes/corpus/repos"), description="Root directory holding the clones")
    manifest: Path | None = Field(default=None, description="Fetch manifest; defaults to <cache>/manifest.jsonl")
    out: Path = Field(default=Path("notes/corpus/corpus.csv"), description="Destination CSV")
    limit: int | None = Field(default=None, ge=1, description="Scan only the first N repositories")

    def cli_cmd(self) -> None:
        """Run the scan stage.

        Raises:
            SystemExit: If no fetch manifest exists yet.
        """
        manifest = self.manifest or self.cache / "manifest.jsonl"
        if not manifest.is_file():
            msg = f"error: no manifest at {manifest}; run the fetch stage first"
            raise SystemExit(msg)
        rows = scan_corpus(manifest, self.cache, self.out, limit=self.limit)
        print(f"scan: {rows} repositories -> {self.out}")


class ReportStage(BaseSettings):
    """Aggregate the corpus CSV into the headline numbers."""

    csv_path: Path = Field(
        default=Path("notes/corpus/corpus.csv"),
        validation_alias=AliasChoices("csv", "csv_path"),
        description="Corpus CSV to aggregate",
    )
    exclude_dynamic: bool = Field(
        default=False,
        description="Drop repositories containing expression-valued uses: from the denominator",
    )
    out: Path | None = Field(default=None, description="Write the Markdown report here instead of stdout")

    def cli_cmd(self) -> None:
        """Run the report stage."""
        text = report(self.csv_path, exclude_dynamic=self.exclude_dynamic)
        if self.out is None:
            print(text)
        else:
            self.out.write_text(text + "\n", encoding="utf-8")
            print(f"report -> {self.out}")


class ScanCorpusSettings(BaseSettings):
    """CLI & environment configuration for the SCaLE 24x corpus scanner."""

    model_config = SettingsConfigDict(
        env_prefix="SCAN_CORPUS_",
        case_sensitive=False,
        populate_by_name=True,
        cli_parse_args=True,
        cli_kebab_case=True,
        cli_implicit_flags=True,
        cli_prog_name="scan_corpus",
    )

    verbose: int = Field(
        default=1,
        ge=0,
        le=3,
        validation_alias=AliasChoices("verbose", "v"),
        description="Verbosity level 0-3, matching the pin-actions CLI",
    )

    frame: CliSubCommand[FrameStage]
    fetch: CliSubCommand[FetchStage]
    scan: CliSubCommand[ScanStage]
    report: CliSubCommand[ReportStage]

    def cli_cmd(self) -> None:
        """Configure logging, then dispatch to the selected stage."""
        configure_logging(self.verbose)
        logger.setLevel(LEVELS_BY_VERBOSITY[self.verbose]["pin_actions"])
        CliApp.run_subcommand(self)


def main() -> None:
    """CLI entry point, mirroring the ``pin-actions`` error-reporting convention.

    Configuration and runtime failures are reported as a single ``Error:`` line on
    stderr with exit status 1, rather than a pydantic traceback.
    """
    try:
        CliApp.run(ScanCorpusSettings)
    except (PinActionsError, ValueError) as exc:  # ValidationError subclasses ValueError
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
