# Pin Non-Standard Refs

Pin composite actions, cross-repo checkout refs, and reusable workflows —
cases beyond a plain `uses:` in a workflow job.

## Composite Actions

`pin-actions` applies the same scan and the same `uses:` resolution to composite `action.yml`/`action.yaml` files,
because `jobs.<id>.steps` and `runs.steps` are structurally identical `steps:` lists.
The default `--paths` already includes `**/action.yml` and `**/action.yaml`.

Point `--paths` at your repo root to pin workflows and composite actions in one pass:

```bash
pin-actions --paths . --github-token $GITHUB_TOKEN
```

Local composite steps (`uses: ./path/to/action`) are always skipped — there is no remote SHA to resolve.

## Checking Out Another Repo

When a step uses `actions/checkout` with `with.repository`, `pin-actions` also pins its `with.ref` —
written as a bare SHA, since `with.ref` takes no `repo@` prefix.

Before:

```yaml
- name: Checkout another repo at a tag
  uses: actions/checkout@v4
  with:
    repository: owner/other-repo
    ref: v3.0.0
```

After:

```yaml
- name: Checkout another repo at a tag
  uses: actions/checkout@a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0  # v4
  with:
    repository: owner/other-repo
    ref: 0f1e2d3c4b5a69788796a5b4c3d2e1f0a9b8c7d6  # v3.0.0
```

### Scope

Both conditions must hold:

- The step's `uses` value starts with `actions/checkout`.
- The step has both a `with.repository` and a `with.ref`.

A `with.ref` without a sibling `with.repository` refers to the current repository,
whose identity is not available to the tool, so it is skipped.

## Reusable Workflows

Reusable workflow refs are pinned by the same `uses:` resolution as any other action.
The workflow path segment is treated as part of the repository identifier, so no special-casing is needed:

```yaml
jobs:
  call-reusable:
    uses: octo-org/example-repo/.github/workflows/reusable.yml@a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0 # v1
```

Already-pinned reusable workflow refs are re-resolved and rewritten if the recorded tag has moved,
exactly like any other `uses:` entry.

## Version Constraints

`--update`, `--full-version`, and `--exclude-newer` apply uniformly to all three cases above.
See [Update Pinned Tags](./update-pinned-tags.md).

## See Also

- [Update Pinned Tags](./update-pinned-tags.md) — version constraint recipes
- [Pin Container Images](./pin-container-images.md) — `docker://`, job, and service containers
- [Reference: core module](../reference/core.md) — `pin_file()` details
