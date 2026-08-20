# Performance Profiling & Testing Guide

Profile `pin-actions` to identify bottlenecks, measure scalability, and validate optimization correctness using synthetic benchmarks and statistical profilers.

## Synthetic Benchmark Scenario

`benchmarks/bench_scenario.py` generates N workflow YAML files with mixed pinned/unpinned refs + mocked GitHub API (httpx2.MockTransport—deterministic, zero network latency variance):

```bash
# Generate 200 workflows, resolve with concurrency=5
python benchmarks/bench_scenario.py --files 200 --concurrency 5

# With environment variables
BENCH_FILES=500 BENCH_CONCURRENCY=10 python benchmarks/bench_scenario.py

# Help
python benchmarks/bench_scenario.py --help
```

**Options** (pydantic-settings + CLI parsing):
- `--files N` — workflow count (default: 100, env: `BENCH_FILES`)
- `--concurrency N` — GitHub client concurrency level (default: 5, env: `BENCH_CONCURRENCY`)
- `--already-pinned-ratio FLOAT` — fraction of actions pre-pinned as SHAs (default: 0.3, env: `BENCH_ALREADY_PINNED_RATIO`)
- `--verbose` — verbosity 0-3 (env: `BENCH_VERBOSE`)

## Profiling Tools

### cProfile (Built-in, No Privileges Required)

CPU profiler via Python stdlib:

```bash
# Record profile
python -m cProfile -o benchmarks/cprofile.pstats benchmarks/bench_scenario.py --files 500

# Analyze
python -c "
import pstats
stats = pstats.Stats('benchmarks/cprofile.pstats')
stats.sort_stats('cumulative')
stats.print_stats(30)
"
```

**Real baseline (200 files, ~0.34s benchmark runtime; ~0.43s with import overhead):**

| Function | Calls | Cumtime | Insight |
|----------|-------|---------|---------|
| `asyncio._run_once` loop | 14 | 0.429s | Event loop; mocked API adds minimal per-call cost |
| `run_benchmark` (setup) | 2 | 0.337s | Imports + file generation (~200 files on tmpfs: ~100ms) |
| `asyncio.Context.run` | 2814 | 0.427s | Coroutine scheduling; efficient |
| Module imports | — | 0.656s | One-time initialization cost (largest initial overhead) |

**Hot path (actual pinning logic—subset not shown due to async scheduling complexity):**
- `pin_file` + `resolve_and_rewrite` hidden inside asyncio loop (hard to extract cumtime via cProfile on async functions)
- Estimated <50ms for 200 files (0.25ms/file) based on mock response speed

### py-spy (Wall-Clock Sampling, SVG Flamegraph)

**Linux (no elevation needed):**
```bash
tox -e flamegraph
# or with custom args:
tox -e flamegraph -- --files 1000
```

**macOS (requires `sudo` due to SIP/ptrace restrictions):**
```bash
sudo tox -e flamegraph
# or with custom args:
sudo tox -e flamegraph -- --files 1000
```

Output: `benchmarks/flamegraph.svg` (SVG-native inferno flamegraph).

**If running directly without tox** (Linux only; macOS requires `sudo`):
```bash
py-spy record -o flamegraph.svg -- benchmarks/bench_scenario.py --files 500
```

**Why py-spy + SVG?**
- Wall-clock time (includes I/O wait, asyncio overhead)
- SVG-native output (ideal for CI artifact embedding in `$GITHUB_STEP_SUMMARY`)
- C-frame visibility into httpx2/yamlrocks bottlenecks
- ~1% overhead (statistical sampling)

**vs cProfile + Tachyon:**
- **cProfile:** CPU-time instrumentation, precise but ~10-20% overhead
- **Tachyon:** Python 3.15+ only, HTML output (not SVG-embeddable), async-aware
- **py-spy:** Best for wall-clock profiling + CI flamegraph embedding

**vs cProfile:**
- **py-spy:** Wall-clock time, external library overhead visible, statistical sampling (~1% overhead)
- **cProfile:** Instrumentation overhead (~10-20%), precise call counts, harder to see I/O wait

### Python 3.15 `profiling.sampling` (PEP 768 / "Tachyon")

Low-overhead async-aware sampling profiler via `tox -e tachyon-py315` (standard) or `tox -e tachyon-py315t` (free-threaded):

