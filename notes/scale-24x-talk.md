# SCaLE 24x Talk Notes — "You Pinned Your Actions. You're Still Not Pinned."

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

Every CI hardening guide tells you to pin GitHub Actions to a commit SHA;
almost nobody tells you that a fully SHA-pinned workflow still executes mutable, attacker-reachable code,
and that the SHA itself may not belong to the repository you think it does.

## Why This Talk Is Novel

Three claims, in descending order of strength.
Only the first two should carry the talk.

1. **Nobody has published the pinning-surface gap.**
   The industry measures "percent of `uses:` pinned."
   Nobody measures what fraction of *fully pinned* repositories still carry mutable `services[*].image`,
   `container.image`, `with.ref`, or pre-commit `rev:` references.
   This number is collectible and will almost certainly be large.
   It reframes a settled problem.
2. **Provenance is not pinning, and the distinction is demonstrable on stage.**
   GitHub serves fork commits from the upstream repository's API namespace.
   Therefore `actions/checkout@<sha-that-only-exists-in-my-fork>` resolves, runs, and reads as legitimate in review.
   Every pinning tool in common use will happily write that SHA.
   This is a live demo with a genuine audience reaction.
3. **A real multi-repo rollout, including the failures.**
   Credibility payload, not the thesis.

## Title Candidates

Ranked.
Prefer plain language over puns; SCaLE abstracts are scanned quickly.

1. **You Pinned Your Actions.
   You're Still Not Pinned.**
2. The Other Half of Your Workflow: Mutable Refs Your Pinning Tool Missed
3. A SHA Is Not a Promise: Provenance Gaps in CI Supply-Chain Hardening

## Draft Abstract (submittable)

> "Pin your GitHub Actions to a commit SHA" is the single most repeated piece of CI supply-chain advice,
> and it works — it is why SHA-pinned repositories survived the tag-hijacking incidents of recent years.
>
> It is also incomplete in two ways that almost nobody checks.
>
> First, `uses:` is only one of at least six mutable references a workflow can carry.
> Job containers, service containers, cross-repository checkout refs, reusable workflow refs,
> and pre-commit hook revisions are all executable, all mutable, and all ignored by most pinning tools.
> I scanned [N] public repositories to find out how big that gap is in practice.
> The answer is uncomfortable.
>
> Second, a commit SHA tells you *what* code runs, not *whose*.
> GitHub serves commits from a repository's entire fork network under the upstream repository's API namespace,
> so a SHA that exists only in an attacker's fork resolves cleanly, passes review, and executes.
> I will demonstrate this live, show that the popular pinning tools write that SHA without complaint,
> and show what verifying provenance at write time looks like instead.
>
> Finally, the operational part: what happened when we rolled pinning across a real repository fleet,
> what broke, and what the remediation actually costs.
>
> You will leave able to audit your own pinning surface and with a concrete checklist to close it.

Keep the bracketed `[N]` only until the scan is run.
Submit with the real number if at all possible; it is the strongest line in the abstract.

## Outline — 35 minutes of content

### 0:00–0:03 — Cold open, no title slide

Show a workflow file that is 100% SHA-pinned.
Ask the room: "This repository follows every piece of pinning advice ever written.
How many mutable references are still in it?"

Reveal: four.
`services.redis.image: redis:7`, `container.image: python:3.14-slim`, `with.ref: main`, and a pre-commit `rev:`.

Do not say the tool name yet.

### 0:03–0:08 — Why pinning became gospel

One slide on tag mutability.
One slide on the tag-hijacking incident class.

> **Fact-check before use.** Verify the tj-actions/changed-files timeline, the CVE identifier,
> and the claim that SHA-pinned consumers were unaffected, against primary sources.
> Do not present incident details from memory.

Land the point in 30 seconds: tags are pointers, pointers move, SHAs do not.
The room already agrees.
Do not belabor it.

### 0:08–0:18 — Part 1: The surface is bigger than `uses:`

The six mutable reference types, one slide each, 45 seconds each, with a one-line "what an attacker gets" for each.

