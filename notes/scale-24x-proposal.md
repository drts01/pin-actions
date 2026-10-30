# SCaLE 24x Talk Proposal

**Title:** You Pinned Your GitHub Actions.
What's Still Mutable?

**Track:** Security (fallback: Developers, Platform Engineering & DevEx)

**Level:** Intermediate

**Format:** Talk, about 45 minutes: about 40 minutes of presentation and 5 minutes for questions

## Short Abstract

Pinning GitHub Actions to commit SHAs is standard advice.
In a scan of 32,863 public repositories, 87.8% don't follow it,
and 14.8% of those that do still reference mutable container images, checkout refs, or pre-commit hooks.
Learn what SHA pinning misses, why a SHA fixes content but not origin, and how to audit your pipelines.

## Long Abstract

You pinned every `uses:` in your GitHub Actions workflows to a full commit SHA.
Your jobs can still run code from mutable container images, cross-repository checkouts, and pre-commit hooks.

Tags are pointers, and pointers move.
In March 2026, attackers force-pushed 76 of 77 version tags of `aquasecurity/trivy-action` to malicious code
and published compromised Trivy container images (CVE-2026-33634).
Images pulled by digest were unaffected,
but older `trivy-action` commits pinned by SHA still loaded a compromised `setup-trivy` action by tag.

I scanned 49,984 public GitHub repositories.
Of the 32,863 using actions from other repositories, 87.8% do not pin all of them to commit SHAs.
Even among the 4,008 that do, one in seven
(592, or 14.8%)
still have a mutable container image, cross-repository checkout ref, or pre-commit revision that CI runs.
In 203 of the 358 repositories with a mutable image, the floating image is the job container itself,
the environment every step runs inside.
These figures are undercounts: the scan does not follow transitive references inside pinned actions.
The same patterns apply to GitLab CI, Jenkins, and CircleCI, or any CI system that pulls images, repositories,
or hooks by tag or branch.

A commit SHA fixes content, not origin.
GitHub documents that fork commits can be reachable through the upstream repository,
so a pinned SHA can name code the upstream maintainers never published.

You will learn how to audit references beyond `uses:`, check where a pinned SHA came from,
compare what tools and platform controls cover,
and weigh the review effort and patch latency that come with maintaining pins.

## Audience Takeaways

- Identify every mutable reference a workflow resolves, not only `uses:`.
- Understand why a commit SHA fixes content but does not establish repository identity,
  and check a SHA's origin with Git.
- Audit container images, cross-repository `actions/checkout` refs,
  and pre-commit revisions without treating expression-valued refs as ordinary tags.
- Recognize the same patterns in GitLab CI, Jenkins, and CircleCI configurations.
- Choose complementary controls for pinning, provenance, updates, and detection, and weigh their costs.

## Session Plan

- **0–7 min:** Show a fully `uses:`-pinned workflow that still has mutable references.
  Recap the `reviewdog`, `tj-actions/changed-files`, and Trivy tag-repointing compromises on one timeline slide.
  Present the 87.8% pin-rate gap, then explain how a bulk pinning task led to the measurement.
- **7–17 min:** Present the corpus measurement: frame, denominators, intervals, and limits.
  Show which images float and where: job containers, services, and `docker://` steps.
  Show transitive references inside pinned actions as an unmeasured undercount.
  Map the same gaps to GitLab CI, Jenkins, and CircleCI on one slide, from vendor documentation.
- **17–27 min:** Explain the difference between a fixed SHA and verified repository identity,
  crediting GitHub's documentation and Chainguard's 2023 imposter-commit research.
  Walk through a workflow running a fork-only commit through the upstream repository's name.
  Show how to check a SHA's origin by hand with Git, where an action lockfile verifies origin,
  and where other platforms and clients are exposed.
- **27–36 min:** Compare controls and their costs: GitHub's SHA-pinning policy, immutable releases, and lockfiles;
  a coverage table of `ratchet`, `pinact`, Updatecli, `pin-github-action`, `zizmor`, and `pinref`;
  digest and SHA pinning; provenance checks; Renovate and Dependabot update configuration;
  the tradeoff between release cooldowns and stale image patches; and review cost.
- **36–40 min:** Close with audit commands and a checklist.
- **40–45 min:** Questions.

## Message to the Reviewers

**Technical setup.** Standard HDMI projector.
No internet access required; the walk-through uses recorded runs.

**Disclosure.**
I maintain `pinref`, one of the tools in the coverage comparison.
Every tool, including `pinref`, is rated by the same criteria, and the table shows where others are stronger.
`pinref` appears only in the comparison table, in one aside about a gap the measurement found in it,
and on the resources slide.

