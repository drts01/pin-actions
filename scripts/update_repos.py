#!/usr/bin/env -S uv run --with-editable . --script
"""Batch-pin GitHub Actions across repositories using pin_actions as a library."""

import asyncio
import csv
import io
import json
import logging
import os
import subprocess
import sys
import tempfile
from functools import partial
from pathlib import Path
from typing import Literal

from pin_actions import GitHubClient, PinActionsError, Settings, run
from pin_actions.core import _LEVELS_BY_VERBOSITY
from pydantic import AliasChoices, BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

type EnvDict = dict[str, str]

logger = logging.getLogger("update_repos")
_cli_out = logging.getLogger("update_repos.cli.out")

DEFAULT_COMMIT_MESSAGE = "chore: pin GitHub Actions to immutable commit SHAs"
DEFAULT_PR_BODY = "Automated by pin-actions."


class UpdateReposSettings(BaseSettings):
    """CLI & environment configuration for the multi-repo batch script."""

    model_config = SettingsConfigDict(env_prefix="UPDATE_REPOS_", case_sensitive=False, populate_by_name=True)

    repos: list[str] = Field(
        default_factory=list,
        description="Repositories to pin (owner/repo); use multiple times or --repos-file",
    )
    repos_file: Path | None = Field(
        default=None,
        description="File with one owner/repo per line (comments/blanks ignored)",
    )
    github_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("UPDATE_REPOS_TOKEN", "GITHUB_TOKEN"),
        description="GitHub token (env: GITHUB_TOKEN or UPDATE_REPOS_TOKEN)",
    )
    dry_run: bool = Field(default=False, description="Print changes without writing, committing, or pushing")
    update: Literal["major", "minor", "patch"] | None = Field(default=None, description="Semver update strategy")
    full_version: bool = Field(default=False, description="Record full tag version instead of truncated precision")
    exclude_newer: str | None = Field(
        default=None,
        description=(
            "Exclude tags newer than this cutoff (cool-off period). "
            "Accepted: RFC 3339 timestamp, ISO 8601 duration (e.g., P7D), "
            "or friendly duration (e.g., '7 days'). Only applies with --update"
        ),
    )
    concurrency: int = Field(default=4, ge=1, description="Max concurrent repo clones")
    api_concurrency: int = Field(default=5, ge=1, description="Max concurrent GitHub API requests")
    branch_prefix: str = Field(default="pin-actions", description="Feature branch prefix")
    base_branch: str | None = Field(
        default=None,
        description="PR base branch; defaults to each repo's actual default branch",
    )
    push: bool = Field(default=False, description="Push and open a PR via gh (requires gh auth login)")
    commit_message: str = Field(default=DEFAULT_COMMIT_MESSAGE, description="Commit message and PR title")
    pr_body: str = Field(default=DEFAULT_PR_BODY, description="Pull request body text")
    format: Literal["table", "markdown", "json", "csv", "tsv"] = Field(  # pyrefly: ignore[bad-assignment]
        default="table",
        description="Summary output format",
    )
    output_file: Path | None = Field(default=None, description="Write summary to this file instead of stdout")
    host: str = Field(
        default="github.com",
        description="GitHub hostname: 'github.com' or GHE Server hostname (e.g. 'github.example.com')",
    )
    verbose: int = Field(
        default=0,
        ge=0,
        le=3,
        validation_alias=AliasChoices("verbose", "v"),
        description="Verbosity level 0-3: 0=warnings, 1=info, 2=debug, 3=debug+dependency logs",
    )

    @property
    def api_base_url(self) -> str:
        """Derive REST API base URL from host (GHE Server uses /api/v3).

        >>> UpdateReposSettings(host="github.com").api_base_url
        'https://api.github.com'
        >>> UpdateReposSettings(host="ghe.example.com").api_base_url
        'https://ghe.example.com/api/v3'
        """
        if self.host == "github.com":
            return "https://api.github.com"
        return f"https://{self.host}/api/v3"


class RepoResult(BaseModel):
    """Outcome of processing one repository."""

    repo: str
    modified: list[Path] = Field(default_factory=list)
    error: str | None = None
    branch: str | None = None
    base_branch: str | None = None
    pr_url: str | None = None


