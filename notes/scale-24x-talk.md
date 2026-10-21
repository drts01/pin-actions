# SCaLE 24x Talk Notes — "Lockfiles Fixed Half Your Workflow. Here's the Other Half."

Working notes for a SCaLE 24x proposal and presentation.
Not part of the published documentation site.

## Venue Facts

| Item          | Value                                                             |
| ------------- | ----------------------------------------------------------------- |
| Conference    | SCaLE 24x, Southern California Linux Expo                         |
| Dates         | April 1–4, 2027, Pasadena Convention Center                       |
| CFP closes    | **November 1, 2026**                                              |
| Reviewers     | ~40 volunteer Program Committee members                           |
| Likely tracks | Security, DevOps/SRE, Open Source Supply Chain                    |
| Format        | Assume 45 minutes including Q&A; design for 35 + 10               |

SCaLE is community-run and explicitly filters vendor and tool pitches.
The committee publicly states it wants new speakers and practitioner content.
A submission framed as "here is my CLI" gets rejected.
A submission framed as "here is a measurement nobody has published, and here is what we did about it" gets accepted.

## The One-Sentence Thesis

GitHub is replacing "pin your actions" with a lockfile that pins and verifies `uses:` references for you —
and that lockfile does not touch the other five mutable, executable reference types a workflow carries,
which is a surface nobody has measured.

