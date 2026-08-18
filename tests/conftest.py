"""Shared pytest fixtures and factories."""

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest
from pin_actions.client import GitHubClient

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


@pytest.fixture
def make_client() -> Callable[..., GitHubClient]:
    """Factory fixture for GitHubClient with sensible test defaults.

    Usage:
        client = make_client(concurrency=2, max_cache_size=100)
    """

    def _make(
        token: str | None = "test",
        base_url: str = "https://api.github.com",
        concurrency: int = 1,
        max_retries: int = 5,
        disk_cache: Any = None,
        cache_ttl: int = 3600,
        max_cache_size: int = 1000,
    ) -> GitHubClient:
        return GitHubClient(
            token=token,
            base_url=base_url,
            concurrency=concurrency,
            max_retries=max_retries,
            disk_cache=disk_cache,
            cache_ttl=cache_ttl,
            max_cache_size=max_cache_size,
        )

    return _make


@pytest.fixture
def make_workflow_file() -> Callable[[Path, str], Path]:
    """Factory fixture for temporary workflow files.

    Usage:
        workflow = make_workflow_file(tmp_path,
            "name: Test\\njobs:\\n  test:\\n    steps:\\n      - uses: actions/checkout@v4")
    """

    def _make(tmp_path: Path, content: str) -> Path:
        workflow_path = tmp_path / "workflow.yml"
        workflow_path.write_text(content)
        return workflow_path

    return _make


@pytest.fixture
def mock_resolve_sha_factory() -> Callable[[dict[tuple[str, str], str]], AsyncMock]:
    """Factory for AsyncMock that resolves SHAs from a dict.

    Usage:
        mock = mock_resolve_sha_factory({
            ("actions/checkout", "v4"): "aaaa...",
            ("actions/setup-python", "v4"): "bbbb...",
        })
    """

    def _make(sha_map: dict[tuple[str, str], str]) -> AsyncMock:
        async def mock_resolve_sha(repo: str, ref: str) -> str:
            return sha_map.get((repo, ref), ref)

        return AsyncMock(side_effect=mock_resolve_sha)

    return _make


class FakeClock:
    """Controllable fake clock for deterministic TTL testing."""

    def __init__(self) -> None:
        self._now: float = 0.0

    def __call__(self) -> float:
        """Return current fake time (monotonic-style)."""
        return self._now

    def advance(self, seconds: float) -> None:
        """Move the fake clock forward."""
        self._now += seconds


class FakeDiskCache:
    """In-memory fake implementing _DiskCache Protocol, with real TTL expiry.

    Usage:
        clock = FakeClock()
        cache = FakeDiskCache(clock=clock)
        client = GitHubClient(..., disk_cache=cache)
        clock.advance(3601)  # simulate TTL expiry
    """

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._storage: dict[str, tuple[object, float | None]] = {}
        self._clock: Callable[[], float] = clock if clock is not None else FakeClock()

    def get(self, key: str, default: object = None) -> object:
        """Get cached value or default; evicts and returns default if expired."""
        if key not in self._storage:
            return default
        value, expires_at = self._storage[key]
        if expires_at is not None and self._clock() >= expires_at:
            del self._storage[key]
            return default
        return value

    def set(self, key: str, value: object, expire: int | None = None) -> None:
        """Set cached value with optional TTL (seconds) from current fake time."""
        expires_at = self._clock() + expire if expire is not None else None
        self._storage[key] = (value, expires_at)


@pytest.fixture
def fake_clock() -> FakeClock:
    """Standalone controllable clock fixture for advancing time in tests."""
    return FakeClock()


@pytest.fixture
def fake_disk_cache(fake_clock: FakeClock) -> FakeDiskCache:
    """In-memory fake implementing _DiskCache Protocol.

    Usage:
        client = GitHubClient(..., disk_cache=fake_disk_cache)
        fake_clock.advance(3601)  # simulate TTL expiry
    """
    return FakeDiskCache(clock=fake_clock)
