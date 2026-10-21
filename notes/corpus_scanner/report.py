"""Aggregate corpus statistics into the talk's Markdown report."""

import csv
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

_Z = 1.959963985
"""Two-sided 95% standard normal quantile."""

_Z_TARGET = 1000
"""Denominator the pre-commit statistic needs before it is worth putting on a slide."""


def _pct(numerator: int, denominator: int) -> str:
    """Format a ratio as a one-decimal percentage or ``n/a`` when empty."""
    return f"{100 * numerator / denominator:.1f}%" if denominator else "n/a"


def wilson(numerator: int, denominator: int) -> tuple[float, float]:
    """Compute the 95% Wilson score interval for a binomial proportion.

    The Wilson interval is used rather than the normal approximation because several
    corpus statistics have small denominators, where the normal interval misbehaves
    and can extend past zero or one.

    Args:
        numerator: Repositories exhibiting the measured property.
        denominator: Repositories in the population.

    Returns:
        Lower and upper bounds as proportions in ``[0.0, 1.0]``, or ``(0.0, 0.0)``
        when the denominator is zero.
    """
    if denominator <= 0:
        return 0.0, 0.0
    proportion = numerator / denominator
    correction = _Z**2 / denominator
    center = (proportion + correction / 2) / (1 + correction)
    spread = (_Z / (1 + correction)) * math.sqrt(
        proportion * (1 - proportion) / denominator + correction / (4 * denominator)
    )
    return max(0.0, center - spread), min(1.0, center + spread)


def _ci(numerator: int, denominator: int) -> str:
    """Format a Wilson interval as a percentage range or ``n/a`` when empty."""
    if denominator <= 0:
        return "n/a"
    low, high = wilson(numerator, denominator)
    return f"{100 * low:.1f}% to {100 * high:.1f}%"


def _sample_for_target(eligible: int, scanned: int, target: int) -> str:
    """Estimate the sample size that yields ``target`` pre-commit-eligible repositories."""
    if eligible <= 0 or scanned <= 0:
        return "n/a"
    return f"{math.ceil(target * scanned / eligible):,}"


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

    # Repositories whose only `uses:` refs are local or expression-valued can never enter the
    # numerator, so they must not sit in the pin-rate denominator either.
    in_scope = [
        row
        for row in with_workflows
        if int(row["uses_total"]) > 0 and not (exclude_dynamic and int(row["uses_dynamic"]) > 0)
    ]
    pinned = [row for row in in_scope if int(row["fully_pinned"])]
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
    excluded_dynamic = sum(1 for row in with_workflows if int(row["uses_total"]) and int(row["uses_dynamic"]))
    dynamic_note = (
        f"{'Excluded' if exclude_dynamic else 'Not excluded'} from the in-scope denominator: "
        f"{excluded_dynamic if exclude_dynamic else 0} "
        f"{'repository' if exclude_dynamic and excluded_dynamic == 1 else 'repositories'} "
        "with expression-valued `uses:`. "
        "Excluded from the residual numerators as neither pinned nor statically mutable: "
        f"{sum(int(row['withref_dynamic']) for row in pinned)} expression-valued `with.ref`, "
        f"{sum(int(row['image_dynamic']) for row in pinned)} expression-valued image refs. "
        f"Local `uses: ./...` and `uses: $/...` actions ({sum(int(row['uses_local']) for row in pinned)}) "
        "are out of scope."
    )

    lines = [
        "# Part 1 corpus results",
        "",
        f"- Repositories scanned: **{scanned}**",
        f"- With at least one workflow or action file: **{len(with_workflows)}**",
        f"- With at least one in-scope `uses:`: **{len(in_scope)}**",
        f"- Fully `uses:`-pinned (denominator `N`): **{denominator}** "
        f"— {_pct(denominator, len(in_scope))} of in-scope repositories, "
        f"95% CI {_ci(denominator, len(in_scope))}"
        + ("  _(expression-valued `uses:` excluded)_" if exclude_dynamic else ""),
        f"- Unparsable YAML files encountered: **{sum(int(row['parse_errors']) for row in rows)}**",
        "",
        "| Residual mutable surface | Count | Denominator | Share | 95% CI |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        f"| {label} | {hits} | {total} | **{_pct(hits, total)}** | {_ci(hits, total)} |" for label, hits, total in table
    )
    lines.extend(("", dynamic_note))

    sizing = _sample_for_target(len(precommit_frame), scanned, _Z_TARGET)
    lines.extend(
        (
            "",
            "## Sizing the full run",
            "",
            f"- `p_pin`, fully pinned share of scanned repositories: **{_pct(denominator, scanned)}**",
            f"- `p_precommit`, pre-commit-eligible share of `N`: **{_pct(len(precommit_frame), denominator)}**",
            f"- Repositories to clone for a `Z` denominator of {_Z_TARGET:,}: **{sizing}**",
            "",
            "Compare the last figure against the frame size in `frame.meta.json`.",
            "When it exceeds the frame, `Z` cannot be measured to slide quality at this sampling frame;",
            "widen the frame or demote `Z` to an anecdote.",
        )
    )
    return "\n".join(lines)
