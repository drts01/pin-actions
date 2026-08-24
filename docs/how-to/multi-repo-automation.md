# Multi-Repo Automation

!!! note "Library usage example"
    This script is a real-world example of using `pin_actions` as a library — see [Use as a Library](./use-as-a-library.md) for the core API it builds on. The library calls are isolated in `_try_pin()`: `Settings(...)` + `await run(settings, client=client)`.

## Overview

The `update_repos.py` script:

- Clones repositories (shallow, for speed)
- Scans `.github/workflows` and `.github/actions` directories
- Pins all mutable action refs to their commit SHAs
- Optionally commits, pushes, and opens PRs via the `gh` CLI
- **Idempotent** — safe to re-run; force-pushes updates to the same branch and reuses the existing PR instead of erroring
- Processes repos concurrently while sharing a single GitHub API client (connection pooling + in-memory cache)

Perfect for organizations with many repositories sharing common actions like `actions/checkout@v4`.

## Prerequisites

- `gh` CLI, authenticated (`gh auth login`) — used for cloning and (with `--push`) PR creation
- `git` CLI — used for committing and pushing
- `uv` — invokes the script with its dependencies; no manual venv/install needed
- `GITHUB_TOKEN` env var or `--github-token` flag (optional — only needed if not using `gh auth login`)

## Installation

No installation needed — the script is self-contained via `uv` (uses inline dependencies).

```bash
curl -O https://raw.githubusercontent.com/drts01/pin-actions/main/scripts/update_repos.py
chmod +x update_repos.py
./update_repos.py --repos org/repo1 --repos org/repo2 --dry-run
```

Or from a cloned `pin-actions` repo:

```bash
uv run --with-editable . scripts/update_repos.py --repos org/repo1 --repos org/repo2 --dry-run
```

## Basic Usage

### Dry-run on one repository

```bash
uv run --with-editable . scripts/update_repos.py --repos octocat/Hello-World --dry-run
```

Output shows which files would be modified without making any changes.

### Dry-run on multiple repositories

```bash
uv run --with-editable . scripts/update_repos.py --repos org/repo1 --repos org/repo2 --repos org/repo3 --dry-run
```

### Pin and commit (without pushing)

```bash
uv run --with-editable . scripts/update_repos.py --repos org/repo1 --repos org/repo2
```

Creates local branches (e.g. `pin-actions/org-repo1`) with commits but does not push.

### Pin, commit, push, and create PRs

```bash
uv run --with-editable . scripts/update_repos.py --repos org/repo1 --repos org/repo2 --push
```

Creates feature branches, pushes them, and opens PRs via `gh pr create`. Each repo's actual default branch (auto-detected) is used as the PR base.

### Load repositories from a file

```bash
cat > repos.txt << EOF
# My organization's repositories
org/service-a
org/service-b
org/infra  # This repo uses many GH Actions

# Infrastructure
org/terraform-modules
EOF

uv run --with-editable . scripts/update_repos.py --repos-file repos.txt --dry-run
```

Comments (`#`) and blank lines are ignored.

### Output in different formats

**Markdown** (for pasting into PR/issue bodies):
```bash
uv run --with-editable . scripts/update_repos.py --repos-file repos.txt --dry-run --format markdown
```

**JSON** (for machine processing):
```bash
uv run --with-editable . scripts/update_repos.py --repos-file repos.txt --dry-run --format json
```

**CSV/TSV** (for spreadsheet import):
```bash
uv run --with-editable . scripts/update_repos.py --repos-file repos.txt --dry-run --format csv > results.csv
```

### Save results to a file

```bash
uv run --with-editable . scripts/update_repos.py --repos-file repos.txt --dry-run --format json --output-file results.json
```

