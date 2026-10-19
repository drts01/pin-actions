# Corpus scanner

Measure residual mutable references in repositories whose GitHub Actions `uses:` references are pinned to full commit
SHAs.

This research tool supports the SCaLE 24x talk documented in [`../scale-24x-talk.md`](../scale-24x-talk.md).

It is not part of the published `pin-actions` package.

## Methodology

Run four resumable stages:

1. `frame` builds a sampling frame through the GitHub repository search API.
2. `fetch` creates blobless sparse clones and records each default branch's HEAD commit SHA.
3. `scan` classifies each clone into one CSV row.
4. `report` aggregates the CSV into Markdown headline figures.

The scanner intentionally imports private collectors from `pin_actions`
so classification matches the implementation under study.

Treat those imports as repository-local coupling;
changes to collector signatures may require corresponding scanner updates.

## Usage

Run commands from the repository root:

```bash
export GITHUB_TOKEN=...  # Optional, but increases the GitHub search rate limit.
uv run python -m notes.corpus_scanner frame --min-stars 100 --pushed-since 2026-04-01 --out notes/corpus/frame.jsonl
uv run python -m notes.corpus_scanner fetch --frame notes/corpus/frame.jsonl --cache notes/corpus/repos --concurrency 16
uv run python -m notes.corpus_scanner scan --cache notes/corpus/repos --out notes/corpus/corpus.csv
uv run python -m notes.corpus_scanner report --csv notes/corpus/corpus.csv --exclude-dynamic
```

## Tests

Run the isolated test suite from the repository root:

```bash
uv run --group test python -m pytest --no-cov notes/corpus_scanner/tests
```

The tests mock GitHub API and Git subprocess boundaries; they do not access live services.

## Artifacts

The default paths remain under `notes/corpus/`:

- `frame.jsonl`: sampled repository names and star counts.
- `frame.meta.json`: sampling parameters and frame size.
- `repos/`: sparse clones and `manifest.jsonl` fetch outcomes.
- `corpus.csv`: per-repository classification data.

Do not commit credentials or place tokens in these artifacts.
