# Run in CI

Schedule pin-actions to keep pins up-to-date automatically via a GitHub Actions workflow.

Pass the token through `env:` rather than on the command line,
so it does not appear in the runner's process list or in `set -x` output.

## Weekly Update Workflow

```yaml
name: Update pinned actions

on:
  schedule:
    - cron: '0 0 * * 0'
  workflow_dispatch: {}

permissions: {}

jobs:
  pin:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false

      - uses: astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d # v10.0.1
        with:
          python-version: '3.14'

      - name: Run pin-actions
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: uv run pin-actions

      - name: Create Pull Request
        uses: peter-evans/create-pull-request@22a9089034f40e5a961c8808d113e2c98fb63676 # v7
        with:
          commit-message: 'ci: update pinned actions'
          title: Update pinned GitHub Actions
          branch: pin-actions-update
```

## Preview Changes in a PR Check

`--diff` prints pin drift without writing files.
It does **not** fail the job on drift — it exits non-zero only when a file cannot be processed.
To block the merge, compare the working tree afterwards:

```yaml
on: pull_request

permissions: {}

jobs:
  check-pins:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d # v10.0.1
      - name: Check for pin drift
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          uv run pin-actions
          git diff --exit-code
```

## Reject Impostor-Commit SHAs

`--provenance strict` refuses to write a SHA that is not a branch head, tag,
or merged pull request commit on the named repository.
Add it to either workflow above to gate fork-network commits at write time:

```yaml
run: uv run pin-actions --provenance strict
```

## See Also

- [Getting Started](../tutorials/getting-started.md) — first-run tutorial
- [Reference: CLI](../reference/cli.md) — full flag list
- [How-to: Update pinned tags](./update-pinned-tags.md) — version constraint recipes
- [Threat Model §3.1](../explanation/threat-model.md#31-github-fork-network-vulnerabilities-imposter-commits) —
    why provenance verification matters