## Command-Line Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--repos` | repeated string | — | Repository (owner/repo); repeat for multiple |
| `--repos-file` | path | — | File with one owner/repo per line |
| `--github-token` | string | `GITHUB_TOKEN` env | GitHub token |
| `--dry-run` | flag | off | Print changes without writing, committing, or pushing |
| `--update` | choice | — | `major`/`minor`/`patch` (re-solve already-pinned tags) |
| `--full-version` | flag | off | Record full tag version (e.g. `v4.1.7` instead of `v4`) |
| `--exclude-newer` | string | — | Cool-off period (RFC 3339, ISO 8601 duration, or friendly); only with `--update` |
| `--concurrency` | int | 4 | Max concurrent repo clones |
| `--api-concurrency` | int | 5 | Max concurrent GitHub API requests |
| `--branch-prefix` | string | `pin-actions` | Feature branch prefix |
| `--base-branch` | string | repo's default | PR base branch; auto-detected per repo if unset |
| `--push` | flag | off | Push branch and open PR via `gh` |
| `--commit-message` | string | `chore: pin GitHub Actions to immutable commit SHAs` | Commit message and PR title |
| `--pr-body` | string | `Pinned by [pin-actions](https://github.com/drts01/pin-actions).` | Pull request body text |
| `--format` | choice | `table` | Output format: `table`, `markdown`, `json`, `csv`, `tsv` |
| `--output-file` | path | stdout | Write summary to file instead of stdout |
| `--host` | string | `github.com` | GitHub hostname; use for GHE Server (e.g. `github.example.com`) |
| `--verbose` / `-v` | int | 0 | Verbosity level 0–3: 0=warnings, 1=info, 2=debug, 3=debug+dependencies |

## Output

Default format (table):

```
REPO                       MODIFIED BRANCH                           BASE_BRANCH STATUS
────────────────────────────────────────────────────────────────────────────────────────
octocat/Hello-World        2        pin-actions/octocat-Hello-World main        OK
my-org/broken-yaml         0        —                                develop     ERROR: 1 file(s) failed
my-org/no-workflows        0        —                                main        OK
```

**Markdown format** (for PR/issue comments):

```markdown
| REPO | MODIFIED | BRANCH | BASE_BRANCH | PR_URL | STATUS |
| --- | --- | --- | --- | --- | --- |
| octocat/Hello-World | 2 | pin-actions/octocat-Hello-World | main | https://github.com/octocat/Hello-World/pull/123 | OK |
| my-org/broken-yaml | 0 | — | develop | — | ERROR: 1 file(s) failed |
| my-org/no-workflows | 0 | — | main | — | OK |
```

**JSON format** (full details, machine-readable):

```json
[
  {
    "repo": "octocat/Hello-World",
    "modified": [".github/workflows/ci.yml"],
    "error": null,
    "branch": "pin-actions/octocat-Hello-World",
    "base_branch": "main",
    "pr_url": "https://github.com/octocat/Hello-World/pull/123"
  },
  {
    "repo": "my-org/broken-yaml",
    "modified": [],
    "error": "1 file(s) failed",
    "branch": null,
    "base_branch": "develop",
    "pr_url": null
  }
]
```

Exit code: 0 if all repos succeeded, 1 if any failed.

## Performance & Efficiency

### Shared Client Benefits

The script creates a **single `GitHubClient`** used across all repositories. This provides:

1. **Connection pooling** — reuses HTTP connections across repos
2. **In-memory caching** — GitHub API responses are cached by (repo, ref); when processing multiple repos that share common actions (e.g. all use `actions/checkout@v4`), subsequent lookups hit the cache instantly
3. **Rate-limit bookkeeping** — semaphore manages 429/403 backoff globally across all repos

### Concurrency Tuning

- `--concurrency N` (default 4): Max repos cloning/processing in parallel (I/O bound)
- `--api-concurrency M` (default 5): Max GitHub API requests in flight from the client

**Example**: `--concurrency 8 --api-concurrency 20` for large organizations (assumes healthy network and GitHub rate-limit headroom).

### Large-Scale Runs

For 100+ repositories:

```bash
python update_repos.py --repos-file all-repos.txt --concurrency 10 --api-concurrency 15 --push
```

Typical runtime: ~2–5 seconds per repo (dominated by clone + pin time, not API calls thanks to caching).

## Examples

### Update pinned semver tags to latest minor version

All repos using `actions/checkout@v4` will be re-pinned to the latest `v4.x.y` available:

```bash
uv run --with-editable . scripts/update_repos.py \
  --repos org/svc1 --repos org/svc2 \
  --update minor \
  --dry-run
```

### Batch automation in CI/CD (with JSON output)

