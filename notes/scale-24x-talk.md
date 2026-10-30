# SCaLE 24x Talk Notes — "You Pinned Your GitHub Actions. What's Still Mutable?"

Working notes for a SCaLE 24x proposal and presentation.
Not part of the published documentation site.

## Venue Facts

| Item       | Value                                                                                                           |
| ---------- | --------------------------------------------------------------------------------------------------------------- |
| Conference | SCaLE 24x, Southern California Linux Expo                                                                       |
| Dates      | April 1–4, 2027, Pasadena Convention Center                                                                     |
| CFP closes | **November 1, 2026**                                                                                            |
| Reviewers  | ~40 volunteer Program Committee members                                                                         |
| Track      | Security; fallback Developers, Platform Engineering & DevEx                                                     |
| Format     | "About 45 minutes" per the CFP; plan 40 + 5 questions; deck drafted at 45                                       |
| CFP fields | Title, Short Abstract (print), Long Abstract, bio (1,000 characters), Track and Level, Message to the reviewers |
| Room       | Hands-free speaker mic, handheld audience mic, HDMI projector                                                   |

SCaLE is community-run and explicitly filters vendor and tool pitches.
The committee publicly states it wants new speakers and practitioner content.
A submission framed as "here is my CLI" gets rejected.
A submission framed as "here is a measurement nobody has published, and here is what we did about it" gets accepted.

The 45-minute slot includes setup and handoff, and the room provides a Q&A microphone.
Dropping Q&A entirely gains about five usable minutes, not ten, so the plan keeps five minutes of questions.
SunSecCon, a co-located security event with its own CFP, explicitly asks for supply-chain talks and live demos;
see task 28.