| Reference                         | What an attacker who controls it gets                                  |
| --------------------------------- | ---------------------------------------------------------------------- |
| `uses:` action ref                | Arbitrary code in the job, with the job's token                        |
| Reusable workflow ref             | Arbitrary jobs, plus whatever secrets are inherited                    |
| `with.ref` on cross-repo checkout | Arbitrary source on disk, usually then built or executed               |
| `docker://` step image            | Arbitrary code in the job                                              |
| `container.image`                 | Control of the environment every step in the job runs inside           |
| `services[*].image`               | Network-reachable service the job trusts, on the job's network         |

Then the data slide.
This is the centerpiece.
Something in the shape of:

> Of [N] repositories with 100% of `uses:` pinned to a SHA,
> [X]% still reference at least one mutable container image,
> [Y]% have an unpinned cross-repo checkout ref,
> [Z]% have unpinned pre-commit revisions running in CI.

Second data slide: tool coverage.
Which of the six each popular tool actually pins.
Present it neutrally and include `pin-actions` in the same table as everyone else.
Neutral framing here buys credibility for Part 2.

### 0:18–0:28 — Part 2: A SHA is not a promise (live demo)

The emotional center of the talk.

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
7. Slide: what verification actually means here — reachability from a real branch, tag, or PR.
   **Say the limitation out loud:** this is best-effort reachability, not cryptographic attestation.
   Artifact attestations and sigstore are the real answer and are not yet available for this.

Honesty about the limitation is what separates this from a product pitch.
The committee and the audience will both reward it.

**Demo safety.**
Pre-record the entire sequence as a fallback video.
Conference wifi plus live GitHub API calls plus a live Actions run is three failure modes stacked.
Run the live version if the network cooperates; cut to video without apologizing if it does not.
Use a throwaway org, a fork you control, and a workflow with `permissions: {}` and no secrets.

### 0:28–0:33 — Part 3: What rolling this out actually costs

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

1. Grep your workflows for `image:` — not just `uses:`.
2. Grep for `ref:` under `with:`.
3. Check `.pre-commit-config.yaml` revisions.
4. Verify any new SHA is reachable on the repo it claims to come from.
5. Refuse releases younger than your cooldown window.
6. Run a detector and a fixer; they are different jobs.

Tool slide last, 20 seconds, one URL.

## Pre-CFP Work — the critical path

Ordered by what blocks the abstract.

| #   | Task                                                                                        | Blocks       | Status                            |
| --- | ------------------------------------------------------------------------------------------- | ------------ | --------------------------------- |
| 1   | Build the corpus scanner; sample public repos with workflow files                           | Abstract `N` | **Done** — `notes/scan_corpus.py` |
| 2   | Run the scan; compute the four headline percentages                                         | Abstract     | Todo                              |
| 3   | Reproduce the fork/impostor demo end-to-end in a throwaway org                              | Demo         | Todo                              |
| 4   | Confirm each competing tool's behavior against the impostor SHA, empirically, not from docs | Part 2       | Todo                              |
| 5   | Fact-check the incident timeline and CVE against primary sources                            | Part 0       | Todo                              |
| 6   | Secure clearance to present anonymized fleet data                                           | Part 3       | Todo                              |
| 7   | Write and submit the abstract                                                               | Nov 1        | Todo                              |

Tasks 1, 2, and 3 are the proposal.
If only one gets done, make it 1 and 2 —
the data is what distinguishes this from the dozens of "supply chain security" submissions the committee will read.

### Scanner methodology notes

State the methodology on a slide; the committee and the audience will both ask.

- Define the sampling frame explicitly (for example: repositories above a star threshold with at least one
  workflow file, sampled on a stated date).
- Report the denominator for every percentage.
- Classify `uses: ./...` local actions as out of scope, not as unpinned.
- Treat `image:` values with an existing `@sha256:` as pinned.
- Count a repository as "fully `uses:`-pinned" only when every non-local `uses:` is a 40-character SHA.
- Publish the scanner and the raw counts so the numbers are reproducible.
  Reproducibility is a strong signal to this committee specifically.

