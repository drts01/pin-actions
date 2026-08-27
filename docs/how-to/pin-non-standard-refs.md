# Pin Non-Standard Refs

Pin composite actions and cross-repo checkout refs — cases beyond a plain `uses:` in a workflow job.

## Composite Actions

pin-actions treats composite `action.yml`/`action.yaml` files identically to workflow files — same scan, same `uses:` resolution, same re-pin behavior.

`pin-actions` scans for `**/*.yml` and `**/*.yaml` under `--path` (no distinction between `.github/workflows/*.yml` and a composite action's `action.yml`). Internally, it walks the parsed YAML tree looking for any `uses:` key, regardless of whether it's nested under `jobs.<id>.steps` (workflow) or `runs.steps` (composite action). Both shapes are structurally identical `steps:` lists, so the same logic pins both.

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

### After (`action.yml`)

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

### Scanning Both Workflows and Actions

Point `--path` at your repo root (or any directory containing both) to pin everything in one pass:

```bash
pin-actions --path . --github-token $GITHUB_TOKEN
```

Or scan them separately if you want isolated dry-runs:

```bash
pin-actions --path .github/workflows --dry-run
pin-actions --path . --dry-run  # includes any action.yml/action.yaml found
```

### Caveats

- Local/relative composite steps (`uses: ./path/to/action`) are always skipped — there's no remote SHA to resolve.
- `with.ref` pinning for `actions/checkout` (below) applies inside composite actions the same way it does in workflows.

## Checking Out Another Repo

When you use `actions/checkout` with `with.repository` to check out a different repository, pin-actions also pins its `with.ref`.

### Before

```yaml
jobs:
  build:
    steps:
      - name: Checkout this repo
        uses: actions/checkout@v4

      - name: Checkout another repo at a tag
        uses: actions/checkout@v4
        with:
          repository: owner/other-repo
          ref: v3.0.0
```

### After

```yaml
jobs:
  build:
    steps:
      - name: Checkout this repo
        uses: actions/checkout@a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b  # v4

      - name: Checkout another repo at a tag
        uses: actions/checkout@a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b  # v4
        with:
          repository: owner/other-repo
          ref: d9e8f7g6h5i4j3k2l1m0n9o8p7q6r5s4t3u2v1w0  # v3.0.0
```

### Scope

Pin-actions **only** pins `with.ref` when:

- The step uses `actions/checkout` (or a version/variant of it)
- **Both** `with.repository` and `with.ref` are present
- The action's `uses` value starts with `actions/checkout`

Steps without a `with.repository` sibling are skipped because the current-repo context is not available to the tool.

### Version Constraints

The same `--update` flags apply to `with.ref` pins:

```bash
# Re-resolve the tag in with.ref
pin-actions --github-token $GITHUB_TOKEN

# Move to latest version within major constraint
pin-actions --update minor --github-token $GITHUB_TOKEN
```

## See Also

- [Update Pinned Tags](update-pinned-tags.md)
- [Reference: core module](../reference/core.md) — `pin_file()` function details