```bash
#!/bin/bash
set -e

uv run --with-editable . scripts/update_repos.py \
  --repos-file teams/infra/repos.txt \
  --update patch \
  --push \
  --branch-prefix "automated/pin-actions-$(date +%Y%m%d)" \
  --format json \
  --output-file results.json
```

Results saved to `results.json` (includes PR URLs in `pr_url` field) for downstream processing.

### Custom commit/PR text

```bash
uv run --with-editable . scripts/update_repos.py \
  --repos org/repo1 --repos org/repo2 \
  --push \
  --commit-message "fix(ci): pin actions to commit SHAs per security policy" \
  --pr-body "See https://github.com/org/security-policy for details."
```

### Generate markdown summary for Slack/PR comment

```bash
uv run --with-editable . scripts/update_repos.py \
  --repos-file my-orgs-repos.txt \
  --push \
  --format markdown \
  --output-file SUMMARY.md
```

Then paste `SUMMARY.md` into a PR or Slack message. PR URLs in the `PR_URL` column are directly clickable.

### Auto-detect each repo's default branch

```bash
uv run --with-editable . scripts/update_repos.py \
  --repos-file repos.txt \
  --push
```

Each repo's actual default branch (main, master, develop, etc.) is automatically detected and used as the PR base. Use `--base-branch CUSTOM` to override for all repos.

## Troubleshooting

### `subprocess.CalledProcessError: clone failed`

Ensure:
- Repository URL is correct (owner/repo format)
- Token has `repo` scope (full repository read access)
- Network connectivity to GitHub
- `gh` CLI is installed and authenticated: `gh auth status`

### `gh: command not found`

Install `gh` CLI:

```bash
# macOS
brew install gh

# Linux
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo gpg --dearmor -o /usr/share/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
sudo apt update && sudo apt install gh
```

Authenticate:

```bash
gh auth login
```

### PR creation fails

Ensure:
- `gh` is authenticated: `gh auth status`
- Token has `repo` and `workflow` scopes (for `--push`)
- Push succeeded (branches exist on origin)
- Each repo's base branch is correct (auto-detected, or set with `--base-branch`)

PR URLs appear in the `pr_url` field/column of the summary output (JSON, markdown, table, CSV) — use them to follow up with reviews directly.

Re-running the script on the same repos is safe: it detects existing PRs via `gh pr view` and updates them in-place instead of failing. The feature branch is force-pushed with the latest pins, and the PR body remains unchanged. If all pins are already up-to-date, the branch will reflect that and the PR won't require changes.

### Out of memory with many repos

Reduce `--api-concurrency`:

```bash
uv run --with-editable . scripts/update_repos.py --repos-file repos.txt --api-concurrency 2 --push
```

### Rate limit exceeded (429 errors)

Reduce `--api-concurrency` or wait:

```bash
uv run --with-editable . scripts/update_repos.py --repos-file repos.txt --api-concurrency 3 --push
```

The script uses exponential backoff with jitter (default 5 retries, up to 60s); it will auto-retry.

### No workflows found (0 modified for all repos)

- Ensure each repo has `.github/workflows/*.yml` or `.github/actions/*` directories
- Verify the clone succeeded (`--dry-run` shows `base_branch` but no files? → try without `--dry-run` to see actual error)
- Some repos may legitimately have no GitHub Actions to pin

## Library Integration

For programmatic usage without cloning (e.g., processing already-local repos), import `pin_actions` directly in Python:

```python
import asyncio
from pathlib import Path
from pin_actions import GitHubClient, Settings, run


async def process_local_repos():
    repos = [Path("./my-service"), Path("./my-infra")]
    async with GitHubClient(token="ghp_xxxx", concurrency=10) as client:
        for repo_path in repos:
            settings = Settings(path=repo_path / ".github", dry_run=False)
            modified = await run(settings, client=client)
            print(f"{repo_path}: {len(modified)} pinned")


asyncio.run(process_local_repos())
```

See [Use as a Library](./use-as-a-library.md) for more examples.

## See Also

- [Use as a Library](./use-as-a-library.md) — Programmatic integration
- [Reference: CLI](../reference/cli.md) — Single-repo CLI
- [Reference: config](../reference/config.md) — `Settings` configuration
