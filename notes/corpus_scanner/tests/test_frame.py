# ruff: noqa: I001, PLR2004, S101
"""Tests for corpus sampling-frame construction."""

import asyncio
import json
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest

from notes.corpus_scanner import frame

if TYPE_CHECKING:
    from pathlib import Path


class _SearchClient:
    """Record repository search requests and return a fixed response."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, Any]]] = []

    async def _get_json(self, path: str, *, params: dict[str, Any]) -> dict[str, Any]:
        self.requests.append((path, params))
        return {"total_count": 1, "items": [{"full_name": "owner/repo", "stargazers_count": 123}]}


@pytest.mark.asyncio
async def test_search_page_uses_expected_query_and_throttles(monkeypatch: pytest.MonkeyPatch) -> None:
    """Send the expected search parameters and sleep after the request."""
    client = _SearchClient()
    sleep = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", sleep)

    result = await frame._search_page(client, "stars:100..200", 3)  # type: ignore[arg-type]

    assert result["total_count"] == 1
    assert client.requests == [
        (
            "/search/repositories",
            {"q": "stars:100..200", "sort": "stars", "order": "desc", "per_page": 100, "page": 3},
        )
    ]
    sleep.assert_awaited_once_with(2.1)


@pytest.mark.asyncio
async def test_build_frame_bisects_large_bands_and_deduplicates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Split capped search bands and write each repository once."""
    queries: list[tuple[str, int]] = []

    async def search_page(_client: object, query: str, page: int) -> dict[str, Any]:
        """Return deterministic results for each bisected star band."""
        queries.append((query, page))
        if query.startswith("stars:0..3"):
            return {"total_count": 1001, "items": []}
        if query.startswith("stars:0..1"):
            return {
                "total_count": 2,
                "items": [
                    {"full_name": "owner/shared", "stargazers_count": 1},
                    {"full_name": "owner/lower", "stargazers_count": 1},
                ],
            }
        return {
            "total_count": 2,
            "items": [
                {"full_name": "owner/shared", "stargazers_count": 2},
                {"full_name": "owner/upper", "stargazers_count": 3},
            ],
        }

    monkeypatch.setattr(frame, "_search_page", search_page)
    output = tmp_path / "frame.jsonl"

    count = await frame.build_frame(object(), output, min_stars=0, max_stars=3, pushed_since="2026-04-01")  # type: ignore[arg-type]

    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert count == 3
    assert {row["repo"] for row in rows} == {"owner/shared", "owner/lower", "owner/upper"}
    assert queries == [
        ("stars:0..3 pushed:>2026-04-01 fork:false archived:false", 1),
        ("stars:2..3 pushed:>2026-04-01 fork:false archived:false", 1),
        ("stars:0..1 pushed:>2026-04-01 fork:false archived:false", 1),
    ]
    assert json.loads(output.with_suffix(".meta.json").read_text(encoding="utf-8")) == {
        "min_stars": 0,
        "max_stars": 3,
        "pushed_since": "2026-04-01",
        "qualifiers": "fork:false archived:false",
        "repos": 3,
    }
