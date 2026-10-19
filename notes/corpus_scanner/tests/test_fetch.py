# ruff: noqa: I001, PLR2004, S101
"""Tests for mocked corpus repository fetching."""

import asyncio
import json
from typing import TYPE_CHECKING, Any

import pytest

from notes.corpus_scanner import fetch

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
async def test_fetch_repo_clones_configures_sparse_checkout_and_reads_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run the expected Git commands for a repository absent from the cache."""
    calls: list[tuple[str, ...]] = []

    async def git(*args: str, timeout: float) -> tuple[int, str, str]:  # noqa: ASYNC109 -- mocks _git
        """Record Git arguments and return a fixed HEAD commit SHA."""
        assert timeout == 30.0
        calls.append(args)
        if args[-2:] == ("rev-parse", "HEAD"):
            return 0, f"{'a' * 40}\n", ""
        return 0, "", ""

    monkeypatch.setattr(fetch, "_git", git)

    result = await fetch.fetch_repo("owner/repo", tmp_path, timeout=30.0)

    assert result == {"repo": "owner/repo", "ok": True, "head_sha": "a" * 40}
    assert calls[0][:2] == ("clone", "--filter=blob:none")
    assert calls[1][-3:] == ("set", ".github/workflows", ".github/actions")
    assert calls[2][-2:] == ("rev-parse", "HEAD")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        ((1, "", "clone denied"), "clone denied"),
        (TimeoutError("too slow"), "TimeoutError: too slow"),
    ],
)
async def test_fetch_repo_records_clone_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: tuple[int, str, str] | TimeoutError,
    expected: str,
) -> None:
    """Convert Git failures and timeouts into manifest rows."""

    async def git(*_args: str, timeout: float) -> tuple[int, str, str]:  # noqa: ASYNC109 -- mocks _git
        """Return or raise the configured Git failure."""
        assert timeout == 1.0
        if isinstance(failure, BaseException):
            raise failure
        return failure

    monkeypatch.setattr(fetch, "_git", git)

    result = await fetch.fetch_repo("owner/repo", tmp_path, timeout=1.0)

    assert result == {"repo": "owner/repo", "ok": False, "error": expected}


@pytest.mark.asyncio
async def test_fetch_corpus_bounds_concurrency_and_writes_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bound concurrent clones and persist every result as JSON Lines."""
    active = 0
    maximum_active = 0

    async def fetch_repo(
        repo: str,
        _cache: Path,
        *,
        timeout: float,  # noqa: ASYNC109 -- mocks fetch_repo
    ) -> dict[str, Any]:
        """Track active fetches and return a successful manifest row."""
        nonlocal active, maximum_active
        assert timeout == 5.0
        active += 1
        maximum_active = max(maximum_active, active)
        await asyncio.sleep(0)
        active -= 1
        return {"repo": repo, "ok": True, "head_sha": repo[-1] * 40}

    monkeypatch.setattr(fetch, "fetch_repo", fetch_repo)

    manifest = await fetch.fetch_corpus(["owner/1", "owner/2", "owner/3"], tmp_path, concurrency=2, timeout=5.0)

    rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
    assert maximum_active == 2
    assert {row["repo"] for row in rows} == {"owner/1", "owner/2", "owner/3"}


def test_select_sample_nests_larger_samples_within_smaller_ones() -> None:
    """Keep a pilot sample as a prefix of the full sample so pilot clones are reused."""
    repos = [f"owner/{index}" for index in range(500)]

    pilot = fetch.select_sample(repos, size=20, seed=7)
    full = fetch.select_sample(repos, size=100, seed=7)

    assert len(pilot) == 20
    assert full[:20] == pilot


def test_select_sample_is_deterministic_and_independent_of_input_order() -> None:
    """Produce the same sample for a fixed seed regardless of how the frame was emitted."""
    repos = [f"owner/{index}" for index in range(100)]

    assert fetch.select_sample(repos, size=10, seed=3) == fetch.select_sample(reversed(repos), size=10, seed=3)
    assert fetch.select_sample(repos, size=10, seed=3) != fetch.select_sample(repos, size=10, seed=4)


def test_select_sample_shuffles_the_whole_frame_when_size_is_unset() -> None:
    """Randomize clone order so an interrupted full fetch still leaves a random subsample."""
    repos = [f"owner/{index:03d}" for index in range(100)]

    selected = fetch.select_sample(repos, size=None, seed=1)

    assert sorted(selected) == repos
    assert selected != repos
