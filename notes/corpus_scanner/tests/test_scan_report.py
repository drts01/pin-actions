# ruff: noqa: S101
"""Tests for corpus classification and report aggregation."""

import csv
from dataclasses import asdict
from typing import TYPE_CHECKING

import pytest
from notes.corpus_scanner.report import CorpusSummary, report, summarize, wilson
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


def _write_corpus(csv_path: Path, rows: list[RepoStats]) -> None:
    """Serialize report input rows the way the scan stage writes them."""
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(rows[0])))
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {key: int(value) if isinstance(value, bool) else value for key, value in asdict(row).items()}
            )


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


@pytest.mark.parametrize(
    "content",
    [
        "[]\n",
        "repos:\n  - repo: https://github.com/owner/repo\n    rev: 1.0\n",
        "repos:\n  - invalid-entry\n",
        "repos:\n",
    ],
)
def test_scan_repo_skips_invalid_precommit_shapes(tmp_path: Path, content: str) -> None:
    """Treat syntactically valid non-pre-commit shapes as containing no refs."""
    (tmp_path / ".pre-commit-config.yaml").write_text(content, encoding="utf-8")

    stats = scan_repo("owner/repo", _SHA, tmp_path)

    assert stats.parse_errors == 0
    assert stats.precommit_total == 0
    assert stats.precommit_mutable == 0


def test_scan_repo_falls_back_to_pyyaml_for_valid_flow_yaml(tmp_path: Path) -> None:
    """Count references in valid YAML rejected by yamlrocks' flow indentation rules."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        f"jobs:\n  test:\n    steps: [\n      {{uses: actions/checkout@{_SHA}}}\n"
        "    , {uses: actions/setup-python@v5}\n    ]\n",
        encoding="utf-8",
    )
    (tmp_path / ".pre-commit-config.yaml").write_text(
        "repos: [\n  {repo: https://github.com/astral-sh/ruff-pre-commit, rev: v0.14.0}\n]\n",
        encoding="utf-8",
    )

    stats = scan_repo("owner/repo", _SHA, tmp_path)

    assert stats.parse_errors == 0
    assert stats.uses_total == 2  # noqa: PLR2004
    assert stats.uses_pinned == 1
    assert not stats.fully_pinned
    assert stats.precommit_total == 1
    assert stats.precommit_mutable == 1


def test_scan_repo_counts_both_forms_of_local_uses(tmp_path: Path) -> None:
    """Count both directory-relative and repo-root local actions as out of scope."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        f"jobs:\n  test:\n    steps:\n      - uses: ./local\n      - uses: $/.github/actions/local\n"
        f"      - uses: actions/checkout@{_SHA}\n",
        encoding="utf-8",
    )

    stats = scan_repo("owner/repo", _SHA, tmp_path)

    assert stats.uses_local == 2  # noqa: PLR2004
    assert stats.uses_total == stats.uses_pinned == 1


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
    _write_corpus(csv_path, rows)

    inclusive = report(csv_path, exclude_dynamic=False)
    exclusive = report(csv_path, exclude_dynamic=True)

    assert "Fully `uses:`-pinned (denominator `N`): **2**" in inclusive
    assert "| Any of the three (headline) | 2 | 2 | **100.0%** |" in inclusive
    assert "Fully `uses:`-pinned (denominator `N`): **1**" in exclusive
    assert "| Any of the three (headline) | 1 | 1 | **100.0%** |" in exclusive
    assert "Excluded from the in-scope denominator: 1 repository with expression-valued `uses:`." in exclusive
    assert "Not excluded from the in-scope denominator: 0 repositories" in inclusive


def test_report_excludes_local_only_repositories_from_the_pin_rate_denominator(tmp_path: Path) -> None:
    """Keep repositories that cannot be pinned out of the in-scope denominator."""
    csv_path = tmp_path / "corpus.csv"
    _write_corpus(
        csv_path,
        [
            _stats("owner/pinned"),
            _stats("owner/unpinned", uses_pinned=0, fully_pinned=False),
            _stats("owner/local-only", uses_total=0, uses_pinned=0, uses_local=3, fully_pinned=False),
        ],
    )

    text = report(csv_path, exclude_dynamic=True)

    assert "- With at least one workflow or action file: **3**" in text
    assert "- With at least one in-scope `uses:`: **2**" in text
    assert "50.0% of in-scope repositories" in text


def test_report_sizes_the_full_run_from_the_precommit_eligible_rate(tmp_path: Path) -> None:
    """Derive the sample size that clears the pre-commit denominator target."""
    csv_path = tmp_path / "corpus.csv"
    _write_corpus(
        csv_path,
        [
            _stats("owner/precommit", precommit_in_ci=True, precommit_total=1, precommit_mutable=1),
            *(_stats(f"owner/plain{index}") for index in range(9)),
        ],
    )

    text = report(csv_path, exclude_dynamic=True)

    assert "`p_pin`, fully pinned share of scanned repositories: **100.0%**" in text
    assert "`p_precommit`, pre-commit-eligible share of `N`: **10.0%**" in text
    assert "Repositories to clone for a `Z` denominator of 1,000: **10,000**" in text


def test_summarize_counts_every_statistic_against_its_own_denominator(tmp_path: Path) -> None:
    """Expose the counts behind the report so slides and the report cannot drift."""
    csv_path = tmp_path / "corpus.csv"
    _write_corpus(
        csv_path,
        [
            _stats("owner/image", image_total=2, image_mutable=1, image_dynamic=1, parse_errors=1),
            _stats("owner/withref", withref_total=2, withref_mutable=1, withref_dynamic=1, uses_local=2),
            _stats("owner/precommit", precommit_in_ci=True, precommit_total=1, precommit_mutable=1),
            _stats("owner/precommit-pinned", precommit_in_ci=True, precommit_total=1),
            _stats("owner/precommit-not-in-ci", precommit_total=1, precommit_mutable=1),
            _stats("owner/dynamic", uses_dynamic=1, image_total=1, image_mutable=1),
            _stats("owner/unpinned", uses_pinned=0, fully_pinned=False, image_total=1, image_mutable=1),
            _stats("owner/no-workflows", workflow_files=0, uses_total=0, uses_pinned=0, fully_pinned=False),
        ],
    )

    summary = summarize(csv_path, exclude_dynamic=True)

    assert summary == CorpusSummary(
        scanned=8,
        with_workflows=7,
        in_scope=6,
        pinned=5,
        any_gap=3,
        image_gap=1,
        withref_gap=1,
        precommit_eligible=2,
        precommit_gap=1,
        excluded_dynamic=1,
        withref_dynamic=1,
        image_dynamic=1,
        uses_local=2,
        parse_errors=1,
    )
    assert summarize(csv_path, exclude_dynamic=False).pinned == 6  # noqa: PLR2004


@pytest.mark.parametrize(
    ("numerator", "denominator", "low", "high"),
    [
        (22, 168, 0.088, 0.190),
        (5, 8, 0.306, 0.863),
        (0, 10, 0.000, 0.278),
        (10, 10, 0.722, 1.000),
    ],
)
def test_wilson_bounds_stay_inside_the_unit_interval(numerator: int, denominator: int, low: float, high: float) -> None:
    """Match published Wilson bounds and never leave ``[0.0, 1.0]``."""
    assert wilson(numerator, denominator) == pytest.approx((low, high), abs=0.001)


def test_wilson_returns_a_degenerate_interval_for_an_empty_population() -> None:
    """Avoid dividing by zero when a denominator is empty."""
    assert wilson(0, 0) == (0.0, 0.0)
