# ruff: noqa: S101
"""Tests for corpus classification and report aggregation."""

import csv
from dataclasses import asdict
from typing import TYPE_CHECKING

from notes.corpus_scanner.report import report
from notes.corpus_scanner.scan import RepoStats, scan_corpus, scan_repo

if TYPE_CHECKING:
    from pathlib import Path

_SHA = "a" * 40
_DIGEST = "b" * 64


def _write_repository(root: Path) -> None:
    """Write a repository fixture spanning every classified reference type."""
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        f"""name: CI
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    container: python:3.14
    services:
      redis:
        image: redis@sha256:{_DIGEST}
    steps:
      - uses: actions/checkout@{_SHA}
        with:
          repository: example/other
          ref: main
      - uses: ./local-action
      - uses: example/dynamic@${{{{ github.ref }}}}
      - uses: docker://alpine:3.21
      - run: pre-commit run --all-files
""",
        encoding="utf-8",
    )
    (root / ".pre-commit-config.yaml").write_text(
        "repos:\n  - repo: https://github.com/astral-sh/ruff-pre-commit\n    rev: v0.14.0\n    hooks: []\n",
        encoding="utf-8",
    )


def _stats(repo: str, **overrides: int | bool | str) -> RepoStats:
    """Build report input with concise defaults."""
    values: dict[str, int | bool | str] = {
        "repo": repo,
        "head_sha": _SHA,
        "workflow_files": 1,
        "parse_errors": 0,
        "uses_total": 1,
        "uses_pinned": 1,
        "uses_dynamic": 0,
        "uses_local": 0,
        "fully_pinned": True,
        "image_total": 0,
        "image_mutable": 0,
        "image_dynamic": 0,
        "withref_total": 0,
        "withref_mutable": 0,
        "withref_dynamic": 0,
        "precommit_in_ci": False,
        "precommit_total": 0,
        "precommit_mutable": 0,
    }
    values.update(overrides)
    return RepoStats(**values)  # type: ignore[arg-type]


def test_scan_repo_classifies_static_dynamic_local_and_precommit_refs(tmp_path: Path) -> None:
    """Classify all measured reference categories from repository files."""
    _write_repository(tmp_path)

    stats = scan_repo("owner/repo", _SHA, tmp_path)

    assert stats == RepoStats(
        repo="owner/repo",
        head_sha=_SHA,
        workflow_files=1,
        parse_errors=0,
        uses_total=1,
        uses_pinned=1,
        uses_dynamic=1,
        uses_local=1,
        fully_pinned=True,
        image_total=3,
        image_mutable=2,
        image_dynamic=0,
        withref_total=1,
        withref_mutable=1,
        withref_dynamic=0,
        precommit_in_ci=True,
        precommit_total=1,
        precommit_mutable=1,
    )


def test_scan_corpus_skips_failed_fetches_and_serializes_boolean_counts(tmp_path: Path) -> None:
    """Write one CSV row per successful manifest entry and encode booleans as integers."""
    cache = tmp_path / "repos"
    repository = cache / "owner" / "repo"
    _write_repository(repository)
    manifest = cache / "manifest.jsonl"
    manifest.write_text(
        f'{{"repo":"owner/failed","ok":false,"error":"denied"}}\n'
        f'{{"repo":"owner/repo","ok":true,"head_sha":"{_SHA}"}}\n',
        encoding="utf-8",
    )
    output = tmp_path / "corpus.csv"

    written = scan_corpus(manifest, cache, output)

    with output.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert written == 1
    assert rows[0]["repo"] == "owner/repo"
    assert rows[0]["fully_pinned"] == "1"
    assert rows[0]["precommit_in_ci"] == "1"


def test_report_uses_expected_denominators_and_can_exclude_dynamic_repositories(tmp_path: Path) -> None:
    """Aggregate gaps and optionally remove dynamic uses from the denominator."""
    csv_path = tmp_path / "corpus.csv"
    rows = [
        _stats("owner/image", image_total=1, image_mutable=1),
        _stats("owner/dynamic", uses_dynamic=1, withref_total=1, withref_mutable=1),
        _stats("owner/unpinned", uses_pinned=0, fully_pinned=False),
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(rows[0])))
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {key: int(value) if isinstance(value, bool) else value for key, value in asdict(row).items()}
            )

    inclusive = report(csv_path, exclude_dynamic=False)
    exclusive = report(csv_path, exclude_dynamic=True)

    assert "Fully `uses:`-pinned (denominator `N`): **2**" in inclusive
    assert "| Any of the three (headline) | 2 | 2 | **100.0%** |" in inclusive
    assert "Fully `uses:`-pinned (denominator `N`): **1**" in exclusive
    assert "| Any of the three (headline) | 1 | 1 | **100.0%** |" in exclusive
