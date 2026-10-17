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
2. `GET /commits/{sha}/pulls` — the SHA belongs to a pull request based on this repository.
3. The cached tag list — the SHA is the commit of some tag.

A match means the SHA is reachable from a real ref on the named repository.

No match means **not confirmed**, not **proven malicious**.
A legitimate commit whose branch was deleted and whose pull request was never opened against the upstream reads
as unverified.
This is reachability against the GitHub API, not cryptographic attestation.

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

Verification adds one GitHub API call per unique `(repo, sha)` pair.
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