**Linux (no elevation needed):**
```bash
# Standard Python 3.15
tox -e tachyon-py315 -- --files 500

# Free-threaded Python 3.15t
tox -e tachyon-py315t -- --files 500
```

**macOS (requires `sudo` due to SIP/ptrace restrictions):**
First time only — create venv without sudo:
```bash
tox -e tachyon-py315 --notest
tox -e tachyon-py315t --notest
```
Then profile with elevation:
```bash
sudo tox -e tachyon-py315 -- --files 500
sudo tox -e tachyon-py315t -- --files 500
```

Output: `benchmarks/tachyon-py315.html` or `benchmarks/tachyon-py315t.html` (interactive flamegraphs).

**If running directly without tox** (Linux only; macOS requires `sudo`):
```bash
# Python 3.15
python3.15 -m profiling.sampling run --mode wall --async-aware --flamegraph \
  -o benchmarks/tachyon-py315.html benchmarks/bench_scenario.py --files 200

# Python 3.15t (free-threaded)
python3.15t -m profiling.sampling run --mode wall --async-aware --flamegraph \
  -o benchmarks/tachyon-py315t.html benchmarks/bench_scenario.py --files 200
```

**Capabilities:**
- `--mode {wall,cpu,gil,exception}` — Wall clock, CPU time, GIL contention, or exception tracking
- `--async-aware` — Task-based stack reconstruction (sees across await boundaries; ideal for asyncio workloads)
- `--flamegraph` / `--pstats` / `--jsonl` / `--heatmap` — Multiple output formats
- `-r/--sampling-rate` — Adjust precision vs overhead (default: 1kHz)

**Comparison to cProfile:**
- **Overhead:** ~1-2% (sampling vs 100% instrumentation)
- **Precision:** Statistical; captures ~99% of execution at 1kHz sampling rate
- **Async support:** Task-based reconstruction (cProfile/py-spy see individual tasks, not control flow)
- **Privilege requirement:** Requires `sudo` on macOS (ptrace/task_for_pid), not on Linux
- **Use when:** Long-running workloads, GIL contention investigation, or production telemetry

On macOS without running `sudo tox -e tachyon`, fall back to cProfile + pytest-benchmark.

## pytest-benchmark Micro-benchmarks

Statistically-sound performance assertions on hot functions. Run via tox or directly:

```bash
# Run all micro-benchmarks
pytest benchmarks/test_benchmarks.py --benchmark-only

# Group by category
pytest benchmarks/test_benchmarks.py::test_is_full_sha_valid --benchmark-only --benchmark-group

# Store baseline for regression detection
pytest benchmarks/test_benchmarks.py --benchmark-only --benchmark-save=baseline

# Compare against baseline
pytest benchmarks/test_benchmarks.py --benchmark-only --benchmark-compare=baseline --benchmark-compare-fail=mean:5%
```

**Current micro-benchmarks** (in `benchmarks/test_benchmarks.py`):
- `test_is_full_sha_valid` / `test_is_full_sha_invalid` — SHA validation overhead
- `test_cached_fetch_cache_hit` — Cache-hit latency in `_cached_fetch`
- `test_resolve_and_rewrite_simple` — YAML mutation + ref resolution on minimal doc

## Integrated tox Environment

Run all profiling tasks in one command:

```bash
# Run micro-benchmarks + scenario benchmark
tox -e profile

# Or manually control:
tox -e profile -- pytest benchmarks/test_benchmarks.py --benchmark-only
tox -e profile -- python benchmarks/bench_scenario.py --files 500 --concurrency 10
```

## Additional Performance Testing Strategies

### 1. **Concurrency Scaling**

Measure throughput vs concurrency to validate semaphore tuning:

```bash
for c in 1 2 5 10 20; do
  echo "=== Concurrency: $c ==="
  time python benchmarks/bench_scenario.py --files 500 --concurrency $c 2>/dev/null | tail -1
done
```

**Expected:** Throughput plateaus around concurrency=5–8 (GitHub API rate limits; diminishing returns beyond).

### 2. **Memory Profiling with tracemalloc**

Detect cache leaks or O(n) memory growth:

```python
import asyncio
import tracemalloc
from benchmarks.bench_scenario import run_benchmark, BenchSettings

tracemalloc.start()
asyncio.run(run_benchmark(BenchSettings(files=1000, concurrency=5)))
current, peak = tracemalloc.get_traced_memory()
print(f"Memory: current={current / 1024 / 1024:.1f}MB, peak={peak / 1024 / 1024:.1f}MB")
tracemalloc.stop()
```

