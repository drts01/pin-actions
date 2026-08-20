"""Shared pytest fixtures and factories."""

from typing import TYPE_CHECKING
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
        max_cache_size: int = 1000,
    ) -> GitHubClient:
        return GitHubClient(
            token=token,
            base_url=base_url,
            concurrency=concurrency,
            max_retries=max_retries,
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
