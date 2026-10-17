# Update Pinned Tags

By default, `pin-actions` re-resolves already-pinned tags on every run and rewrites the SHA if the tag has moved.
`--update` moves pins forward to newer versions instead.

## Re-resolve Tags (Default)

Without `--update`, the tag recorded in the trailing comment is resolved fresh on every run.
If `actions/checkout@v4` now points to a different commit, the SHA is rewritten:

```bash
pin-actions --github-token $GITHUB_TOKEN
```

## Move Pins Forward

| Strategy         | Bound              | Example             |
| ---------------- | ------------------ | ------------------- |
| `--update major` | none               | `v4.0.5` → `v9.1.2` |
| `--update minor` | same major         | `v4.0.5` → `v4.9.0` |
| `--update patch` | same `major.minor` | `v4.2.3` → `v4.2.9` |

```bash
pin-actions --update minor --github-token $GITHUB_TOKEN
```

Branch refs never parse as a version, so `--update` has no effect on them.
They are always re-resolved against the branch name.

## Precision Preservation

By default the rewritten comment matches the original's precision, so `v4` stays `v4`.
`--full-version` records the full resolved tag instead —
see the [precision table](../reference/cli.md#precision-preservation-full-version):

```bash
pin-actions --update minor --full-version --github-token $GITHUB_TOKEN
```

## Cool-off Period

A newly published tag may carry an undiscovered compromise.
`--exclude-newer` refuses to auto-select a tag younger than the cutoff, giving detection tooling time to catch up.
This mirrors npm's `minimumReleaseAge`, pnpm, and Renovate.

```bash
pin-actions --update minor --exclude-newer "7 days" --github-token $GITHUB_TOKEN
```

Accepted formats:

- RFC 3339 timestamp — `2006-12-02T02:07:43Z` (absolute cutoff)
- ISO 8601 duration — `P7D`, `PT24H`, `P1W` (relative to now)
- Friendly duration — `7 days`, `24 hours`, `1 week` (case-insensitive)

If every candidate is too new, `pin-actions` warns and leaves the pin unchanged.

Cool-off applies only to `--update`.
Exact tag re-resolution is unaffected,
because a tag you named explicitly is not auto-selected and carries different risk.

## Handling Missing Tags

If no tag satisfies the constraint, `pin-actions` logs a warning
and leaves the entry unchanged rather than dropping the pin or aborting the batch:

```text
WARNING:pin_actions.core: no tag matching version constraint for actions/checkout@v4.0.5; leaving pinned as-is
```

## See Also

- [Reference: CLI](../reference/cli.md) — flag matrix and precision table
- [Explanation: Design Decisions](../explanation/design-decisions.md) — version constraint rationale
- [Verify SHA Provenance](./verify-provenance.md) — reject SHAs that do not belong to the named repository