### Running the scan

`notes/scan_corpus.py` implements all of the above in four resumable stages.
Each stage writes its artifact to disk, so the published numbers are reproducible from the published inputs.

```bash
export GITHUB_TOKEN=...   # search is 10 req/min unauthenticated, 30 req/min authenticated
./notes/scan_corpus.py frame  --min-stars 100 --pushed-since 2026-04-01 --out notes/corpus/frame.jsonl
./notes/scan_corpus.py fetch  --frame notes/corpus/frame.jsonl --cache notes/corpus/repos --concurrency 16
./notes/scan_corpus.py scan   --cache notes/corpus/repos --out notes/corpus/corpus.csv
./notes/scan_corpus.py report --csv notes/corpus/corpus.csv --exclude-dynamic
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
- `scan` reuses the production collectors
  (`_collect_refs`, `_collect_image_refs`, `_collect_precommit_refs`)
  so the measurement cannot drift from what the tool actually pins.
- `report` emits a Markdown table ready to paste into the Part 1 data slide.

Publish `frame.jsonl`, `frame.meta.json`, `corpus.csv`, and the script itself.

### Measurement definitions

Resolve these before the slide is drawn; every one of them is a question the committee can ask.

- **Denominator `N`** — repositories with at least one workflow or action file,
  at least one in-scope `uses:`,
  and every in-scope `uses:` already a 40-character SHA.
- **`X`** — share of `N` carrying at least one container image reference without a `sha256:` digest.
- **`Y`** — share of `N` carrying at least one cross-repository `actions/checkout` `with.ref` that is not a SHA.
- **`Z`** — share of the repositories in `N` that both run pre-commit in CI and have hook revisions,
  carrying at least one revision that is not a SHA.
  `Z` has its own denominator; say so on the slide.
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
It supports the talk's actual thesis — that the pinning surface is larger than anyone's mental model of it,
including the author's — and it is the kind of self-implicating detail that buys credibility with this committee.

Still-known undercounts to disclose on the methodology slide:

- Docker container action definitions (`runs.image` in an `action.yml`) are not classified.
- `runs-on:` runner images are mutable and not pinnable by any tool; acknowledged as future work.
- Default-branch snapshot only; no history.

## Q&A Preparation

Hard questions, with honest answers.

**"Isn't this just an ad for your tool?"**
Most of the talk is a measurement and a GitHub platform behavior.
Both are tool-independent.
The checklist works with any tool, including none.

**"Why not just use Dependabot or Renovate?"**
They open pull requests after the fact.
They cannot make a pull request land already pinned, and they do not verify provenance.
Complementary, not substitutes.

**"Isn't `--provenance strict` just checking GitHub's own API?
What if GitHub is compromised?"** Correct, and stated in the talk.
It raises the bar from "any SHA in the fork network" to "a SHA reachable from a real ref on the named repo."
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
- The full tool feature matrix.
  One coverage table in Part 1; link the rest.
- Architecture, async internals, caching, benchmarks.
  Wrong conference, wrong talk.
- Any slide about why Python was chosen.

## Open Risks

- The headline statistic may come back undramatic.
  If the gap is small, the talk thesis is wrong and should be rewritten around Part 2 alone.
  Run the scan before committing to the framing.
- Live demo depends on GitHub Actions executing on conference wifi timing.
  Pre-record.
- Fleet data clearance may not arrive.
  Have the public-corpus substitute ready.
- Competing tools may ship provenance checks between submission and April 2027.
  That weakens claim 2 but strengthens the talk's premise; be prepared to update the slide and say so on stage.
- The project may be renamed before the conference; see [naming notes](naming.md).
  Decide the name before submitting on November 1 — changing it after acceptance is worse than either option.
- `sethvargo/ratchet` has been evaluated and already closes most of the coverage gap on GitHub Actions.
  The talk's Part 1 tool-coverage slide must show `ratchet` as near-complete,
  or the committee and audience will catch the omission.
  The surviving per-tool gaps are `with.ref`, pre-commit revisions, and provenance — lead with provenance.
