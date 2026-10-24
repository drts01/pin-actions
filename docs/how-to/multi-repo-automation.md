# Multi-Repo Automation

Pin GitHub Actions across many repositories in one run with `scripts/update_repos.py`,
a bundled script that clones each repository, pins its refs, and opens pull requests.

!!! note "Library usage example"
    The script is a working example of `pinref` used as a library.
    Library calls are isolated in `_try_pin()`: `Settings(...)` and `await run(settings, client=client, cwd=repo_dir)`.

## Overview

For each repository, the script:

1. Shallow-clones it with `gh repo clone`.
2. Pins mutable action refs to commit SHAs and container image tags to `sha256:` digests.
3. Remediates script-injection findings — [on by default](#script-injection-remediation).
4. Optionally runs `zizmor --fix` for additional hardening.
5. Commits to a branch and, with `--push`, opens or updates a pull request.

Repositories are processed concurrently through a single shared `GitHubClient`.
Re-running is safe: the branch is force-pushed and an existing open PR is reused rather than duplicated.

## Prerequisites

- `gh` CLI, authenticated with `gh auth login` — used for cloning, forking, and PR creation.
- `git` CLI — used for committing and pushing.
- `uv` — runs the script with its dependencies.
- `GITHUB_TOKEN` or `UPDATE_REPOS_TOKEN` env var, or `--github-token` (optional when `gh auth login` is set up).

## Installation

The script is not standalone: it imports `scripts.fix_injection`, and its shebang invokes `uv run --with-editable .`.
Clone the repository and run it from the checkout root.

```bash
git clone https://github.com/drts01/pinref
cd pinref
uv run --with-editable . scripts/update_repos.py --repos org/service-a --dry-run
```

## Basic Usage

### Preview changes

`--dry-run` resolves refs and prints the summary without writing, committing, or pushing.

```bash
uv run --with-editable . scripts/update_repos.py --repos org/service-a --repos org/service-b --dry-run
```

### Pin, push, and open pull requests

```bash
uv run --with-editable . scripts/update_repos.py \
  --repos-file repos.txt \
  --push \
  --branch-name automated/pinref \
  --commit-message "fix(ci): pin actions to commit SHAs per security policy" \
  --format json --output-file results.json
```

Without `--push`, the script still commits to the branch locally but never pushes.
The PR base is each repository's own default branch, read from the clone;
override it for all repositories with `--base-branch`.

`--repos-file` takes one `owner/repo` per line.
Blank lines and lines beginning with `#` are skipped; trailing comments on a repository line are *not* stripped.

```text
# Services
org/service-a
org/service-b

org/terraform-modules
```

### Pin through a fork

Use `--fork` when you lack write access to the target repositories.
The script creates the fork if needed, pushes the branch there,
and opens a cross-fork PR into the upstream default branch.
Add `--fork-org ORG` to fork into an organization instead of your personal account.

```bash
uv run --with-editable . scripts/update_repos.py \
  --repos upstream/repo1 --repos upstream/repo2 --fork --push
```

To re-resolve already-pinned tags, add `--update major|minor|patch`;
see [Update Pinned Tags](./update-pinned-tags.md) for the semantics.

## Key Flags

Run `uv run --with-editable . scripts/update_repos.py --help` for the complete list.
Understand these before any non-dry run.

| Flag                | Default      | Behavior                                                                   |
| ------------------- | ------------ | -------------------------------------------------------------------------- |
| `--repos`           | —            | Repository as `owner/repo`; repeat for multiple                            |
| `--repos-file`      | —            | File with one `owner/repo` per line                                        |
| `--dry-run`         | off          | Resolve and report only; no writes, commits, or pushes                     |
| `--fix-injection`   | **on**       | Also rewrite `run:` steps to remediate script injection                    |
| `--push`            | off          | Push the branch and open or update a PR via `gh`                           |
| `--fork`            | off          | Push to a fork (created if needed) and open a cross-fork PR                |
| `--fork-org`        | —            | Fork into this organization instead of the authenticated user              |
| `--branch-name`     | `pinref`     | Exact branch name created in every repository; force-pushed on re-runs     |
| `--base-branch`     | repo default | PR base branch; detected per repository when unset                         |
| `--run-zizmor`      | off          | Also run `zizmor --fix` (requires `zizmor` on `PATH`; skipped on dry runs) |
| `--zizmor-fix`      | `safe`       | `zizmor --fix` mode: `safe` or `all`                                       |
| `--concurrency`     | `4`          | Max repositories cloned and processed in parallel                          |
| `--api-concurrency` | `5`          | Max in-flight GitHub API requests on the shared client                     |

### Script-injection remediation

`--fix-injection` is **on by default**.
Every non-dry run therefore rewrites `run:` steps
that interpolate untrusted `${{ ... }}` expressions in addition to pinning refs,
and those edits land in the same commit and pull request.
Pass `--no-fix-injection` to pin refs only.

Findings that cannot be fixed automatically are logged as `REVIEW` warnings
and counted in the `review` column of the summary.
See [Remediate Code Injection](./remediate-code-injection.md) for exactly what is rewritten.

## Output

`--format` defaults to `table` and also accepts `markdown`, `json`, `csv`, and `tsv`.
`--output-file` writes the summary to a file instead of stdout.

```text
REPO          MODIFIED BRANCH      BASE_BRANCH FORK_OWNER PR_URL                                   REVIEW STATUS
---------------------------------------------------------------------------------------------------------------------------------
org/service-a 2        pinref main        —          https://github.com/org/service-a/pull/42 1      OK
org/service-b 0        —           develop     —          —                                        —      ERROR: 1 file(s) failed
```

`json` emits the full result records, including every modified file path.
The exit code is `0` when all repositories succeeded and `1` when any failed.

## Concurrency

All repositories share one `GitHubClient`,
so HTTP connections are pooled and API responses are cached by repository and ref:
the second repository using `actions/checkout@v7` resolves from cache instead of the network.
Raise `--concurrency` for clone and pin throughput; lower `--api-concurrency` when GitHub rate-limits you.

## Troubleshooting

### `clone failed`

Verify the `owner/repo` spelling, network reachability, `gh auth status`, and that the token has `repo` scope.

### `gh: command not found`

Install the GitHub CLI from <https://cli.github.com/>, then run `gh auth login`.

### PR or fork creation fails

`--push` needs a token with `repo` and `workflow` scopes.
Re-runs are safe: the script finds the existing open PR for the branch and updates it in place.
A merged or closed PR is not reused; a new one is opened.

`--fork` needs `repo` scope, and `--fork-org` additionally needs permission to create forks in that organization.
Organizations with forking disabled return HTTP 403.

### Rate limit exceeded

Lower `--api-concurrency`.
The client retries up to five times with exponential backoff and jitter, honoring `Retry-After` and `X-RateLimit-Reset`.

### `0 modified` for every repository

Confirm each repository has `.github/workflows/*.yml` or an `action.yml`, and that its refs are not already pinned.
Add `--verbose 2` for per-file detail.

## Library Integration

To process already-local repositories without cloning, import `pinref` directly and pass `cwd=` per repository: see
[Use as a Library — Multi-Repo Processing with a Shared Client](./use-as-a-library.md#multi-repo-processing-with-a-shared-client).

The sibling script `scripts/update_repos-with-zizmor.py` is a variant
that delegates pinning to `zizmor --fix=all` instead of the `pinref` library.

## See Also

- [Use as a Library](./use-as-a-library.md) — Programmatic integration
- [Remediate Code Injection](./remediate-code-injection.md) — What `--fix-injection` rewrites
- [Update Pinned Tags](./update-pinned-tags.md) — `--update` semantics
- [Reference: CLI](../reference/cli.md) — Single-repo CLI
- [Reference: config](../reference/config.md) — `Settings` configuration
