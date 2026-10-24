"""Command-line interface for the corpus scanner stages."""

import asyncio
import json
import logging
import sys
from datetime import date  # noqa: TC003 -- pydantic resolves the annotation at runtime
from pathlib import Path
from typing import Self

from pinref.client import GitHubClient
from pinref.core import LEVELS_BY_VERBOSITY, configure_logging
from pinref.errors import PinActionsError
from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, CliApp, CliSubCommand, SettingsConfigDict

from .fetch import fetch_corpus, select_sample
from .frame import build_frame
from .io import read_jsonl
from .report import report
from .scan import scan_corpus

logger = logging.getLogger("scan_corpus")


class FrameStage(BaseSettings):
    """Build the sampling frame from the GitHub repository search API."""

    out: Path = Field(
        default=Path("notes/corpus/frame.jsonl"),
        description="Destination JSON Lines frame; the query is recorded in a sibling .meta.json",
    )
    min_stars: int = Field(default=100, ge=0, description="Inclusive lower star bound of the frame")
    max_stars: int = Field(default=500_000, ge=0, description="Inclusive upper star bound of the frame")
    pushed_since: date = Field(
        description="Only include repos pushed after this ISO date (e.g. 2026-04-01); state it in the methodology",
    )
    github_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("PINREF_TOKEN", "GITHUB_TOKEN"),
        description="GitHub API token; search is 10 req/min unauthenticated, 30 req/min authenticated",
    )

    @model_validator(mode="after")
    def _check_star_band(self) -> Self:
        """Reject an inverted star band.

        Returns:
            The validated model.

        Raises:
            ValueError: If ``min_stars`` exceeds ``max_stars``.
        """
        if self.min_stars > self.max_stars:
            msg = f"min_stars ({self.min_stars}) must not exceed max_stars ({self.max_stars})"
            raise ValueError(msg)
        return self

    def cli_cmd(self) -> None:
        """Run the frame stage."""
        if self.github_token is None:
            logger.warning("no GitHub token; unauthenticated search is capped at 10 requests/minute")

        async def _run() -> int:
            token = self.github_token.get_secret_value() if self.github_token else None
            async with GitHubClient(token=token, concurrency=1) as client:
                return await build_frame(
                    client,
                    self.out,
                    min_stars=self.min_stars,
                    max_stars=self.max_stars,
                    pushed_since=self.pushed_since.isoformat(),
                )

        print(f"frame: {asyncio.run(_run())} repositories -> {self.out}")


class FetchStage(BaseSettings):
    """Blobless sparse-clone every repository in the frame."""

    frame: Path = Field(default=Path("notes/corpus/frame.jsonl"), description="Frame file to read")
    cache: Path = Field(default=Path("notes/corpus/repos"), description="Root directory for clones")
    concurrency: int = Field(default=16, ge=1, description="Max simultaneous clones")
    timeout: float = Field(default=120.0, gt=0, description="Per-git-invocation timeout in seconds")
    sample: int | None = Field(
        default=None,
        ge=1,
        description="Clone a random sample of this size; a larger sample with the same seed is a superset",
    )
    seed: int = Field(default=0, description="Sampling seed; record it in the methodology")
    limit: int | None = Field(default=None, ge=1, description="Clone only the first N repositories after sampling")

    def cli_cmd(self) -> None:
        """Run the fetch stage."""
        repos = select_sample((row["repo"] for row in read_jsonl(self.frame)), size=self.sample, seed=self.seed)
        if self.sample is not None:
            sample_path = self.frame.with_name("sample.jsonl")
            sample_path.write_text(
                "".join(json.dumps({"repo": repo}) + "\n" for repo in repos),
                encoding="utf-8",
            )
            logger.info("sampled %d repositories (seed %d) -> %s", len(repos), self.seed, sample_path)
        repos = repos[: self.limit]
        manifest = asyncio.run(fetch_corpus(repos, self.cache, concurrency=self.concurrency, timeout=self.timeout))
        print(f"fetch: {len(repos)} repositories -> {manifest}")


class ScanStage(BaseSettings):
    """Classify the clones into the corpus CSV."""

    cache: Path = Field(default=Path("notes/corpus/repos"), description="Root directory holding the clones")
    manifest: Path | None = Field(default=None, description="Fetch manifest; defaults to <cache>/manifest.jsonl")
    out: Path = Field(default=Path("notes/corpus/corpus.csv"), description="Destination CSV")
    limit: int | None = Field(default=None, ge=1, description="Scan only the first N repositories")

    def cli_cmd(self) -> None:
        """Run the scan stage.

        Raises:
            SystemExit: If no fetch manifest exists yet.
        """
        manifest = self.manifest or self.cache / "manifest.jsonl"
        if not manifest.is_file():
            msg = f"error: no manifest at {manifest}; run the fetch stage first"
            raise SystemExit(msg)
        rows = scan_corpus(manifest, self.cache, self.out, limit=self.limit)
        print(f"scan: {rows} repositories -> {self.out}")


class ReportStage(BaseSettings):
    """Aggregate the corpus CSV into the headline numbers."""

    csv_path: Path = Field(
        default=Path("notes/corpus/corpus.csv"),
        validation_alias=AliasChoices("csv", "csv_path"),
        description="Corpus CSV to aggregate",
    )
    exclude_dynamic: bool = Field(
        default=False,
        description="Drop repositories containing expression-valued uses: from the denominator",
    )
    out: Path | None = Field(default=None, description="Write the Markdown report here instead of stdout")

    def cli_cmd(self) -> None:
        """Run the report stage."""
        text = report(self.csv_path, exclude_dynamic=self.exclude_dynamic)
        if self.out is None:
            print(text)
        else:
            self.out.write_text(text + "\n", encoding="utf-8")
            print(f"report -> {self.out}")


class ScanCorpusSettings(BaseSettings):
    """Configure the SCaLE 24x corpus scanner CLI."""

    model_config = SettingsConfigDict(
        env_prefix="SCAN_CORPUS_",
        case_sensitive=False,
        populate_by_name=True,
        cli_parse_args=True,
        cli_kebab_case=True,
        cli_implicit_flags=True,
        cli_prog_name="scan_corpus",
    )

    verbose: int = Field(
        default=1,
        ge=0,
        le=3,
        validation_alias=AliasChoices("verbose", "v"),
        description="Verbosity level 0-3, matching the pinref CLI",
    )

    frame: CliSubCommand[FrameStage]
    fetch: CliSubCommand[FetchStage]
    scan: CliSubCommand[ScanStage]
    report: CliSubCommand[ReportStage]

    def cli_cmd(self) -> None:
        """Configure logging and dispatch to the selected stage."""
        configure_logging(self.verbose)
        logger.setLevel(LEVELS_BY_VERBOSITY[self.verbose]["pinref"])
        CliApp.run_subcommand(self)


def main() -> None:
    """Run the corpus scanner CLI and convert expected failures to exit status 1."""
    try:
        CliApp.run(ScanCorpusSettings)
    except (PinActionsError, ValueError) as exc:  # ValidationError subclasses ValueError
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