**Expectation:** ~5–15 MB for 1000 files (YAML ASTs + caches bounded). If > 100 MB, suspect unbounded cache growth.

### 3. **Asyncio Debug Mode (Slow-Callback Detection)**

Enable in tests to catch blocking I/O or long-running sync code:

```bash
PYTHONASYNCDEBUG=1 pytest tests/ -k "not slow" --tb=short
# or for a scenario
python -X dev benchmarks/bench_scenario.py --files 50
```

Warns on callbacks > 100ms (detects sync I/O or CPU-bound code in event loop).

### 4. **Cache Dedup Stress Test**

Verify single-flight dedup prevents cache stampede under high concurrency:

```bash
pytest tests/test_client.py::TestConcurrentDedup::test_concurrent_requests_same_key_single_fetch -v
```

Validates that 100+ concurrent requests for the same key result in a single API fetch.

### 5. **Wall-Clock Scaling Test with hyperfine**

Measure CLI wall-clock linearity across file counts:

```bash
# Install: brew install hyperfine
hyperfine \
  'python benchmarks/bench_scenario.py --files 100' \
  'python benchmarks/bench_scenario.py --files 500' \
  'python benchmarks/bench_scenario.py --files 1000' \
  --warmup 1
```

Outputs: wall-clock histogram + statistical summary (O(n) linearity check).

### 6. **Concurrency + File Count Matrix**

Comprehensive scalability test:

```bash
for files in 100 500 1000; do
  for c in 1 5 10; do
    echo "$files files, concurrency=$c"
    python benchmarks/bench_scenario.py --files $files --concurrency $c 2>/dev/null | tail -1
  done
done
```

## CI Integration Example

`.github/workflows/profile.yml` (path-triggered on `trunk` or manual `workflow_dispatch`, 2 jobs):

### Job 1: Benchmarks (matrixed across Python versions)

```yaml
name: Profiling

on:
  push:
    branches: [trunk]
    paths:
      - src/pin_actions/**
      - benchmarks/**
      - pyproject.toml
      - tox.toml
      - .github/workflows/profile.yml
  workflow_dispatch: {}

jobs:
  benchmark:
    strategy:
      matrix:
        python-version: ['3.14', 3.14t, '3.15', 3.15t]
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d # v10.0.1
        with:
          python-version: ${{ matrix.python-version }}
          enable-cache: true

      # Run micro-benchmarks + scenario benchmark (all versions)
      - run: uv run --group ci tox run -e profile

      # Generate flamegraph SVG (3.14 only, avoid redundant runs)
      - if: matrix.python-version == '3.14'
        run: uv run --group ci tox run -e flamegraph

      # Parse benchmark.json → markdown table (jq)
      - if: matrix.python-version == '3.14' && always()
        id: metrics
        run: |
          jq_query='
            [.benchmarks[] | {name: .fullname, mean: .stats.mean, ...}]
            | sort_by(.mean) | reverse
            | "| Name | Mean (ms) | ... |\n" + (map("| \(.name | split("::")[-1]) | ... |") | join("\n"))
          '
          table=$(jq -r "$jq_query" benchmark.json)
          echo "table<<EOF" >> $GITHUB_OUTPUT
          echo "$table" >> $GITHUB_OUTPUT
          echo "EOF" >> $GITHUB_OUTPUT

      # Embed summary: benchmark table + SVG (with ::warning::/::error:: for issues)
      - if: matrix.python-version == '3.14' && always()
        run: |
          echo "### 📊 Performance Benchmarks (Python 3.14)" >> $GITHUB_STEP_SUMMARY
          echo "${{ steps.metrics.outputs.table }}" >> $GITHUB_STEP_SUMMARY

          if [ ! -f benchmarks/flamegraph.svg ]; then
            echo "::error::flamegraph.svg not found"
            exit 1
          fi

          svg_size=$(wc -c < benchmarks/flamegraph.svg)
          if [ $svg_size -gt $((700 * 1024)) ]; then
            echo "::warning::Flamegraph SVG too large — see artifact"
          else
            svg_b64=$(base64 -i benchmarks/flamegraph.svg | tr -d '\n')
            echo "### 🔥 Flamegraph (py-spy)" >> $GITHUB_STEP_SUMMARY
            echo '<img src="data:image/svg+xml;base64,'$svg_b64'" width="100%" />' >> $GITHUB_STEP_SUMMARY
          fi

      # Upload: one artifact per matrix leg
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: profiling-py${{ matrix.python-version }}
          path: |
            benchmark.json
            benchmarks/flamegraph.svg
          retention-days: 30
```

