# SCaLE 24x Talk Proposal

**Title:** You Pinned Your GitHub Actions.
What's Still Mutable?

**Optional subtitle (if the CFP form supports one):** Mutable references in a 50,000-repository sample

**Track:** Security / Open Source Supply Chain (confirm against the SCaLE 24x CFP form)

**Format:** 45 minutes, including 10 minutes for questions

## Abstract

Pin every `uses:` in a GitHub Actions workflow to a full commit SHA.
The job can still run code from mutable container images, cross-repository checkouts, and pre-commit hooks.

I scanned 49,984 public GitHub repositories.
Of the 32,863 using actions from other repositories, 87.8% do not pin all of them to commit SHAs.
Even among the 4,008 that do, one in seven (14.8%) still have a mutable container image, cross-repository checkout ref,
or pre-commit revision.
The same gaps apply to any CI system that pulls images, repositories, or hooks by tag or branch.

A commit SHA fixes content, not origin.
GitHub documents that fork commits can be reachable through the upstream repository,
so a pinned SHA can name code the upstream maintainers never published.

You will learn how to audit references beyond `uses:` on GitHub and other CI systems,
compare what tools and platform controls cover,
and weigh the review effort and patch latency that come with maintaining pins.

## Audience takeaways

- Identify every executable reference in a workflow, not only `uses:`.
- Understand why a commit SHA fixes content but does not establish repository identity.
- Audit container images, cross-repository `actions/checkout` refs,
  and pre-commit revisions without treating expression-valued refs as ordinary tags.
- Recognize the same gaps in GitLab CI, CircleCI, Jenkins, and Tekton configurations.
- Choose complementary controls for pinning, provenance, updates, and detection, and weigh their costs.

## Session plan

- **0–7 min:** Show a fully `uses:`-pinned workflow that still has mutable references;
  present the 87.8% pin-rate gap, then explain how a bulk pinning task led to the measurement.
- **7–17 min:** Present the corpus measurement, denominators, limitations,
  transitive references inside pinned actions,
  a neutral coverage comparison of existing tools and platform features,
  and how the same gaps appear on other CI systems.
- **17–23 min:** Explain the difference between a fixed SHA and verified repository identity,
  using a pre-commit hook pinned to a fork-only commit if that reproduces, or a GitHub Action otherwise.
  Use a recording or a documented walk-through if the live service is unavailable.
  Show where an action lockfile verifies origin and where separate checks are still needed.
- **23–33 min:** Controls and their costs: GitHub's SHA-pinning policy, immutable releases, and lockfiles;
  digest and SHA pinning, provenance checks, automated updates,
  the tradeoff between release cooldowns and stale image patches, review cost, and detectors.
  Use only public-corpus remediation results if the dry run is complete.
- **33–35 min:** Close with an audit checklist; reserve the remaining 10 minutes for questions.

## Notes for reviewers

**Disclosure.**
I maintain `pinref`, one of the pinning tools in the coverage comparison.
The comparison treats every tool, including `pinref`, by the same criteria, and shows where others are stronger.
`pinref` appears only in the comparison tables, in one aside about a gap the measurement found in it,
and on the resources slide.

**Method.**
The frame is active, non-archived, non-fork public repositories with at least 100 stars, pushed since 2026-04-01;
the sample is a seeded 50,000-repository draw, of which 49,984 still existed.
Every percentage is reported with its denominator and a 95% Wilson interval.
Local actions and expression-valued references (`${{ ... }}`) are excluded.
The scanner, sampling inputs, seed, raw counts, and reproduction instructions will be published with the talk.

**Known limits.**
Results cover GitHub Actions only and may differ below the 100-star floor.
Other CI systems are covered from vendor documentation, not measured.
The scan reads a default-branch snapshot, does not classify Docker container action definitions,
and does not count `runs-on:` runner images.

**Platform context.**
GitHub's workflow dependency lockfiles, in public preview, pin and verify action references.
The talk covers them as one control; they do not cover container images, checkout refs, or pre-commit revisions.

**Speaker.** See [Speaker Bio](#speaker-bio).
There is no employer clearance: do not name the employer, its repositories, the repository count, or the trigger.

## Speaker Bio

Adapted from [`scale-24x-speaker-bios.md`](scale-24x-speaker-bios.md); confirm accuracy and the CFP's bio limit.
Do not add the employer's name or internal rollout details without clearance.

> Carlos Meza is a software engineer and longtime SCaLE volunteer.
> He found his way into tech through Linux user groups and local meetups,
> has spoken at SCaLE about DNSSEC, CI/CD, and Python,
> and now leads a team on the conference's A/V crew.
> He maintains `pinref`, an open-source tool for pinning mutable CI references to immutable commits and digests.
> Building it for a bulk pinning task led him to investigate what common GitHub Actions pinning advice overlooks.

## Submission checks (not part of the CFP text)

- Confirm the SCaLE 24x CFP fields, word limits, and track names, and map the sections above onto them.
- Confirm the speaker bio's volunteer and speaking-history claims, accuracy, and CFP word limit;
  keep the employer's name out without clearance.
- Confirm whether the employer's outside-activity policy requires approval to speak at all, independent of content.
- Re-check the lockfile feature's status and coverage against GitHub's documentation before submission.
- Reproduce the fork-only-commit demonstration, preferably with pre-commit, before promising it live;
  retain the prerecorded or slide-based fallback.
- Do not quote remediation or rollout results until the public-corpus dry run is complete.
  Do not present internal data; there is no employer clearance.
