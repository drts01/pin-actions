# Checkout Another Repo

Use pin-actions to pin `actions/checkout` steps that check out repositories other than the current one.

## Pinning `with.ref`

When you use `actions/checkout` with `with.repository` to check out a different repository, you can also pin its `with.ref`:

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

## Scope

Pin-actions **only** pins `with.ref` when:

- The step uses `actions/checkout` (or a version/variant of it)
- **Both** `with.repository` and `with.ref` are present
- The action's `uses` value starts with `actions/checkout`

Steps without a `with.repository` sibling are skipped because the current-repo context is not available to the tool.

## Version Constraints

The same `--update` flags apply to `with.ref` pins:

```bash
# Re-resolve the tag in with.ref
pin-actions --github-token $GITHUB_TOKEN

# Move to latest version within major constraint
pin-actions --update minor --github-token $GITHUB_TOKEN
```

## See Also

- [Tutorial: Getting Started](../tutorials/getting-started.md)
- [Reference: core module](../reference/core.md) — `pin_file()` function details
