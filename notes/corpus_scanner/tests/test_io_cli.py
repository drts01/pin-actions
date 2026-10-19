# ruff: noqa: I001, S101
"""Tests for shared corpus scanner I/O and CLI validation."""

import json
from datetime import date
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from notes.corpus_scanner.cli import FrameStage, ScanStage
from notes.corpus_scanner.io import read_jsonl

if TYPE_CHECKING:
    from pathlib import Path


def test_read_jsonl_skips_blank_lines(tmp_path: Path) -> None:
    """Ignore blank lines while preserving parsed object order."""
    path = tmp_path / "rows.jsonl"
    path.write_text('\n{"repo":"owner/one"}\n  \n{"repo":"owner/two"}\n', encoding="utf-8")

    assert list(read_jsonl(path)) == [{"repo": "owner/one"}, {"repo": "owner/two"}]


def test_read_jsonl_rejects_invalid_json(tmp_path: Path) -> None:
    """Propagate malformed artifact data instead of silently skipping it."""
    path = tmp_path / "rows.jsonl"
    path.write_text("not json\n", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        list(read_jsonl(path))


def test_frame_stage_rejects_inverted_star_band() -> None:
    """Reject a minimum star count greater than the maximum."""
    with pytest.raises(ValidationError, match=r"min_stars.*must not exceed max_stars"):
        FrameStage(min_stars=10, max_stars=9, pushed_since=date(2026, 4, 1))


def test_scan_stage_requires_a_manifest(tmp_path: Path) -> None:
    """Fail with an actionable message when fetch has not produced a manifest."""
    stage = ScanStage(cache=tmp_path)

    with pytest.raises(SystemExit, match="run the fetch stage first"):
        stage.cli_cmd()