Venue facts were checked against the [SCaLE 24x CFP](https://www.socallinuxexpo.org/scale/24x/cfp) on 2026-10-26.

## The One-Sentence Thesis

Pinning advice focuses on `uses:`, yet a workflow executes code from at least six kinds of mutable reference;
most repositories do not pin even `uses:`, one in seven of those that do still carry other mutable references,
and a pinned SHA does not prove which repository it came from.

Three rounds of evidence produced this framing.
The pilot scan ruled out the original "pinning is deeply incomplete" thesis (see [Pilot Results](#pilot-results)).
A primary-source review then ruled out the provenance-only thesis that briefly replaced it
(see [Primary-Source Review](#primary-source-review)).
The lockfile-centered framing that followed was dropped on 2026-10-23: lockfiles are in public preview,
most of the audience cannot adopt them, and a title built on a preview feature expires if the feature changes.
Lockfiles remain in the talk as one control among several, not as the premise.

## Why This Talk Is Novel

Three claims, in descending order of strength.

1. **The pinning surface is wider than the advice, and the gap is unmeasured.**
   Guidance and most tools target `uses:`.
   `container.image`, `services[*].image`, `docker://` steps, cross-repo `with.ref`, pre-commit revisions,
   and `runs-on:` are also mutable, and GitHub's preview lockfile does not cover them either.
   The corpus measurement is the only published number for both the pin rate and what is left after pinning,
   and it holds regardless of which platform features ship.
2. **Provenance is not pinning, and the distinction is demonstrable on stage.**
   GitHub serves fork commits from the upstream repository's API namespace,
   so `actions/checkout@<sha-that-only-exists-in-my-fork>` resolves, runs, and reads as legitimate in review.
   Still a great demo.
   But see the novelty caveat in [Primary-Source Review](#primary-source-review): GitHub documents the behavior,
   warns about it in one line, and is now shipping the fix.
   Present this as *motivation for why the lockfile exists*, not as an unknown.
   Credit Chainguard's 2023 imposter-commit research and `zizmor`'s `impostor-commit` audit by name;
   the proposal's reviewer message already does (see [Citations](#citations)).
3. **A public-corpus remediation dry run, including the failures, if task 17 is completed.**
   Credibility payload, not the thesis; do not use internal rollout data.

## Title Candidates

Ranked.
Prefer plain language over puns; SCaLE abstracts are scanned quickly.

1. **You Pinned Your GitHub Actions.
   What's Still Mutable?**
   The CFP form has no subtitle field; "a 50,000-repository sample" lives in the short abstract instead.
2. Every Mutable Reference in Your CI Workflow, Measured
3. A SHA Is Not a Promise: Immutable References in CI Workflows
4. You Pinned Your GitHub Actions.
   You're Still Not Pinned.
5. Lockfiles Fixed Half Your Workflow.
   Here's the Other Half.

Candidate 1 names the measured platform and asks the question the cold open answers.
It does not imply that all pinned repositories have remaining mutable references (the scan finds about one in seven).
Candidate 4 makes that claim too broadly; candidate 5 depends on a preview feature and is retained only for the record.
Keep all of them listed so the reasoning is not relitigated.

## Draft Abstract (submittable)

The submittable text lives in [`scale-24x-proposal.md`](scale-24x-proposal.md); edit it there.

Figures come from the 2026-10-21 full run over 49,984 repositories; see [Full-Run Results](#full-run-results).
The abstract does not claim the answer is "uncomfortable," and it does not claim the fork-network behavior is unknown.
Both claims were checked and neither survived.

Revised 2026-10-23 to drop the lockfile premise:

- Led with the general advice and the 87.8% pin-rate gap instead of the lockfile.
- Named lockfiles once, as a preview feature, among the available controls.
  Omitting them reads as ignorance to reviewers with current docs open.
- Kept the measurement scoped to GitHub Actions; other platforms appear only in Q&A,
  from documentation and source review.

Revised 2026-10-26 to show scope beyond GitHub without renaming the talk:

- Added one abstract sentence: the same gaps apply to any CI system that pulls images, repositories,
  or hooks by tag or branch.
- Added one Part 1 slide, "Not a GitHub problem", that maps the three measured gaps to GitLab CI, CircleCI, Jenkins,
  Tekton, Drone, and Bitbucket from vendor documentation
  (see [Cross-platform review](#cross-platform-review)).
- Kept impostor commits beyond GitHub as a backup slide and Q&A answer; that material is source review, not tested.
- Added "other CI systems are covered from vendor documentation, not measured" to the proposal's known limits.

Revised 2026-10-26 for a longer session (40 minutes of content plus 5 of questions, drafted at 45):

- Added a short abstract for the CFP's print field and the job-container finding to the long abstract.
- Part 1 gained a computed "What actually floats" slide and two configuration slides for GitLab CI, Jenkins,
  and CircleCI.
- Part 2 gained a "Check it by hand" slide and moved "Impostor commits beyond GitHub" from backup into the deck.
- Part 3 gained a Renovate and Dependabot configuration slide.
- The close gained a "Questions you were about to ask" slide.

Revised 2026-10-20 for `ratchet`, which pins `docker://`, `container.image`, and `services[*].image` on GitHub Actions
(see [`docs/explanation/comparison.md`](../docs/explanation/comparison.md)):

- Dropped "the part nobody is talking about"; `ratchet` and Updatecli already address the image rows.
- Named `ratchet` in the abstract.
  A reviewer who knows it reads the omission as ignorance; naming it reads as a survey.
- Moved the novelty claim from "no tool covers this" to "nobody has measured what is left".
  The measurement survives any tool's existence; the coverage claim did not.
- Replaced "the popular pinning tools write it without complaint" with "most pinning tools I reviewed do not check
  whether that SHA came from the named repository".
  `zizmor` flags impostor commits after the fact, so "popular tools" was false as a blanket claim.
  The qualified claim rests on source review of `ratchet`, `pinact`, Updatecli, and `pin-github-action`;
  task 7 must still be completed before presenting any empirical tool comparison or demo.

Revised 2026-10-29 after a mock CFP review:

- Rewrote the short abstract around the scan's denominators and opened the long abstract with a scenario.
- Added the `tj-actions/changed-files` compromise (CVE-2025-30066), verified against GHSA-mrrh-fwg8-r2c3.
- Added a prior-work paragraph to the reviewer message: GitHub's documentation, Chainguard (2023),
  and `zizmor`'s `impostor-commit` audit.
- Added the 149,570-repository frame, the 592/4,008 and 203/358 counts, and a March 2027 re-scan commitment.
- Disclosed that pre-commit revisions count only when CI runs pre-commit,
  that cross-repository checkout refs count whether or not the job executes them,
  and that transitive references make every figure an undercount.
- Narrowed the cross-CI claim to "the same patterns apply" and cut it to one slide.
- Moved the tool-coverage table from Part 1 to Part 3 and named every compared tool.
- Replaced the conditional demo wording with one committed demo and a recorded fallback.
- Moved every note-to-self and the employer-clearance line into the proposal's Submission Checks.

Revised again 2026-10-29 for the deadline:

- Changed "Demonstrate" to "Walk through" in the 17–27 minute segment.
  The recording is the plan, not the fallback, so the proposal needs no internet and task 6 no longer blocks submission.
- Dropped The Walt Disney Studios from the bio; added DevOpsDays LA and SoCal Code Camp to the speaking record.
- Sourced the `tj-actions/changed-files` incident to StepSecurity, CISA, and the upstream issue.
  Dropped the "SHA-pinned consumers were unaffected" claim:
  issue #2463 reports SHA pins updated to the malicious commit.
- Replaced the abstract's `tj-actions` sentence with the March 2026 Trivy compromise (CVE-2026-33634):
  it is newer and exercises three of the talk's claims at once — action tags, image tags vs. digests,
  and a transitive tag inside a SHA-pinned action.
  `tj-actions` and `reviewdog` (CVE-2025-30154) stay in the deck on Part 0's timeline slide.
- Reordered `scale-24x-slides.py` to this outline
  (task 32):
  the coverage table moved to Part 3, and the GitLab CI and Jenkins/CircleCI configuration slides moved to backup.
  Speaker-note timestamps now follow the 40-minute plan.
- Wired the incidents into the deck: the Trivy transitive tag on the transitive-references slide,
  the `tj-actions` Renovate lesson on the cost slide, and advisories on the resources slide.
- Added the Chainguard and `zizmor` prior-work credit to Part 2's first slide, as the proposal promises.
- Renamed the Part 2 demo slide to a walk-through and made the recording the primary path.

## Outline — 40 minutes plus 5 of questions

Timings match the proposal's session plan as of 2026-10-29: 7, 10, 10, 9, and 4 minutes, then 5 of questions.
The slide draft follows this order since 2026-10-29 (task 32) but still runs about 45 minutes; cut it to 40 (task 23).

### 0:00–0:03 — Cold open, no title slide

Show a workflow file that is 100% SHA-pinned.
Ask the room: "This repository follows every piece of pinning advice ever written.
How many mutable references are still in it?"

Reveal: four.
`services.redis.image: redis:7`, `container.image: python:3.14-slim`, `with.ref: main`, and a pre-commit `rev:`.

Then the second question, which is the one the talk is actually about: "Now look at the SHAs you *did* pin.
How do you know those commits came from the repositories they name?"

Do not say the tool name yet.

### 0:03–0:07 — The advice, the compliance gap, and why I measured it

Title slide, fifteen seconds; save the motivation until after the 87.8% figure.

One slide on tag mutability.
One timeline slide on the tag-hijacking incident class, three rows, one lesson each:

| Date                 | Incident                                     | Lesson for this talk                                  |
| -------------------- | -------------------------------------------- | ----------------------------------------------------- |
| 2025-03-11           | `reviewdog/action-setup@v1` (CVE-2025-30154) | Embedded tags bypass your own pins                    |
| 2025-03-14 to 15     | `tj-actions/changed-files` (CVE-2025-30066)  | A SHA pin helps only if the update chose a good SHA   |
| 2026-03-19 and 03-22 | Trivy (CVE-2026-33634)                       | Action tags, image tags, and a transitive tag at once |

Row 1, `reviewdog`:

> **Verified 2026-10-29** against the [CVE-2025-30154 record][cve-reviewdog], [Wiz][wiz-reviewdog],
> [Hunters][hunters], and [CISA][cisa]:
> `reviewdog/action-setup@v1` was compromised on 2025-03-11 from 18:42 to 20:31 UTC and dumped secrets to workflow logs.
> The CVE lists `action-shellcheck`, `action-composite-template`, `action-staticcheck`, `action-ast-grep`,
> and `action-typos` as affected "regardless of version or pinning method", because they embed `action-setup@v1`.
> Say "Wiz suspects" a link to the `tj-actions` compromise; do not state it as established.

Row 2, `tj-actions/changed-files`:

> **Verified 2026-10-29** against [StepSecurity][stepsec], [CISA][cisa], [tj-actions/changed-files#2463][tj-2463],
> and [GHSA-mrrh-fwg8-r2c3][ghsa]: CVE-2025-30066, the March 14–15, 2025 window,
> version tags retroactively repointed to malicious commit `0e58ed8671d6b60d0890c21b07f8835ace038e67`,
> and CI secrets printed to workflow logs.
> Do not say SHA-pinned consumers were unaffected.
> Issue #2463 reports repositories that ran the malicious commit by SHA after an automated Renovate update.
> Say instead: a pin to a known-good SHA resists later tag movement;
> it does not help if the update that wrote the pin selected the malicious SHA.
> That second half sets up Part 3's cooldown and review-cost slides.

Row 3, Trivy:

> **Verified 2026-10-29** against [GHSA-69fq-xp46-6x23][ghsa-trivy], [Aqua's disclosure][aqua-trivy],
> and [StepSecurity][stepsec-trivy]: on 2026-03-19, 76 of 77 `trivy-action` tags and all seven `setup-trivy` tags
> were replaced and Trivy v0.69.4 was released with malicious code; on 2026-03-22, Docker Hub images v0.69.5 and
> v0.69.6 were compromised.
> Safe versions: `trivy-action@0.35.0` and `setup-trivy@0.2.6`.
> Images referenced by digest were unaffected.
> SHA pins to `trivy-action` commits from after 2025-04-09 were unaffected;
> older pinned commits still fetched `setup-trivy` by tag and ran the compromised version.
> Do not say "SHA-pinned users were safe"; say which SHAs.
> StepSecurity's write-up is independent reporting; Aqua's discussion and the GHSA are the vendor's disclosure.
> Re-check the GHSA before each use; it was still being revised in 2026.

Land the point in 30 seconds: tags are pointers, pointers move, SHAs do not.
The timeline slide gets 60 seconds total; read one lesson per row, not the incident details.
Trivy's transitive-tag row foreshadows Part 1's undercount, so say "we will come back to this."
The room already agrees.
Do not belabor it.

One extra beat earned by the full-run data:
**87.8% of public repositories that use third-party actions do not pin all of them to a commit SHA.**
The advice is near-universal and compliance is not.
Scope the claim on the slide: active, non-archived, non-fork repositories above 100 stars, with at least one non-local,
non-expression `uses:` (28,855 of 32,863; 95% CI 87.4%–88.2%).

Bridge: "Most of you have not done step one.
This talk is about what remains after step one."

Then the motivation slide, forty-five seconds: the job was to pin every action reference across many repositories;
the tools the speaker knew, `actionlint` and `zizmor`, validate and detect;
writing a bulk fixer anyway meant listing every place a workflow pulls code by name,
and that list was longer than the advice.
Credit `ratchet` and `pinact` by name, and do not name `pinref` on this slide.
Date the story: `zizmor` now ships an unsafe-tier `--fix=all` for `unpinned-uses`,
so "the tools I knew" must carry a month and year: August 2026, the date of `pinref`'s public first commit.
There is no employer clearance, so omit the employer, the repository count, and the trigger (task 20).
This slide now leads directly into Part 1's inventory; do not return to the lockfile until Part 3.

### 0:07–0:17 — Part 1: The surface no lockfile covers

Target ten minutes: the reference inventory, transitive references, the measurement, what floats,
and one cross-CI slide.

Open with the coverage boundary: the usual advice targets `uses:` and reusable workflow refs.
Introduce the preview lockfile later, as one of Part 3's platform controls.

Then the seven mutable reference types on one slide, 45 seconds total, with a one-line "what an attacker gets" for each.

| Reference                         | What an attacker who controls it gets                                  |
| --------------------------------- | ---------------------------------------------------------------------- |
| `uses:` action ref                | Arbitrary code in the job, with the job's token                        |
| Reusable workflow ref             | Arbitrary jobs, plus whatever secrets are inherited                    |
| `with.ref` on cross-repo checkout | Arbitrary source on disk, usually then built or executed               |
| `docker://` step image            | Arbitrary code in the job                                              |
| `container.image`                 | Control of the environment every step in the job runs inside           |
| `services[*].image`               | Network-reachable service the job trusts, on the job's network         |
| Pre-commit hook `rev:`            | Arbitrary code wherever the hook runs, CI included                     |

Then one slide on transitive references, another answer to the title's question:
a composite action pinned by SHA that calls `other/helper@v2` inside,
and a Docker action pinned by SHA whose `Dockerfile` starts `FROM node:20`.
Briefly note that a lockfile covers the first; defer the platform-control explanation to Part 3.
Nothing in the consuming repository covers the second.
The scan counts neither, so say that every figure that follows is an undercount.

Then the data slide.
This is the centerpiece:

> Of 4,008 repositories where every `uses:` is already pinned to a commit SHA,
> **one in seven** (14.8%) still reference at least one mutable container image, cross-repo checkout ref,
> or pre-commit revision —
> reference types the usual advice does not mention.

Break it down on the same slide: 8.9% have a mutable container image (`X`)
and 2.8% have an unpinned cross-repo `with.ref` (`Y`).
Report the pre-commit share separately because it has its own denominator.

Then "What actually floats", 90 seconds, computed from `corpus/images-full.csv`
(see [Image breakdown](#image-breakdown)).
Of the 358 repositories with a mutable image, 203 have a mutable job container, 160 a mutable service image,
and 18 a mutable `docker://` step.
Lead with that: the residual is not only test databases.
Show the tag shapes and the most common images; `postgres` leads at 100 repositories.

Say the inverse out loud before anyone else does: about 85% of pinned repositories show none of these three.
Do not call them clean; the scanner has known undercounts (see the methodology notes).
The finding is that a residual surface exists at all, that no guide tells you to look for it,
and that even the platform's preview fix does not reach it.
Volunteering the deflating reading is what makes the rest of the numbers trustworthy.

The tool-coverage table moved to Part 3 on 2026-10-29; Part 1 stays on the measurement.

Close Part 1 with one slide, about one minute: "Not a GitHub problem".
The proposal promises one slide, so keep it in the main deck.
It maps container images, cross-repository refs, and pre-commit revisions to GitLab CI, CircleCI, Jenkins, Tekton,
Drone, and Bitbucket, and ends on the CircleCI orb executor that defaults to a mutable image tag.
Label it as vendor documentation, not measurement.

Move the two configuration slides to backup for Q&A: a GitLab CI file with a tagged job image, a tagged service,
`include:project` at `ref: main`, and a component at `@~latest`;
and a Jenkins `@Library('...@master')` with a Docker agent image,
beside CircleCI orbs at a major version and `@volatile` with a tagged executor image.
The Jenkins and CircleCI syntax and quotes were verified against vendor documentation on 2026-10-26.

### 0:17–0:27 — Part 2: A SHA is not a promise (recorded walk-through)

Target ten minutes: the walk-through, the review-diff beat, a hand check, and impostor exposure beyond GitHub.
The proposal says "Walk through", so present Part 2 from a recording; a live run is optional, not promised.
Task 6 produces the recording; it no longer blocks submission.
If task 12 reproduces, record the pre-commit `rev:` variant instead of an action: pre-commit fetches by SHA,
is one of Part 1's measured surfaces, and lies outside every lockfile,
so one walk-through carries both halves of the thesis.
The action-based sequence below is the fallback.

The emotional center of the talk, and — after the primary-source review —
the *explanation* for the lockfile rather than a scoop.
Frame it that way in the first sentence: "Here is concretely why GitHub put a run-time identity check in that lockfile."

1. Slide: GitHub's fork network stores all fork commits in one object store,
   and the API serves them under the upstream path.
   Credit prior work on the same slide: GitHub's *About forks* page, Chainguard's "What the fork?" post (2023-03-08),
   and `zizmor`'s `impostor-commit` audit.
   Add Truffle Security's FOR research only after task 31 verifies it.
2. Demo step 1: fork a well-known action, push a commit that writes a marker to the job log.
3. Demo step 2: `curl` the **upstream** repository's commits API with that SHA.
   It returns 200.
4. Demo step 3: put `actions/<action>@<fork-sha>` in a workflow.
   It runs.
   Show the marker in the log.
5. Demo step 4: run the pinning tools tested in task 7 against it.
   Show each tool's observed behavior; do not claim they all accept the impostor SHA before testing.
6. Demo step 5: `pinref --provenance strict`.
   It refuses.
   Show the error.
7. Slide: what verification actually means here — a branch head, a tag,
   or the head or merge commit of a *merged* PR on the named repository.
   Open PRs do not count; anyone can open one.
   **Say the limitation out loud:** this is best-effort reachability, not cryptographic attestation.
   Immutable releases now attach a release attestation binding a tag to a commit SHA;
   whether consumers can use it to verify an action pin is open (task 22).
   Until then, do not say attestations are "not yet available for this."
8. Close on the limitation: a workflow dependency lockfile checks action origin at run time,
   but it does not cover pre-commit revisions or cross-repository checkout refs.
   Audit and verify those separately; `pinref` does support provenance checks for GitHub-hosted pre-commit hooks.
   This ties the demo back to the measured surface, not to one preview control.

With the extra time this segment gains over the original plan, add:

- A review-realism beat: show the impostor pin inside a realistic pull request diff
  and ask the room what they would have caught.
  Nobody catches it; that is the point.
- The one-line GitHub warning on screen — "verify it is from the action's repository and not a repository fork" —
  followed by "and here is every tool that checks that for you."
  Quoting the vendor's own doc is stronger than claiming nobody said it.
- A "Check it by hand" slide after the review diff, 90 seconds.
  `git ls-remote` compares the pinned SHA with the tag in its version comment;
  `tag --contains` in a bare upstream clone fails for a fork-only commit.
  Both were tested against `actions/checkout` v7.0.1 on 2026-10-26.
  The warning against `--filter` (a partial clone fetches missing objects on demand) is an inference; see task 27.
- "Impostor commits beyond GitHub" after the verification slide, one minute, promoted from backup.
  Its last bullet carries the point: the client that fetches the SHA decides exposure, not the CI platform.
- Optional 20-second aside on the verification slide:
  StepSecurity reports that the malicious Trivy v0.69.4 release workflow pinned `actions/checkout` to an impostor commit
  SHA.
  Confirm the SHA and that it was fork-only against [StepSecurity][stepsec-trivy] before using it (task 33).
- If time allows, run both demo variants: pre-commit first, then the action.

Honesty about the limitation is what separates this from a product pitch.
The committee and the audience will both reward it.

**Demo safety.**
The recording is the primary path; the proposal tells reviewers no internet is required.
Conference wifi plus live GitHub API calls plus a live Actions run is three failure modes stacked.
Run live only if it reproduced reliably in rehearsal and the network cooperates;
otherwise play the recording without apologizing.
If task 6 never reproduces end to end, present Part 2 from annotated screenshots and slides.
Use a throwaway org, a fork you control, and a workflow with `permissions: {}` and no secrets.

### 0:27–0:36 — Part 3: Controls and what they cost

Target nine minutes, two fewer than the earlier draft, with the coverage table added.
If rehearsal runs long, cut the remediation slide first; the proposal no longer promises it.

Open with one slide on the platform controls, before any tool: the organization or enterprise SHA-pinning policy
(GitHub changelog, 2025-08-15),
immutable releases (a publisher control that consumers cannot require,
and that leaves floating tags such as `v4` movable), and the preview lockfile.
Explain that the lockfile verifies source-repository identity and covers transitive action dependencies,
but not image bases, pre-commit revisions, or cross-repository checkout refs.
Recommend all three where available, then show that none of them reaches the residual surface.
Re-verify the lockfile's preview status and coverage before the conference.

Then the tool-coverage table, moved from Part 1 on 2026-10-29.
Show which reference types `ratchet`, `pinact`, Updatecli, `pin-github-action`, `zizmor`, and `pinref` pin or detect,
**with a lockfile column**; the proposal names all six.
Present it neutrally and include `pinref` in the same table as everyone else.
`ratchet` is near-complete on GitHub Actions; show that honestly.
Settle the `zizmor` image cells first (task 21).

If task 17 is done, use a public-corpus dry run to show how many files and refs change, what fails, and the review cost.
Show representative, reproducible examples of parse failures, unresolvable refs,
version comments that preserve reviewability, and the tradeoff between a release cooldown and staleness.
Give image staleness its own slide: a digest pin stops receiving the publisher's security patches,
so pair it with automated digest updates and state the patch latency the cooldown adds.
Follow it with a "Keep pins current" slide showing a Renovate and a Dependabot configuration side by side.
Verified against vendor documentation on 2026-10-26: Renovate's `github-actions` manager updates `container:`,
`services:`, and `docker://` images, and its pre-commit manager is off by default.
Dependabot updates SHA-pinned actions and their version comments, and supports pre-commit and `cooldown`,
but does not update workflow `container:`, `services:`, or `docker://` images.
Validate both configurations in a scratch repository before the talk (task 26).
Do not claim a fleet rollout or its observed failure rates on the basis of this dry run.
If task 17 slips, cut the remediation-results slide; keep platform controls, image staleness, and the audit.
Give the recovered time to the review-diff beat in Part 2.

Internal campaign data is out of scope: there is no employer clearance, so do not use it in any form.
The public-corpus version of this talk needs no internal data.

### 0:36–0:40 — Close

The checklist slide, which is what people photograph:

1. Pin every `uses:` to a commit SHA with a version comment, enforce it with the SHA-pinning policy,
   or adopt a lockfile once it is available to you.
2. Verify any new SHA is reachable on the repository it claims to come from.
3. Grep your workflows for `image:` — not just `uses:` — and pin images to `sha256:` digests.
4. Grep for `ref:` under `with:`.
5. Check `.pre-commit-config.yaml` revisions.
6. Refuse releases younger than your cooldown window.
7. Run a detector and a fixer; they are different jobs.

Before the checklist, call back to the opening: "I started with detectors, but I needed a fixer."
Precede the checklist with a 60-second audit slide: four `rg` one-liners for `uses:`, images, `with.ref`,
and pre-commit `rev:`, then `zizmor` with a token for its online audits.
The commands were tested against a fixture on 2026-10-25; re-run them before the talk.

Follow the checklist with "Questions you were about to ask", 90 seconds: `ratchet`, Dependabot, lockfiles,
test databases, SHA-1, and stale digests, each with a one-line answer.
It covers objections that a five-minute Q&A cannot; it is the first slide to cut if the draft runs long.

Tool slide last, 20 seconds, one URL.

### 0:40–0:45 — Questions

Five minutes on the handheld audience mic.
Answers are in [Q&A Preparation](#qa-preparation); the backup slides cover GitLab CI, Jenkins, and CircleCI.

## Pre-CFP Work — the critical path

Ordered by what blocks the abstract.
Reprioritized after the full scan and the 2026-10-23 reframing: lockfiles are no longer the premise,
so task 5 is talk preparation, not an abstract blocker.
The impostor demo and empirical tool comparison are talk-preparation work too.
Since 2026-10-29 the proposal promises a recorded walk-through, so task 6 no longer blocks submission.
The full scan finished on 2026-10-21.

| #   | Task                                                                                            | Blocks       | Status                                                                                                                             |
| --- | ----------------------------------------------------------------------------------------------- | ------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Build the corpus scanner; sample public repos with workflow files                               | Abstract `N` | **Done** — `notes/corpus_scanner/`                                                                                                 |
| 2   | Run the pilot; decide the framing from the measured rates                                       | Thesis       | **Done** — see [Pilot Results](#pilot-results)                                                                                     |
| 3   | Fact-check the fork-network and pinning claims against GitHub's documentation                   | Thesis       | **Done** — see [Primary-Source Review](#primary-source-review)                                                                     |
| 4   | Run the full 50,000-repository scan; publish the artifacts                                      | Abstract `N` | **Scan done** — see [Full-Run Results](#full-run-results); publish data, code, seed, and instructions with the talk and slides     |
| 5   | Test `gh actions-lock` here and verify uncovered refs on a disposable branch or test repo       | Part 0 slide | Todo — installed `gh` (2.102.0) does not have `actions-lock`; no longer blocks the abstract                                        |
| 6   | Reproduce the fork/impostor demo end-to-end in a throwaway org                                  | Part 2       | Todo — record the walk-through once it reproduces; no longer blocks submission                                                     |
| 7   | Confirm each competing tool's behavior against the impostor SHA, empirically, not from docs     | Part 2       | Todo                                                                                                                               |
| 8   | Decide whether to widen the frame for `Z` or drop `Z`                                           | Part 1       | **Done** — use `Z` only as supporting evidence (163/204, 79.9%); do not widen the frame for the proposal                           |
| 9   | Fact-check the incident timeline and CVE against primary sources                                | Part 0       | **Done** 2026-10-29 — `tj-actions`, `reviewdog`, and Trivy checked against CVE, GHSA, and vendor sources                           |
| 10  | Secure clearance to present anonymized fleet data                                               | Part 3       | Dropped 2026-10-25 — no employer clearance; use the public-corpus dry run only                                                     |
| 11  | Write and submit the abstract                                                                   | Nov 1        | Text final 2026-10-29 in `scale-24x-proposal.md`; submit after the P0 checks                                                       |
| 12  | Reproduce a pre-commit impostor `rev:` end to end on repositories you own                       | Part 2 demo  | Todo — preferred demo: ties Part 1's measured surface to Part 2's provenance gap                                                   |
| 13  | Fix `verify_provenance` to reject open-PR-only SHAs; add a regression test                      | Part 2 demo  | **Done** — merged PR head or merge commit only                                                                                     |
| 14  | Empirically test GitLab paths A and B (API, `git fetch`, `include:project`, component @SHA)     | Q&A          | Partly answered from source; end-to-end plan in [`impostor-e2e-tests.md`](impostor-e2e-tests.md)                                   |
| 15  | Split `X` into official and other images, and `Y` into same-owner and other-owner repos         | Part 1       | `X` partly done 2026-10-26 via `images-full.csv`; split `Y` by owner and by whether the job executes the checkout                  |
| 16  | Find a primary-source incident per reference type, or state that none is known                  | Part 1       | Partly done 2026-10-29 — action tags, image tags, transitive tags sourced; checkout `ref:` and pre-commit `rev:` open              |
| 17  | Run the public-corpus remediation dry run                                                       | Part 3       | Todo — abstract no longer promises results; quote none until done                                                                  |
| 18  | Package the scanner so attendees can audit their own repositories                               | Close        | Todo                                                                                                                               |
| 19  | Review the speaker bio and confirm SCaLE 24x CFP fields, word limits, and track names           | Nov 1        | CFP fields, tracks, and the 1,000-character bio limit confirmed 2026-10-26; confirm the bio's claims and the Level options         |
| 20  | Supply motivation facts: month and year, trigger, rounded fleet size, and clearance to say them | Nov 1        | Done 2026-10-25 — no clearance; date from the public first commit, no employer, count, or trigger                                  |
| 21  | Verify `zizmor` coverage cells for `docker://` and service images against its audit docs        | Part 3       | Docs re-read 2026-10-29: `unpinned-images` covers `container.image` only; test service and `docker://` cells                       |
| 22  | Decide whether immutable-release attestations can verify an action pin                          | Part 2       | Todo — governs the "not cryptographic attestation" wording on the verification slide                                               |
| 23  | Time a full rehearsal of the 45-minute draft; cut to 40 minutes using the Cut List              | Talk         | Todo — outline budgets 40 minutes plus 5 of questions since 2026-10-29; the deck still runs about 45                               |
| 24  | Verify the cold-open SHAs match their version comments                                          | Part 0       | **Done** 2026-10-25 — `actions/checkout` v7.0.1 and `astral-sh/setup-uv` v10.0.1 tags resolve to the SHAs shown                    |
| 25  | Verify GitHub's SHA-pinning policy and immutable releases against primary sources               | Part 3       | **Done** 2026-10-25 — changelog 2025-08-15 and the *Immutable releases* docs page; re-check in March 2027                          |
| 26  | Validate the Renovate and Dependabot configurations on the "Keep pins current" slide            | Part 3       | Todo — options verified in vendor docs 2026-10-26; confirm the `pre-commit` ecosystem key and `:enablePreCommit` in a scratch repo |
| 27  | Confirm that a `--filter` partial clone fetches a fork-only commit on demand                    | Part 2       | Todo — inference from partial-clone behavior; test with the task 6 commit, or drop the warning from the hand-check slide           |
| 28  | Decide whether to also submit to SunSecCon                                                      | Nov 1        | Todo — separate CFP tool; check its deadline and dual-submission policy                                                            |
| 29  | Rerun the scan in March 2027 and update every figure in the deck and abstract                   | Talk         | Todo — promised in the reviewer message; choose the method first (see Open Questions)                                              |
| 30  | Confirm that naming The Walt Disney Studios, a former employer, is acceptable in the CFP bio    | Nov 1        | **Done** 2026-10-29 — omitted from the bio; the community speaking record fits better                                              |
| 31  | Read Truffle Security's 2024 Cross Fork Object Reference (FOR) post at the source               | Part 2       | Todo — page unreachable 2026-10-29; cite it only after reading it, or drop it                                                      |
| 32  | Reorder `scale-24x-slides.py` to match the 2026-10-29 outline                                   | Talk         | **Done** 2026-10-29 — coverage table in Part 3; GitLab, Jenkins, and CircleCI slides in backup                                     |
| 33  | Confirm the impostor `actions/checkout` SHA in the malicious Trivy v0.69.4 release workflow     | Part 2       | Todo — optional Part 2 aside; verify the SHA is fork-only before citing StepSecurity's claim                                       |

The scan half of task 4 is done; publish its artifacts with the talk and slides in a dedicated repository.
The measurement is the thesis again, so `N` belongs in the abstract.
Use this repository's already SHA-pinned workflows for the first task 5 test,
then use a disposable branch or test repository with container images, cross-repository `with.ref`,
and pre-commit revisions to check exclusions.
The current `gh` installation does not recognize `actions-lock`; install or enable the feature before testing.
Complete task 5 before stating the lockfile coverage boundary as an empirically verified fact on a slide.
For task 7, retain the qualified phrase "most pinning tools I reviewed" based on source review;
do not claim empirical impostor behavior for untested tools.

Task 6 no longer blocks the thesis or the submission, and it is still the best ten minutes of the talk.
Record it once it reproduces; that recording is what Part 2 presents.
If it never reproduces, Part 2 becomes a slide-only explanation of why lockfiles verify identity,
and the talk survives — which is precisely the resilience the previous framing lacked.

### Open Work by Priority

As of 2026-10-29; the CFP closes 2026-11-01.

**P0 — before submission (November 1).**

- Task 19: confirm the bio's claims (five SCaLE talks, DevOpsDays LA talk and chair role, two Code Camp talks),
  plus the Level options and any short-abstract limit (see [Open Questions](#open-questions)).
- Confirm whether the employer's outside-activity policy requires approval to speak at all, independent of content.
- Re-check the lockfile's preview status and coverage against GitHub's documentation.
- Re-check the abstract's Trivy figures against GHSA-69fq-xp46-6x23; the advisory was revised after disclosure.
- Task 28: decide on a SunSecCon submission.
- Task 11: paste the proposal into the CFP form, following its Submission Checks, and submit.

**P1 — before the slides are final (target February 2027).**

- Task 23: time a rehearsal and cut to 40 minutes using the Cut List.
- Task 6: reproduce the impostor walk-through and record it; decide on a live run only after it reproduces reliably.
- Tasks 7 and 12: test each tool against the impostor SHA, and try the pre-commit variant of the demo.
  Until then, the demo, review-diff, and provenance-table slides keep their warning callouts.
- Task 31: verify the Truffle Security FOR post, or leave it off the prior-work slide.
- Task 17: run the public-corpus dry run, or cut the remediation slide and extend the Part 2 review-diff beat.
- Task 4: publish the scanner, inputs, seed, and raw counts; fill the resources-slide URL.
- Task 5: test `gh actions-lock` before calling the lockfile boundary empirically verified.
- Tasks 21 and 22: settle the `zizmor` coverage cells and the attestation wording.
- Tasks 26 and 27: validate the update configurations and the partial-clone warning.

**March 2027 — before the conference.**

- Task 29: rerun the scan and update every figure; the proposal's reviewer message promises it.
- Re-verify the lockfile, the SHA-pinning policy, immutable releases, fork-network API behavior,
  the cross-CI slides, and the Renovate and Dependabot options.

**P2 — strengthens the talk; safe to drop.**

- Tasks 15, 16, and 18: split `Y`, source checkout-ref and pre-commit incidents, and package the scanner.
- Task 33: confirm the Trivy impostor `actions/checkout` SHA, or drop the Part 2 aside.
- Task 14: test the GitLab paths end to end, or keep "the source says" wording.
- Add a 20-second primer slide on `uses:`, `container:`, and `services:` if rehearsal shows the room needs it.
- Measure transitive references (composite-action `uses:` and Docker action base images),
  or keep them as a disclosed undercount.

## Full-Run Results

Run 2026-10-21 over 49,984 repositories, a seeded 50,000-repository sample of the 149,570-repository frame.
The other 16 repositories no longer existed when cloned.
Full output is in [`corpus/report-full.md`](corpus/report-full.md); per-repository rows are in `corpus/corpus.csv`.
This section supersedes the pilot figures below for every slide.

| Statistic                                   | Value                | 95% CI      | Verdict                                  |
| ------------------------------------------- | -------------------- | ----------- | ---------------------------------------- |
| Fully pinned share of in-scope repositories | 12.2% (4,008/32,863) | 11.8%–12.6% | Part 0 hook: 87.8% are not fully pinned  |
| Headline residual surface                   | 14.8% (592/4,008)    | 13.7%–15.9% | Part 1 headline: "one in seven"          |
| `X` mutable container image                 | 8.9% (358/4,008)     | 8.1%–9.9%   | Keep; the largest single component       |
| `Y` unpinned cross-repo `with.ref`          | 2.8% (113/4,008)     | 2.4%–3.4%   | Keep; do not lead with it                |
| `Z` unpinned pre-commit rev in CI           | 79.9% (163/204)      | 73.9%–84.8% | Supporting observation, not the headline |

What changed from the pilot:

- **The headline moved from one in eight to one in seven.**
  13.1% (n=168) became 14.8% (n=4,008), inside the pilot's interval.
- **The pin rate held.**
  12.7% became 12.2%; "compliance is one in eight" still holds for the pin rate.
  Keep the two figures apart on the slides: one in eight in-scope repositories is fully pinned,
  and one in seven of *those* still has residual surface.
- **`Z` is now an interval, not an anecdote.** n=204 gives about ±5.5 points,
  enough to say "roughly four in five" with its denominator on the slide.
  It is still below the 1,000-repository target and covers 5.1% of `N`, so it cannot be the headline.

Corrections applied before these figures were produced:

- Eight clones from an interrupted fetch had empty working trees and were counted as having no workflows.
  They were repaired at their recorded HEAD commit SHAs and rescanned.
- `yamlrocks` 0.6.1 rejected 471 valid YAML files, mostly flow sequences with leading commas.
  The scanner now falls back to PyYAML's read-only `BaseLoader`; 35 files remain unparsable.
- The local-action count now includes the `$/` repository-root form as well as `./`.

### Image breakdown

Run 2026-10-26 with the scanner's `images` stage over the same clones;
rows are in [`corpus/images-full.csv`](corpus/images-full.csv).
It found 1,129 mutable image references in 358 repositories, matching `X` and the sum of `image_mutable` exactly.

| Where the mutable image is | Repositories (of 358) | References |
| -------------------------- | --------------------- | ---------- |
| Job container              | 203                   | 661        |
| Service container          | 160                   | 447        |
| `docker://` step           | 18                    | 21         |

| Tag shape                    | Example            | Repositories |
| ---------------------------- | ------------------ | ------------ |
| Major version                | `postgres:16`      | 135          |
| `latest`, written or implied | `ubuntu`           | 104          |
| Minor version                | `python:3.14-slim` | 93           |
| Named channel                | `node:lts`         | 78           |
| Full version                 | `nginx:1.27.3`     | 57           |

The examples illustrate each shape; they are not counts of those exact tags.
A repository can appear in several rows.
Most common images by repository: `postgres` 100, `redis` 31, `mysql` 25, `ubuntu` 18, `archlinux` 18.
`rhysd/actionlint` appears in 8 repositories as a `docker://` step, 7 of them at `latest`.

The job-container count answers the "isn't this just test databases?" objection:
more than half of the repositories with a mutable image float the environment every step runs inside.

## Pilot Results

Kept for the record; the figures in [Full-Run Results](#full-run-results) replace these on every slide.

Run 2026-10-19 over a 1,996-repository subsample of the frame;
full output in [`corpus/report-pilot.md`](corpus/report-pilot.md).

| Statistic                                   | Value            | 95% CI          | Verdict                         |
| ------------------------------------------- | ---------------- | --------------- | ------------------------------- |
| Fully pinned share of in-scope repositories | 12.7% (168/1321) | 11.0%–14.6%     | **Promote to Part 0**           |
| Headline residual surface                   | 13.1% (22/168)   | 8.8%–19.0%      | Keep; reframe as "one in eight" |
| `X` mutable container image                 | 7.1% (12/168)    | 4.1%–12.1%      | Keep                            |
| `Y` unpinned cross-repo `with.ref`          | 3.0% (5/168)     | 1.3%–6.8%       | Keep; do not lead with it       |
| `Z` unpinned pre-commit rev in CI           | 62.5% (5/8)      | **30.6%–86.3%** | **Do not put on a slide**       |

Four decisions follow from this table.

**The thesis moves to provenance.**
The original framing promised that pinning is substantially incomplete.
13.1% does not deliver that promise, and the inverse reading — 87% of fully pinned repositories are clean —
is what a hostile reviewer will compute.
This is the first entry in [Open Risks](#open-risks) firing exactly as written.
Part 1 shrinks from ten minutes to eight and becomes supporting evidence.

**`Z` is the only dramatic number and it rests on n=8.**
An interval spanning 30.6% to 86.3% says nothing.
State it as an observation about a handful of repositories, or cut it.

**`Z` cannot be rescued by the planned full run.**
Pre-commit-eligible repositories are 0.4% of those scanned, so a denominator of 1,000 needs roughly 249,500 clones —
larger than the entire 149,570-repository frame.
Scanning the whole frame yields a denominator near 600; the planned 50,000 yields about 200, or ±6.8 points.
Either lower `--min-stars` to widen the frame, or demote `Z` permanently.

**The pin rate is the better opening number.**
87.3% of active, non-archived public repositories above 100 stars are not fully pinned.
After years of universal advice, compliance is one in eight.
That is a stronger and better-supported hook than the residual-surface figure, and it costs thirty seconds in Part 0.

What the full run still fixes: at 50,000 repositories `N` lands near 4,200,
putting the headline interval inside roughly ±1.0 points and making `X` and `Y` publishable without hedging.

## Primary-Source Review

Checked 2026-10-20 against GitHub's documentation, after the pilot pivot put provenance at the center.
The pivot did not survive the check.

**Finding 1 — GitHub documents the fork-network behavior.**

> Commits pushed to any repository in a network can be accessible from other repositories in that network,
> including the upstream repository.
> — [About forks](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/about-forks)

**Finding 2 — GitHub's hardening reference already warns about the attack, in one line.**

> When selecting a SHA, you should verify it is from the action's repository and not a repository fork.
> — [Secure use reference](https://docs.github.com/en/actions/reference/security/secure-use)

This sits in the canonical page people are sent to.
The talk cannot claim "nobody tells you."
The defensible claim is narrower and still true: the warning is one sentence,
it tells you to verify without telling you how, and no mainstream pinning tool checked it.

**Finding 3 — the decisive one.
GitHub shipped the fix.**

[Workflow dependency lockfiles](https://docs.github.com/en/actions/concepts/security/workflow-dependency-lockfiles)
(public preview)
place a `.github/workflows/actions.lock` in the repository recording, per action dependency, the requested `ref`,
the resolved `commit`, and the `owner_id`/`repo_id` numeric identity of the source repository.
GitHub verifies that identity at run time and requires
that "this commit must exist within a branch of the source repository."

That is the `--provenance strict` reachability check, enforced by the platform.
GitHub further states that for repositories adopting a lockfile,
SHA pinning in workflow files is "no longer necessary" and the lockfile "supersedes SHA pinning."

### Consequences

**Do not build the talk on provenance.**
By April 2027 the feature may be generally available.
A 45-minute talk whose thesis is "here is a gap GitHub closed eighteen months ago" is a bad talk,
and the committee reads submissions with current docs open.

**The pilot measurement is the durable asset after all.**
Lockfiles cover action and reusable-workflow references.
They do not cover container images, cross-repo `with.ref`, pre-commit revisions, or `runs-on:`,
and they do not cover the dependencies of reusable workflows defined elsewhere.
Every reference type in the 14.8% is outside the lockfile's scope.
The measurement's relevance *increases* as lockfiles roll out,
because the lockfile removes the `uses:` column and leaves the residual surface as the whole remaining problem.

**The demo survives, with a changed job.**
It stops being "here is a secret nobody knows"
and becomes "here is concretely why GitHub built run-time identity verification into the lockfile,
and here is what you are exposed to until you adopt one."
That is honest, it is still a strong live moment,
and it positions the speaker as current rather than as someone who missed a platform release.

**This also matters beyond the CFP.**
`pinref` competes with a first-party feature on `uses:` pinning and provenance,
and should compete on the surface the lockfile does not cover.
Captured in [`docs/explanation/threat-model.md` §4.1 and §6.1](../docs/explanation/threat-model.md).

**Process note.**
Two consecutive thesis pivots were proposed before anyone read the primary sources.
Fact-check against primary sources (tasks 3, 9, and 16) *before* the next framing decision, not after.

### Cross-platform review

Checked 2026-10-20 against vendor documentation for GitLab CI, CircleCI, Azure Pipelines, Jenkins, Buildkite, Tekton,
Drone, Docker Hub, Amazon ECR, and GHCR.
Full write-up, written for a general audience, in
[`docs/explanation/mutable-references-across-platforms.md`](../docs/explanation/mutable-references-across-platforms.md).

**The thesis generalizes, and narrows.**
Every platform has mutable config-layer references.
CircleCI registry orbs are the one platform that solved the config layer by construction:
published versions are immutable and orb-to-orb dependencies are flattened at publish time.
GitHub's lockfile puts it second.
GitLab, Azure, Jenkins, Buildkite, Tekton, and Drone have guidance or optional controls only.

**The image layer is the industry-wide gap.**
Tags are mutable pointers under the OCI Distribution Spec on every registry.
Docker Hub (beta, opt-in) and ECR (per-repository) offer tag immutability,
but it is a *publisher* control a consumer cannot observe or require.
Digest pinning is the only consumer-side control on any registry.
CircleCI's own orb docs define an executor as `cimg/ruby:<< parameters.tag >>` defaulting to `'2.7'`:
an immutable orb running a mutable image.
That is the strongest single slide for "the other half" — the platform that solved the config layer still leaks `X`.

**Impostor commits have two paths, not one.**

- *Path A, shared fork storage:* verified on GitHub only.
  GitLab's object pools are seeded from the upstream project only, so fork-only commits stay in the fork
  (inference from GitLab's docs; a GitLab staff remark in issue #600030 conflicts and is unresolved).
- *Path B, pull/merge request refs:* opening a PR or MR copies the contributor's commit into `refs/pull/N/head`
  or `refs/merge-requests/N/head` in the target repository.
  No maintainer action required.
  Verified for GitLab via Git (MR head refs persist 14 days after close); GitHub documents the same.

Consumer exposure depends on whether the client fetches the exact SHA. pre-commit
(`git fetch origin <rev> --depth=1`),
pip `git+https`, and the Tekton `git` resolver fetch by SHA: exposed to path A on GitHub
(inference from source, high confidence).
Buildkite plugins and Jenkins shared libraries (default settings) clone branches and tags first: not exposed.
Go modules refuse by design.

**pre-commit is the talk-relevant finding.**
It fetches `rev:` by SHA, it is outside every lockfile, and it is already one of the three measured surfaces.
A pre-commit impostor demo would tie Part 1 and Part 2 together.
Not yet reproduced; see task 12.

**Bitbucket Cloud** restricts new forks to the parent workspace from July 1, 2026; storage sharing is undocumented.

### Impostor-commit follow-up (2026-10-20)

Checked against vendor source code and issue trackers; every claim below was re-read at the primary source.
None has been tested end to end.

**GitLab `include:project` and components: exposed to path B, and possibly permanently.**
Both resolve the pinned ref with `project.commit(ref)`
(`lib/gitlab/ci/config/external/file/project.rb`, `lib/gitlab/ci/components/instance_path.rb`),
an object lookup with no branch-or-tag check.
An MR copies the contributor's commit into the target project.
The `refs/merge-requests/<iid>/head` ref is deleted 14 days after close,
but `merge_request_diff.rb` enqueues `KeepAroundRefsWorker` for the MR head SHA in both the target and source projects.
Inference: an impostor commit opened as an MR, then closed, stays resolvable through `include:project`.
This is talk-worthy and the strongest cross-platform Q&A answer.

**Azure Pipelines checking out a GitHub repository resource: exposed to paths A and B.** The agent fetches the resolved
SHA directly, `git fetch origin +<sha>`, when Git is 2.26 or newer and `DisableFetchByCommit` is unset (default `false`,
`AgentKnobs.cs`).
GitHub serves fork and PR commits to that request.
Open: whether `ref:` on a `type: github` resource accepts a raw SHA, and how compile-time templates resolve
(server code is not public).

**Bitbucket Cloud: not exposed to path B.** No PR refs: BCLOUD-5814 requested them in 2012 and is still "Reviewing".
Pipelines `import:` cannot pin a SHA at all;
Atlassian's docs say a branch import "will always reference the HEAD commit of the targeted branch".
Path A remains undocumented.
**Bitbucket Data Center** does create `refs/pull-requests/<id>/from` (BSERV-12284),
so it is exposed to path B for any client that fetches a SHA (inference).

Written up in the cross-platform doc's §4.

### `--provenance strict` accepted path B (found and fixed 2026-10-20)

`GitHubClient.verify_provenance()` returned `"verified"`
if `GET /commits/{sha}/pulls` returned any PR whose base was the named repository.
GitHub's REST docs: "If the commit is not present in the default branch,
it will return merged and open pull requests associated with the commit."
Anyone can open a PR from a fork against a public repository,
so an attacker who opened one passed `--provenance strict`.

**Fixed (task 13).**
A PR now counts only when `merged_at` is set, its base is the named repository,
and the SHA is the PR's head commit or merge commit.
The head-or-merge rule also closes a second hole: push a malicious commit, revert it in the same PR,
get it squash-merged, and the malicious SHA would otherwise be "in a merged PR".
Regression tests: `tests/test_client.py::TestVerifyProvenance::test_unverified_pull_regressions`.
Demo step 5 is unblocked; re-run it against an open PR before the talk to confirm the refusal live.

### Scanner methodology notes

State the methodology on a slide; the committee and the audience will both ask.

- Define the sampling frame explicitly (for example: repositories above a star threshold with at least one
  workflow file, sampled on a stated date).
- Report the denominator for every percentage, and report a 95% Wilson interval alongside it.
  Use Wilson rather than the normal approximation;
  `Z`'s denominator is small enough that the normal interval leaves `[0, 1]`.
- Classify `uses: ./...` local actions as out of scope, not as unpinned.
- Keep repositories that carry no in-scope `uses:` out of the pin-rate denominator entirely.
  They cannot enter the numerator, so counting them understates the pin rate.
- Treat `image:` values with an existing `@sha256:` as pinned.
- Count a repository as "fully `uses:`-pinned" only when every non-local `uses:` is a 40-character SHA.
- Publish the scanner and the raw counts so the numbers are reproducible.
  Reproducibility is a strong signal to this committee specifically.

### Running the scan

The `notes.corpus_scanner` module implements all of the above in four resumable stages.
Each stage writes its artifact to disk, so the published numbers are reproducible from the published inputs.

```bash
notes/corpus_scanner/collect.sh frame   # sampling frame; ~90-120 min, <20 MB
notes/corpus_scanner/collect.sh pilot   # 2,000 repos; ~10 min, ~2.2 GB; measures the rates that size the full run
notes/corpus_scanner/collect.sh full    # 50,000 repos; ~4 h, ~55 GB; the published corpus
```

`collect.sh` resolves the token with `gh auth token`,
verifies free disk space against the estimate plus 10% headroom before cloning, and prints the artifacts to publish.
Its header documents every tunable and the resource estimates behind them.
To drive the stages directly:

```bash
export GITHUB_TOKEN=...   # search is 10 req/min unauthenticated, 30 req/min authenticated
uv run --group corpus python -m notes.corpus_scanner frame  --min-stars 100 --pushed-since 2026-04-01 --out notes/corpus/frame.jsonl
uv run --group corpus python -m notes.corpus_scanner fetch  --frame notes/corpus/frame.jsonl --cache notes/corpus/repos --sample 50000 --seed 20260401 --concurrency 10
uv run --group corpus python -m notes.corpus_scanner scan   --cache notes/corpus/repos --out notes/corpus/corpus.csv
uv run --group corpus python -m notes.corpus_scanner report --csv notes/corpus/corpus.csv --exclude-dynamic
```

Configuration goes through `pydantic-settings` like the rest of the project,
so every flag also reads from the environment and `.env`,
the token is a `SecretStr` resolved from `PINREF_TOKEN` or `GITHUB_TOKEN`,
and `--pushed-since` is validated as a real date rather than pasted into the query as a string.
`--verbose`/`-v` is a root flag (0–3) and precedes the stage name.

- `frame` bisects star bands around GitHub's 1000-result search cap
  and records the exact query in a sibling `frame.meta.json`.
- `fetch` uses `git clone --filter=blob:none --sparse --depth=1`,
  which is not charged against the REST rate limit and leaves cone-mode's top-level files —
  including `.pre-commit-config.yaml` — in place.
  Each clone's HEAD SHA is recorded so the scan is pinned to a specific snapshot.
  `--sample` shuffles the frame once under `--seed` and takes a prefix,
  so samples nest and the pilot's clones are reused by the full run.
- `scan` reuses the production collectors
  (`_collect_refs`, `_collect_image_refs`, `_collect_precommit_refs`)
  so the measurement cannot drift from what the tool actually pins.
- `report` emits a Markdown table ready to paste into the Part 1 data slide,
  with Wilson intervals and a sizing block that states how many clones `Z`'s denominator would require.

Publish `frame.jsonl`, `frame.meta.json`, `sample.jsonl`, the sampling seed, `manifest.jsonl`, `corpus.csv`,
and the script itself.

The full frame is roughly 150k repositories; cloning all of them is ~12 h and ~200 GB.
The full run measured a pin rate of 8.0% of scanned repositories,
so the 50,000-repository sample put `N` at 4,008 and the headline percentage inside roughly ±1.1 points.
That is the right size for the headline, `X`, and `Y`.
It is not enough to make `Z` a headline; see [Full-Run Results](#full-run-results).

### Measurement definitions

Resolve these before the slide is drawn; every one of them is a question the committee can ask.

- **In-scope population** — repositories with at least one workflow or action file and at least one non-local,
  non-expression `uses:`.
  This is the denominator for the pin rate quoted in Part 0.
- **Denominator `N`** — the in-scope repositories whose every in-scope `uses:` is already a 40-character SHA.
- **`X`** — share of `N` carrying at least one container image reference without a `sha256:` digest.
- **`Y`** — share of `N` carrying at least one cross-repository `actions/checkout` `with.ref` that is not a SHA.
- **`Z`** — share of the repositories in `N` that both run pre-commit in CI and have hook revisions,
  carrying at least one revision that is not a SHA.
  `Z` has its own denominator; say so on the slide, and say its size.
- Expression-valued references (`${{ ... }}`) are counted separately and excluded from numerator and denominator.
  They are neither pinned nor statically mutable,
  and a `with.ref: ${{ github.event.pull_request.head.sha }}` is a different vulnerability class
  (`pwn-request`, zizmor's territory), not a pinning gap.
- Local `uses: ./...` actions are counted and reported, but are out of scope by definition.

### Finding from building the scanner

`pinref` itself only detected the `jobs.<job>.container.image` mapping form,
not GitHub's documented `jobs.<job>.container: node:20` string shorthand.
Fixed in `core._is_image_path` before running the scan, so `X` is not a lower bound.

This is a usable 20-second aside in Part 1: the measurement found a gap in the tool that was built to close the gap.
It supports the surface argument — that the pinning surface is larger than anyone's mental model of it,
including the author's — and it is the kind of self-implicating detail that buys credibility with this committee.

Still-known undercounts to disclose on the methodology slide:

- Docker container action definitions (`runs.image` in an `action.yml`) are not classified.
- `runs-on:` runner images are mutable and not pinnable by any tool; acknowledged as future work.
- Default-branch snapshot only; no history.
- 35 YAML files that neither parser accepts are excluded from classification.
- Frame floor of 100 stars.
  Pinning discipline plausibly correlates with popularity,
  so both the pin rate and the residual surface may differ below the floor.
  Say this before someone asks.

## Q&A Preparation

Hard questions, with honest answers.
The "Questions you were about to ask" slide answers six of these on screen; keep the rest for the five-minute Q&A.

**"Isn't the image gap just test databases?"**
No. Of the 358 fully pinned repositories with a mutable image, 203 have a mutable job container,
the environment every step runs inside; 160 have a mutable service image.
See [Image breakdown](#image-breakdown).

**"Why not just use GitHub's lockfile and ignore all of this?"**
For action references, once it is available to you, do exactly that — the talk recommends it.
It is in public preview, so most of the room cannot adopt it yet, and it does not cover container images,
cross-repo `with.ref`, pre-commit revisions, or `runs-on:`.
Part 1 measures precisely that surface.

**"If SHA pins did not save `tj-actions` and Trivy users, why pin?"**
They protected users whose pin named a known-good commit with no tag-based dependencies inside.
The exceptions prove the talk's two other points.
Some `tj-actions` users had an updater write the malicious SHA
(issue #2463), which is why review cost and cooldowns matter.
Older `trivy-action` SHAs fetched `setup-trivy` by tag, which is the transitive undercount.
Trivy images pinned by digest were unaffected.

**"Isn't the fork-network behavior already documented by GitHub?"**
Yes, and the talk quotes both the behavior and the one-line warning from GitHub's own docs.
Chainguard published the same finding as "imposter commits" on 2023-03-08, and the talk credits it.
The contribution is not the disclosure.
It is showing what that one line means in practice, comparing the tools actually reviewed or tested,
and explaining why the platform built the check in.

**"How is this different from `zizmor`?"** `zizmor` is a detector, and the close recommends running it.
Its `impostor-commit` audit flags a fork-only SHA after it is committed,
and its `unpinned-images` audit covers `container.image`.
The talk's contribution is the measurement of what remains after pinning, not a competing detector.

**"Isn't this just an ad for your tool?"**
The proposal discloses that the speaker maintains `pinref`.
Most of the talk is a measurement and a GitHub platform behavior.
Both are tool-independent.
The checklist opens by recommending GitHub's lockfile over any third-party tool, including the speaker's.

**"Why write another pinning tool when `ratchet` and `pinact` exist?"**
Because the speaker did not know about them at the time, and says so on the motivation slide.
The rollout needed a bulk fixer; the tools the speaker knew, `actionlint` and `zizmor`, validate and detect.
Writing one anyway is what produced the list of reference types this talk measures.
On GitHub Actions, `ratchet` is near-complete; the coverage table shows it.

**"Doesn't GitHub's SHA-pinning policy already enforce this?"**
For `uses:`, yes, and the talk recommends turning it on.
It checks for a full commit SHA, so it does not check where that SHA came from, and it does not cover images,
`with.ref`, or pre-commit revisions.

**"Don't immutable releases make tags safe?"**
For releases whose publisher enabled them, a released tag cannot move.
Consumers cannot require it, floating tags such as `v4` that no release owns still move,
and it does nothing for container images.

**"15% isn't very much.
Doesn't that mean pinning basically works?"**
For the residual surface, largely yes, and the talk says so.
The argument is not that the gap is enormous; it is that nobody knew the number, no guide tells you to look,
no lockfile covers it, and the one in seven who are exposed are exposed to arbitrary code execution.

**"Your pre-commit number has a small denominator."**
Correct: 204 repositories, 95% CI 73.9%–84.8%, which is why it is a supporting figure and not the headline.
The pre-commit-eligible population is 0.4% of repositories scanned;
a 1,000-repository denominator needs a frame wider than the one sampled.
Stated as a limitation, not smoothed over.

**"Why not just use Dependabot or Renovate?"**
They open pull requests after the fact.
They cannot make a pull request land already pinned, and they do not verify provenance.
Complementary, not substitutes.

**"Isn't this just a GitHub problem?"**
No. Every CI platform reviewed has mutable config-layer references, and every container registry has mutable tags.
CircleCI registry orbs are the one config layer that is immutable by construction —
and CircleCI's own docs show an immutable orb running a mutable image.
The image layer is the gap no platform closes.

**"What if the attacker opens a pull request with the impostor commit?"**
The PR copies the commit into `refs/pull/N/head` on the upstream repository.
GitHub's lockfile still rejects it, because it requires the commit to be on a branch.
`--provenance strict` rejects it too: only the head or merge commit of a *merged* PR counts.
That rule also defeats the revert-then-squash variant, where the malicious commit sits inside a merged PR.
On GitLab the same trick works against `include:project` pinned to a SHA, and keep-around refs may make it permanent.

**"Is this only GitHub?"**
The "Not a GitHub problem" slide answers for images, cross-repository refs, and pre-commit revisions.
For impostor commits: shared fork storage is GitHub-specific as far as anyone has documented.
Merge request refs are not: GitLab includes and components resolve an MR-only commit by SHA
(from source), and Azure's agent fetches GitHub commits by SHA.
Bitbucket Cloud has no PR refs, and its shared-config imports cannot pin a SHA at all.

**"Isn't `--provenance strict` just checking GitHub's own API?
What if GitHub is compromised?"** Correct, and stated in the talk.
It raises the bar from "any SHA in the fork network" to "a SHA a maintainer put on the named repo."
It is not an attestation and should not be sold as one.

**"Doesn't pinning everything break Dependabot/Renovate update flows?"**
No, both understand SHA pins with version comments.
The trailing `# v4` comment is what makes that work; do not strip it.

**"Doesn't pinning images to a digest mean you miss security patches?"**
Yes, unless something updates the pin.
On GitHub Actions, Renovate updates workflow `container:`, `services:`, and `docker://` images; Dependabot does not
(GitHub Docs, October 2026).
Accept the patch latency the cooldown adds; Part 3 shows the tradeoff.

**"What about pinning the runner image?"** Legitimate gap.
`runs-on: ubuntu-latest` is mutable and not pinnable by any of these tools.
Acknowledge it as future work rather than hand-waving.

**"Is SHA-1 strong enough to pin to?"**
Git has used collision-detecting SHA-1 (SHA-1DC) by default since Git 2.13, and a SHA-256 object format exists.
The practical risk in this talk is where a SHA came from, not a collision.

**"What's the review cost of a 200-line SHA diff?"** Real and nontrivial.
Answer with the public-corpus dry run and the comment-preservation mitigation; do not cite internal data.

## Cut List

Things that feel important and are not.

- A long retrospective on any single incident.
  One slide maximum.
- Arguing that pinning is good.
  The room agrees before you start.
- Arguing that the residual surface is enormous.
  It is one in seven; say so and move on.
- The full tool feature matrix.
  One coverage table in Part 3, with a lockfile column; link the rest.
- A deep dive on lockfile mechanics.
  Six bullets in Part 0 and the coverage boundary in Part 1; GitHub's docs cover the rest.
- Architecture, async internals, caching, benchmarks.
  Wrong conference, wrong talk.
- Any slide about why Python was chosen.
- If over time after task 23, cut to 40 minutes in this order: "Questions you were about to ask"
  (about 90 seconds; its answers stay in Q&A preparation),
  the remediation slide (the proposal no longer promises it), the second demo variant in Part 2,
  the platform-controls slide (keep it as backup), the gap-in-my-own-tool aside, the audit slide
  (move the commands to the published repository), and the transitive slide last; it carries the title.
  The GitLab, Jenkins, and CircleCI configuration slides are already backup.
  Do not cut the "Not a GitHub problem" slide; the proposal promises it.
  Do not cut "What actually floats"; the abstract's job-container sentence depends on it.
  Do not cut the coverage table; the proposal names every tool in it.

## Open Risks

- ~~The headline statistic may come back undramatic.~~ **Fired.**
  The pilot returned 13.1%; the full run returned 14.8%.
  Resolved by reframing as "one in seven, and no lockfile covers any of it"; see [Full-Run Results](#full-run-results).
- ~~Competing tools may ship provenance checks between submission and April 2027.~~
  **Fired, and worse than anticipated.**
  GitHub itself shipped it, in the platform, enforced at run time.
  Resolved by moving the thesis back to the residual surface; see [Primary-Source Review](#primary-source-review).
- **Lockfiles reach general availability, change, or expand scope before April 2027.**
  Mitigated by the 2026-10-23 reframing: the thesis no longer depends on the feature.
  Expansion to container-image or `with.ref` coverage would shrink the lockfile column on one slide,
  not the measurement.
  Re-check the feature's documentation at submission, at acceptance, and in March 2027.
- The impostor walk-through has not been reproduced end-to-end yet.
  No longer thesis-critical or submission-critical, but it is still the best segment in the talk.
- `Z` cannot reach a 1,000-repository denominator at the current sampling frame.
  The full run gives 79.9% (163/204, 95% CI 73.9%–84.8%): usable as a supporting figure with its denominator shown,
  not as a headline.
  Widen the frame below 100 stars only if `Z` must carry more weight.
- A live run would depend on GitHub Actions executing on conference wifi timing.
  The proposal promises a recording, so this risk applies only if you choose to run live.
- There is no employer clearance.
  Use only public-corpus data; do not name the employer, its repositories, or internal counts in the talk or Q&A.
  If asked where the story happened, answer "at work, on many repositories" and move on.
- GitHub may change fork-network API behavior and invalidate the demo outright.
  Unlikely on this timescale, but re-verify in March 2027.
- The project name is **pinref** for the proposal and distribution; use it consistently in public materials.
- ~~`--provenance strict` accepts a SHA from any open PR against the named repository (path B).~~
  **Resolved** by task 13.
  Residual: a maintainer who merges a malicious PR defeats the check by design; say so if asked.
- The GitLab keep-around and Azure fetch-by-SHA findings come from reading source, not from tests.
  Present them as "the source says", or run task 14 first.
- `sethvargo/ratchet` has been evaluated and already closes most of the coverage gap on GitHub Actions.
  The talk's Part 1 tool-coverage slide must show `ratchet` as near-complete,
  or the committee and audience will catch the omission.
  The surviving per-tool gaps are `with.ref`, pre-commit revisions, and provenance.
- The motivation story can read as a claim that no fixer existed.
  Date it, credit `ratchet` and `pinact` on the same slide,
  and note that `zizmor` now has an unsafe-tier `--fix=all` for `unpinned-uses`.
- The proposal commits to a recorded walk-through and a March 2027 re-scan.
  If task 6 never reproduces, present Part 2 from slides; if the re-scan moves the figures, update the deck,
  and tell the audience the abstract quoted the 2026-10-21 run.
- Part 3 lost two minutes and gained the coverage table.
  Rehearse it first; it is the segment most likely to overrun.

## Open Questions

Decide each by the date in brackets.

1. **Level [Nov 1].**
   Which Level options does the CFP form offer?
   The proposal says Intermediate.
2. **Short Abstract limit [Nov 1].**
   Does the print field have a length limit?
   The current text is about 330 characters.
3. ~~**Former employer in the bio [Nov 1].**~~
   **Resolved 2026-10-29:** the bio omits The Walt Disney Studios; the community speaking record fits this CFP better.
   Revisit only for a variant that needs a professional credential (task 30).
4. **Outside-activity policy [Nov 1].**
   Does the current employer require approval to speak at all?
5. **SunSecCon [Nov 1].**
   What is its deadline, and does it allow dual submission?
   See task 28.
6. **Walk-through variant [February 2027].** Action or pre-commit?
   The proposal's "a workflow running a fork-only commit" fits both; pre-commit ties Part 1 to Part 2.
7. **Live run [March 2027].**
   Run Part 2 live at the venue, or play the recording only?
   Decide after task 6 reproduces in rehearsal; the proposal promises only the recording.
8. **Re-scan method [March 2027].**
   Re-draw the frame with a new `--pushed-since`, or rescan the same 49,984 repositories at their current HEADs?
   The same sample keeps the figures comparable; a new frame keeps "active" accurate.
   State the choice on the methodology slide (task 29).
9. **`Y` scope [February 2027].**
   Restrict cross-repository checkout refs to code the job executes?
   The proposal discloses that `Y` counts both (task 15).
10. **Transitive references [February 2027].**
    Measure composite-action `uses:` and Docker action base images, or keep them as a disclosed undercount?

## Citations

Every claim in the proposal or on a slide needs a primary source.
Status as of 2026-10-29.

### Verified

| Claim                                                                                         | Source                                                                      | Checked    | Used in          |
| --------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- | ---------- | ---------------- |
| Fork commits are reachable from the upstream repository                                       | [GitHub: About forks][gh-forks]                                             | 2026-10-20 | Proposal; Part 2 |
| Verify a SHA comes from the action's repository, not a fork                                   | [GitHub: Secure use reference][gh-secure]                                   | 2026-10-20 | Part 2           |
| Lockfiles verify source-repository identity; public preview                                   | [GitHub: Workflow dependency lockfiles][gh-lock]                            | 2026-10-20 | Proposal; Part 3 |
| Organization and enterprise SHA-pinning policy                                                | GitHub changelog, 2025-08-15                                                | 2026-10-25 | Part 3           |
| Immutable releases                                                                            | GitHub Docs, *Immutable releases*                                           | 2026-10-25 | Part 3           |
| `tj-actions/changed-files`: CVE-2025-30066, repointed tags, secrets in logs, 2025-03-14 to 15 | [GHSA][ghsa], [StepSecurity][stepsec], [CISA][cisa], [#2463][tj-2463]       | 2026-10-29 | Part 0           |
| Some SHA-pinned consumers ran the malicious commit after Renovate updates                     | [tj-actions/changed-files#2463][tj-2463]                                    | 2026-10-29 | Part 0           |
| `reviewdog/action-setup@v1`: CVE-2025-30154, 2025-03-11, embedding actions affected           | [CVE record][cve-reviewdog], [Wiz][wiz-reviewdog], [Hunters][hunters]       | 2026-10-29 | Part 0           |
| Trivy: CVE-2026-33634, 76 of 77 action tags, compromised images, older-SHA caveat             | [GHSA][ghsa-trivy], [Aqua][aqua-trivy], [StepSecurity][stepsec-trivy]       | 2026-10-29 | Proposal; Part 0 |
| Imposter commits: disclosed to GitHub 2022-09-08, published 2023-03-08                        | [Chainguard, "What the fork?"][chainguard]                                  | 2026-10-29 | Proposal; Part 2 |
| `impostor-commit` covers workflows, actions, and pre-commit                                   | [`zizmor` audit rules][zizmor]                                              | 2026-10-29 | Proposal; Q&A    |
| `unpinned-images` covers `container.image` only, with no auto-fix                             | [`zizmor` audit rules][zizmor]                                              | 2026-10-29 | Part 3 table     |
| Renovate and Dependabot image, pre-commit, and cooldown support                               | Vendor documentation                                                        | 2026-10-26 | Part 3           |
| GitLab CI, Jenkins, and CircleCI syntax                                                       | Vendor documentation                                                        | 2026-10-26 | Part 1; backup   |
| Corpus figures, frame size, and image breakdown                                               | `corpus/report-full.md`, `corpus/images-full.csv`, `corpus/frame.meta.json` | 2026-10-26 | Proposal; Part 1 |

### Needed

| Claim                                                          | Gap                                              | Task |
| -------------------------------------------------------------- | ------------------------------------------------ | ---- |
| Truffle Security FOR research (2024)                           | Page unreachable 2026-10-29                      | 31   |
| One incident per reference type                                | Checkout `ref:` and pre-commit `rev:` unsourced  | 16   |
| Trivy release workflow used an impostor `actions/checkout` SHA | StepSecurity only; SHA not independently checked | 33   |
| `zizmor` coverage of service images and `docker://` steps      | Docs name `container.image` only                 | 21   |
| Immutable-release attestations can verify an action pin        | Unresolved                                       | 22   |
| A partial clone fetches a fork-only commit on demand           | Inference from partial-clone behavior            | 27   |
| GitLab keep-around refs and Azure fetch-by-SHA                 | Source reading, not tests                        | 14   |
| Lockfile coverage boundary                                     | Documentation only; `gh actions-lock` untested   | 5    |
| Renovate and Dependabot configurations work as shown           | Documentation only                               | 26   |
| Published scanner repository URL                               | Not yet published                                | 4    |

[gh-forks]: https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/about-forks
[gh-secure]: https://docs.github.com/en/actions/reference/security/secure-use
[gh-lock]: https://docs.github.com/en/actions/concepts/security/workflow-dependency-lockfiles
[ghsa]: https://github.com/advisories/GHSA-mrrh-fwg8-r2c3
[stepsec]: https://www.stepsecurity.io/blog/harden-runner-detection-tj-actions-changed-files-action-is-compromised
[cisa]: https://www.cisa.gov/news-events/alerts/2025/03/18/supply-chain-compromise-third-party-tj-actionschanged-files-cve-2025-30066-and-reviewdogaction
[tj-2463]: https://github.com/tj-actions/changed-files/issues/2463
[cve-reviewdog]: https://www.cve.org/CVERecord?id=CVE-2025-30154
[wiz-reviewdog]: https://www.wiz.io/blog/new-github-action-supply-chain-attack-reviewdog-action-setup
[hunters]: https://www.hunters.security/en/blog/github-actions-supply-chain-attack
[ghsa-trivy]: https://github.com/advisories/GHSA-69fq-xp46-6x23
[aqua-trivy]: https://github.com/aquasecurity/trivy/discussions/10425
[stepsec-trivy]: https://www.stepsecurity.io/blog/trivy-compromised-a-second-time---malicious-v0-69-4-release
[chainguard]: https://www.chainguard.dev/unchained/what-the-fork-imposter-commits-in-github-actions-and-ci-cd
[zizmor]: https://docs.zizmor.sh/audits/
