# SCaLE 24x Talk Proposal

**Title:** You Pinned Your Actions.
You're Still Not Pinned.

**Track:** Security / Open Source Supply Chain (confirm against the SCaLE 24x CFP form)

**Format:** 45 minutes, including 10 minutes for questions

## Abstract

"Pin your GitHub Actions to a commit SHA" is the most repeated piece of CI supply-chain advice.
Most repositories do not follow it, and those that do are often pinned only where the advice points.
Workflows also run container images, cross-repository checkouts, and pre-commit hooks,
and each of them can be a mutable tag or branch.

I scanned 49,984 public GitHub repositories.
87.8% of those using actions from other repositories do not pin all of them to a commit SHA.
Of the 4,008 that do, one in seven still carry a mutable container image, checkout ref, or pre-commit revision.

Pinning has a second limit: a commit SHA fixes content, not origin.
GitHub documents that fork commits can be reachable through the upstream repository,
so a pinned SHA can name code the upstream maintainers never published.

You will learn how to audit every mutable reference in your workflows, which controls close each one,
and what pinning costs in review effort and patch latency.

## Audience takeaways

- Identify every executable reference in a workflow, not only `uses:`.
- Understand why a commit SHA fixes content but does not establish repository identity.
- Audit container images, cross-repository `actions/checkout` refs,
  and pre-commit revisions without treating expression-valued refs as ordinary tags.
- Choose complementary controls for pinning, provenance, updates, and detection, and weigh their costs.

## Session plan

- **0–7 min:** Show a fully `uses:`-pinned workflow that still has mutable references;
  present the 87.8% pin-rate gap.
- **7–17 min:** Present the corpus measurement, denominators, limitations,
  and a neutral coverage comparison of existing tools and platform features.
- **17–23 min:** Explain the difference between a fixed SHA and verified repository identity,
  using a pre-commit hook pinned to a fork-only commit if that reproduces, or a GitHub Action otherwise.
  Use a recording or a documented walk-through if the live service is unavailable.
- **23–33 min:** Controls and their costs: digest and SHA pinning, provenance checks, automated updates,
  the tradeoff between release cooldowns and stale image patches, review cost, and detectors.
- **33–35 min:** Close with an audit checklist; reserve the remaining 10 minutes for questions.

## Notes for reviewers

**Disclosure.**
I maintain `pinref`, one of the pinning tools in the coverage comparison.
The comparison treats every tool, including `pinref`, by the same criteria, and shows where others are stronger.
The talk names `pinref` once, at the end.

**Method.**
The frame is active, non-archived, non-fork public repositories with at least 100 stars, pushed since 2026-04-01;
the sample is a seeded 50,000-repository draw, of which 49,984 still existed.
Every percentage is reported with its denominator and a 95% Wilson interval.
Local actions and expression-valued references (`${{ ... }}`) are excluded.
The scanner, sampling inputs, seed, raw counts, and reproduction instructions will be published with the talk.

**Known limits.**
Results cover GitHub Actions only and may differ below the 100-star floor.
The scan reads a default-branch snapshot, does not classify Docker container action definitions,
and does not count `runs-on:` runner images.

**Platform context.**
GitHub's workflow dependency lockfiles, in public preview, pin and verify action references.
The talk covers them as one control; they do not cover container images, checkout refs, or pre-commit revisions.

**Speaker.**
Todo: write a short bio emphasizing practitioner experience rolling out pinning across many repositories.
Do not name internal fleet details without employer clearance.

## Submission checks (not part of the CFP text)

- Confirm the SCaLE 24x CFP fields, word limits, and track names, and map the sections above onto them.
- Re-check the lockfile feature's status and coverage against GitHub's documentation before submission.
- Reproduce the fork-only-commit demonstration, preferably with pre-commit, before promising it live;
  retain the prerecorded or slide-based fallback.
- Do not quote remediation or rollout results until the public-corpus dry run is complete.
  Do not present internal fleet data without clearance.
