# Update Pinned Tags

By default, pin-actions re-resolves already-pinned tags on every run and updates the SHA if the tag has moved. You can also use version constraints to move pins forward intelligently.

## Re-resolving Tags (Default)

Without any `--update` flag, a tag like `v4` is resolved fresh on every run. If `actions/checkout@v4` now points to a different commit, the SHA is updated:

```bash
pin-actions --github-token $GITHUB_TOKEN
```

This mirrors the behavior of [mheap/pin-github-action](https://github.com/mheap/pin-github-action).

## Moving to Latest Version

Use `--update major`, `--update minor`, or `--update patch` to move pins to newer versions:

### `--update major` — Absolute latest tag

Crosses major boundaries. A pin to `v4.0.5` can move to `v9.1.2`:

```bash
pin-actions --update major --github-token $GITHUB_TOKEN
```

### `--update minor` — Latest within same major

Stays within the same major version. A pin to `v4.0.5` moves to `v4.9.0`, never `v5.x`:

```bash
pin-actions --update minor --github-token $GITHUB_TOKEN
```

### `--update patch` — Latest within same major.minor

Stays within the same major.minor. A pin to `v4.2.3` moves to `v4.2.9`, never `v4.3.x`:

```bash
pin-actions --update patch --github-token $GITHUB_TOKEN
```

## Precision Preservation

Use `--full-version` to record the full tag version instead of matching the original's precision — see [Reference: CLI](../reference/cli.md#precision-preservation-full-version) for the precision table:

```bash
pin-actions --update minor --full-version --github-token $GITHUB_TOKEN
```

## Cool-off Period (Supply-Chain Risk Mitigation)

When using `--update`, a newly published tag may carry undiscovered malware (zero-day or 1-day compromise). Use `--exclude-newer` to skip tags younger than a cutoff, giving the security community time to scan and detect attacks before adoption.

This mirrors package managers like npm (`minimumReleaseAge`), pnpm, and Renovate:

```bash
pin-actions --update minor --exclude-newer "7 days" --github-token $GITHUB_TOKEN
```

Accepted formats:

- **RFC 3339 timestamp:** `2006-12-02T02:07:43Z` — absolute cutoff
- **ISO 8601 duration:** `P7D`, `PT24H`, `P1W` — relative to now
- **Friendly duration:** `7 days`, `24 hours`, `1 week` — intuitive and case-insensitive

When set, only tags older than the cutoff are considered for auto-selection. If all candidates are too new, pin-actions warns and leaves the pin unchanged.

**Note:** Cool-off applies *only* to `--update` mode. Exact tag re-resolution (the default) is unaffected, because explicit user-named tags are not auto-selected and thus carry different risk semantics.

## Branch refs

Branch refs (e.g., `main`, `develop`) never parse as a version, so `--update` has no effect on them — they're always re-resolved against the branch name, the same as the default no-constraint path:

```bash
pin-actions --update minor --github-token $GITHUB_TOKEN
```

## Handling Missing Tags

If no tag on the remote satisfies the constraint, pin-actions warns to stderr and leaves the entry unchanged:

```
pin-actions: warning: no tag matching version constraint for actions/checkout@v4.0.5; leaving pinned as-is
```

This is safer than silently dropping a pin or raising an error mid-batch.

## See Also

- [Reference: CLI](../reference/cli.md) — Flag matrix and precision table
- [Explanation: Design Decisions](../explanation/design-decisions.md) — Version constraint rationale
