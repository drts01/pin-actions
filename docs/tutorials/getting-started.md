# Getting Started

Learn how to install and run pin-actions for the first time.

## Installation

Use `uv` (recommended) or pip:

```bash
uv add pin-actions
```

Or via pip:
```bash
pip install pin-actions
```

## First Run: Dry-Run

Before making any changes, always preview what pin-actions will do with `--dry-run`:

```bash
export GITHUB_TOKEN=ghp_xxxx
pin-actions --dry-run --path .github/workflows
```

This parses your workflows, resolves mutable refs to SHAs, and prints what **would** be changed — without writing files.

## Apply the Changes

Once you're confident in the changes:

```bash
pin-actions --path .github/workflows --github-token $GITHUB_TOKEN
```

Check `git diff` to verify the changes, then commit:

```bash
git add .github/workflows/
git commit -m "fix(ci): pin GitHub Actions to commit SHAs"
```

## Integrate into CI

Add pin-actions to your workflow to keep pins up-to-date:

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

## Next Steps

- Learn how to [update already-pinned tags](../how-to/update-pinned-tags.md)
- Explore [library usage](../how-to/use-as-a-library.md) for programmatic access
- Check the [CLI reference](../reference/cli.md) for all available options
