"""Tests for GitHubClient (rate limiting, retries, caching, LRU eviction)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pin_actions.client import GitHubClient
from pin_actions.errors import AuthError, InvalidRefError, RateLimitExhaustedError


def _mock_http_client(get_side_effect) -> MagicMock:
    """Build a MagicMock standing in for httpx2.AsyncClient."""
    mock = MagicMock()
    mock.get = AsyncMock(side_effect=get_side_effect)
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=None)
    return mock


class TestResolveShaPinned:
    """Test resolve_sha with already-pinned refs (fast path)."""

    @pytest.mark.asyncio
    async def test_pinned_sha_skip_api_call(self) -> None:
        """Skip API call if ref is already SHA."""
        client = GitHubClient(token="test")
        sha = "abc1234def5678abc1234def5678abc1234def56"

        result = await client.resolve_sha("owner/repo", sha)

        assert result == sha


class TestResolveShaCaching:
    """Test resolve_sha caching behavior."""

    @pytest.mark.asyncio
    async def test_cache_hit_memory(self) -> None:
        """Return cached SHA without second request."""
        client = GitHubClient(token="test", concurrency=1)
        client._sha_cache._store[("owner/repo", "v4")] = "abc1234def5678abc1234def5678abc1234def56"

        result = await client.resolve_sha("owner/repo", "v4")

        assert result == "abc1234def5678abc1234def5678abc1234def56"

    @pytest.mark.asyncio
    async def test_cache_miss_api_call(self) -> None:
        """Mock API response for cache miss."""
        client = GitHubClient(token="test", concurrency=1)
        sha = "abc1234def5678abc1234def5678abc1234def56"

        async def mock_get_json(_path: str, _params: dict | None = None) -> dict:
            return {"sha": sha}

        with patch.object(client, "_get_json", side_effect=mock_get_json):
            result = await client.resolve_sha("owner/repo", "v4")

        assert result == sha
        assert client._sha_cache._store[("owner/repo", "v4")] == sha


class TestResolveShaBehavior:
    """Test resolve_sha error handling and ref resolution."""

    @pytest.mark.asyncio
    async def test_invalid_ref_404_raises(self) -> None:
        """Raise InvalidRefError on 404."""
        client = GitHubClient(token="test", concurrency=1)

        async def mock_get_json(path: str, _params: dict | None = None) -> dict:
            repo = "owner/repo"
            raise InvalidRefError(repo, path)

        with (
            patch.object(client, "_get_json", side_effect=mock_get_json),
            pytest.raises(InvalidRefError, match="Ref not found"),
        ):
            await client.resolve_sha("owner/repo", "nonexistent")

    @pytest.mark.asyncio
    async def test_rate_limit_exhausted_raises(self) -> None:
        """Raise RateLimitExhaustedError after max retries."""
        client = GitHubClient(token="test", concurrency=1, max_retries=2)

        async def mock_get_json(path: str, _params: dict | None = None) -> dict:
            repo = "owner/repo"
            raise RateLimitExhaustedError(repo, path, 2)

        with (
            patch.object(client, "_get_json", side_effect=mock_get_json),
            pytest.raises(RateLimitExhaustedError, match="Failed to resolve"),
        ):
            await client.resolve_sha("owner/repo", "v4")


class TestGetJsonRealPath:
    """Test _get_json with mocked httpx2.AsyncClient."""

    @pytest.mark.asyncio
    async def test_404_response_raises(self) -> None:
        """404 response raises InvalidRefError."""
        client = GitHubClient(token="test", concurrency=1)
        mock_resp = MagicMock(status_code=404)
        mock_http_client = _mock_http_client(lambda *_a, **_k: mock_resp)

        with (
            patch("pin_actions.client.httpx2.AsyncClient", return_value=mock_http_client),
            pytest.raises(InvalidRefError, match="Ref not found"),
        ):
            await client.resolve_sha("owner/repo", "nonexistent")

    @pytest.mark.asyncio
    async def test_429_exhausted_raises(self) -> None:
        """429 response after max retries raises RateLimitExhaustedError."""
        client = GitHubClient(token="test", concurrency=1, max_retries=2)
        mock_resp = MagicMock(status_code=429, headers={"Retry-After": "0"})
        mock_http_client = _mock_http_client(lambda *_a, **_k: mock_resp)

        with (
            patch("pin_actions.client.httpx2.AsyncClient", return_value=mock_http_client),
            pytest.raises(RateLimitExhaustedError, match="Failed to resolve"),
        ):
            await client.resolve_sha("owner/repo", "v4")

    @pytest.mark.asyncio
    async def test_403_not_rate_limited_raises_auth_error(self) -> None:
        """403 with rate limit remaining raises AuthError, not a retry."""
        client = GitHubClient(token="test", concurrency=1, max_retries=3)
        mock_resp = MagicMock(status_code=403, headers={"x-ratelimit-remaining": "10"})
        mock_http_client = _mock_http_client(lambda *_a, **_k: mock_resp)

        with (
            patch("pin_actions.client.httpx2.AsyncClient", return_value=mock_http_client),
            pytest.raises(AuthError, match="403"),
        ):
            await client.resolve_sha("owner/repo", "v4")
        assert mock_http_client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_403_rate_limited_retries(self) -> None:
        """403 with zero rate limit remaining backs off and retries."""
        client = GitHubClient(token="test", concurrency=1, max_retries=3)
        sha = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        responses = [
            MagicMock(status_code=403, headers={"x-ratelimit-remaining": "0", "Retry-After": "0"}),
            MagicMock(status_code=200, json=MagicMock(return_value={"sha": sha})),
        ]
        response_iter = iter(responses)
        mock_http_client = _mock_http_client(lambda *_a, **_k: next(response_iter))

        with patch("pin_actions.client.httpx2.AsyncClient", return_value=mock_http_client):
            result = await client.resolve_sha("owner/repo", "v4")

        assert result == sha
        assert mock_http_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_composite_action_subpath_strips_subdir(self) -> None:
        """Composite action subpath is stripped for API call.

        Regression: 'owner/repo/subdir@ref' hits commits API on 'owner/repo' only.
        """
        client = GitHubClient(token="test", concurrency=1)
        sha = "abc1234def5678abc1234def5678abc1234def56"
        mock_resp = MagicMock(status_code=200, json=MagicMock(return_value={"sha": sha}))
        mock_http_client = _mock_http_client(lambda *_a, **_k: mock_resp)

        with patch("pin_actions.client.httpx2.AsyncClient", return_value=mock_http_client):
            result = await client.resolve_sha("uhg-pipelines/epl-jf/saas-setup", "v5")

        assert result == sha
        called_path = mock_http_client.get.call_args.args[0]
        assert called_path == "/repos/uhg-pipelines/epl-jf/commits/v5"


class TestListTags:
    """Test list_tags API behavior."""

    @pytest.mark.asyncio
    async def test_list_tags_fetch(self) -> None:
        """Fetch tags for repo."""
        client = GitHubClient(token="test", concurrency=1)

        async def mock_fetch_all_tags(_owner_repo: str) -> list[tuple[str, str]]:
            return [("v1", "1111111111111111111111111111111111111111")]

        with patch.object(client, "_fetch_all_tags", side_effect=mock_fetch_all_tags):
            result = await client.list_tags("owner/repo")

        assert result == [("v1", "1111111111111111111111111111111111111111")]


class TestLRUCacheEviction:
    """Test in-memory LRU cache eviction on write."""

    @pytest.mark.asyncio
    async def test_evicts_oldest_on_overflow(self) -> None:
        """LRU eviction when cache size exceeds max_cache_size."""
        client = GitHubClient(token="test", concurrency=1, max_cache_size=2)
        cache = client._sha_cache._store
        cache[("owner/repo", "v1")] = "1111111111111111111111111111111111111111"
        cache[("owner/repo", "v2")] = "2222222222222222222222222222222222222222"

        async def mock_get_json(_path: str, _params: dict | None = None) -> dict:
            return {"sha": "3333333333333333333333333333333333333333"}

        with patch.object(client, "_get_json", side_effect=mock_get_json):
            result = await client.resolve_sha("owner/repo", "v3")

        assert result == "3333333333333333333333333333333333333333"
        assert ("owner/repo", "v1") not in cache
        assert ("owner/repo", "v2") in cache
        assert ("owner/repo", "v3") in cache
        assert len(cache) == 2

    @pytest.mark.asyncio
    async def test_touch_on_hit_prevents_eviction(self) -> None:
        """Cache hit on oldest entry moves it to end, preventing eviction."""
        client = GitHubClient(token="test", concurrency=1, max_cache_size=2)
        cache = client._sha_cache._store
        cache[("owner/repo", "v1")] = "1111111111111111111111111111111111111111"
        cache[("owner/repo", "v2")] = "2222222222222222222222222222222222222222"

        result1 = await client.resolve_sha("owner/repo", "v1")
        assert result1 == "1111111111111111111111111111111111111111"

        async def mock_get_json(_path: str, _params: dict | None = None) -> dict:
            return {"sha": "3333333333333333333333333333333333333333"}

        with patch.object(client, "_get_json", side_effect=mock_get_json):
            result3 = await client.resolve_sha("owner/repo", "v3")

        assert result3 == "3333333333333333333333333333333333333333"
        assert ("owner/repo", "v1") in cache
        assert ("owner/repo", "v2") not in cache
        assert ("owner/repo", "v3") in cache
        assert len(cache) == 2

    @pytest.mark.asyncio
    async def test_tags_cache_eviction(self) -> None:
        """LRU eviction on separate tags cache."""
        client = GitHubClient(token="test", concurrency=1, max_cache_size=2)
        cache = client._tags_cache._store
        cache["owner/repo1"] = [("v1", "1111111111111111111111111111111111111111")]
        cache["owner/repo2"] = [("v2", "2222222222222222222222222222222222222222")]

        async def mock_fetch_all_tags(_owner_repo: str) -> list[tuple[str, str]]:
            return [("v3", "3333333333333333333333333333333333333333")]

        with patch.object(client, "_fetch_all_tags", side_effect=mock_fetch_all_tags):
            result = await client.list_tags("owner/repo3")

        assert result == [("v3", "3333333333333333333333333333333333333333")]
        assert "owner/repo1" not in cache
        assert "owner/repo2" in cache
        assert "owner/repo3" in cache
        assert len(cache) == 2


class TestUnboundedCache:
    """Test max_cache_size=0 disables LRU eviction."""

    @pytest.mark.asyncio
    async def test_unbounded_cache_no_eviction(self) -> None:
        """With max_cache_size=0, cache grows unbounded."""
        client = GitHubClient(token="test", concurrency=1, max_cache_size=0)
        cache = client._sha_cache._store
        for i in range(10):
            sha = f"{i:040d}"
            cache[(f"owner/repo{i}", f"ref{i}")] = sha

        async def mock_get_json(_path: str, _params: dict | None = None) -> dict:
            return {"sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}

        with patch.object(client, "_get_json", side_effect=mock_get_json):
            await client.resolve_sha("owner/repo11", "ref11")

        assert len(cache) == 11
        for i in range(10):
            assert (f"owner/repo{i}", f"ref{i}") in cache
        assert ("owner/repo11", "ref11") in cache


class TestRetryAndBackoff:
    """Test retry logic and exponential backoff."""

    @pytest.mark.asyncio
    async def test_retry_on_429_with_retry_after_header(self) -> None:
        """Retry on 429 with Retry-After header, then succeed."""
        client = GitHubClient(token="test", concurrency=1, max_retries=3)
        responses = [
            MagicMock(status_code=429, headers={"Retry-After": "0.01"}),
            MagicMock(
                status_code=200, json=MagicMock(return_value={"sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"})
            ),
        ]
        response_iter = iter(responses)
        mock_http_client = _mock_http_client(lambda *_a, **_k: next(response_iter))

        with patch("pin_actions.client.httpx2.AsyncClient", return_value=mock_http_client):
            result = await client.resolve_sha("owner/repo", "v4")

        assert result == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        assert mock_http_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_500_with_exponential_backoff(self) -> None:
        """Retry on 500 errors with exponential backoff, then succeed."""
        client = GitHubClient(token="test", concurrency=1, max_retries=3)
        responses = [
            MagicMock(status_code=500, headers={}),
            MagicMock(status_code=503, headers={}),
            MagicMock(
                status_code=200, json=MagicMock(return_value={"sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"})
            ),
        ]
        response_iter = iter(responses)
        mock_http_client = _mock_http_client(lambda *_a, **_k: next(response_iter))

        with patch("pin_actions.client.httpx2.AsyncClient", return_value=mock_http_client):
            result = await client.resolve_sha("owner/repo", "v4")

        assert result == "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        assert mock_http_client.get.call_count == 3


class TestFetchAllTagsPagination:
    """Test _fetch_all_tags pagination."""

    @pytest.mark.asyncio
    async def test_pagination_across_multiple_pages(self) -> None:
        """Paginate across multiple pages of tags."""
        client = GitHubClient(token="test", concurrency=1)
        page_responses = [
            MagicMock(
                status_code=200,
                json=MagicMock(
                    return_value=[
                        {"name": f"v1.{i}", "commit": {"sha": f"{'0' * (39 - len(str(i)))}{i}"}} for i in range(100)
                    ],
                ),
            ),
            MagicMock(
                status_code=200,
                json=MagicMock(
                    return_value=[
                        {"name": f"v1.{i}", "commit": {"sha": f"{'1' * (39 - len(str(i)))}{i}"}} for i in range(50)
                    ],
                ),
            ),
        ]
        response_iter = iter(page_responses)
        mock_http_client = _mock_http_client(lambda *_a, **_k: next(response_iter))

        with patch("pin_actions.client.httpx2.AsyncClient", return_value=mock_http_client):
            tags = await client.list_tags("owner/repo")

        assert len(tags) == 150
        assert mock_http_client.get.call_count == 2


class TestConcurrentDedup:
    """Test single-flight de-duplication prevents cache stampede."""

    @pytest.mark.asyncio
    async def test_concurrent_requests_same_key_single_fetch(self) -> None:
        """Concurrent requests for same key share a single fetch."""
        client = GitHubClient(token="test", concurrency=10)
        call_count = 0

        async def mock_fetch_all_tags(_owner_repo: str) -> list[tuple[str, str]]:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)  # simulate latency
            return [("v1", "1111111111111111111111111111111111111111")]

        with patch.object(client, "_fetch_all_tags", side_effect=mock_fetch_all_tags):
            results = await asyncio.gather(
                client.list_tags("actions/checkout"),
                client.list_tags("actions/checkout"),
                client.list_tags("actions/checkout"),
                client.list_tags("actions/checkout"),
                client.list_tags("actions/checkout"),
            )

        assert call_count == 1
        assert all(r == [("v1", "1111111111111111111111111111111111111111")] for r in results)


class TestVerifyProvenance:
    """Test verify_provenance's branch/PR/tag fallback chain and caching."""

    @pytest.mark.asyncio
    async def test_verified_via_branches_where_head(self) -> None:
        """Non-empty branches-where-head result verifies the SHA."""
        client = GitHubClient(token="test", concurrency=1)
        sha = "a" * 40

        async def mock_get_json(path: str, _params: dict | None = None) -> list:
            assert "branches-where-head" in path
            return [{"name": "main"}]

        with patch.object(client, "_get_json", side_effect=mock_get_json):
            result = await client.verify_provenance("owner/repo", sha)

        assert result == "verified"

    @pytest.mark.asyncio
    async def test_verified_via_matching_pull(self) -> None:
        """Empty branches-where-head, but a matching PR base repo verifies the SHA."""
        client = GitHubClient(token="test", concurrency=1)
        sha = "b" * 40

        async def mock_get_json(path: str, _params: dict | None = None) -> list:
            if "branches-where-head" in path:
                return []
            if "pulls" in path:
                return [{"base": {"repo": {"full_name": "owner/repo"}}}]
            raise AssertionError(path)

        with patch.object(client, "_get_json", side_effect=mock_get_json):
            result = await client.verify_provenance("owner/repo", sha)

        assert result == "verified"

    @pytest.mark.asyncio
    async def test_verified_via_matching_tag(self) -> None:
        """Empty branches/pulls, but a matching tag SHA verifies the SHA."""
        client = GitHubClient(token="test", concurrency=1)
        sha = "c" * 40

        async def mock_get_json(path: str, **_kwargs: object) -> list:
            if "branches-where-head" in path or "pulls" in path:
                return []
            if path == "/repos/owner/repo/tags":
                return [{"name": "v1", "commit": {"sha": sha}}]
            raise AssertionError(path)

        with patch.object(client, "_get_json", side_effect=mock_get_json):
            result = await client.verify_provenance("owner/repo", sha)

        assert result == "verified"

    @pytest.mark.asyncio
    async def test_unverified_when_no_match(self) -> None:
        """No branch/pull/tag match returns unverified."""
        client = GitHubClient(token="test", concurrency=1)
        sha = "d" * 40

        async def mock_get_json(_path: str, **_kwargs: object) -> list:
            return []

        with patch.object(client, "_get_json", side_effect=mock_get_json):
            result = await client.verify_provenance("owner/repo", sha)

        assert result == "unverified"

    @pytest.mark.asyncio
    async def test_404_on_branches_where_head_falls_through(self) -> None:
        """404 on an unsupported endpoint (e.g. old GHE) falls through to the next check."""
        client = GitHubClient(token="test", concurrency=1)
        sha = "e" * 40

        async def mock_get_json(path: str, _params: dict | None = None) -> list:
            if "branches-where-head" in path:
                repo = "owner/repo"
                raise InvalidRefError(repo, path)
            if "pulls" in path:
                return [{"base": {"repo": {"full_name": "owner/repo"}}}]
            raise AssertionError(path)

        with patch.object(client, "_get_json", side_effect=mock_get_json):
            result = await client.verify_provenance("owner/repo", sha)

        assert result == "verified"

    @pytest.mark.asyncio
    async def test_cache_hit_skips_second_fetch(self) -> None:
        """Second call for the same (repo, sha) doesn't re-hit the network."""
        client = GitHubClient(token="test", concurrency=1)
        sha = "f" * 40
        client._provenance_cache._store[("owner/repo", sha)] = "verified"

        with patch.object(client, "_get_json", side_effect=AssertionError("should not be called")):
            result = await client.verify_provenance("owner/repo", sha)

        assert result == "verified"

    @pytest.mark.asyncio
    async def test_concurrent_requests_same_key_single_fetch(self) -> None:
        """Concurrent verify_provenance calls for the same key share a single fetch."""
        client = GitHubClient(token="test", concurrency=10)
        sha = "1" * 40
        call_count = 0

        async def mock_get_json(_path: str, **_kwargs: object) -> list:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return []

        with patch.object(client, "_get_json", side_effect=mock_get_json):
            results = await asyncio.gather(
                client.verify_provenance("owner/repo", sha),
                client.verify_provenance("owner/repo", sha),
                client.verify_provenance("owner/repo", sha),
            )

        assert call_count == 3  # branches-where-head, pulls, tags -- once, then cached
        assert all(r == "unverified" for r in results)


class TestContextManager:
    """Test async context manager interface."""

    @pytest.mark.asyncio
    async def test_context_manager_cleanup(self) -> None:
        """Async context manager properly closes pooled client."""
        client = GitHubClient(token="test")

        async with client as ctx:
            assert ctx is client
