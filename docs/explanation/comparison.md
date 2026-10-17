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
- Pre-commit hook pinning ships as the bundled `scripts/update_precommit.py` entry point,
  not as a `pin_actions` public API; see [Pin Pre-Commit Hooks](../how-to/pin-pre-commit-hooks.md).

## Feature Matrix

Reference coverage is in the table above; this matrix covers everything else.

| Feature                                            |           pin-actions            |                         ratchet                          |                pinact                |                  Updatecli                   |           pin-github-action            |                      zizmor                      |
| -------------------------------------------------- | :------------------------------: | :------------------------------------------------------: | :----------------------------------: | :------------------------------------------: | :------------------------------------: | :----------------------------------------------: |
| CI systems supported                               |       GitHub Actions only        | GH Actions, GitLab, CircleCI, Cloud Build, Drone, Tekton |         GitHub Actions only          |              Many, via plugins               |          GitHub Actions only           |               GitHub Actions only                |
| Re-resolves already-pinned SHA if tag moved        |                ✅                |                            ✅                            |                  ✅                  |                      ✅                      |                   ✅                   |                        ❌                        |
| Update pinned tags forward                         | ✅<br/>major, minor, &amp; patch |              ✅<br/>`upgrade`; Actions only              |                  ✅                  |         ✅<br/>configurable filters          |                   ❌                   |                        ❌                        |
| Cool-off / minimum-release-age gate                |   ✅<br/>`--update` tags only    |          ✅<br/>`-bake-delay`; also containers           |                  ✅                  | ✅<br/>not applied to workflow Docker images |                   ❌                   |                        ❌                        |
| Unpin command (reverse the operation)              |                ❌                |                            ✅                            |                  ❌                  |                      ❌                      |                   ❌                   |                        ❌                        |
| Non-zero-exit CI gate                              |                ❌                |                      ✅<br/>`lint`                       |           ✅<br/>`-verify`           |                      ❌                      |                   ❌                   |                        ✅                        |
| Skip-list / allow-list for specific actions        |                ✅                |             ✅<br/>`# ratchet:exclude` only              |                  ✅                  |              ✅<br/>ignore/only              |                   ✅                   |                        ✅                        |
| Config file support                                |      ✅<br/>TOML/PyProject       |             ❌<br/>comment annotations only              |        ✅<br/>`.pinact.yaml`         |            ✅<br/>YAML manifests             |         ❌<br/>CLI flags only          |               ✅<br/>`zizmor.yml`                |
| Non-Bearer registries (ECR, GCR)                   |   ❌<br/>`UnsupportedRegistry`   |                   ✅<br/>keychain auth                   |                 N/A                  |                ⚠️<br/>varies                 |                  N/A                   |                       N/A                        |
| Usable as an importable library (not just CLI)     |                ✅                |           ⚠️<br/>Go packages, undocumented API           |                  ❌                  |                      ❌                      |                   ❌                   |                        ❌                        |
| Async/concurrent API calls with rate-limit backoff |                ✅                |           ⚠️<br/>bounded; backoff undocumented           | ⚠️<br/>undocumented backoff strategy |         ⚠️<br/>undocumented strategy         |                   ❌                   |                 N/A<br/>unknown                  |
| Preserve YAML comments/formatting                  |                ✅                |        ⚠️<br/>comments kept; indent forced to 2sp        |                  ✅                  | ⚠️<br/>comments preserved; YAML reserialized |                   ✅                   |                        ✅                        |
| Distribution                                       |       Python Wheel / PyPI        |       Static binary / container / brew / nix / go        | Static binary<br/>(aqua/goreleaser)  |     Static binary / packages / container     |                  npm                   | PyPI / Rust binary / pre-commit hook / GH Action |
| pre-commit hook                                    |        ❌<br/>Coming Soon        |                            ❌                            |                  ❌                  |                      ❌                      |                   ✅                   |                        ✅                        |
| GitHub Action                                      |        ❌<br/>Coming Soon        |                ✅<br/>`sethvargo/ratchet`                |                  ❌                  |                      ✅                      | ✅<br/>via `ensure-sha-pinned-actions` |                        ✅                        |
| GitHub annotations                                 |                ❌                |                            ❌                            |                  ❌                  |                      ❌                      |                   ❌                   |                        ✅                        |
| Generate SARIF                                     |                ❌                |                            ❌                            |                  ✅                  |                      ❌                      |                   ❌                   |                        ✅                        |
| License                                            |            Apache 2.0            |                        Apache 2.0                        |                 MIT                  |                  Apache 2.0                  |                  MIT                   |                       MIT                        |

## Pros and Cons

### pin-actions

