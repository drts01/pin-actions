# Pin Composite Actions

pin-actions treats composite `action.yml`/`action.yaml` files identically to workflow files — same scan, same `uses:` resolution, same re-pin behavior.

## Why It Works

`pin-actions` scans for `**/*.yml` and `**/*.yaml` under `--path` (no distinction between `.github/workflows/*.yml` and a composite action's `action.yml`). Internally, it walks the parsed YAML tree looking for any `uses:` key, regardless of whether it's nested under `jobs.<id>.steps` (workflow) or `runs.steps` (composite action). Both shapes are structurally identical `steps:` lists, so the same logic pins both.

## Example

### Before (`action.yml`)

```yaml
name: My Composite Action
runs:
  using: composite
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-node@v4
      with:
        node-version: "20"
    - run: npm ci
      shell: bash
```

### After

```yaml
name: My Composite Action
runs:
  using: composite
  steps:
    - uses: actions/checkout@a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b  # v4
    - uses: actions/setup-node@f1e2d3c4b5a6f7e8d9c0b1a2f3e4d5c6b7a8f9e  # v4
      with:
        node-version: "20"
    - run: npm ci
      shell: bash
```

## Scanning Both Workflows and Actions

Point `--path` at your repo root (or any directory containing both) to pin everything in one pass:

```bash
pin-actions --path . --github-token $GITHUB_TOKEN
```

Or scan them separately if you want isolated dry-runs:

```bash
pin-actions --path .github/workflows --dry-run
pin-actions --path . --dry-run  # includes any action.yml/action.yaml found
```

## Caveats

- Local/relative composite steps (`uses: ./path/to/action`) are always skipped — there's no remote SHA to resolve.
- `with.ref` pinning for `actions/checkout` (see [Checkout Another Repo](checkout-another-repo.md)) applies inside composite actions the same way it does in workflows.

## See Also

- [Checkout Another Repo](checkout-another-repo.md)
- [Update Pinned Tags](update-pinned-tags.md)
- [Reference: core module](../reference/core.md) — `pin_file()` function details