**Prior work.**
Chainguard described imposter commits in 2023, GitHub's documentation warns about fork commits,
and `zizmor`'s `impostor-commit` audit detects them after they are committed.
The talk credits all three.
Its additions are a measurement of mutable references beyond `uses:`,
and a comparison of where lockfiles and pinning tools do and do not verify origin.

**Method.**
The frame is 149,570 active, non-archived, non-fork public repositories with at least 100 stars,
pushed since 2026-04-01; the sample is a seeded 50,000-repository draw, of which 49,984 still existed.
Every percentage is reported with its denominator and a 95% Wilson interval.
Local actions and expression-valued references (`${{ ... }}`) are excluded.
Pre-commit revisions count only when a workflow runs pre-commit;
cross-repository checkout refs count whether or not the job executes the checked-out code.
I will rerun the scan in March 2027 and update every figure.
The scanner, sampling inputs, seed, raw counts, and reproduction instructions will be published with the talk.

**Known limits.**
Results cover GitHub Actions only and may differ below the 100-star floor.
Other CI systems are covered from vendor documentation, not measured.
The scan reads a default-branch snapshot, does not follow transitive references inside pinned actions,
does not classify Docker container action definitions, and does not count `runs-on:` runner images,
so every figure is an undercount.

**Platform context.**
GitHub's workflow dependency lockfiles, in public preview, pin and verify action references.
The talk covers them as one control; they do not cover container images, checkout refs, or pre-commit revisions.

**Speaking history.**
SCaLE 14x: DNSSEC; Getting Started with TDI (DevOpsDays LA, co-located with SCaLE 14x).
SCaLE 15x: How To DevOps (CI/CD).
SCaLE 18x: Make Python Great Again.
SCaLE 20x: UpSCALE lightning talk.
SoCal Code Camp: Test Driven Infrastructure (2015); How-to DevOps: Learning CI/CD by Building Personal Websites (2016).

## Speaker Bio

> Carlos Meza is a software engineer and longtime SCaLE volunteer.
> He found his way into tech through Linux user groups and local meetups.
> He has spoken five times at SCaLE since SCaLE 14x, on DNSSEC, CI/CD, and Python,
> and at DevOpsDays LA and SoCal Code Camp.
> He chaired DevOpsDays LA and now leads a team on the conference's A/V crew.
> He maintains `pinref`, an open-source tool for pinning mutable CI references to immutable commits and digests.
> Building it for a bulk pinning task led him to investigate what common GitHub Actions pinning advice overlooks.

## Submission Checks (not part of the CFP text)

Do not paste this section into the CFP form.

- Map sections to CFP fields: **Short Abstract** (print), **Long Abstract** (online), **Speaker Bio**
  (1,000 characters maximum, third person), Track and Level, and **Message to the Reviewers**.
  Append the takeaways and session plan to the Long Abstract or the reviewer message if the form has no outline field.
- Confirm the Level options and any Short Abstract length limit in the CFP form;
  the Track names, the "about 45 minutes" format, and the 1,000-character bio limit were confirmed on 2026-10-26.
- Confirm the bio's claims against [`scale-24x-speaker-bios.md`](scale-24x-speaker-bios.md): five SCaLE talks,
  the DevOpsDays LA talk and chair role, two SoCal Code Camp talks, and the A/V crew.
  The bio omits former employers by choice; the community speaking record is the stronger credential here.
  Recount characters after any edit.
- Keep the current employer out of every field: no employer clearance exists,
  so do not name the employer, its repositories, the repository count, or the trigger.
- Confirm whether the employer's outside-activity policy requires approval to speak at all, independent of content.
- Re-check the lockfile feature's status and coverage against GitHub's documentation before submission.
- Re-check the Trivy figures in the Long Abstract against GHSA-69fq-xp46-6x23 before submission:
  76 of 77 `trivy-action` tags, compromised images, CVE-2026-33634, and the older-SHA `setup-trivy` caveat.
- The 17–27 minute segment promises a recorded walk-through, not a live demo, so it does not block submission.
  Record the fork-only-commit run before the conference, with pre-commit if it reproduces.
  Run it live only if it reproduces reliably; the recording stays the fallback.
- Do not quote remediation or rollout results until the public-corpus dry run is complete.
  Do not present internal data.
- Rerun the scan in March 2027 with the published seed, as the reviewer message promises.
- Decide whether to also submit to SunSecCon, the co-located security event with its own CFP tool;
  its CFP asks for supply-chain talks and live demos.
  Check its deadline and whether dual submission is allowed.
  Promise a live demo there only after the fork-only-commit run reproduces.
