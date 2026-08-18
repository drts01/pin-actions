"""Tests for GitHubClient (rate limiting, retries, caching, LRU eviction)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pin_actions.client import GitHubClient
from pin_actions.errors import InvalidRefError, RateLimitExhaustedError


class TestResolveShaPinned:
    """Test resolve_sha with already-pinned refs (fast path)."""

    @pytest.mark.asyncio
    async def test_pinned_sha_skip_api_call(self) -> None:
        """Skip API call if ref is already SHA."""
        # Arrange
        client = GitHubClient(token="test")
        sha = "abc1234def5678abc1234def5678abc1234def56"

        # Act
        result = await client.resolve_sha("owner/repo", sha)

        # Assert
        assert result == sha


class TestResolveShaCaching:
    """Test resolve_sha caching behavior."""

    @pytest.mark.asyncio
    async def test_cache_hit_memory(self) -> None:
        """Return cached SHA without second request."""
        # Arrange
        client = GitHubClient(token="test", concurrency=1)
        client._cache[("owner/repo", "v4")] = "abc1234def5678abc1234def5678abc1234def56"

        # Act
        result = await client.resolve_sha("owner/repo", "v4")

        # Assert
        assert result == "abc1234def5678abc1234def5678abc1234def56"

    @pytest.mark.asyncio
    async def test_cache_miss_api_call(self) -> None:
        """Mock API response for cache miss."""
        # Arrange
        client = GitHubClient(token="test", concurrency=1)
        sha = "abc1234def5678abc1234def5678abc1234def56"

        async def mock_request_with_backoff(_repo: str, _ref: str) -> str:
            return sha

        # Act
        with patch.object(client, "_request_with_backoff", side_effect=mock_request_with_backoff):
            result = await client.resolve_sha("owner/repo", "v4")

        # Assert
        assert result == sha
        assert client._cache[("owner/repo", "v4")] == sha


class TestResolveShaBehavior:
    """Test resolve_sha error handling and ref resolution."""

    @pytest.mark.asyncio
    async def test_invalid_ref_404_raises(self) -> None:
        """Raise InvalidRefError on 404."""
        # Arrange
        client = GitHubClient(token="test", concurrency=1)

        async def mock_request_with_backoff(repo: str, ref: str) -> str:
            raise InvalidRefError(repo, ref)

        # Act, Assert
        with (
            patch.object(client, "_request_with_backoff", side_effect=mock_request_with_backoff),
            pytest.raises(InvalidRefError, match="Ref not found"),
        ):
            await client.resolve_sha("owner/repo", "nonexistent")

    @pytest.mark.asyncio
    async def test_rate_limit_exhausted_raises(self) -> None:
        """Raise RateLimitExhaustedError after max retries."""
        # Arrange
        client = GitHubClient(token="test", concurrency=1, max_retries=2)

        async def mock_request_with_backoff(repo: str, ref: str) -> str:
            raise RateLimitExhaustedError(repo, ref, 2)

        # Act, Assert
        with (
            patch.object(client, "_request_with_backoff", side_effect=mock_request_with_backoff),
            pytest.raises(RateLimitExhaustedError, match="Failed to resolve"),
        ):
            await client.resolve_sha("owner/repo", "v4")


class TestRequestWithBackoffRealPath:
    """Test _request_with_backoff with mocked httpx2.AsyncClient."""

    @pytest.mark.asyncio
    async def test_404_response_raises(self) -> None:
        """404 response raises InvalidRefError."""
        # Arrange
        client = GitHubClient(token="test", concurrency=1)

        mock_resp = MagicMock()
        mock_resp.status_code = 404

        mock_http_client = MagicMock()
        mock_http_client.get = AsyncMock(return_value=mock_resp)
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=None)

        # Act, Assert
        with (
            patch("pin_actions.client.httpx2.AsyncClient", return_value=mock_http_client),
            pytest.raises(InvalidRefError, match="Ref not found"),
        ):
            await client.resolve_sha("owner/repo", "nonexistent")

    @pytest.mark.asyncio
    async def test_429_exhausted_raises(self) -> None:
        """429 response after max retries raises RateLimitExhaustedError."""
        # Arrange
        client = GitHubClient(token="test", concurrency=1, max_retries=2)

        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {"Retry-After": "0"}

        mock_http_client = MagicMock()
        mock_http_client.get = AsyncMock(return_value=mock_resp)
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=None)

        # Act, Assert
        with (
            patch("pin_actions.client.httpx2.AsyncClient", return_value=mock_http_client),
            pytest.raises(RateLimitExhaustedError, match="Failed to resolve"),
        ):
            await client.resolve_sha("owner/repo", "v4")

    @pytest.mark.asyncio
    async def test_composite_action_subpath_strips_subdir(self) -> None:
        """Composite action subpath is stripped for API call.

        Regression: 'owner/repo/subdir@ref' hits commits API on 'owner/repo' only.
        """
        # Arrange
        client = GitHubClient(token="test", concurrency=1)
        sha = "abc1234def5678abc1234def5678abc1234def56"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"sha": sha}

        mock_http_client = MagicMock()
        mock_http_client.get = AsyncMock(return_value=mock_resp)
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=None)

        # Act
        with patch("pin_actions.client.httpx2.AsyncClient", return_value=mock_http_client):
            result = await client.resolve_sha("uhg-pipelines/epl-jf/saas-setup", "v5")

        # Assert
        assert result == sha
        called_url = mock_http_client.get.call_args.args[0]
        assert called_url.endswith("/repos/uhg-pipelines/epl-jf/commits/v5")


class TestListTags:
    """Test list_tags API behavior."""

    @pytest.mark.asyncio
    async def test_list_tags_fetch(self) -> None:
        """Fetch tags for repo."""
        # Arrange
        client = GitHubClient(token="test", concurrency=1)

        async def mock_fetch_all_tags(_owner_repo: str) -> list[tuple[str, str]]:
            return [("v1", "1111111111111111111111111111111111111111")]

        # Act
        with patch.object(client, "_fetch_all_tags", side_effect=mock_fetch_all_tags):
            result = await client.list_tags("owner/repo")

        # Assert
        assert result == [("v1", "1111111111111111111111111111111111111111")]


class TestLRUCacheEviction:
    """Test in-memory LRU cache eviction on write."""

    @pytest.mark.asyncio
    async def test_evicts_oldest_on_overflow(self) -> None:
        """LRU eviction when cache size exceeds max_cache_size."""
        # Arrange
        client = GitHubClient(token="test", concurrency=1, max_cache_size=2)
        client._cache[("owner/repo", "v1")] = "1111111111111111111111111111111111111111"
        client._cache[("owner/repo", "v2")] = "2222222222222222222222222222222222222222"

        async def mock_request_with_backoff(_repo: str, _ref: str) -> str:
            return "3333333333333333333333333333333333333333"

        # Act
        with patch.object(client, "_request_with_backoff", side_effect=mock_request_with_backoff):
            result = await client.resolve_sha("owner/repo", "v3")

        # Assert
        assert result == "3333333333333333333333333333333333333333"
        assert ("owner/repo", "v1") not in client._cache
        assert ("owner/repo", "v2") in client._cache
        assert ("owner/repo", "v3") in client._cache
        assert len(client._cache) == 2

    @pytest.mark.asyncio
    async def test_touch_on_hit_prevents_eviction(self) -> None:
        """Cache hit on oldest entry moves it to end, preventing eviction."""
        # Arrange
        client = GitHubClient(token="test", concurrency=1, max_cache_size=2)
        client._cache[("owner/repo", "v1")] = "1111111111111111111111111111111111111111"
        client._cache[("owner/repo", "v2")] = "2222222222222222222222222222222222222222"

        # Act: hit v1 (oldest), should move to end
        result1 = await client.resolve_sha("owner/repo", "v1")
        assert result1 == "1111111111111111111111111111111111111111"

        async def mock_request_with_backoff(_repo: str, _ref: str) -> str:
            return "3333333333333333333333333333333333333333"

        # Act: resolve v3, which should evict v2 (now oldest after v1 touch), not v1
        with patch.object(client, "_request_with_backoff", side_effect=mock_request_with_backoff):
            result3 = await client.resolve_sha("owner/repo", "v3")

        # Assert
        assert result3 == "3333333333333333333333333333333333333333"
        assert ("owner/repo", "v1") in client._cache
        assert ("owner/repo", "v2") not in client._cache
        assert ("owner/repo", "v3") in client._cache
        assert len(client._cache) == 2

    @pytest.mark.asyncio
    async def test_tags_cache_eviction(self) -> None:
        """LRU eviction on separate _tags_cache."""
        # Arrange
        client = GitHubClient(token="test", concurrency=1, max_cache_size=2)
        client._tags_cache["owner/repo1"] = [("v1", "1111111111111111111111111111111111111111")]
        client._tags_cache["owner/repo2"] = [("v2", "2222222222222222222222222222222222222222")]

        async def mock_fetch_all_tags(_owner_repo: str) -> list[tuple[str, str]]:
            return [("v3", "3333333333333333333333333333333333333333")]

        # Act
        with patch.object(client, "_fetch_all_tags", side_effect=mock_fetch_all_tags):
            result = await client.list_tags("owner/repo3")

        # Assert
        assert result == [("v3", "3333333333333333333333333333333333333333")]
        assert "owner/repo1" not in client._tags_cache
        assert "owner/repo2" in client._tags_cache
        assert "owner/repo3" in client._tags_cache
        assert len(client._tags_cache) == 2


class TestMemoryCacheNoExpiry:
    """Pin current behavior: in-memory cache has no TTL (unlike disk cache)."""

    @pytest.mark.asyncio
    async def test_memory_cache_never_expires(self, make_client) -> None:  # type: ignore[no-untyped-def]
        """In-memory cache serves stale values indefinitely; only disk cache honors TTL."""
        # Arrange: no disk_cache, so only in-memory _cache is exercised
        client = make_client(cache_ttl=1)  # cache_ttl is irrelevant to memory cache
        sha = "ffffffffffffffffffffffffffffffffffffffff"
        call_count = 0

        async def mock_request_with_backoff(_repo: str, _ref: str) -> str:
            nonlocal call_count
            call_count += 1
            return sha

        # Act
        with patch.object(client, "_request_with_backoff", side_effect=mock_request_with_backoff):
            await client.resolve_sha("owner/repo", "v1")
            await client.resolve_sha("owner/repo", "v1")  # would-be "expired" if TTL applied

        # Assert: only one real fetch — memory cache never expires regardless of cache_ttl
        assert call_count == 1


class TestUnboundedCache:
    """Test max_cache_size=0 disables LRU eviction."""

    @pytest.mark.asyncio
    async def test_unbounded_cache_no_eviction(self) -> None:
        """With max_cache_size=0, cache grows unbounded."""
        # Arrange
        client = GitHubClient(token="test", concurrency=1, max_cache_size=0)
        for i in range(10):
            sha = f"{i:040d}"
            client._cache[(f"owner/repo{i}", f"ref{i}")] = sha

        async def mock_request_with_backoff(_repo: str, _ref: str) -> str:
            return "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

        # Act
        with patch.object(client, "_request_with_backoff", side_effect=mock_request_with_backoff):
            await client.resolve_sha("owner/repo11", "ref11")

        # Assert
        assert len(client._cache) == 11
        for i in range(10):
            assert (f"owner/repo{i}", f"ref{i}") in client._cache
        assert ("owner/repo11", "ref11") in client._cache


class TestRetryAndBackoff:
    """Test retry logic and exponential backoff."""

    @pytest.mark.asyncio
    async def test_retry_on_429_with_retry_after_header(self) -> None:
        """Retry on 429 with Retry-After header, then succeed."""
        # Arrange
        client = GitHubClient(token="test", concurrency=1, max_retries=3)
        responses = [
            MagicMock(status_code=429, headers={"Retry-After": "0.01"}),
            MagicMock(
                status_code=200,
                json=MagicMock(return_value={"sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}),
            ),
        ]
        response_iter = iter(responses)

        mock_http_client = MagicMock()
        mock_http_client.get = AsyncMock(side_effect=lambda *_args, **_kwargs: next(response_iter))
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=None)

        # Act
        with patch("pin_actions.client.httpx2.AsyncClient", return_value=mock_http_client):
            result = await client.resolve_sha("owner/repo", "v4")

        # Assert
        assert result == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        assert mock_http_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_500_with_exponential_backoff(self) -> None:
        """Retry on 500 errors with exponential backoff, then succeed."""
        # Arrange
        client = GitHubClient(token="test", concurrency=1, max_retries=3)
        responses = [
            MagicMock(status_code=500),
            MagicMock(status_code=503),
            MagicMock(
                status_code=200,
                json=MagicMock(return_value={"sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}),
            ),
        ]
        response_iter = iter(responses)

        mock_http_client = MagicMock()
        mock_http_client.get = AsyncMock(side_effect=lambda *_args, **_kwargs: next(response_iter))
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=None)

        # Act
        with patch("pin_actions.client.httpx2.AsyncClient", return_value=mock_http_client):
            result = await client.resolve_sha("owner/repo", "v4")

        # Assert
        assert result == "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        assert mock_http_client.get.call_count == 3


class TestFetchAllTagsPagination:
    """Test _fetch_all_tags pagination."""

    @pytest.mark.asyncio
    async def test_pagination_across_multiple_pages(self) -> None:
        """Paginate across multiple pages of tags."""
        # Arrange
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

        mock_http_client = MagicMock()
        mock_http_client.get = AsyncMock(side_effect=lambda *_args, **_kwargs: next(response_iter))
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=None)

        # Act
        with patch("pin_actions.client.httpx2.AsyncClient", return_value=mock_http_client):
            tags = await client.list_tags("owner/repo")

        # Assert
        assert len(tags) == 150
        assert mock_http_client.get.call_count == 2


class TestDiskCache:
    """Test persistent disk cache behavior."""

    @pytest.mark.asyncio
    async def test_disk_cache_hit(self, fake_disk_cache: object) -> None:
        """Disk cache hit: return cached value without API call."""
        # Arrange
        client = GitHubClient(token="test", concurrency=1, disk_cache=fake_disk_cache)  # type: ignore[arg-type]
        sha = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

        # Pre-populate disk cache with a key
        fake_disk_cache.set("resolve_sha:https://api.github.com:actions/checkout:v4", sha)  # type: ignore[union-attr]

        # Act
        result = await client.resolve_sha("actions/checkout", "v4")

        # Assert
        assert result == sha

    @pytest.mark.asyncio
    async def test_disk_cache_write_through(self, fake_disk_cache: object) -> None:
        """Disk cache write-through: fetched value gets written to disk cache."""
        # Arrange
        client = GitHubClient(token="test", concurrency=1, disk_cache=fake_disk_cache, cache_ttl=3600)  # type: ignore[arg-type]
        sha = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

        async def mock_request_with_backoff(_repo: str, _ref: str) -> str:
            return sha

        # Act
        with patch.object(client, "_request_with_backoff", side_effect=mock_request_with_backoff):
            result = await client.resolve_sha("actions/checkout", "v4")

        # Assert
        assert result == sha
        # Verify value was written to disk cache
        cache_key = "resolve_sha:https://api.github.com:actions/checkout:v4"
        assert fake_disk_cache.get(cache_key) == sha  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_tags_list_disk_cache_hit(self, fake_disk_cache: object) -> None:
        """Disk cache hit for list_tags."""
        # Arrange
        client = GitHubClient(token="test", concurrency=1, disk_cache=fake_disk_cache)  # type: ignore[arg-type]
        tags = [("v1", "1111111111111111111111111111111111111111")]

        # Pre-populate disk cache
        fake_disk_cache.set("list_tags:https://api.github.com:actions/checkout", tags)  # type: ignore[union-attr]

        # Act
        result = await client.list_tags("actions/checkout")

        # Assert
        assert result == tags

    @pytest.mark.asyncio
    async def test_disk_cache_expires_after_ttl(self, fake_disk_cache: object, fake_clock: object) -> None:
        """After TTL elapses, a fresh API call is made instead of serving stale cache."""
        # Arrange
        client = GitHubClient(token="test", concurrency=1, disk_cache=fake_disk_cache, cache_ttl=3600)  # type: ignore[arg-type]
        old_sha = "cccccccccccccccccccccccccccccccccccccccc"
        new_sha = "dddddddddddddddddddddddddddddddddddddddd"
        call_count = 0

        async def mock_request_with_backoff(_repo: str, _ref: str) -> str:
            nonlocal call_count
            call_count += 1
            return new_sha if call_count > 1 else old_sha

        # Act: first call populates cache
        with patch.object(client, "_request_with_backoff", side_effect=mock_request_with_backoff):
            first = await client.resolve_sha("actions/checkout", "v5")
        # Advance clock past TTL, then clear in-memory cache to isolate disk-cache expiry
        fake_clock.advance(3601)  # type: ignore[attr-defined]
        client._cache.clear()
        # Second call after expiry must hit the API again
        with patch.object(client, "_request_with_backoff", side_effect=mock_request_with_backoff):
            second = await client.resolve_sha("actions/checkout", "v5")

        # Assert
        assert first == old_sha
        assert second == new_sha
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_disk_cache_not_expired_within_ttl(self, fake_disk_cache: object, fake_clock: object) -> None:
        """Within TTL, cached value is served without a new API call."""
        # Arrange
        client = GitHubClient(token="test", concurrency=1, disk_cache=fake_disk_cache, cache_ttl=3600)  # type: ignore[arg-type]
        sha = "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
        call_count = 0

        async def mock_request_with_backoff(_repo: str, _ref: str) -> str:
            nonlocal call_count
            call_count += 1
            return sha

        # Act: first call populates cache
        with patch.object(client, "_request_with_backoff", side_effect=mock_request_with_backoff):
            first = await client.resolve_sha("actions/checkout", "v6")
        # Advance clock but stay within TTL, then clear in-memory cache to isolate disk-cache
        fake_clock.advance(3599)  # type: ignore[attr-defined]
        client._cache.clear()
        with patch.object(client, "_request_with_backoff", side_effect=mock_request_with_backoff):
            second = await client.resolve_sha("actions/checkout", "v6")

        # Assert
        assert first == sha
        assert second == sha
        assert call_count == 1  # only one real fetch; second call served from cache


class TestContextManager:
    """Test async context manager interface."""

    @pytest.mark.asyncio
    async def test_context_manager_cleanup(self) -> None:
        """Async context manager properly closes pooled client."""
        # Arrange
        client = GitHubClient(token="test")

        # Act, Assert
        async with client as ctx:
            assert ctx is client