Two rounds of evidence produced this framing.
The pilot scan ruled out the original "pinning is deeply incomplete" thesis (see [Pilot Results](#pilot-results)).
A primary-source review then ruled out the provenance-only thesis that briefly replaced it
(see [Primary-Source Review](#primary-source-review)).

## Why This Talk Is Novel

Three claims, in descending order of strength.

1. **The residual surface is unmeasured, and the platform's own fix does not close it.**
   Lockfiles cover action and reusable-workflow references.
   They do not cover `container.image`, `services[*].image`, `docker://` steps, cross-repo `with.ref`,
   pre-commit revisions, or `runs-on:`.
   The corpus measurement is the only published number for what is left,
   and it is the one claim that gets *stronger* as lockfiles roll out, not weaker.
2. **Provenance is not pinning, and the distinction is demonstrable on stage.**
   GitHub serves fork commits from the upstream repository's API namespace,
   so `actions/checkout@<sha-that-only-exists-in-my-fork>` resolves, runs, and reads as legitimate in review.
   Still a great demo.
   But see the novelty caveat in [Primary-Source Review](#primary-source-review): GitHub documents the behavior,
   warns about it in one line, and is now shipping the fix.
   Present this as *motivation for why the lockfile exists*, not as an unknown.
3. **A real multi-repo rollout, including the failures.**
   Credibility payload, not the thesis.

## Title Candidates

Ranked.
Prefer plain language over puns; SCaLE abstracts are scanned quickly.

1. **Lockfiles Fixed Half Your Workflow.
   Here's the Other Half.**
2. The Other Half of Your Workflow: Mutable Refs No Lockfile Covers
3. A SHA Is Not a Promise: Provenance Gaps in CI Supply-Chain Hardening
4. You Pinned Your Actions.
   You're Still Not Pinned.

Candidates 3 and 4 were each briefly ranked first and each lost to evidence.
Keep them listed so the reasoning is not relitigated.

## Draft Abstract (submittable)

> "Pin your GitHub Actions to a commit SHA" has been the single most repeated piece of CI supply-chain advice
> for years — and GitHub is now replacing it.
> Workflow dependency lockfiles pin every action you depend on, including transitive dependencies,
> and verify at run time that the commit really came from the repository it names.
> If you can adopt one, you should.
>
> Then comes the part the lockfile leaves to you.
> A lockfile covers `uses:`.
> A workflow has at least five other ways to execute code from somewhere else:
> job containers, service containers, `docker://` steps, cross-repository checkout refs,
> and pre-commit hook revisions.
> Every one of them is mutable.
> None of them is in the lockfile.
> Good tools already exist for some of them — `ratchet` pins container images across six CI systems —
> but cross-repository checkout refs and pre-commit revisions are outside most pinning tools,
> and a tool only helps in the repositories that run it.
>
> So I measured what is actually left.
> I scanned 4,008 public repositories that had already pinned every single `uses:` to a commit SHA,
> and counted what was still mutable underneath.
> One in seven still had something mutable.
> I will publish the scanner, the raw counts, and the sampling seed so you can check the numbers.
>
> Along the way I will show you live why the lockfile's run-time identity check exists:
> GitHub serves commits from a repository's entire fork network under the upstream repository's API namespace,
> so a SHA that exists only in an attacker's fork resolves cleanly, passes review, and executes.
> Most pinning tools write that SHA without checking where it came from;
> I will show which ones do.
>
> Finally, the operational part: what happened when we rolled this across a real repository fleet,
> what broke, and what the remediation actually costs.
>
> You will leave able to audit your own pinning surface and with a concrete checklist to close it.

`N` is 4,008, from the 2026-10-21 full run over 49,984 repositories; see [Full-Run Results](#full-run-results).
The abstract no longer claims the answer is "uncomfortable,"
and it no longer claims the fork-network behavior is unknown.
Both claims were checked and neither survived.

Revised 2026-10-20 for `ratchet`, which pins `docker://`, `container.image`, and `services[*].image` on GitHub Actions
(see [`naming.md`](naming.md) and `docs/explanation/comparison.md`):

- Dropped "the part nobody is talking about"; `ratchet` and Updatecli already address the image rows.
- Named `ratchet` in the abstract.
  A reviewer who knows it reads the omission as ignorance; naming it reads as a survey.
- Moved the novelty claim from "no tool covers this" to "nobody has measured what is left".
  The measurement survives any tool's existence; the coverage claim did not.
- Replaced "the popular pinning tools write it without complaint" with "most pinning tools write
  that SHA without checking where it came from".
  `zizmor` flags impostor commits after the fact, so "popular tools" was false as a blanket claim.
  The remaining claim rests on source review of `ratchet`, `pinact`, Updatecli, and `pin-github-action`;
  confirm it empirically with task 7 before submitting, or soften to "tools I tested".

## Outline — 35 minutes of content

### 0:00–0:03 — Cold open, no title slide

Show a workflow file that is 100% SHA-pinned.
Ask the room: "This repository follows every piece of pinning advice ever written.
How many mutable references are still in it?"

Reveal: four.
`services.redis.image: redis:7`, `container.image: python:3.14-slim`, `with.ref: main`, and a pre-commit `rev:`.

Then the second question, which is the one the talk is actually about: "Now look at the SHAs you *did* pin.
How do you know those commits came from the repositories they name?"

Do not say the tool name yet.

### 0:03–0:07 — Why pinning became gospel, and what is replacing it

One slide on tag mutability.
One slide on the tag-hijacking incident class.

> **Fact-check before use.** Verify the tj-actions/changed-files timeline, the CVE identifier,
> and the claim that SHA-pinned consumers were unaffected, against primary sources.
> Do not present incident details from memory.

Land the point in 30 seconds: tags are pointers, pointers move, SHAs do not.
The room already agrees.
Do not belabor it.

One extra beat earned by the full-run data:
**87.8% of public repositories that use third-party actions do not pin all of them to a commit SHA.**
The advice is near-universal and compliance is not.
Scope the claim on the slide: active, non-archived, non-fork repositories above 100 stars, with at least one non-local,
non-expression `uses:` (28,855 of 32,863; 95% CI 87.4%–88.2%).

Then the slide that keeps the talk current — **workflow dependency lockfiles**.
State it plainly and without hedging:

- `.github/workflows/actions.lock`, generated by `gh actions-lock`.
- Records `ref`, resolved `commit`, and the `owner_id`/`repo_id` of the source repository.
- GitHub verifies that identity at run time and requires the commit to exist on a branch of the source repo.
- Covers transitive action dependencies, which SHA pinning cannot.
- GitHub's position: this supersedes SHA pinning for repositories that adopt it.
- Public preview as of this writing; **re-verify status before the conference.**

Say "adopt it" out loud.
Giving the audience the platform answer first is what earns permission to spend the next ten minutes on what the
platform answer does not cover.
A talk that hides this gets caught in Q&A and deserves to be.

### 0:07–0:17 — Part 1: The surface no lockfile covers

Open with the coverage boundary, as a single slide: the lockfile closes `uses:` and reusable workflow refs,
and stops there.

Then the six mutable reference types, one slide each, 45 seconds each, with a one-line "what an attacker gets" for each.

| Reference                         | What an attacker who controls it gets                                  |
| --------------------------------- | ---------------------------------------------------------------------- |
| `uses:` action ref                | Arbitrary code in the job, with the job's token                        |
| Reusable workflow ref             | Arbitrary jobs, plus whatever secrets are inherited                    |
| `with.ref` on cross-repo checkout | Arbitrary source on disk, usually then built or executed               |
| `docker://` step image            | Arbitrary code in the job                                              |
| `container.image`                 | Control of the environment every step in the job runs inside           |
| `services[*].image`               | Network-reachable service the job trusts, on the job's network         |

Then the data slide.
This is the centerpiece again, and the lockfile framing makes it land harder than it did on its own:

> Of 4,008 repositories where every `uses:` is already pinned to a commit SHA,
> **one in seven** (14.8%) still reference at least one mutable container image, cross-repo checkout ref,
> or pre-commit revision —
> and not one of those reference types is covered by a lockfile.

Break it down on the same slide: 8.9% have a mutable container image (`X`)
and 2.8% have an unpinned cross-repo `with.ref` (`Y`).
Report the pre-commit share separately because it has its own denominator.

Say the inverse out loud before anyone else does: about 85% of pinned repositories show none of these three.
Do not call them clean; the scanner has known undercounts (see the methodology notes).
The finding is that a residual surface exists at all, that no guide tells you to look for it,
and that the platform's new fix does not reach it.
Volunteering the deflating reading is what makes the rest of the numbers trustworthy.

Second data slide: tool coverage.
Which of the six each popular tool actually pins, **with a lockfile column**.
Present it neutrally and include `pin-actions` in the same table as everyone else.
`ratchet` is near-complete on GitHub Actions; show that honestly.
Neutral framing here buys credibility for Part 2.

### 0:17–0:27 — Part 2: A SHA is not a promise (live demo)

The emotional center of the talk, and — after the primary-source review —
the *explanation* for the lockfile rather than a scoop.
Frame it that way in the first sentence: "Here is concretely why GitHub put a run-time identity check in that lockfile."

1. Slide: GitHub's fork network stores all fork commits in one object store,
   and the API serves them under the upstream path.
2. Demo step 1: fork a well-known action, push a commit that writes a marker to the job log.
3. Demo step 2: `curl` the **upstream** repository's commits API with that SHA.
   It returns 200.
4. Demo step 3: put `actions/<action>@<fork-sha>` in a workflow.
   It runs.
   Show the marker in the log.
5. Demo step 4: run the popular pinning tools against it.
   They re-resolve, verify, and leave it alone.
   Nobody objects.
6. Demo step 5: `pin-actions --provenance strict`.
   It refuses.
   Show the error.
7. Slide: what verification actually means here — a branch head, a tag,
   or the head or merge commit of a *merged* PR on the named repository.
   Open PRs do not count; anyone can open one.
   **Say the limitation out loud:** this is best-effort reachability, not cryptographic attestation.
   Artifact attestations and sigstore are the real answer and are not yet available for this.
8. Slide: the lockfile does this natively, at run time, with repository IDs rather than names.
   Close the loop — this is the control, and everything before it is what you do until you have it.

With the extra time this segment gains over the original plan, add:

- A review-realism beat: show the impostor pin inside a realistic pull request diff
  and ask the room what they would have caught.
  Nobody catches it; that is the point.
- The one-line GitHub warning on screen — "verify it is from the action's repository and not a repository fork" —
  followed by "and here is every tool that checks that for you."
  Quoting the vendor's own doc is stronger than claiming nobody said it.

Honesty about the limitation is what separates this from a product pitch.
The committee and the audience will both reward it.

**Demo safety.**
Pre-record the entire sequence as a fallback video.
Conference wifi plus live GitHub API calls plus a live Actions run is three failure modes stacked.
Run the live version if the network cooperates; cut to video without apologizing if it does not.
Use a throwaway org, a fork you control, and a workflow with `permissions: {}` and no secrets.

### 0:27–0:33 — Part 3: What rolling this out actually costs

The fleet story.
Use the real campaign data from `output.csv`, `repos.txt`, and `prs.txt`.

Include, specifically:

- How many repositories, how many files, how many refs changed.
- The failure modes: `403 Write access to repository not granted`, parse failures, unresolvable refs.
- The fork-and-PR fallback for repositories you cannot push to.
- What review burden a wall of SHA diffs creates, and how the trailing `# v4` comment mitigates it.
- The cooldown argument: why you should refuse releases younger than ~7 days, and what that costs in staleness.

> **Blocker.** The campaign data is internal (`uhc-consumer/*`).
> Anonymize repository names and obtain employer clearance before this appears in a proposal or slide.
> If clearance is not forthcoming, replace this section with a public-corpus dry run.

### 0:33–0:35 — Close

The checklist slide, which is what people photograph:

1. Adopt a workflow dependency lockfile if you can.
   It covers `uses:` and verifies provenance for you.
2. Verify any new SHA is reachable on the repository it claims to come from if you cannot.
3. Grep your workflows for `image:` — not just `uses:`.
   No lockfile covers it.
4. Grep for `ref:` under `with:`.
5. Check `.pre-commit-config.yaml` revisions.
6. Refuse releases younger than your cooldown window.
7. Run a detector and a fixer; they are different jobs.

Tool slide last, 20 seconds, one URL.

## Pre-CFP Work — the critical path

Ordered by what blocks the abstract.
Reprioritized after the pilot: the demo now blocks the abstract and the full scan does not.
The full scan finished on 2026-10-21.

| #   | Task                                                                                        | Blocks         | Status                                                                                            |
| --- | ------------------------------------------------------------------------------------------- | -------------- | ------------------------------------------------------------------------------------------------- |
| 1   | Build the corpus scanner; sample public repos with workflow files                           | Abstract `N`   | **Done** — `notes/corpus_scanner/`                                                                |
| 2   | Run the pilot; decide the framing from the measured rates                                   | Thesis         | **Done** — see [Pilot Results](#pilot-results)                                                    |
| 3   | Fact-check the fork-network and pinning claims against GitHub's documentation               | Thesis         | **Done** — see [Primary-Source Review](#primary-source-review)                                    |
| 4   | Run the full 50,000-repository scan; publish the artifacts                                  | Abstract `N`   | **Scan done** — see [Full-Run Results](#full-run-results); publishing the artifacts is still todo |
| 5   | Adopt `gh actions-lock` on a test repository; verify coverage claims empirically            | Part 0, Part 1 | Todo                                                                                              |
| 6   | Reproduce the fork/impostor demo end-to-end in a throwaway org                              | Part 2         | Todo                                                                                              |
| 7   | Confirm each competing tool's behavior against the impostor SHA, empirically, not from docs | Part 2         | Todo                                                                                              |
| 8   | Decide whether to widen the frame for `Z` or drop `Z`                                       | Part 1         | Todo — the full run gives n=204; see [Full-Run Results](#full-run-results)                        |
| 9   | Fact-check the incident timeline and CVE against primary sources                            | Part 0         | Todo                                                                                              |
| 10  | Secure clearance to present anonymized fleet data                                           | Part 3         | Todo                                                                                              |
| 11  | Write and submit the abstract                                                               | Nov 1          | Todo                                                                                              |
| 12  | Reproduce a pre-commit impostor `rev:` end to end on repositories you own                   | Part 1, Part 2 | Todo                                                                                              |
| 13  | Fix `verify_provenance` to reject open-PR-only SHAs; add a regression test                  | Part 2 demo    | **Done** — merged PR head or merge commit only                                                    |
| 14  | Empirically test GitLab paths A and B (API, `git fetch`, `include:project`, component @SHA) | Q&A            | Partly answered from source; end-to-end plan in [`impostor-e2e-tests.md`](impostor-e2e-tests.md)  |

Tasks 4 and 5 are the proposal; the scan half of task 4 is done.
The measurement is the thesis again, so `N` belongs in the abstract,
and task 5 is what lets the lockfile coverage boundary be stated as fact rather than as a reading of the docs.
Get both done before writing the final abstract.

Task 6 is no longer abstract-blocking, but it is still the best ten minutes of the talk.
If it does not reproduce, Part 2 becomes a slide-only explanation of why lockfiles verify identity,
and the talk survives — which is precisely the resilience the previous framing lacked.

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
`pin-actions` competes with a first-party feature on `uses:` pinning and provenance,
and should compete on the surface the lockfile does not cover.
Captured in [`docs/explanation/threat-model.md` §4.1 and §6.1](../docs/explanation/threat-model.md).

**Process note.**
Two consecutive thesis pivots were proposed before anyone read the primary sources.
Run task 7 (fact-checking) *before* the next framing decision, not after.

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
the token is a `SecretStr` resolved from `PIN_ACTIONS_TOKEN` or `GITHUB_TOKEN`,
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

`pin-actions` itself only detected the `jobs.<job>.container.image` mapping form,
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

**"Why not just use the lockfile and ignore all of this?"**
For action references, do exactly that — the talk recommends it in Part 0.
The lockfile does not cover container images, cross-repo `with.ref`, pre-commit revisions, or `runs-on:`,
and it is in public preview, so a large share of the room cannot adopt it yet.
Part 1 measures precisely the surface the lockfile leaves behind.

**"Isn't the fork-network behavior already documented by GitHub?"**
Yes, and the talk quotes both the behavior and the one-line warning from GitHub's own docs.
The contribution is not the disclosure.
It is showing what that one line means in practice, showing that no mainstream tool enforced it,
and explaining why the platform ended up building the check in.

**"Isn't this just an ad for your tool?"**
Most of the talk is a measurement and a GitHub platform behavior.
Both are tool-independent.
The checklist opens by recommending GitHub's lockfile over any third-party tool, including the speaker's.

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
Shared fork storage is GitHub-specific as far as anyone has documented.
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

**"What about pinning the runner image?"** Legitimate gap.
`runs-on: ubuntu-latest` is mutable and not pinnable by any of these tools.
Acknowledge it as future work rather than hand-waving.

**"What's the review cost of a 200-line SHA diff?"** Real and nontrivial.
Answer with the fleet data and the comment-preservation mitigation.

## Cut List

Things that feel important and are not.

- A long retrospective on any single incident.
  One slide maximum.
- Arguing that pinning is good.
  The room agrees before you start.
- Arguing that the residual surface is enormous.
  It is one in seven; say so and move on.
- The full tool feature matrix.
  One coverage table in Part 1, with a lockfile column; link the rest.
- A deep dive on lockfile mechanics.
  Six bullets in Part 0 and the coverage boundary in Part 1; GitHub's docs cover the rest.
- Architecture, async internals, caching, benchmarks.
  Wrong conference, wrong talk.
- Any slide about why Python was chosen.

## Open Risks

- ~~The headline statistic may come back undramatic.~~ **Fired.**
  The pilot returned 13.1%; the full run returned 14.8%.
  Resolved by reframing as "one in seven, and no lockfile covers any of it"; see [Full-Run Results](#full-run-results).
- ~~Competing tools may ship provenance checks between submission and April 2027.~~
  **Fired, and worse than anticipated.**
  GitHub itself shipped it, in the platform, enforced at run time.
  Resolved by moving the thesis back to the residual surface; see [Primary-Source Review](#primary-source-review).
- **Lockfiles reach general availability or expand scope before April 2027.**
  The dangerous direction is expansion: if GitHub adds container-image or `with.ref` coverage,
  Part 1 loses rows and the talk loses its thesis a second time.
  Re-check the feature's documentation at submission, at acceptance, and in March 2027.
  Treat the Part 1 coverage boundary as a perishable claim with a known expiry risk.
- The impostor demo has not been reproduced end-to-end yet.
  No longer thesis-critical, but it is still the best segment in the talk.
- `Z` cannot reach a 1,000-repository denominator at the current sampling frame.
  The full run gives 79.9% (163/204, 95% CI 73.9%–84.8%): usable as a supporting figure with its denominator shown,
  not as a headline.
  Widen the frame below 100 stars only if `Z` must carry more weight.
- Live demo depends on GitHub Actions executing on conference wifi timing.
  Pre-record.
- Fleet data clearance may not arrive.
  Have the public-corpus substitute ready.
- GitHub may change fork-network API behavior and invalidate the demo outright.
  Unlikely on this timescale, but re-verify in March 2027.
- The project may be renamed before the conference; see [naming notes](naming.md).
  Decide the name before submitting on November 1 — changing it after acceptance is worse than either option.
- ~~`--provenance strict` accepts a SHA from any open PR against the named repository (path B).~~
  **Resolved** by task 13.
  Residual: a maintainer who merges a malicious PR defeats the check by design; say so if asked.
- The GitLab keep-around and Azure fetch-by-SHA findings come from reading source, not from tests.
  Present them as "the source says", or run task 14 first.
- `sethvargo/ratchet` has been evaluated and already closes most of the coverage gap on GitHub Actions.
  The talk's Part 1 tool-coverage slide must show `ratchet` as near-complete,
  or the committee and audience will catch the omission.
  The surviving per-tool gaps are `with.ref`, pre-commit revisions, and provenance.
