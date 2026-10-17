# pin-actions

<!-- --8<-- [start:overview] -->
Pin every mutable reference in your CI to an immutable digest — Action refs, reusable workflows, cross-repo checkouts,
container images, and pre-commit hooks —
then verify that each resolved commit actually belongs to the repository it claims to.

Works as both a **CLI tool** and an **importable library**,
with dedicated commands for GitHub workflow/action files and pre-commit configuration.

## What Separates pin-actions

SHA-pinning `uses:` is a solved problem; several good tools do it.
`pin-actions` exists because pinning `uses:` is **necessary and insufficient**.

✅ pins or gates · ⚠️ reports only, no fix · ❌ not covered.

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

Full detail, including where `pin-actions` is the wrong choice,
is in [Comparing pin-actions to Similar Tools](https://drts01.github.io/pin-actions/explanation/comparison/).

### 1. Provenance verification at write time

Pinning to a commit SHA defeats tag hijacking.
It does **not** defeat an attacker who hands you a SHA that lives in a *fork* of the action.
GitHub serves fork commits from the upstream repository's API namespace,
so `actions/checkout@<attacker-sha>` resolves cleanly and reads as legitimate in review.

`--provenance strict` refuses to write a SHA that is not reachable from a real branch, tag,
or pull request on the named repository; `--provenance warn` logs it instead.
Static analyzers report impostor commits after they land.
`pin-actions` is the only fixer that blocks them at the moment of writing.
See [Verify SHA Provenance](https://drts01.github.io/pin-actions/how-to/verify-provenance/).

### 2. The widest pinning surface, without reformatting your YAML

Every row above is executable code.
A repository can be 100% SHA-pinned on `uses:` and still run an attacker-controlled service container,
check out an attacker-controlled branch of a sibling repository, or execute an unpinned pre-commit hook in CI.
Cross-repo `with.ref` and pre-commit revisions are covered by `pin-actions` alone.

`pin-actions` round-trips YAML through `yamlrocks` and rewrites only the mutated nodes,
so a pin-only change produces a pin-only diff.
[`ratchet`](https://github.com/sethvargo/ratchet), the closest alternative,
documents that it normalizes all indentation to two spaces —
on an established repository that turns a small security change into a whole-file diff.
See [Pin Non-Standard Refs](https://drts01.github.io/pin-actions/how-to/pin-non-standard-refs/)
and [Pin Container Images](https://drts01.github.io/pin-actions/how-to/pin-container-images/).

### 3. A cool-off gate on every forward update

`--exclude-newer` (`7 days`, `P7D`, or an RFC 3339 timestamp) refuses to adopt a release
that is younger than the cutoff, so `--update` never pulls in a same-day or one-day compromise
before detection tooling catches up.

### 4. Library-first, not CLI-only

`pin_actions.run()` is a supported entry point with a shared client, connection pooling, and caching across calls,
so fleet automation and policy engines can embed pinning instead of shelling out.
See [Multi-Repo Automation](https://drts01.github.io/pin-actions/how-to/multi-repo-automation/).

## Features

- Resolves mutable refs (branches, tags, short SHAs) to full commit SHAs
- Updates already-pinned refs: re-resolves the tag/branch and rewrites SHA if it has moved
- Pins `actions/checkout` `with.ref` parameters (checkout-another-repo workflows)
- Resolves `docker://` steps, job containers, and service containers to `sha256:` digests
- Verifies SHA provenance against the named repository (`--provenance warn|strict`)
- Enforces a minimum release age with `--exclude-newer`
- Skips local actions (`./...`)
- Thread-safe async/concurrent request handling with rate-limit backoff
- No-op when nothing has changed
- Preserves comments and formatting
- Optional `--update` to move pinned tags forward within version constraints

## Quick Start

```bash
# Install
uv add pin-actions

# Run with GitHub token
pin-actions --paths .github/workflows --github-token $GITHUB_TOKEN

# Dry-run to see what would change
pin-actions --dry-run

# Reject any SHA that is not reachable from a real ref on the named repo
pin-actions --provenance strict

# Move tags forward, but ignore releases younger than 7 days
pin-actions --update minor --exclude-newer "7 days"
```

## What It Does

Before:

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    container:
      image: python:3.14-slim
    services:
      redis:
        image: redis:7
    steps:
      - uses: actions/checkout@v4
        with:
          repository: my-org/other-repo
          ref: main
      - uses: actions/setup-python@main
```

After:

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    container:
      image: python@sha256:7d1e2c3b4a5f6e7d8c9b0a1f2e3d4c5b6a7f8e9d0c1b2a3f4e5d6c7b8a9f0e1d  # 3.14-slim
    services:
      redis:
        image: redis@sha256:1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b  # 7
    steps:
      - uses: actions/checkout@a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0  # v4
        with:
          repository: my-org/other-repo
          ref: 0f1e2d3c4b5a69788796a5b4c3d2e1f0a9b8c7d6  # main
      - uses: actions/setup-python@f1e2d3c4b5a6f7e8d9c0b1a2f3e4d5c6b7a8f9e0  # main
```

<!-- --8<-- [end:overview] -->

## Documentation

📖 **[Full Documentation](https://drts01.github.io/pin-actions/)**

- **[Tutorials](https://drts01.github.io/pin-actions/tutorials/getting-started/)** — Getting started, first pin
- **[How-To Guides](https://drts01.github.io/pin-actions/how-to/update-pinned-tags/)** — Common tasks and workflows
- **[Reference](https://drts01.github.io/pin-actions/reference/cli/)** — Full API and CLI documentation
- **[Explanation](https://drts01.github.io/pin-actions/explanation/architecture/)** — Design, architecture,
  and rationale
- **[Threat Model](https://drts01.github.io/pin-actions/explanation/threat-model/)** —
  The supply-chain attack model this tool defends against
- **[Comparison with Similar Tools](https://drts01.github.io/pin-actions/explanation/comparison/)** —
  How `pin-actions` stacks up against ratchet, pinact, Updatecli, pin-github-action, and zizmor

## Development

- **Lint & test**: `prek run -a` (ruff, interrogate, pytest)
- **Docs**: `zensical build --strict`
- **Contributing**: See [CONTRIBUTING.md](CONTRIBUTING.md)

## License

[Apache 2.0](LICENSE)
