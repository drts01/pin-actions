"""Build the corpus sampling frame from GitHub repository search results."""

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any, TextIO

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from pin_actions.client import GitHubClient

logger = logging.getLogger("scan_corpus")

_SEARCH_PAGE_SIZE = 100
_SEARCH_RESULT_CAP = 1000
_SEARCH_THROTTLE_SECONDS = 2.1  # GitHub search allows 30 requests/minute authenticated.


async def _search_page(client: GitHubClient, query: str, page: int) -> dict[str, Any]:
    """Fetch one page of repository search results and throttle to the search quota."""
    data = await client._get_json(
        "/search/repositories",
        params={"q": query, "sort": "stars", "order": "desc", "per_page": _SEARCH_PAGE_SIZE, "page": page},
    )
    await asyncio.sleep(_SEARCH_THROTTLE_SECONDS)
    return data


def _write_frame_items(handle: TextIO, items: Iterable[dict[str, Any]], seen: set[str]) -> int:
    """Append unseen search results to the frame file as JSON lines."""
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
    """Enumerate the sampling frame by bisecting star bands around GitHub's 1000-result cap.

    Args:
        client: GitHub API client.
        out: Destination JSON Lines file; a sibling ``.meta.json`` records the query.
        min_stars: Inclusive lower star bound of the frame.
        max_stars: Inclusive upper star bound of the frame.
        pushed_since: ISO date; only repositories pushed after this are included.

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