def _run(*cmd: str, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run subprocess, raising with captured stderr on failure."""
    return subprocess.run(cmd, cwd=cwd, env=env, check=True, capture_output=True, text=True)  # noqa: S603


def _load_repos(settings: UpdateReposSettings) -> list[str]:
    """Merge --repos with --repos-file lines (comments/blanks skipped)."""
    if not settings.repos_file:
        return settings.repos
    lines = (line.strip() for line in settings.repos_file.read_text().splitlines())
    return [*settings.repos, *(line for line in lines if line and not line.startswith("#"))]


def _gh_env(token: SecretStr | None, host: str) -> EnvDict:
    """Build GitHub CLI environment (GH_TOKEN, GH_HOST for GHE Server).

    >>> "GH_TOKEN" in _gh_env(SecretStr("x"), "github.com")
    True
    >>> "GH_HOST" in _gh_env(None, "github.com")
    False
    >>> _gh_env(None, "ghe.example.com")["GH_HOST"]
    'ghe.example.com'
    """
    env = os.environ.copy()
    if token:
        env["GH_TOKEN"] = token.get_secret_value()
    if host != "github.com":
        env["GH_HOST"] = host
    return env


def _clone(repo: str, dest: Path, token: SecretStr | None, host: str) -> None:
    """Clone via gh (uses GH_TOKEN + GH_HOST for auth/host override)."""
    env = _gh_env(token, host)
    _run("gh", "repo", "clone", repo, str(dest), "--", "--depth", "1", "--quiet", cwd=dest.parent, env=env)


def _default_branch(repo_dir: Path) -> str:
    """Read the branch checked out by the shallow clone — the repo's actual default."""
    return _run("git", "branch", "--show-current", cwd=repo_dir).stdout.strip()


def _fail(result: RepoResult, repo: str, msg: str) -> bool:
    """Record an error, log it, return False (failure sentinel)."""
    result.error = msg
    logger.warning("%s: %s", repo, msg)
    return False


def _try_clone(repo: str, repo_dir: Path, settings: UpdateReposSettings, result: RepoResult) -> bool:
    """Clone repo and record its default branch; sets result.error on failure."""
    try:
        _clone(repo, repo_dir, settings.github_token, settings.host)
    except subprocess.CalledProcessError as exc:
        return _fail(result, repo, f"clone failed: {exc.stderr.strip()}")
    result.base_branch = settings.base_branch or _default_branch(repo_dir)
    return True


async def _try_pin(client: GitHubClient, repo_dir: Path, settings: UpdateReposSettings, result: RepoResult) -> bool:
    """Pin actions in repo_dir; sets result.modified/error. Returns True unless a hard error occurred."""
    pin_settings = Settings(
        paths=[repo_dir / ".github/workflows", repo_dir / "action.yml", repo_dir / "action.yaml"],
        github_token=settings.github_token,
        dry_run=settings.dry_run,
        update=settings.update,
        full_version=settings.full_version,
        exclude_newer=settings.exclude_newer,
    )
    try:
        result.modified = await run(pin_settings, client=client)
    except ExceptionGroup as eg:
        return _fail(result, result.repo, f"{len(eg.exceptions)} file(s) failed")
    except PinActionsError as exc:
        return _fail(result, result.repo, str(exc))
    except ValueError:
        return False
    return True


def _publish(repo: str, repo_dir: Path, settings: UpdateReposSettings, result: RepoResult) -> None:
    """Commit modified files to a new branch, and push/open a PR if requested."""
    branch = f"{settings.branch_prefix}/{repo.replace('/', '-')}"
    result.branch = branch
    env = _gh_env(settings.github_token, settings.host)
    try:
        _run("git", "checkout", "-b", branch, cwd=repo_dir, env=env)
        _run("git", "add", "-A", cwd=repo_dir, env=env)
        _run("git", "commit", "-m", settings.commit_message, cwd=repo_dir, env=env)
        if settings.push:
            _run("git", "push", "origin", branch, cwd=repo_dir, env=env)
            assert result.base_branch is not None, "base_branch set by _try_clone before _publish runs"  # noqa: S101
            pr = _run(
                "gh",
                "pr",
                "create",
                "--repo",
                repo,
                "--base",
                result.base_branch,
                "--head",
                branch,
                "--title",
                settings.commit_message,
                "--body",
                settings.pr_body,
                cwd=repo_dir,
                env=env,
            )
            result.pr_url = pr.stdout.strip()
            logger.info("%s: PR opened: %s", repo, result.pr_url)
    except subprocess.CalledProcessError as exc:
        _fail(result, repo, f"git/gh op failed: {exc.stderr.strip()}")


async def _process_repo(client: GitHubClient, repo: str, settings: UpdateReposSettings) -> RepoResult:
    """Clone, pin, and publish (commit/push/PR) one repo."""
    result = RepoResult(repo=repo)
    with tempfile.TemporaryDirectory(prefix="pin-actions-") as tmp:
        repo_dir = Path(tmp) / "repo"
        if not _try_clone(repo, repo_dir, settings, result):
            return result
        if not await _try_pin(client, repo_dir, settings, result):
            return result
        if result.modified and not settings.dry_run:
            _publish(repo, repo_dir, settings, result)
    return result


async def _run_all(settings: UpdateReposSettings) -> list[RepoResult]:
    """Process all repos concurrently, sharing one GitHubClient."""
    repos = _load_repos(settings)
    if not repos:
        sys.exit("Error: no repositories specified")

    sem = asyncio.Semaphore(settings.concurrency)
    token = settings.github_token.get_secret_value() if settings.github_token else None

    async def bound(repo: str, client: GitHubClient) -> RepoResult:
        """Process one repo, bounded by the concurrency semaphore."""
        async with sem:
            return await _process_repo(client, repo, settings)

    async with GitHubClient(
        token=token, base_url=settings.api_base_url, concurrency=settings.api_concurrency
    ) as client:
        return await asyncio.gather(*(bound(r, client) for r in repos))


_HEADERS = ("repo", "modified", "branch", "base_branch", "pr_url", "status")


def _rows(results: list[RepoResult]) -> list[dict[str, str]]:
    """Flatten results into string rows for tabular formats.

    >>> _rows([RepoResult(repo="o/r", error="boom")])[0]["status"]
    'ERROR: boom'
    >>> _rows([RepoResult(repo="o/r")])[0]["branch"]
    '—'
    """
    return [
        {
            "repo": r.repo,
            "modified": str(len(r.modified)),
            "branch": r.branch or "—",
            "base_branch": r.base_branch or "—",
            "pr_url": r.pr_url or "—",
            "status": "OK" if r.error is None else f"ERROR: {r.error}",
        }
        for r in results
    ]


def _configure_logging(verbose: int) -> None:
    """Configure logging levels per namespace based on verbosity count."""
    logging.basicConfig(format="%(levelname)s:%(name)s: %(message)s", force=True)
    levels = _LEVELS_BY_VERBOSITY[min(verbose, 3)]
    for namespace, level in levels.items():
        logging.getLogger(namespace).setLevel(level)
    logger.setLevel(levels["pin_actions"])

    # Rebuild CLI logger's handlers for test isolation (capsys-safe: fresh stream references).
    _cli_out.propagate = False
    _cli_out.setLevel(logging.INFO)
    _cli_out.handlers.clear()
    _cli_out.addHandler(logging.StreamHandler(sys.stdout))


def _to_json(results: list[RepoResult]) -> str:
    """Format results as JSON."""
    return json.dumps([r.model_dump(mode="json") for r in results], indent=2)


def _to_csv_tsv(results: list[RepoResult], delimiter: str = ",") -> str:
    """Format results as CSV or TSV."""
    rows = _rows(results)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_HEADERS, delimiter=delimiter)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def _to_markdown(results: list[RepoResult]) -> str:
    """Format results as Markdown table."""
    rows = _rows(results)
    head = "| " + " | ".join(h.upper() for h in _HEADERS) + " |"
    sep = "| " + " | ".join("---" for _ in _HEADERS) + " |"
    body = "\n".join("| " + " | ".join(row[h] for h in _HEADERS) + " |" for row in rows)
    return "\n".join([head, sep, body])


