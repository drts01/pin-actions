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

Run `collect.sh` from anywhere; it resolves the repository root itself:

```bash
notes/corpus_scanner/collect.sh frame    # build the sampling frame (once, 90-120 min)
notes/corpus_scanner/collect.sh pilot    # 2,000 repos; measures the rates that size the full run
notes/corpus_scanner/collect.sh full     # 50,000 repos; the published corpus
notes/corpus_scanner/collect.sh report   # re-aggregate without refetching
```

The script resolves the GitHub token with `gh auth token`,
checks for the estimated disk requirement plus 10% headroom before cloning, and records its parameters in the artifacts.
Resource estimates and tuning variables are documented in the script header.

To drive the stages directly, run commands from the repository root:

```bash
export GITHUB_TOKEN=...  # Optional, but increases the GitHub search rate limit.
uv run python -m notes.corpus_scanner frame --min-stars 100 --pushed-since 2026-04-01 --out notes/corpus/frame.jsonl
uv run python -m notes.corpus_scanner fetch --frame notes/corpus/frame.jsonl --cache notes/corpus/repos --sample 50000 --seed 20260401 --concurrency 10
uv run python -m notes.corpus_scanner scan --cache notes/corpus/repos --out notes/corpus/corpus.csv
uv run python -m notes.corpus_scanner report --csv notes/corpus/corpus.csv --exclude-dynamic
```

## Sampling

Cloning the whole frame is neither practical nor necessary; `N` is the fully `uses:`-pinned subset,
so a 50,000-repository sample already drives the headline percentages below a two-point confidence interval.

`fetch` shuffles the frame once with `--seed` and takes a `--sample`-sized prefix.
Samples therefore nest: for a fixed seed, a larger `--sample` is a superset of every smaller one,
so the pilot's clones are reused by the full run.
The shuffle is applied even without `--sample`,
so an interrupted fetch leaves a random subsample rather than the star-descending prefix the frame stage emits.

Publish `sample.jsonl` and the seed; both are required to reproduce the corpus.

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
- `sample.jsonl`: the repositories selected for fetching, written whenever `--sample` is used.
- `repos/`: sparse clones and `manifest.jsonl` fetch outcomes.
- `corpus.csv`: per-repository classification data.

Do not commit credentials or place tokens in these artifacts.
