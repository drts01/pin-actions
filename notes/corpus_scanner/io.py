"""Shared file-format helpers for the corpus scanner."""

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """Yield each non-empty line of a JSON Lines file as a parsed object.

    Args:
        path: JSON Lines file to read.

    Yields:
        Parsed objects for each non-empty line.
    """
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)
