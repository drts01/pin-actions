# Verify SHA Provenance

Reject commit SHAs that do not belong to the repository the ref names.

Pinning to a commit SHA defeats tag hijacking.
It does not defeat an attacker who hands you a SHA that lives in a *fork* of the action.
GitHub serves fork commits from the upstream repository's API namespace,
so `actions/checkout@<attacker-sha>` resolves successfully and reads as legitimate in code review.

`--provenance` gates that case at the moment the SHA is written.

## Warn on Unverifiable SHAs

Log a warning and continue:

```bash
pin-actions --provenance warn --github-token $GITHUB_TOKEN
```

## Reject Unverifiable SHAs

Raise `UnverifiedProvenanceError` and leave the file untouched:

```bash
pin-actions --provenance strict --github-token $GITHUB_TOKEN
```

Use `strict` in CI, where a failed job is the desired outcome.
Use `warn` for a first pass over an existing repository, where pre-existing pins may be unverifiable for benign reasons.

## What "Verified" Means

`pin-actions` checks, in order, stopping at the first match:

1. `GET /commits/{sha}/branches-where-head` — the SHA is the HEAD of some branch.
2. `GET /commits/{sha}/pulls` — the SHA is the head commit or merge commit of a **merged** pull request
   into this repository.
3. The cached tag list — the SHA is the commit of some tag.

A match means a maintainer of the named repository put the SHA there: they pushed the branch, created the tag,
or merged the pull request.

Two kinds of pull request deliberately do not count:

- **Open or closed-unmerged pull requests.**
  Anyone can open a pull request from a fork,
  and GitHub then serves its commits from the upstream repository through `refs/pull/N/head`.
  Counting it would let an attacker verify their own impostor commit.
- **Commits in the middle of a merged pull request.**
  An attacker can push a malicious commit, revert it in a later commit, and get the pull request squash-merged.
  The malicious commit is listed under the merged pull request but never landed.
  Only the pull request's final head commit, which the reviewer saw, and its merge commit count.

No match means **not confirmed**, not **proven malicious**.
A legitimate commit that is no longer a branch head, carries no tag,
and was never a merged pull request's head reads as unverified.
This is a check against the GitHub API, not cryptographic attestation.

## Blind Spot: Pins Without a Trailing Comment

Provenance is verified when `pin-actions` **writes** a SHA.
An already-pinned ref carrying no trailing tag comment is skipped before verification ever runs:

```yaml
- uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0
```

There is no recorded tag to re-resolve against,
so the entry is left alone and `pin-actions --provenance strict` reports no modifications.

This is the shape a hand-edited impostor SHA takes.
Treat the trailing comment as load-bearing: let `pin-actions` write the pins so the comment is always present,
and review any pin that arrives without one.

## Cost

Verification adds up to two GitHub API calls per unique `(repo, sha)` pair, stopping at the first match,
plus the repository's tag list.
The tag list is fetched once per repository, up to 1,000 tags, and shared with tag resolution.
Results are cached for the lifetime of the client,
so a monorepo pinning `actions/checkout` fifty times pays for it once.

The default is `off`.

## From Python

`run()` reads `settings.provenance`:

```python
import asyncio

from pin_actions import Settings, run


async def main():
    settings = Settings(github_token="ghp_xxxx", provenance="strict")
    await run(settings)


asyncio.run(main())
```

`pin_file()` takes the mode directly as `provenance_mode="off" | "warn" | "strict"`.

## See Also

- [Threat Model §3.1](../explanation/threat-model.md#31-github-fork-network-vulnerabilities-imposter-commits) —
    the fork-network attack this defends against
- [Reference: errors](../reference/errors.md) — `UnverifiedProvenanceError` attributes
- [Run in CI](./run-in-ci.md) — gating a pull request on provenance
