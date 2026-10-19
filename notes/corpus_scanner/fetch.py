"""Fetch repositories for the corpus with blobless sparse clones."""

import asyncio
import json
import logging
import os
import random
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from pathlib import Path

logger = logging.getLogger("scan_corpus")

_SPARSE_PATHS = (".github/workflows", ".github/actions")
_GIT_ENV = {"GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "/bin/echo", "GIT_CONFIG_NOSYSTEM": "1"}
_ERROR_EXCERPT_CHARS = 200


def select_sample(repos: Iterable[str], *, size: int | None, seed: int) -> list[str]:
    """Deterministically shuffle repository names and take a prefix.

    Shuffling once and slicing keeps samples nested: for a fixed seed, a larger ``size`` is a superset of every
    smaller one, so a pilot run's clones are reused by the full run rather than discarded. The shuffle is applied
    even when ``size`` is ``None`` so that an interrupted fetch leaves a random subsample rather than the
    star-descending prefix that the frame stage emits.

    Args:
        repos: Repository full names, in any order.
        size: Number of repositories to keep, or ``None`` to keep all of them.
        seed: Seed for the permutation; record it in the published methodology.

    Returns:
        The selected repository names in shuffled order.
    """
    ordered = sorted(set(repos))
    random.Random(seed).shuffle(ordered)  # noqa: S311 -- sampling, not security
    return ordered if size is None else ordered[:size]


async def _git(*args: str, timeout: float) -> tuple[int, str, str]:  # noqa: ASYNC109 -- see below
    """Run ``git`` with prompts disabled and explicitly kill it on timeout."""
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
    """Blobless sparse-clone one repository and record its HEAD commit SHA.

    Args:
        repo: Repository in ``owner/name`` form.
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


async def fetch_corpus(repos: Sequence[str], cache: Path, *, concurrency: int, timeout: float) -> Path:  # noqa: ASYNC109
    """Clone every repository and write a manifest as results arrive.

    Args:
        repos: Repository full names.
        cache: Root directory for clones.
        concurrency: Maximum simultaneous clones.
        timeout: Per-git-invocation timeout in seconds.

    Returns:
        Path to the JSON Lines manifest.
    """
    cache.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240 -- Path has no async equivalent
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
