"""Aggregate corpus statistics into the talk's Markdown report."""

import csv
import math
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class CorpusSummary:
    """Repository counts behind the talk's Part 1 statistics.

    Attributes:
        scanned: Repositories in the CSV.
        with_workflows: Repositories with at least one workflow or action file.
        in_scope: Pin-rate denominator: repositories with at least one in-scope ``uses:``.
        pinned: Denominator ``N``: in-scope repositories whose every ``uses:`` is a commit SHA.
        any_gap: Repositories in ``N`` with any residual mutable reference (the headline).
        image_gap: Repositories in ``N`` with a mutable container image (``X``).
        withref_gap: Repositories in ``N`` with an unpinned cross-repository ``with.ref`` (``Y``).
        precommit_eligible: Repositories in ``N`` that run pre-commit in CI and have hook revisions.
        precommit_gap: Eligible repositories with an unpinned pre-commit revision (``Z``).
        excluded_dynamic: Repositories with expression-valued ``uses:``, regardless of exclusion.
        withref_dynamic: Expression-valued ``with.ref`` values in ``N``.
        image_dynamic: Expression-valued image references in ``N``.
        uses_local: Local ``uses:`` references in ``N``.
        parse_errors: Unparsable YAML files across all scanned repositories.
    """

    scanned: int
    with_workflows: int
    in_scope: int
    pinned: int
    any_gap: int
    image_gap: int
    withref_gap: int
    precommit_eligible: int
    precommit_gap: int
    excluded_dynamic: int
    withref_dynamic: int
    image_dynamic: int
    uses_local: int
    parse_errors: int


def summarize(csv_path: Path, *, exclude_dynamic: bool) -> CorpusSummary:
    """Count the repositories behind every Part 1 statistic.

    Args:
        csv_path: CSV produced by the scan stage.
        exclude_dynamic: Drop repositories containing expression-valued ``uses:`` refs
            from the denominator instead of counting them as fully pinned.

    Returns:
        Aggregate counts; percentages and intervals are left to the caller.
    """
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    with_workflows = [row for row in rows if int(row["workflow_files"]) > 0]

    # Repositories whose only `uses:` refs are local or expression-valued can never enter the
    # numerator, so they must not sit in the pin-rate denominator either.
    in_scope = [
        row
        for row in with_workflows
        if int(row["uses_total"]) > 0 and not (exclude_dynamic and int(row["uses_dynamic"]) > 0)
    ]
    pinned = [row for row in in_scope if int(row["fully_pinned"])]

    def _has_precommit_gap(row: dict[str, str]) -> bool:
        return bool(int(row["precommit_in_ci"]) and int(row["precommit_mutable"]))

    precommit_frame = [row for row in pinned if int(row["precommit_in_ci"]) and int(row["precommit_total"])]
    return CorpusSummary(
        scanned=len(rows),
        with_workflows=len(with_workflows),
        in_scope=len(in_scope),
        pinned=len(pinned),
        any_gap=sum(
            1 for row in pinned if int(row["image_mutable"]) or int(row["withref_mutable"]) or _has_precommit_gap(row)
        ),
        image_gap=sum(1 for row in pinned if int(row["image_mutable"])),
        withref_gap=sum(1 for row in pinned if int(row["withref_mutable"])),
        precommit_eligible=len(precommit_frame),
        precommit_gap=sum(1 for row in precommit_frame if int(row["precommit_mutable"])),
        excluded_dynamic=sum(1 for row in with_workflows if int(row["uses_total"]) and int(row["uses_dynamic"])),
        withref_dynamic=sum(int(row["withref_dynamic"]) for row in pinned),
        image_dynamic=sum(int(row["image_dynamic"]) for row in pinned),
        uses_local=sum(int(row["uses_local"]) for row in pinned),
        parse_errors=sum(int(row["parse_errors"]) for row in rows),
    )


def report(csv_path: Path, *, exclude_dynamic: bool) -> str:
    """Aggregate a corpus CSV into the Part 1 headline numbers.

    Args:
        csv_path: CSV produced by the scan stage.
        exclude_dynamic: Drop repositories containing expression-valued ``uses:`` refs
            from the denominator instead of counting them as fully pinned.

    Returns:
        Markdown report ready to paste into the talk notes.
    """
    s = summarize(csv_path, exclude_dynamic=exclude_dynamic)
    table = (
        ("Any of the three (headline)", s.any_gap, s.pinned),
        ("Mutable container image (`X`)", s.image_gap, s.pinned),
        ("Unpinned cross-repo `with.ref` (`Y`)", s.withref_gap, s.pinned),
        ("Unpinned pre-commit rev in CI (`Z`)", s.precommit_gap, s.precommit_eligible),
    )
    dynamic_note = (
        f"{'Excluded' if exclude_dynamic else 'Not excluded'} from the in-scope denominator: "
        f"{s.excluded_dynamic if exclude_dynamic else 0} "
        f"{'repository' if exclude_dynamic and s.excluded_dynamic == 1 else 'repositories'} "
        "with expression-valued `uses:`. "
        "Excluded from the residual numerators as neither pinned nor statically mutable: "
        f"{s.withref_dynamic} expression-valued `with.ref`, "
        f"{s.image_dynamic} expression-valued image refs. "
        f"Local `uses: ./...` and `uses: $/...` actions ({s.uses_local}) "
        "are out of scope."
    )

    lines = [
        "# Part 1 corpus results",
        "",
        f"- Repositories scanned: **{s.scanned}**",
        f"- With at least one workflow or action file: **{s.with_workflows}**",
        f"- With at least one in-scope `uses:`: **{s.in_scope}**",
        f"- Fully `uses:`-pinned (denominator `N`): **{s.pinned}** "
        f"— {_pct(s.pinned, s.in_scope)} of in-scope repositories, "
        f"95% CI {_ci(s.pinned, s.in_scope)}" + ("  _(expression-valued `uses:` excluded)_" if exclude_dynamic else ""),
        f"- Unparsable YAML files encountered: **{s.parse_errors}**",
        "",
        "| Residual mutable surface | Count | Denominator | Share | 95% CI |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        f"| {label} | {hits} | {total} | **{_pct(hits, total)}** | {_ci(hits, total)} |" for label, hits, total in table
    )
    lines.extend(("", dynamic_note))

    sizing = _sample_for_target(s.precommit_eligible, s.scanned, _Z_TARGET)
    lines.extend(
        (
            "",
            "## Sizing the full run",
            "",
            f"- `p_pin`, fully pinned share of scanned repositories: **{_pct(s.pinned, s.scanned)}**",
            f"- `p_precommit`, pre-commit-eligible share of `N`: **{_pct(s.precommit_eligible, s.pinned)}**",
            f"- Repositories to clone for a `Z` denominator of {_Z_TARGET:,}: **{sizing}**",
            "",
            "Compare the last figure against the frame size in `frame.meta.json`.",
            "When it exceeds the frame, `Z` cannot be measured to slide quality at this sampling frame;",
            "widen the frame or demote `Z` to an anecdote.",
        )
    )
    return "\n".join(lines)
