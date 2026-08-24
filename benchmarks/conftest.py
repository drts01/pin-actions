"""Shared fixtures for benchmark tests."""

import asyncio
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest
import yamlrocks
from pin_actions.client import GitHubClient, _Cache

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


def bench_async(
    benchmark: pytest.benchmark.fixture.BenchmarkFixture,
    coro_fn: Callable[[], Awaitable[Any]],
) -> None:
    """Run an async coroutine under pytest-benchmark.

    Args:
        benchmark: pytest-benchmark fixture.
        coro_fn: Callable that returns an awaitable coroutine.
    """
    benchmark(lambda: asyncio.run(coro_fn()))


@pytest.fixture
def github_client() -> GitHubClient:
    """GitHubClient with concurrency=1 for deterministic benchmarking."""
    return GitHubClient(concurrency=1)


@pytest.fixture
def mock_resolve_client() -> AsyncMock:
    """Mock GitHub client with fixed SHA resolution."""
    mock_client = AsyncMock()
    mock_client.resolve_sha = AsyncMock(side_effect=lambda _repo, tag: f"mock_sha_for_{tag}")
    return mock_client


@pytest.fixture
def sample_workflow_doc() -> Any:  # noqa: ANN401
    """Minimal YAML document with 3 action refs."""
    doc_text = """
name: Test
uses_checkout: actions/checkout@v4
uses_python: actions/setup-python@v5
uses_artifact: actions/upload-artifact@v4
"""
    return yamlrocks.loads(doc_text, option=yamlrocks.OPT_ROUND_TRIP)


@pytest.fixture
def cached_fetch_setup() -> _Cache[str]:
    """Pre-configured _Cache instance (with one warm entry) for cache-hit benchmarks."""
    cache: _Cache[str] = _Cache(max_size=1000)
    cache._store[("actions/checkout", "v4")] = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b"
    return cache
