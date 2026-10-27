# SCaLE 24x Talk Proposal

**Title:** You Pinned Your GitHub Actions.
What's Still Mutable?

The CFP form has no subtitle field; the former subtitle is folded into the short abstract.

**Track:** Security (fallback: Developers, Platform Engineering & DevEx)

**Level:** Intermediate (confirm the level options in the CFP form)

**Format:** Talk, about 45 minutes: about 40 minutes of presentation and 5 minutes for questions

Field mapping in the CFP tool: **Short Abstract** (print), **Long Abstract** (online), speaker biography
(1,000 characters maximum), Track and Level, and **Message to the reviewers**.

## Short Abstract

Pinning GitHub Actions to commit SHAs is standard advice,
yet 87.8% of 32,863 public repositories using actions from other repositories do not,
and one in seven that do still run mutable container images, checkout refs, or pre-commit hooks.
Learn what pinning misses, why a SHA proves content but not origin, and how to audit GitHub, GitLab, Jenkins,
and CircleCI pipelines.

## Abstract

Use this section as the **Long Abstract**.

Pin every `uses:` in a GitHub Actions workflow to a full commit SHA.
The job can still run code from mutable container images, cross-repository checkouts, and pre-commit hooks.

I scanned 49,984 public GitHub repositories.
Of the 32,863 using actions from other repositories, 87.8% do not pin all of them to commit SHAs.
Even among the 4,008 that do, one in seven (14.8%) still have a mutable container image, cross-repository checkout ref,
or pre-commit revision.
More than half of the repositories with a mutable image float the job container itself,
the environment every step runs inside.
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

The slide deck is drafted at 45 minutes and is trimmed to 40 in rehearsal.

- **0–7 min:** Show a fully `uses:`-pinned workflow that still has mutable references;
  present the 87.8% pin-rate gap, then explain how a bulk pinning task led to the measurement.
- **7–19 min:** Present the corpus measurement, denominators, limitations,
  which images float and where (job containers, services, `docker://` steps),
  transitive references inside pinned actions,
  a neutral coverage comparison of existing tools and platform features,
  and the same gaps in GitLab CI, Jenkins, and CircleCI configuration.
- **19–28 min:** Explain the difference between a fixed SHA and verified repository identity,
  using a pre-commit hook pinned to a fork-only commit if that reproduces, or a GitHub Action otherwise.
  Use a recording or a documented walk-through if the live service is unavailable.
  Show how to check a SHA's origin by hand with Git, where an action lockfile verifies origin,
  and where other platforms and clients are exposed.
- **28–36 min:** Controls and their costs: GitHub's SHA-pinning policy, immutable releases, and lockfiles;
  digest and SHA pinning, provenance checks, Renovate and Dependabot update configuration,
  the tradeoff between release cooldowns and stale image patches, review cost, and detectors.
  Use only public-corpus remediation results if the dry run is complete.
- **36–40 min:** Close with audit commands and a checklist.
- **40–45 min:** Questions.

## Notes for reviewers

Condense this section into the CFP's **Message to the reviewers** field.

**Technical setup.**
None beyond the standard HDMI projector.
The live demonstration needs internet access and falls back to a recording without it.

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

Adapted from [`scale-24x-speaker-bios.md`](scale-24x-speaker-bios.md); confirm accuracy.
The CFP limits the biography to 1,000 characters, written in the third person; this version is about 460.
Do not add the employer's name or internal rollout details without clearance.

> Carlos Meza is a software engineer and longtime SCaLE volunteer.
> He found his way into tech through Linux user groups and local meetups,
> has spoken at SCaLE about DNSSEC, CI/CD, and Python,
> and now leads a team on the conference's A/V crew.
> He maintains `pinref`, an open-source tool for pinning mutable CI references to immutable commits and digests.
> Building it for a bulk pinning task led him to investigate what common GitHub Actions pinning advice overlooks.

## Submission checks (not part of the CFP text)

- Confirm the Level options and any Short Abstract length limit in the CFP form;
  the Track names and the 1,000-character bio limit were confirmed on the CFP page on 2026-10-26.
- Confirm the speaker bio's volunteer and speaking-history claims and accuracy;
  keep the employer's name out without clearance.
- Confirm whether the employer's outside-activity policy requires approval to speak at all, independent of content.
- Re-check the lockfile feature's status and coverage against GitHub's documentation before submission.
- Reproduce the fork-only-commit demonstration, preferably with pre-commit, before promising it live;
  retain the prerecorded or slide-based fallback.
- Do not quote remediation or rollout results until the public-corpus dry run is complete.
  Do not present internal data; there is no employer clearance.
- Decide whether to also submit to SunSecCon, the co-located security event with its own CFP tool;
  its CFP asks for supply-chain talks and live demos.
  Check its deadline and whether dual submission is allowed.