### Job 2: Tachyon (Python 3.15 + 3.15t, matrixed)

```yaml
  tachyon:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.15', 3.15t]
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d # v10.0.1
        with:
          python-version: ${{ matrix.python-version }}
          enable-cache: true

      # Generate Tachyon HTML (interactive JS-based flamegraph)
      - run: |
          env_suffix=$(echo "${{ matrix.python-version }}" | tr -d '.')
          uv run --group ci tox run -e tachyon-py${env_suffix}

      # Summary note (can't embed interactive HTML in GitHub summaries)
      - if: always()
        run: |
          echo "### 📈 Tachyon Profiler (Python ${{ matrix.python-version }})" >> $GITHUB_STEP_SUMMARY
          echo "Interactive HTML flamegraph with async-aware stacks. Download artifact to view." >> $GITHUB_STEP_SUMMARY

      # Upload HTML artifact (not inlinable, so artifact-only)
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: profiling-tachyon-py${{ matrix.python-version }}
          path: benchmarks/tachyon-py*.html
          retention-days: 30
```

**Key points:**
- **Benchmark job** matrixed across 3.14/3.14t/3.15/3.15t; all run `tox -e profile` (pytest-benchmark micro-tests → `benchmark.json`)
- **Flamegraph** (py-spy SVG) runs once on 3.14 leg only (avoid 4x redundant profiler runs)
- **jq-parsed benchmark table** embedded in step summary (name, min, mean, max, ops/sec sorted by mean)
- **SVG base64-embedded** with ~700KB size guard; `::warning::`/`::error::` for sizing issues
- **Tachyon job** separate, non-matrixed (Python 3.15 only); generates interactive HTML artifact (can't be inlined due to `<script>` sanitization by GitHub)
- All profiling logic delegated to tox; no duplicated shell commands

## Optimization Targets

| Component | Bottleneck | %Total | Mitigation |
|-----------|-----------|--------|-----------|
| **Module imports** | Python stdlib + dependencies startup | ~70% (incl. import overhead) | Negligible for CLI; only matters in long-running server mode |
| **File I/O** | `pathlib.read_bytes` + YAML parse | ~25–30% | Unavoidable (sync ops); asyncio.to_thread for large batches if needed |
| **YAML walking** | `_find_uses_paths` / `_find_with_ref_paths` | ~3–5% | Already efficient (single walk); further optimization unlikely to yield benefit |
| **Cache lookups** | `_cached_fetch` (OrderedDict ops) | <1% | Optimal; no further optimization needed |
| **Single-flight dedup** | In-flight task tracking/await | <1% | Working correctly; stamped dedup prevents redundant fetches |
| **Asyncio scheduling** | Event loop overhead | ~5–10% | Acceptable for CLI tool; tuning unlikely to improve perception |

**Recommendation:** Current design is near-optimal for the problem domain. Further optimization would have diminishing returns. Focus on:
1. Testing regression: use pytest-benchmark with CI baselines
2. Load testing: concurrency sweeps to validate GitHub API limit handling
3. Memory profiling: tracemalloc on 1000+ file workloads to detect cache leaks

## Quick Checklist

- [ ] Baseline cProfile: `python -m cProfile -o benchmarks/cprofile.pstats benchmarks/bench_scenario.py --files 500`
- [ ] Compare micro-benchmarks: `pytest benchmarks/ --benchmark-only`
- [ ] Memory check: `tracemalloc` on 1000-file scenario
- [ ] Asyncio debug mode: `PYTHONASYNCDEBUG=1 pytest tests/ --tb=short`
- [ ] Concurrency scaling: sweep 1–20 on 500-file scenario
- [ ] (Optional) py-spy flamegraph on Linux: `tox -e flamegraph` (or `sudo tox -e flamegraph` on macOS)
- [ ] (Optional) Tachyon on py3.15+Linux: `tox -e tachyon` (or `sudo tox -e tachyon` on macOS)
