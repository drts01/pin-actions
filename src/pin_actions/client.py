"""Async GitHub API client with rate limiting and caching."""

import asyncio
import http
import logging
import random
from collections import OrderedDict
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

import httpx2

from pin_actions._util import is_full_sha
from pin_actions.errors import GitHubAPIError, InvalidRefError, NetworkError, RateLimitExhaustedError

logger = logging.getLogger(__name__)

_MAX_TAG_PAGES = 10  # 100 tags/page cap; guards against runaway pagination on huge repos
_TAGS_PER_PAGE = 100


class GitHubClient:
    """Async GitHub API client with in-memory LRU caching, rate limiting, and backoff."""

    def __init__(
        self,
        token: str | None = None,
        base_url: str = "https://api.github.com",
        concurrency: int = 5,
        max_retries: int = 5,
        max_cache_size: int = 1000,
    ) -> None:
        """Initialize GitHub client.

        Args:
            token: GitHub API token (optional, uses unauthenticated rate limit if None).
            base_url: GitHub API base URL.
            concurrency: Max concurrent requests via asyncio.Semaphore.
            max_retries: Max retry attempts on 403/429 errors.
            max_cache_size: Max entries in in-memory cache before LRU eviction (0 = unbounded).
        """
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.max_retries = max_retries
        self.max_cache_size = max_cache_size
        self._semaphore = asyncio.Semaphore(concurrency)
        self._cache: OrderedDict[tuple[str, str], str] = OrderedDict()
        self._cache_inflight: dict[Any, asyncio.Task[str]] = {}
        self._tags_cache: OrderedDict[str, list[tuple[str, str]]] = OrderedDict()
        self._tags_cache_inflight: dict[Any, asyncio.Task[list[tuple[str, str]]]] = {}
        self._commit_date_cache: OrderedDict[tuple[str, str], str] = OrderedDict()
        self._commit_date_cache_inflight: dict[Any, asyncio.Task[str]] = {}
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

    async def __aenter__(self) -> Self:
        """Enter async context manager."""
        return self

    async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Exit async context manager, closing pooled client."""
        await self.aclose()

    async def _cached_fetch[T](
        self,
        cache: OrderedDict[Any, T],
        inflight: dict[Any, asyncio.Task[T]],
        key: Any,  # noqa: ANN401
        fetch: Callable[[], Awaitable[T]],
    ) -> T:
        """Check in-memory cache → in-flight dedup → fetch → write-through cache.

        Prevents cache stampede by de-duplicating concurrent requests for the same key.

        Args:
            cache: In-memory cache dict (e.g., _cache or _tags_cache).
            inflight: Tracking dict for in-flight fetches (same type as cache).
            key: Key for in-memory cache lookup/write.
            fetch: Async callable that performs the remote fetch.

        Returns:
            Cached or freshly-fetched value.
        """
        if key in cache:
            cache.move_to_end(key)
            logger.debug("Cache hit: %s", key)
            return cache[key]

        if key in inflight:
            logger.debug("Awaiting in-flight fetch: %s", key)
            return await inflight[key]

        async def _fetch_and_store() -> T:
            async with self._semaphore:
                value = await fetch()
            cache[key] = value
            if self.max_cache_size and len(cache) > self.max_cache_size:
                cache.popitem(last=False)
            return value

        logger.debug("Cache miss (fetching): %s", key)
        task: asyncio.Task[T] = asyncio.ensure_future(_fetch_and_store())
        inflight[key] = task
        try:
            return await task
        finally:
            inflight.pop(key, None)

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
            self._tags_cache,
            self._tags_cache_inflight,
            owner_repo,
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
            params = {"per_page": _TAGS_PER_PAGE, "page": page}

            for attempt in range(self.max_retries):
                try:
                    resp = await client.get(url, headers=headers, params=params, timeout=10.0)
                except httpx2.RequestError as exc:
                    if attempt < self.max_retries - 1:
                        await self._backoff(None, attempt)
                        continue
                    msg = f"Network error listing tags for {owner_repo}"
                    raise NetworkError(msg) from exc

                if resp.status_code == http.HTTPStatus.OK:
                    break
                if resp.status_code in (403, 429) or resp.status_code >= http.HTTPStatus.INTERNAL_SERVER_ERROR:
                    await self._backoff(resp, attempt)
                    continue
                if resp.status_code == http.HTTPStatus.NOT_FOUND:
                    msg = f"Repository not found: {owner_repo}"
                    raise GitHubAPIError(msg)
                resp.raise_for_status()
            else:
                raise RateLimitExhaustedError(owner_repo, "tags", self.max_retries)

            data = resp.json()
            if not data:
                break
            tags.extend((entry["name"], entry["commit"]["sha"]) for entry in data)
            if len(data) < _TAGS_PER_PAGE:
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
            self._cache,
            self._cache_inflight,
            (repo, ref),
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

                if resp.status_code == http.HTTPStatus.OK:
                    data = resp.json()
                    return data["sha"]

                if resp.status_code in (403, 429):
                    await self._backoff(resp, attempt)
                    continue

                if resp.status_code == http.HTTPStatus.NOT_FOUND:
                    raise InvalidRefError(repo, ref)

                if resp.status_code >= http.HTTPStatus.INTERNAL_SERVER_ERROR:
                    await self._backoff(resp, attempt)
                    continue

                resp.raise_for_status()

            except httpx2.RequestError as exc:
                if attempt < self.max_retries - 1:
                    await self._backoff(None, attempt)
                    continue
                msg = f"Network error resolving {repo}@{ref}"
                raise NetworkError(msg) from exc

        raise RateLimitExhaustedError(repo, ref, self.max_retries)

    async def get_commit_date(self, repo: str, sha: str) -> str:
        """Fetch commit date as RFC 3339 string for a given SHA.

        Results are cached per-repo-sha for the lifetime of the client.

        Args:
            repo: Repository in 'owner/repo' format (may include sub-path).
            sha: Commit SHA (40-char or short).

        Returns:
            RFC 3339 timestamp string (e.g., '2006-12-02T15:04:05Z').

        Raises:
            InvalidRefError: If the commit does not exist on the remote repository (404).
            RateLimitExhaustedError: If retries are exhausted while rate-limited.
            NetworkError: On unrecoverable network errors.
        """
        owner_repo = "/".join(repo.split("/")[:2])
        return await self._cached_fetch(
            self._commit_date_cache,
            self._commit_date_cache_inflight,
            (owner_repo, sha),
            lambda: self._fetch_commit_date(owner_repo, sha),
        )

    async def _fetch_commit_date(self, owner_repo: str, sha: str) -> str:
        """Fetch commit date with exponential backoff on rate limits.

        Args:
            owner_repo: Repository in 'owner/repo' format.
            sha: Commit SHA.

        Returns:
            RFC 3339 timestamp string.

        Raises:
            InvalidRefError: If the commit does not exist (404).
            RateLimitExhaustedError: If retries are exhausted while rate-limited.
            NetworkError: On unrecoverable network errors.
        """
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"token {self.token}"

        url = f"{self.base_url}/repos/{owner_repo}/commits/{sha}"
        client = await self._get_http_client()

        for attempt in range(self.max_retries):
            try:
                resp = await client.get(url, headers=headers, timeout=10.0)

                if resp.status_code == http.HTTPStatus.OK:
                    data = resp.json()
                    return data["commit"]["committer"]["date"]

                if resp.status_code in (403, 429):
                    await self._backoff(resp, attempt)
                    continue

                if resp.status_code == http.HTTPStatus.NOT_FOUND:
                    raise InvalidRefError(owner_repo, sha)

                if resp.status_code >= http.HTTPStatus.INTERNAL_SERVER_ERROR:
                    await self._backoff(resp, attempt)
                    continue

                resp.raise_for_status()

            except httpx2.RequestError as exc:
                if attempt < self.max_retries - 1:
                    await self._backoff(None, attempt)
                    continue
                msg = f"Network error fetching commit date for {owner_repo}@{sha}"
                raise NetworkError(msg) from exc

        raise RateLimitExhaustedError(owner_repo, sha, self.max_retries)

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
        logger.warning("Retry attempt %d; backing off %.1fs %s", attempt + 1, delay, status)
        await asyncio.sleep(min(delay, 60.0))  # Cap at 60 seconds
