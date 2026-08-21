# Run in CI

Schedule pin-actions to keep pins up-to-date automatically via a GitHub Actions workflow.

## Weekly Update Workflow

```yaml
name: Update pinned actions

on:
  schedule:
    - cron: '0 0 * * 0'  # Weekly
  workflow_dispatch:  # Manual trigger

jobs:
  pin:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v3
        with:
          python-version: '3.14'

      - name: Run pin-actions
        run: uv run pin-actions --github-token ${{ secrets.GITHUB_TOKEN }}

      - name: Create Pull Request
        uses: peter-evans/create-pull-request@v6
        with:
          commit-message: 'ci: update pinned actions'
          title: 'Update pinned GitHub Actions'
          branch: pin-actions-update
```

## Preview Changes in a PR Check

Add a `--diff` step to a pull-request-triggered workflow to surface pin drift without writing files:

```yaml
on: pull_request

jobs:
  check-pins:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv run pin-actions --diff --github-token ${{ secrets.GITHUB_TOKEN }}
```

## See Also

- [Getting Started](../tutorials/getting-started.md) — first-run tutorial
- [Reference: CLI](../reference/cli.md) — full flag list
- [How-to: Update pinned tags](./update-pinned-tags.md) — version constraint recipes
