"""Aggregate corpus statistics into the talk's Markdown report."""

import csv
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def _pct(numerator: int, denominator: int) -> str:
    """Format a ratio as a one-decimal percentage or ``n/a`` when empty."""
    return f"{100 * numerator / denominator:.1f}%" if denominator else "n/a"


def report(csv_path: Path, *, exclude_dynamic: bool) -> str:
    """Aggregate a corpus CSV into the Part 1 headline numbers.

    Args:
        csv_path: CSV produced by the scan stage.
        exclude_dynamic: Drop repositories containing expression-valued ``uses:`` refs
            from the denominator instead of counting them as fully pinned.

    Returns:
        Markdown report ready to paste into the talk notes.
    """
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    scanned = len(rows)
    with_workflows = [row for row in rows if int(row["workflow_files"]) > 0]

    pinned = [
        row
        for row in with_workflows
        if int(row["fully_pinned"]) and not (exclude_dynamic and int(row["uses_dynamic"]) > 0)
    ]
    denominator = len(pinned)

    def _has_precommit_gap(row: dict[str, str]) -> bool:
        return bool(int(row["precommit_in_ci"]) and int(row["precommit_mutable"]))

    image_gap = sum(1 for row in pinned if int(row["image_mutable"]))
    withref_gap = sum(1 for row in pinned if int(row["withref_mutable"]))
    precommit_frame = [row for row in pinned if int(row["precommit_in_ci"]) and int(row["precommit_total"])]
    precommit_gap = sum(1 for row in precommit_frame if int(row["precommit_mutable"]))
    any_gap = sum(
        1 for row in pinned if int(row["image_mutable"]) or int(row["withref_mutable"]) or _has_precommit_gap(row)
    )

    table = (
        ("Any of the three (headline)", any_gap, denominator),
        ("Mutable container image (`X`)", image_gap, denominator),
        ("Unpinned cross-repo `with.ref` (`Y`)", withref_gap, denominator),
        ("Unpinned pre-commit rev in CI (`Z`)", precommit_gap, len(precommit_frame)),
    )
    dynamic_note = (
        "Excluded from the numerators as neither pinned nor statically mutable: "
        f"{sum(int(row['uses_dynamic']) for row in pinned)} expression-valued `uses:`, "
        f"{sum(int(row['withref_dynamic']) for row in pinned)} expression-valued `with.ref`, "
        f"{sum(int(row['image_dynamic']) for row in pinned)} expression-valued image refs. "
        f"Local `uses: ./...` actions ({sum(int(row['uses_local']) for row in pinned)}) are out of scope."
    )

    lines = [
        "## Part 1 corpus results",
        "",
        f"- Repositories scanned: **{scanned}**",
        f"- With at least one workflow or action file: **{len(with_workflows)}**",
        f"- Fully `uses:`-pinned (denominator `N`): **{denominator}**"
        + ("  _(expression-valued `uses:` excluded)_" if exclude_dynamic else ""),
        f"- Unparsable YAML files encountered: **{sum(int(row['parse_errors']) for row in rows)}**",
        "",
        "| Residual mutable surface | Count | Denominator | Share |",
        "| --- | --- | --- | --- |",
    ]
    lines.extend(f"| {label} | {hits} | {total} | **{_pct(hits, total)}** |" for label, hits, total in table)
    lines.extend(("", dynamic_note))
    return "\n".join(lines)