| Pros                                                                                             | Cons                                                                                         |
| ------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------- |
| Only compared tool that **verifies SHA provenance before writing** (`--provenance warn\|strict`) | Requires a Python runtime; not a single static binary like `ratchet` or `pinact`             |
| Only compared tool covering `with.ref` cross-repo checkouts                                      | GitHub Actions only; `ratchet` covers six CI systems                                         |
| Only compared tool covering Action refs, container digests, **and** pre-commit revs in one pass  | Newer/smaller community than `ratchet`, `pinact`, or `zizmor`; less battle-testing           |
| True round-trip YAML editing — only mutated nodes are rewritten, indentation untouched           | No `unpin`, no `lint`-style CI gate, no SARIF, no GitHub annotations                         |
| `--exclude-newer` cool-off period guards against same-day/1-day supply-chain compromises         | Cool-off applies only to `--update` tag selection, not to re-resolution or container digests |
| Precision-preserving version updates (`v4` stays `v4`, `v4.0.5` keeps full precision)            | Bearer-token registries only; ECR and GCR raise `UnsupportedRegistryError`                   |
| Usable as a Python library (`pin_actions.run()`) with a shared client across repositories        | Pre-commit pinning is a bundled script, not a `pin_actions` public API                       |
| Async I/O, LRU cache, and semaphore rate-limiting are fast on monorepos with many workflows      |                                                                                              |

### ratchet

The closest alternative on reference coverage, and the broadest by CI system.

| Pros                                                                                            | Cons                                                                                            |
| ----------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Covers six CI systems: GitHub Actions, GitLab CI, CircleCI, Cloud Build, Drone, Tekton          | **Normalizes all indentation to two spaces**, by its own documented limitation                  |
| Matches `pin-actions` on Actions, reusable workflows, and all three container-image surfaces    | Does not resolve values in YAML anchors or aliases                                              |
| `-bake-delay` cooldown applies to `pin`, `update`, and `upgrade`, and to container images       | No provenance verification; writes whatever SHA the API returns                                 |
| Unique `unpin` command reverses pinning; `lint` gives a non-zero-exit CI gate                   | Does not pin `with.ref` cross-repo checkouts or pre-commit hook revisions                       |
| Keychain container auth resolves ECR and GCR, which `pin-actions` rejects                       | Exclusions are per-line `# ratchet:exclude` comments only; no config file                       |
| Single static binary, plus container, Homebrew, Nix, and an official GitHub Action              | `upgrade` is Actions-only; container upgrades are an open TODO upstream                         |
| Honest upstream docs about what bake delay does and does not guarantee                          | No SARIF output or GitHub annotations                                                           |

### pinact

| Pros                                                                                           | Cons                               |
| ---------------------------------------------------------------------------------------------- | ---------------------------------- |
| Single static Go binary                                                                        | No Docker/OCI image digest pinning |
| Pins Reusable Workflow refs, same as `pin-actions`; `pin-github-action` does not               | No pre-commit hook pinning         |
| Built-in minimum-release-age cooldown (`-min-age`/`-verify-min-age`)                           | No provenance verification         |
| `--branch-to-tag` lets you opt-in to converting branch refs (`@main`) to the latest stable tag | —                                  |

### Updatecli

| Pros                                                                                                  | Cons                                                                                              |
| ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Built-in `github/action` autodiscovery pins Actions and workflow container images by default          | General-purpose update engine; more concepts and configuration than a dedicated pinning CLI       |
| Configurable version filters and minimum-release-age policy                                           | Does not pin reusable workflow refs, `actions/checkout` `with.ref`, or pre-commit hook revisions  |
| Updates many dependency types and can commit changes and open pull requests through one policy engine | Minimum-release-age filtering does not apply to Docker images discovered in workflow files        |
| Single static Go binary with packages, container images, and an official GitHub Action                | YAML updates preserve comments but may reserialize surrounding formatting                         |

### mheap/pin-github-action

| Pros                                                         | Cons                                                                                               |
| ------------------------------------------------------------ | -------------------------------------------------------------------------------------------------- |
| Simple, minimal, easy to read/audit (small Node.js codebase) | No version-update mode (`--update`) — only pins/re-resolves existing refs, never bumps versions    |
|                                                              | No Docker image pinning, no Reusable Workflow pinning, no cooldown gating                          |
|                                                              | Smallest community of the four fixers (183 stars vs. ~1k `ratchet`, 1.2k `pinact`); slower cadence |
|                                                              | Requires Node.js runtime                                                                           |

### zizmor

| Pros                                                                                                                                                               | Cons                                                                                                                                                         |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Detects far more than unpinned actions: template injection, credential leakage/persistence, excessive permissions, impostor commits, confusable git refs, and more | Pinning is not its primary focus — `--fix` only covers `unpinned-uses` (and a couple other audits), not Docker image digests or pre-commit hook revs         |
| Rust binary — fast, no runtime dependency                                                                                                                          | Broader scope means noisier output if you only care about pinning                                                                                            |
| Actively maintained, well-sponsored (Trail of Bits, Grafana Labs, Kusari)                                                                                          | Does not distinguish "already pinned but tag drifted" the way fixer tools' re-resolution does — `--fix` pins unpinned refs but doesn't re-resolve moved tags |
| Covers Dependabot config and pre-commit config, not just Actions workflows                                                                                         | No cooldown/minimum-release-age gating                                                                                                                       |
|                                                                                                                                                                    | Cannot pin Docker image digests (flags them via `unpinned-images`, no auto-fix)                                                                              |

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
