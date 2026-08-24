"""Micro-benchmarks for hot-path functions using pytest-benchmark."""

import asyncio
from typing import TYPE_CHECKING, Any

import pytest
from conftest import bench_async
from pin_actions._util import is_full_sha
from pin_actions.core import resolve_and_rewrite

if TYPE_CHECKING:
    from unittest.mock import AsyncMock

    from pin_actions.client import _Cache

pytest.importorskip("pytest_benchmark")


@pytest.mark.benchmark(group="validation")
@pytest.mark.parametrize(
    "input_value",
    [
        pytest.param("a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b", id="valid_sha"),
        pytest.param("v4.0.0", id="invalid_ref"),
    ],
)
def test_is_full_sha(benchmark: pytest.benchmark.fixture.BenchmarkFixture, input_value: str) -> None:
    """Benchmark SHA validation (valid and invalid cases)."""
    benchmark(is_full_sha, input_value)


@pytest.mark.benchmark(group="cache")
def test_cached_fetch_cache_hit(
    benchmark: pytest.benchmark.fixture.BenchmarkFixture,
    cached_fetch_setup: _Cache[str],
) -> None:
    """Benchmark cache-hit latency in _Cache.get_or_fetch."""
    cache = cached_fetch_setup

    async def mock_fetch() -> str:
        """Mock fetch (shouldn't be called on cache hit)."""
        await asyncio.sleep(0.01)
        return "not_called"

    async def run_cache_hit() -> str:
        """Run a single cache hit."""
        return await cache.get_or_fetch(("actions/checkout", "v4"), mock_fetch)

    bench_async(benchmark, run_cache_hit)


@pytest.mark.benchmark(group="yaml")
def test_resolve_and_rewrite_simple(
    benchmark: pytest.benchmark.fixture.BenchmarkFixture,
    sample_workflow_doc: Any,  # noqa: ANN401
    mock_resolve_client: AsyncMock,
) -> None:
    """Benchmark resolve_and_rewrite on a small document."""
    refs_to_resolve = {
        ("actions/checkout", "v4"): [(("uses_checkout",), None, False)],
        ("actions/setup-python", "v5"): [(("uses_python",), None, False)],
        ("actions/upload-artifact", "v4"): [(("uses_artifact",), None, False)],
    }

    async def run_resolve() -> None:
        """Run resolve_and_rewrite."""
        await resolve_and_rewrite(sample_workflow_doc, mock_resolve_client, refs_to_resolve)

    bench_async(benchmark, run_resolve)
