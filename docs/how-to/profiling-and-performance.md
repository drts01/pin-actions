# Profile and Performance-Test

Find where `pin-actions` spends time, measure how it scales, and catch regressions before they merge.
Every recipe drives a synthetic workload against a mocked GitHub API, so results need no network access or token.

## Generate a Synthetic Workload

`benchmarks/bench_scenario.py` writes N workflow files mixing pinned and unpinned refs,
then resolves them through an `httpx2.MockTransport`:

```bash
python benchmarks/bench_scenario.py --files 200 --concurrency 5
```

Flags, with their environment variables:

- `--files N` — workflow file count (default `100`, `BENCH_FILES`)
- `--concurrency N` — client concurrency (default `5`, `BENCH_CONCURRENCY`)
- `--already-pinned-ratio F` — fraction of refs already pinned to commit SHAs
    (default `0.3`, `BENCH_ALREADY_PINNED_RATIO`)

## Pick a Profiler

| Tool                           | Overhead | Needs `sudo` | Output           | Use when                                           |
| ------------------------------ | -------- | ------------ | ---------------- | -------------------------------------------------- |
| cProfile                       | 10-20%   | No           | `.pstats`        | You want exact call counts and no extra tooling    |
| py-spy                         | ~1%      | macOS only   | SVG flamegraph   | You want wall-clock time, including I/O wait       |
| Tachyon (`profiling.sampling`) | ~1-2%    | macOS only   | Interactive HTML | You need async-aware stacks or GIL contention data |

Both samplers attach to a live process, which SIP blocks on macOS; Tachyon additionally needs Python 3.15 or newer.

## Record a cProfile Profile

```bash
python -m cProfile -o benchmarks/cprofile.pstats benchmarks/bench_scenario.py --files 500
python -c "import pstats; pstats.Stats('benchmarks/cprofile.pstats').sort_stats('cumulative').print_stats(30)"
```

cProfile attributes time to the event loop, not the awaiting coroutine; use a sampler to read async control flow.

## Record a Sampling Flamegraph

py-spy writes `benchmarks/flamegraph.svg`, which embeds into a job summary because it carries no `<script>` tag:

```bash
uv run --group ci tox run -e flamegraph -- --files 1000
```

Tachyon writes an interactive `benchmarks/tachyon-py315.html`; use `tachyon-py315t` for free-threaded builds:

```bash
uv run --group ci tox run -e tachyon-py315 -- --files 500
```

Prefix either command with `sudo` on macOS,
and run it once with `--notest` beforehand so that only the profiling step is elevated.

## Detect Micro-Benchmark Regressions

`benchmarks/test_benchmarks.py` covers `test_is_full_sha`, `test_cached_fetch_cache_hit`,
and `test_resolve_and_rewrite_simple`.
Save a baseline, then fail when the mean regresses:

```bash
pytest benchmarks/test_benchmarks.py --benchmark-only --benchmark-save=baseline
pytest benchmarks/test_benchmarks.py --benchmark-only --benchmark-compare=baseline --benchmark-compare-fail=mean:5%
```

Add `--benchmark-group-by=func` to group results by function instead of by parameter.
`uv run --group ci tox run -e profile` runs these micro-benchmarks plus a 200-file scenario,
but it appends posargs to both commands, so pass scenario arguments to the script directly.

## Sweep Concurrency and File Count

Confirm that throughput scales and that the semaphore bound is tuned correctly:

```bash
for files in 100 500 1000; do
  for c in 1 5 10; do
    echo "files=$files concurrency=$c"
    time python benchmarks/bench_scenario.py --files "$files" --concurrency "$c" >/dev/null
  done
done
```

Wall-clock time should grow linearly with `--files`.
Throughput plateaus near `--concurrency 5` to `8`; the CLI default is `--concurrency 5`.

## Check Memory and Event-Loop Health

Peak memory should stay in the low tens of megabytes for 1000 files; more suggests unbounded cache growth.

```python
import asyncio
import tracemalloc
from benchmarks.bench_scenario import BenchSettings, run_benchmark

tracemalloc.start()
asyncio.run(run_benchmark(BenchSettings(files=1000, concurrency=5)))
print(tracemalloc.get_traced_memory())
tracemalloc.stop()
```

Asyncio debug mode warns on any callback that blocks the loop for more than 100 ms:

```bash
PYTHONASYNCIODEBUG=1 python -X dev benchmarks/bench_scenario.py --files 50
```

Run `pytest tests/test_client.py::TestConcurrentDedup -v` to confirm
that single-flight deduplication still collapses concurrent fetches for one key.

## Run Profiling in CI

[`.github/workflows/profile.yml`](https://github.com/drts01/pin-actions/blob/trunk/.github/workflows/profile.yml)
already runs the `profile`, `flamegraph`, and Tachyon environments on pushes to `trunk` and on `workflow_dispatch`, then
uploads the artifacts.

## Where Time Goes

- Interpreter startup and module imports dominate a single short CLI run.
- Reading files and parsing YAML is the largest in-process cost, and it is synchronous.
- Ref and digest resolution is network-bound in real use and capped by `--concurrency`.

## See Also

- [Reference: CLI](../reference/cli.md) — full flag list
- [Architecture Overview](../explanation/architecture.md) — pipeline stages and concurrency model
- [Caching](../explanation/caching.md) — cache layers and deduplication behavior
- [How-to: Run in CI](./run-in-ci.md) — wiring `pin-actions` into a workflow
