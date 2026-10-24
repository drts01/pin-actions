# Getting Started

Learn how to install and run pinref for the first time.

## Installation

Use `uv` (recommended) or pip:

```bash
uv add pinref
```

Or via pip:

```bash
pip install pinref
```

## First Run: Dry-Run

Before making any changes, always preview what pinref will do with `--dry-run`:

```bash
export GITHUB_TOKEN=ghp_xxxx
pinref --dry-run --paths .github/workflows
```

This parses your workflows, resolves mutable refs to SHAs, and prints what **would** be changed — without writing files.

## Apply the Changes

Once you're confident in the changes:

```bash
pinref --paths .github/workflows --github-token $GITHUB_TOKEN
```

Check `git diff` to verify the changes, then commit:

```bash
git add .github/workflows/
git commit -m "fix(ci): pin GitHub Actions to commit SHAs"
```

## Next Steps

- Work through [Pin an Existing Repository End to End](pin-an-existing-repo.md) —
    actions, images, and provenance in one pass
- Learn how to [update already-pinned tags](../how-to/update-pinned-tags.md)
- Explore [library usage](../how-to/use-as-a-library.md) for programmatic access
- Check the [CLI reference](../reference/cli.md) for all available options
- Automate pinning with [scheduled runs in CI](../how-to/run-in-ci.md)
