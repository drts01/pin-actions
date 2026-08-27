# Comparing pin-actions to Similar Tools

Multiple tools solve the "unpinned GitHub Actions" problem. Pick the right one for your stack — this page compares `pin-actions` against three notable alternatives so you can make an informed choice.

## TL;DR

| Tool                                                                      | Category                                  | Language | Best fit                                                                                                                                              |
| ------------------------------------------------------------------------- | ----------------------------------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| **pin-actions**                                                           | Pin + update (fixer)                      | Python   | Teams wanting SHA pinning *and* Docker/OCI image digest pinning *and* pre-commit hook pinning in one Python-native tool, usable as a CLI or a library |
| **[pinact](https://github.com/suzuki-shunsuke/pinact)**                   | Pin + update + verify (fixer)             | Go       | Teams standardizing on Go/aqua-ecosystem CLI tooling who also want a dedicated `-verify` CI-gate mode and a built-in minimum-release-age cooldown     |
| **[mheap/pin-github-action](https://github.com/mheap/pin-github-action)** | Pin only (fixer)                          | Node.js  | Simple, minimal pinning needs in a Node-based toolchain; the historical baseline whose re-resolution behavior `pin-actions` and others mirror         |
| **[zizmor](https://github.com/zizmorcore/zizmor)**                        | Static analysis (detector), with auto-fix | Rust     | Primarily a linter for CI/CD vulnerability classes; its `unpinned-uses` audit also ships a stable `--fix` mode that can hash-pin actions itself       |

**Key distinction — detector-first vs. fixer-first:** `pin-actions`, `pinact`, and `pin-github-action` are purpose-built fixers that rewrite workflow files to add SHA pins as their primary job. `zizmor` is primarily a detector (it reports far more vulnerability classes than just unpinned actions — template injection, credential leakage, excessive permissions, impostor commits, and more) — but it is **not fix-mode-free**: its `unpinned-uses` audit supports a stable, non-experimental `zizmor --fix` mode that hash-pins actions directly, in the same spirit as the dedicated pinning tools. zizmor's own docs even recommend `pinact` as a complementary/alternative pinning tool for users who want a dedicated pinning CLI. Run a detector for broad CI/CD vulnerability coverage; run a dedicated fixer (or zizmor's own `--fix`) to remediate pinning. Treat them as complementary layers, not strict competitors — this project deliberately dogfoods `zizmor` and `actionlint` in its own `.pre-commit-config.yaml` and CI (see [Threat Model §6](threat-model.md#6-how-pin-actions-addresses-this-threat-model)).

## Feature Matrix

| Feature                                                              |           pin-actions            |                pinact                |           pin-github-action            |                      zizmor                      |
| -------------------------------------------------------------------- | :------------------------------: | :----------------------------------: | :------------------------------------: | :----------------------------------------------: |
| Pins `uses:` refs to full SHA                                        |                ✅                |                  ✅                  |                   ✅                   |                        ✅                        |
| Re-resolves already-pinned SHA if tag moved                          |                ✅                |                  ✅                  |                   ✅                   |                        ❌                        |
| Update pinned tags forward                                           | ✅<br/>major, minor, &amp; patch |                  ✅                  |                   ❌                   |                        ❌                        |
| Cool-off / minimum-release-age gate                                  |                ✅                |                  ✅                  |                   ❌                   |                        ❌                        |
| Pins `actions/checkout` `with.ref` (cross-repo checkout)             |                ✅                |                  ❌                  |                   ❌                   |                        ❌                        |
| Pins Reusable Workflow refs (`org/repo/.github/workflows/x.yml@ref`) |                ❌                |                  ✅                  |                   ❌                   |                ❌<br/>audit only                 |
| Pins Docker/OCI image refs to `sha256:` digests                      |                ✅                |                  ❌                  |                   ❌                   |                ❌<br/>audit only                 |
| Pins pre-commit hook `rev:` to commit SHA                            |                ✅                |                  ❌                  |                   ❌                   |                ❌<br/>audit only                 |
| Skip-list / allow-list for specific actions                          |                ✅                |                  ✅                  |                   ✅                   |                        ✅                        |
| Config file support                                                  |      ✅<br/>TOML/PyProject       |        ✅<br/>`.pinact.yaml`         |         ❌<br/>CLI flags only          |               ✅<br/>`zizmor.yml`                |
| Usable as an importable library (not just CLI)                       |                ✅                |                  ❌                  |                   ❌                   |                        ❌                        |
| Async/concurrent API calls with rate-limit backoff                   |                ✅                | ⚠️<br/>undocumented backoff strategy |                   ❌                   |                 N/A<br/>unknown                  |
| Preserve YAML comments/formatting                                    |                ✅                |                  ✅                  |                   ✅                   |                        ✅                        |
| Distribution                                                         |       Python Wheel / PyPI        | Static binary<br/>(aqua/goreleaser)  |                  npm                   | PyPI / Rust binary / pre-commit hook / GH Action |
| pre-commit hook                                                      |        ❌<br/>Coming Soon        |                  ❌                  |                   ✅                   |                        ✅                        |
| GitHub Action                                                        |        ❌<br/>Coming Soon        |                  ❌                  | ✅<br/>via `ensure-sha-pinned-actions` |                        ✅                        |
| GitHub annotations                                                   |                ❌                |                  ❌                  |                   ❌                   |                        ✅                        |
| Generate SARIF                                                       |                ❌                |                  ✅                  |                   ❌                   |                        ✅                        |
| License                                                              |            Apache 2.0            |                 MIT                  |                  MIT                   |                       MIT                        |

## Pros and Cons

### pin-actions

| Pros                                                                                              | Cons                                                                                       |
| ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| Only tool of the four covering SHA pins **and** Docker image digests **and** pre-commit hook revs | Requires a Python runtime; not a single static binary like `pinact`                        |
| `--exclude-newer` cool-off period guards against same-day/1-day supply-chain compromises          | Does not pin Reusable Workflow refs (`org/repo/.github/workflows/x.yml@ref`)               |
| Async I/O + LRU cache + semaphore rate-limiting is fast on large monorepos with many workflows    | Newer/smaller community than `pinact` or `zizmor`; fewer GitHub stars, less battle-testing |
| Precision-preserving version updates (`v4` stays `v4`, `v4.0.5` keeps full precision)             |                                                                                            |
| Usable as a Python library (`pin_actions.run()`)                                                  |                                                                                            |

### pinact

| Pros                                                                                           | Cons                               |
| ---------------------------------------------------------------------------------------------- | ---------------------------------- |
| Single static Go binary                                                                        | No Docker/OCI image digest pinning |
| Pins Reusable Workflow refs, which `pin-actions` and `pin-github-action` do not                | No pre-commit hook pinning         |
| Built-in minimum-release-age cooldown (`-min-age`/`-verify-min-age`)                           | —                                  |
| `--branch-to-tag` lets you opt-in to converting branch refs (`@main`) to the latest stable tag |                                    |

### mheap/pin-github-action

| Pros                                                         | Cons                                                                                            |
| ------------------------------------------------------------ | ----------------------------------------------------------------------------------------------- |
| Simple, minimal, easy to read/audit (small Node.js codebase) | No version-update mode (`--update`) — only pins/re-resolves existing refs, never bumps versions |
|                                                              | No Docker image pinning, no Reusable Workflow pinning, no cooldown gating                       |
|                                                              | Smallest community of the three fixers (183 stars vs. 1.2k `pinact`); slower release cadence    |
|                                                              | Requires Node.js runtime                                                                        |

### zizmor

| Pros                                                                                                                                                               | Cons                                                                                                                                                         |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Detects far more than unpinned actions: template injection, credential leakage/persistence, excessive permissions, impostor commits, confusable git refs, and more | Pinning is not its primary focus — `--fix` only covers `unpinned-uses` (and a couple other audits), not Docker image digests or pre-commit hook revs         |
| Rust binary — fast, no runtime dependency                                                                                                                          | Broader scope means noisier output if you only care about pinning                                                                                            |
| Actively maintained, well-sponsored (Trail of Bits, Grafana Labs, Kusari)                                                                                          | Does not distinguish "already pinned but tag drifted" the way fixer tools' re-resolution does — `--fix` pins unpinned refs but doesn't re-resolve moved tags |
| Covers Dependabot config and pre-commit config, not just Actions workflows                                                                                         | No cooldown/minimum-release-age gating                                                                                                                       |
|                                                                                                                                                                    | Cannot pin Docker image digests (flags them via `unpinned-images`, no auto-fix)                                                                              |

## Anything Else Worth Noting

- **Fork Network / impostor commits (§3.1 of the [Threat Model](threat-model.md)):** none of the four tools verify *provenance* of a SHA — pinning to a SHA only stops tag-hijacking, not a malicious fork's SHA being pinned in the first place. `zizmor`'s `impostor-commit` audit is the closest thing to a mitigation here; combine it with manual PR review of any new SHA.
- **Renovate/Dependabot overlap:** `pinact`'s README explicitly notes it complements (not replaces) Renovate's `helpers:pinGitHubActionDigestsToSemver` preset, because Renovate cannot pin actions *before* a PR merges. The same reasoning applies to `pin-actions` — run it as a pre-commit hook or CI gate so PRs land already pinned, and let Renovate/Dependabot handle the ongoing version-bump PRs afterward.

## See Also

- [Threat Model](threat-model.md) — The supply-chain attack model this tool defends against
- [Architecture Overview](architecture.md) — Container image pinning and concurrency model details
