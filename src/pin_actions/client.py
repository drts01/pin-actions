"""Async GitHub API client with rate limiting and caching."""

import asyncio
import logging
import random
import threading
from collections import OrderedDict
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

import httpx2

from pin_actions._util import is_full_sha
from pin_actions.errors import GitHubAPIError, InvalidRefError, NetworkError, RateLimitExhaustedError

logger = logging.getLogger(__name__)

_MAX_TAG_PAGES = 10  # 100 tags/page cap; guards against runaway pagination on huge repos


class _DiskCache(Protocol):
    """Minimal disk cache interface (duck-typed for diskcache_rs.Cache)."""

    def get(self, key: str, default: object = None) -> object:
        """Get cached value or default."""
        ...

    def set(self, key: str, value: object, expire: int | None = None) -> None:
        """Set cached value with optional TTL."""
        ...


class GitHubClient:
    """Async GitHub API client with thread-safe caching, rate limiting, and backoff."""

    def __init__(
        self,
        token: str | None = None,
        base_url: str = "https://api.github.com",
        concurrency: int = 5,
        max_retries: int = 5,
        disk_cache: _DiskCache | None = None,
        cache_ttl: int = 3600,
        max_cache_size: int = 1000,
    ) -> None:
        """Initialize GitHub client.

        Args:
            token: GitHub API token (optional, uses unauthenticated rate limit if None).
            base_url: GitHub API base URL.
            concurrency: Max concurrent requests via asyncio.Semaphore.
            max_retries: Max retry attempts on 403/429 errors.
            disk_cache: Optional diskcache_rs.Cache instance for persistent caching.
            cache_ttl: TTL in seconds for disk cache entries.
            max_cache_size: Max entries in in-memory cache before LRU eviction (0 = unbounded).
        """
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.max_retries = max_retries
        self.disk_cache = disk_cache
        self.cache_ttl = cache_ttl
        self.max_cache_size = max_cache_size
        self._semaphore = asyncio.Semaphore(concurrency)
        self._cache: OrderedDict[tuple[str, str], str] = OrderedDict()
        self._cache_lock = threading.Lock()
        self._tags_cache: OrderedDict[str, list[tuple[str, str]]] = OrderedDict()
        self._tags_cache_lock = threading.Lock()
        self._http_client: httpx2.AsyncClient | None = None
        self._http_client_lock = asyncio.Lock()

    async def _get_http_client(self) -> httpx2.AsyncClient:
        """Get or create the pooled HTTP client (lazy-init).

        Thread-safe via asyncio.Lock; reuses the same client across all requests
        for connection pooling and performance.
        """
        if self._http_client is None:
            async with self._http_client_lock:
                if self._http_client is None:
                    self._http_client = httpx2.AsyncClient()
        return self._http_client

    async def aclose(self) -> None:
        """Close the pooled HTTP client if it exists."""
        if self._http_client is not None:
            await self._http_client.aclose()

    async def __aenter__(self) -> GitHubClient:
        """Enter async context manager."""
        return self

    async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Exit async context manager, closing pooled client."""
        await self.aclose()

    async def _cached_fetch[T](
        self,
        disk_cache_key: str,
        mem_cache: OrderedDict[Any, T],
        mem_key: Any,  # noqa: ANN401
        mem_lock: threading.Lock,
        fetch: Callable[[], Awaitable[T]],
    ) -> T:
        """Check disk cache → in-memory cache → fetch (gated by semaphore) → write-through both.

        Args:
            disk_cache_key: Key for disk cache lookup/write.
            mem_cache: In-memory cache dict (e.g., _cache or _tags_cache).
            mem_key: Key for in-memory cache lookup/write.
            mem_lock: Lock guarding in-memory cache.
            fetch: Async callable that performs the remote fetch.

        Returns:
            Cached or freshly-fetched value.
        """
        # Check disk cache first
        if self.disk_cache is not None and (cached := self.disk_cache.get(disk_cache_key)) is not None:
            logger.debug(f"Disk cache hit: {disk_cache_key}")
            return cached  # type: ignore[return-value]

        # Check in-memory cache (LRU: touch on hit)
        with mem_lock:
            if mem_key in mem_cache:
                mem_cache.move_to_end(mem_key)
                logger.debug(f"Memory cache hit: {mem_key}")
                return mem_cache[mem_key]

        logger.debug(f"Cache miss (fetching): {mem_key}")
        # Fetch under semaphore (rate limiting)
        async with self._semaphore:
            value = await fetch()

        # Write to in-memory cache with LRU eviction
        with mem_lock:
            mem_cache[mem_key] = value
            if self.max_cache_size and len(mem_cache) > self.max_cache_size:
                mem_cache.popitem(last=False)

        # Write to disk cache
        if self.disk_cache is not None:
            self.disk_cache.set(disk_cache_key, value, expire=self.cache_ttl)

        return value

    async def list_tags(self, repo: str) -> list[tuple[str, str]]:
        """List all tags for a repo as (tag_name, commit_sha) pairs.

        Results are cached per-repo for the lifetime of the client.

        Args:
            repo: Repository in 'owner/repo' format (sub-paths stripped).

        Returns:
            All tags on the remote repository.

        Raises:
            RateLimitExhaustedError: If retries are exhausted while rate-limited.
            NetworkError: On unrecoverable network errors.
        """
        owner_repo = "/".join(repo.split("/")[:2])
        return await self._cached_fetch(
            f"list_tags:{self.base_url}:{owner_repo}",
            self._tags_cache,
            owner_repo,
            self._tags_cache_lock,
            lambda: self._fetch_all_tags(owner_repo),
        )

    async def _fetch_all_tags(self, owner_repo: str) -> list[tuple[str, str]]:
        """Paginate ``GET /repos/{owner_repo}/tags`` and collect all (name, sha) pairs."""
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"token {self.token}"

        tags: list[tuple[str, str]] = []
        client = await self._get_http_client()
        for page in range(1, _MAX_TAG_PAGES + 1):
            url = f"{self.base_url}/repos/{owner_repo}/tags"
            params = {"per_page": 100, "page": page}

            for attempt in range(self.max_retries):
                try:
                    resp = await client.get(url, headers=headers, params=params, timeout=10.0)
                except httpx2.RequestError as exc:
                    if attempt < self.max_retries - 1:
                        await self._backoff(None, attempt)
                        continue
                    raise NetworkError(f"Network error listing tags for {owner_repo}") from exc

                if resp.status_code == 200:
                    break
                if resp.status_code in (403, 429) or resp.status_code >= 500:
                    await self._backoff(resp, attempt)
                    continue
                if resp.status_code == 404:
                    raise GitHubAPIError(f"Repository not found: {owner_repo}")
                resp.raise_for_status()
            else:
                raise RateLimitExhaustedError(owner_repo, "tags", self.max_retries)

            data = resp.json()
            if not data:
                break
            tags.extend((entry["name"], entry["commit"]["sha"]) for entry in data)
            if len(data) < 100:
                break

        return tags

    async def resolve_sha(self, repo: str, ref: str) -> str:
        """Resolve a mutable ref (branch/tag) to its immutable commit SHA.

        Args:
            repo: Repository in 'owner/repo' format (may include sub-path like 'owner/repo/path').
            ref: Commit reference (branch, tag, or partial SHA).

        Returns:
            40-character commit SHA.

        Raises:
            InvalidRefError: If the ref does not exist on the remote repository (404).
            RateLimitExhaustedError: If retries are exhausted while rate-limited.
            NetworkError: On unrecoverable network errors.
        """
        if is_full_sha(ref):
            return ref

        return await self._cached_fetch(
            f"resolve_sha:{self.base_url}:{repo}:{ref}",
            self._cache,
            (repo, ref),
            self._cache_lock,
            lambda: self._request_with_backoff(repo, ref),
        )

    async def _request_with_backoff(self, repo: str, ref: str) -> str:
        """Fetch commit SHA with exponential backoff on rate limits.

        Args:
            repo: Repository in 'owner/repo' format.
            ref: Commit reference.

        Returns:
            40-character commit SHA.

        Raises:
            InvalidRefError: If the ref does not exist on the remote repository (404).
            RateLimitExhaustedError: If retries are exhausted while rate-limited.
            NetworkError: On unrecoverable network errors.
        """
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"token {self.token}"

        # `repo` may include a composite-action subpath (e.g. 'owner/repo/subdir'
        # from 'uses: owner/repo/subdir@ref'); the commits API only accepts
        # 'owner/repo', so strip anything past the second path segment.
        owner_repo = "/".join(repo.split("/")[:2])
        url = f"{self.base_url}/repos/{owner_repo}/commits/{ref}"

        client = await self._get_http_client()
        for attempt in range(self.max_retries):
            try:
                resp = await client.get(url, headers=headers, timeout=10.0)

                if resp.status_code == 200:
                    data = resp.json()
                    return data["sha"]

                if resp.status_code in (403, 429):
                    await self._backoff(resp, attempt)
                    continue

                if resp.status_code == 404:
                    raise InvalidRefError(repo, ref)

                if resp.status_code >= 500:
                    await self._backoff(resp, attempt)
                    continue

                resp.raise_for_status()

            except httpx2.RequestError as exc:
                if attempt < self.max_retries - 1:
                    await self._backoff(None, attempt)
                    continue
                raise NetworkError(f"Network error resolving {repo}@{ref}") from exc

        raise RateLimitExhaustedError(repo, ref, self.max_retries)

    async def _backoff(
        self,
        response: httpx2.Response | None,
        attempt: int,
    ) -> None:
        """Wait with exponential backoff, respecting Retry-After header.

        Args:
            response: HTTP response (None if network error).
            attempt: Current attempt number (0-indexed).
        """
        if response and "Retry-After" in response.headers:
            # Parse Retry-After: can be seconds (int) or HTTP-date
            retry_after_str = response.headers["Retry-After"]
            try:
                delay = float(retry_after_str)
            except ValueError:
                # Fallback: assume it's an HTTP-date, use exponential backoff
                delay = 2**attempt
        else:
            # Exponential backoff with jitter: 2^attempt + random(0, 1)
            delay = 2**attempt + random.random()  # noqa: S311 -- jitter, not crypto

        status = f"(status {response.status_code})" if response else "(network error)"
        logger.warning(f"Retry attempt {attempt + 1}; backing off {delay:.1f}s {status}")
        await asyncio.sleep(min(delay, 60.0))  # Cap at 60 seconds