def _to_table(results: list[RepoResult]) -> str:
    """Format results as ASCII table."""
    rows = _rows(results)
    widths = {h: max(len(h), *(len(row[h]) for row in rows)) if rows else len(h) for h in _HEADERS}
    lines = [" ".join(h.upper().ljust(widths[h]) for h in _HEADERS)]
    lines.append("-" * (sum(widths.values()) + len(_HEADERS) - 1))
    lines += [" ".join(row[h].ljust(widths[h]) for h in _HEADERS) for row in rows]
    return "\n".join(lines)


_FORMATTERS = {
    "json": _to_json,
    "csv": partial(_to_csv_tsv, delimiter=","),
    "tsv": partial(_to_csv_tsv, delimiter="\t"),
    "markdown": _to_markdown,
    "table": _to_table,
}


def _format_summary(results: list[RepoResult], fmt: str) -> str:
    """Render results in the requested format."""
    return _FORMATTERS[fmt](results)


def main() -> None:
    """CLI entry point."""
    settings = UpdateReposSettings(
        _cli_parse_args=True,
        _cli_kebab_case=True,
        _cli_implicit_flags=True,
        _cli_prog_name="update-repos",
    )
    _configure_logging(settings.verbose)
    results = asyncio.run(_run_all(settings))
    summary = _format_summary(results, settings.format)

    if settings.output_file:
        settings.output_file.write_text(summary + "\n")
        _cli_out.info(f"Wrote summary to {settings.output_file}")
    else:
        print(summary)

    sys.exit(1 if any(r.error for r in results) else 0)


if __name__ == "__main__":
    main()
