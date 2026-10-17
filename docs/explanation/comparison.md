# Comparing pin-actions to Similar Tools

Multiple tools solve the "unpinned GitHub Actions" problem.
SHA-pinning `uses:` is, by now, a commodity feature —
and the reason this page exists is that pinning `uses:` is **necessary and insufficient**.
This page compares `pin-actions` against five notable alternatives so you can make an informed choice,
and is explicit about where `pin-actions` is *not* the right answer.

## TL;DR

| Tool                                                                      | Category                                  | Language | Best fit                                                                                                                                                 |
| ------------------------------------------------------------------------- | ----------------------------------------- | -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **pin-actions**                                                           | Pin + update + verify (fixer)             | Python   | Teams that want the *entire* mutable-reference surface pinned in one pass and want impostor-commit SHAs rejected before they are written; CLI or library |
| **[ratchet](https://github.com/sethvargo/ratchet)**                       | Pin + unpin + update + lint (fixer)       | Go       | Teams pinning across **multiple CI systems** — GitHub Actions, GitLab CI, CircleCI, Cloud Build, Drone, Tekton — from one static binary                  |
| **[pinact](https://github.com/suzuki-shunsuke/pinact)**                   | Pin + update + verify (fixer)             | Go       | Teams standardizing on Go/aqua-ecosystem CLI tooling who also want a dedicated `-verify` CI-gate mode and a built-in minimum-release-age cooldown        |
| **[Updatecli](https://github.com/updatecli/updatecli)**                   | Declarative update policy engine (fixer)  | Go       | Teams wanting one policy-driven tool to update Actions, container images, package versions, and other values, then open pull requests                    |
| **[mheap/pin-github-action](https://github.com/mheap/pin-github-action)** | Pin only (fixer)                          | Node.js  | Simple, minimal pinning needs in a Node-based toolchain; the historical baseline whose re-resolution behavior `pin-actions` and others mirror            |
| **[zizmor](https://github.com/zizmorcore/zizmor)**                        | Static analysis (detector), with auto-fix | Rust     | Primarily a linter for CI/CD vulnerability classes; its `unpinned-uses` audit also ships a stable `--fix` mode that can hash-pin actions itself          |

**Key distinction — dedicated fixer vs. general updater vs. detector:** `pin-actions`, `ratchet`, `pinact`,
and `pin-github-action` are purpose-built fixers that rewrite workflow files to add SHA pins as their primary job.
`ratchet` is the broadest of them by CI system, covering six platforms rather than GitHub Actions alone.
[Updatecli's `github/action` autodiscovery](https://www.updatecli.io/docs/plugins/autodiscovery/githubaction/) provides
comparable SHA and container-digest pinning inside a broader declarative dependency-update engine.
`zizmor` is primarily a detector (it reports far more vulnerability classes than just unpinned actions —
template injection, credential leakage, excessive permissions, impostor commits, and more) —
but it is **not fix-mode-free**: its `unpinned-uses` audit supports a stable,
non-experimental `zizmor --fix` mode that hash-pins actions directly,
in the same spirit as the dedicated pinning tools. zizmor's own docs even recommend `pinact`
as a complementary/alternative pinning tool for users who want a dedicated pinning CLI.
Run a detector for broad CI/CD vulnerability coverage; run a dedicated fixer, a general updater such as Updatecli,
or zizmor's own `--fix` to remediate pinning.
Treat them as complementary layers, not strict competitors —
this project deliberately dogfoods `zizmor` and `actionlint` in its own `.pre-commit-config.yaml` and CI
(see [Threat Model §6](threat-model.md#6-how-pin-actions-addresses-this-threat-model)).

## What Separates pin-actions

One table says most of it. ✅ pins or gates · ⚠️ reports only, no fix · ❌ not covered.

| Mutable reference                  | Where                                | pin-actions | ratchet | pinact | Updatecli | pin-github-action | zizmor |
| ---------------------------------- | ------------------------------------ | :---------: | :-----: | :----: | :-------: | :---------------: | :----: |
| Action ref                         | `uses: actions/checkout@v4`          |     ✅      |   ✅    |   ✅   |    ✅     |        ✅         |   ✅   |
| Reusable workflow ref              | `uses: org/repo/.github/...@main`    |     ✅      |   ✅    |   ✅   |    ❌     |        ❌         |   ⚠️   |
| Cross-repo checkout ref            | `with: {ref: main}`                  |     ✅      |   ❌    |   ❌   |    ❌     |        ❌         |   ❌   |
| Step container image               | `uses: docker://alpine:3`            |     ✅      |   ✅    |   ❌   |    ✅     |        ❌         |   ⚠️   |
| Job container image                | `jobs.<id>.container.image`          |     ✅      |   ✅    |   ❌   |    ✅     |        ❌         |   ⚠️   |
| Service container image            | `jobs.<id>.services.<name>.image`    |     ✅      |   ✅    |   ❌   |    ❌     |        ❌         |   ⚠️   |
| Pre-commit hook revision           | `rev: v1.2.3`                        |     ✅      |   ❌    |   ❌   |    ❌     |        ❌         |   ⚠️   |
| **Provenance of the resolved SHA** | does this commit belong to the repo? |     ✅      |   ❌    |   ❌   |    ❌     |        ❌         |   ⚠️   |

`ratchet` is the closest tool to `pin-actions` on reference coverage and the main alternative to weigh.
Two things still separate them.

### 1. Provenance verification at write time

Pinning to a commit SHA defeats tag hijacking.
It does **not** defeat an attacker who supplies a SHA that lives in a *fork* of the action.
GitHub serves fork commits from the upstream repository's API namespace,
so `actions/checkout@<attacker-sha>` resolves successfully and reads as legitimate in code review
(see [Threat Model §3.1](threat-model.md#31-github-fork-network-vulnerabilities-imposter-commits)).

`pin-actions` is the only compared tool that gates on this *while writing*.
`--provenance strict` refuses to write a SHA that is not reachable from a branch, tag,
or pull request on the named repository; `--provenance warn` logs it and continues.
`zizmor`'s `impostor-commit` audit detects the same condition, but only after the SHA is already committed.
The remaining tools resolve and write whatever the API returns.

### 2. Coverage and formatting fidelity

A workflow carries far more mutable references than `uses:`, and each one is executable.
A repository can be 100% SHA-pinned on `uses:` and still run an attacker-controlled service container,
check out an attacker-controlled branch of a sibling repository, or execute an unpinned pre-commit hook in CI.

On GitHub Actions, `ratchet` matches `pin-actions` everywhere except cross-repo `with.ref` and pre-commit revisions,
and it covers five CI systems that `pin-actions` does not.
The practical tradeoff is formatting: `ratchet` documents that it normalizes **all** indentation to two spaces,
because its YAML library does not retain pre-parse indentation,
and it does not resolve values inside anchors or aliases.
`pin-actions` round-trips through `yamlrocks` and rewrites only the mutated nodes,
so a pin-only diff stays a pin-only diff.
It also preserves the precision of the tag recorded in the trailing comment,
so a `v4` pin stays `v4` rather than widening to `v4.1.7` and enlarging the diff.
On an existing repository with established formatting,
that difference decides whether the first pull request is reviewable.

### Honest limits

- `pin-actions` is **not** faster, smaller, or more battle-tested than `ratchet` or `pinact`.
  Both are static binaries with larger communities.
- `pin-actions` handles GitHub Actions only.
  If you need GitLab CI, CircleCI, Cloud Build, Drone, or Tekton, use `ratchet`.
- `ratchet`'s `-bake-delay` cooldown is **broader** than `--exclude-newer`: it applies to `pin`, `update`,
  and `upgrade`, and to container images as well as Actions.
  `pin-actions` applies `--exclude-newer` only when `--update` auto-selects a tag, and not to container digests.
- `ratchet` resolves container registries through keychain auth, so it handles ECR and GCR.
  `pin-actions` supports only Bearer-token registries and raises `UnsupportedRegistryError` for the rest.
- `pin-actions` has no `unpin` command and no `lint`-style non-zero-exit CI gate; `ratchet` has both.
- Provenance verification costs an extra GitHub API call per unique `(repo, sha)` pair.
  It is cached and off by default.
- Provenance verification is best-effort reachability against the GitHub API, not cryptographic attestation.
- Pre-commit hook pinning uses a separate `pin-precommit` command rather than automatic discovery by `pin-actions`;
  see [Pin Pre-Commit Hooks](../how-to/pin-pre-commit-hooks.md).

## Feature Matrix

Reference coverage is in the table above; this matrix covers everything else.

| Feature                                            |           pin-actions            |                         ratchet                          |                pinact                |                  Updatecli                   |           pin-github-action            |       zizmor        |
| -------------------------------------------------- | :------------------------------: | :------------------------------------------------------: | :----------------------------------: | :------------------------------------------: | :------------------------------------: | :-----------------: |
| CI systems supported                               |       GitHub Actions only        | GH Actions, GitLab, CircleCI, Cloud Build, Drone, Tekton |         GitHub Actions only          |              Many, via plugins               |          GitHub Actions only           | GitHub Actions only |
| Re-resolves already-pinned SHA if tag moved        |                ✅                |                            ✅                            |                  ✅                  |                      ✅                      |                   ✅                   |         ❌          |
| Update pinned tags forward                         | ✅<br/>major, minor, &amp; patch |              ✅<br/>`upgrade`; Actions only              |                  ✅                  |         ✅<br/>configurable filters          |                   ❌                   |         ❌          |
| Cool-off / minimum-release-age gate                |   ✅<br/>`--update` tags only    |          ✅<br/>`-bake-delay`; also containers           |                  ✅                  | ✅<br/>not applied to workflow Docker images |                   ❌                   |         ❌          |
| Unpin command (reverse the operation)              |                ❌                |                            ✅                            |                  ❌                  |                      ❌                      |                   ❌                   |         ❌          |
| Non-zero-exit CI gate                              |                ❌                |                      ✅<br/>`lint`                       |           ✅<br/>`-verify`           |                      ❌                      |                   ❌                   |         ✅          |
| Skip-list / allow-list for specific actions        |                ✅                |             ✅<br/>`# ratchet:exclude` only              |                  ✅                  |              ✅<br/>ignore/only              |                   ✅                   |         ✅          |
| Config file support                                |      ✅<br/>TOML/PyProject       |             ❌<br/>comment annotations only              |        ✅<br/>`.pinact.yaml`         |            ✅<br/>YAML manifests             |         ❌<br/>CLI flags only          | ✅<br/>`zizmor.yml` |
| Non-Bearer registries (ECR, GCR)                   |   ❌<br/>`UnsupportedRegistry`   |                   ✅<br/>keychain auth                   |                 N/A                  |                ⚠️<br/>varies                 |                  N/A                   |         N/A         |
| Usable as an importable library (not just CLI)     |                ✅                |           ⚠️<br/>Go packages, undocumented API           |                  ❌                  |                      ❌                      |                   ❌                   |         ❌          |
| Async/concurrent API calls with rate-limit backoff |                ✅                |           ⚠️<br/>bounded; backoff undocumented           | ⚠️<br/>undocumented backoff strategy |         ⚠️<br/>undocumented strategy         |                   ❌                   |   N/A<br/>unknown   |
| Preserve YAML comments/formatting                  |                ✅                |        ⚠️<br/>comments kept; indent forced to 2sp        |                  ✅                  | ⚠️<br/>comments preserved; YAML reserialized |                   ✅                   |         ✅          |
| Convert a branch ref to the latest stable tag      |                ❌                |                            ❌                            |       ✅<br/>`--branch-to-tag`       |                      ❌                      |                   ❌                   |         ❌          |
| Opens pull requests itself                         | ⚠️<br/>bundled `update_repos.py` |                            ❌                            |                  ❌                  |                      ✅                      |                   ❌                   |         ❌          |
| pre-commit hook                                    |        ❌<br/>Coming Soon        |                            ❌                            |                  ❌                  |                      ❌                      |                   ✅                   |         ✅          |
| GitHub Action                                      |        ❌<br/>Coming Soon        |                ✅<br/>`sethvargo/ratchet`                |                  ❌                  |                      ✅                      | ✅<br/>via `ensure-sha-pinned-actions` |         ✅          |
| GitHub annotations                                 |                ❌                |                            ❌                            |                  ❌                  |                      ❌                      |                   ❌                   |         ✅          |
| Generate SARIF                                     |                ❌                |                            ❌                            |                  ✅                  |                      ❌                      |                   ❌                   |         ✅          |

## Project Health

Star counts, last push, and license read from the GitHub API on 2026-10-17.
License and distribution moved here from the feature matrix; they are project metadata, not features.

| Tool              | Language    | Stars |  Last push | License    | Distribution                                                     |
| ----------------- | ----------- | ----: | ---------: | ---------- | ---------------------------------------------------------------- |
| pin-actions       | Python 3.14 |     — |          — | Apache-2.0 | Python wheel — **not yet published to PyPI**                     |
| ratchet           | Go          |   969 | 2026-07-18 | Apache-2.0 | Static binary, container, Homebrew, Nix, `go install`, GH Action |
| pinact            | Go          | 1,230 | 2026-10-15 | MIT        | Static binary (aqua / goreleaser)                                |
| Updatecli         | Go          |   998 | 2026-10-17 | Apache-2.0 | Static binary, OS packages, container, GH Action                 |
| pin-github-action | JavaScript  |   185 | 2026-08-13 | MIT        | npm                                                              |
| zizmor            | Rust        | 6,719 | 2026-10-17 | MIT        | PyPI, Rust binary, pre-commit hook, GH Action                    |

Treat this table as the counterweight to the coverage table above.
`pin-actions` has the widest reference coverage and the least production exposure of any tool listed.
`zizmor` is an order of magnitude more widely adopted than every fixer here combined, and is sponsored by Trail of Bits,
Grafana Labs, and Kusari.
`ratchet`'s last push predates the others by roughly three months.

## Anything Else Worth Noting

- **Fork Network / impostor commits (§3.1 of the [Threat Model](threat-model.md)):** pinning to a SHA only stops
    tag-hijacking, not a malicious fork's SHA being pinned in the first place.
    `pin-actions` is the only compared *fixer* that gates on this at write time (`--provenance strict`).
    `zizmor`'s `impostor-commit` audit detects the same condition after the fact; `ratchet`, `pinact`, Updatecli,
    and `pin-github-action` do not check it at all.
    Provenance verification is best-effort reachability, not cryptographic attestation —
    still combine it with manual review of any new SHA.
- **Cooldown gates are not equivalent.**
    `ratchet`'s `-bake-delay` is the broadest: it covers pin, update, upgrade, and container images.
    `ratchet`'s own documentation is candid that a bake delay cannot detect a tag repointed at an already-old commit,
    and that a moving major tag such as `v4` falls back to the commit date because it has no matching release.
    The same caveats apply to `pin-actions` `--exclude-newer`.
    Treat any cooldown as risk reduction, not a guarantee.
- **Renovate/Dependabot overlap:** `pinact`'s README explicitly notes it complements
    (not replaces)
    Renovate's `helpers:pinGitHubActionDigestsToSemver` preset,
    because Renovate cannot pin actions *before* a PR merges.
    The same reasoning applies to `pin-actions` — run it as a pre-commit hook or CI gate so PRs land already pinned,
    and let Renovate/Dependabot handle the ongoing version-bump PRs afterward.
    Updatecli overlaps more directly with Renovate and Dependabot because it can discover updates,
    enforce declarative conditions, and open pull requests itself.

## Which Should You Use

| If you…                                                                          | Use                                 |
| -------------------------------------------------------------------------------- | ----------------------------------- |
| Pin across GitLab CI, CircleCI, Cloud Build, Drone, or Tekton as well as Actions | `ratchet`                           |
| Want a static binary, an `unpin` escape hatch, and a `lint` CI gate              | `ratchet`                           |
| Pull images from ECR or GCR                                                      | `ratchet`                           |
| Only need `uses:` pinned, want a static binary and SARIF output                  | `pinact`                            |
| Want broad CI/CD vulnerability detection beyond pinning                          | `zizmor` (run it alongside a fixer) |
| Already run a declarative update engine for images, charts, and package versions | Updatecli                           |
| Need impostor-commit gating before a SHA is ever written                         | `pin-actions`                       |
| Need `with.ref` cross-repo checkouts or pre-commit hook revisions pinned         | `pin-actions`                       |
| Cannot accept a tool reindenting your existing YAML                              | `pin-actions`                       |
| Need to embed pinning inside Python automation rather than shelling out to a CLI | `pin-actions`                       |

These are layers, not substitutes.
A reasonable stack is `zizmor` for detection plus one fixer for remediation.
If you run `ratchet` for multi-CI coverage,
`pin-actions --provenance strict` still adds the impostor-commit gate that no other fixer provides.

## See Also

- [Threat Model](threat-model.md) — The supply-chain attack model this tool defends against
- [Architecture Overview](architecture.md) — Container image pinning and concurrency model details
