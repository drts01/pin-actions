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
from pin_actions.errors import AuthError, GitHubAPIError, InvalidRefError, NetworkError, RateLimitExhaustedError

logger = logging.getLogger(__name__)

_MAX_TAG_PAGES = 10  # 100 tags/page cap; guards against runaway pagination on huge repos
_TAGS_PER_PAGE = 100
_USER_AGENT = "pin-actions"


class _Cache[T]:
    """LRU-with-single-flight-dedup cache for one kind of fetch."""

    __slots__ = ("_inflight", "_store", "max_size")

    def __init__(self, max_size: int) -> None:
        """Initialize with an eviction threshold (0 = unbounded)."""
        self.max_size = max_size
        self._store: OrderedDict[Any, T] = OrderedDict()
        self._inflight: dict[Any, asyncio.Task[T]] = {}

    def __contains__(self, key: object) -> bool:
        """Check membership without touching LRU order."""
        return key in self._store

    async def get_or_fetch(self, key: Any, fetch: Callable[[], Awaitable[T]]) -> T:  # noqa: ANN401
        """Check cache → in-flight dedup → fetch → write-through cache.

        Prevents cache stampede by de-duplicating concurrent requests for the same key.
        """
        if key in self._store:
            self._store.move_to_end(key)
            logger.debug("Cache hit: %s", key)
            return self._store[key]

        if key in self._inflight:
            logger.debug("Awaiting in-flight fetch: %s", key)
            return await self._inflight[key]

        async def _fetch_and_store() -> T:
            value = await fetch()
            self._store[key] = value
            if self.max_size and len(self._store) > self.max_size:
                self._store.popitem(last=False)
            return value

        logger.debug("Cache miss (fetching): %s", key)
        task: asyncio.Task[T] = asyncio.ensure_future(_fetch_and_store())
        self._inflight[key] = task
        try:
            return await task
        finally:
            self._inflight.pop(key, None)


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
        self._semaphore = asyncio.Semaphore(concurrency)
        self._sha_cache = _Cache[str](max_cache_size)
        self._tags_cache = _Cache[list[tuple[str, str]]](max_cache_size)
        self._date_cache = _Cache[str](max_cache_size)
        self._http_client: httpx2.AsyncClient | None = None
        self._http_client_lock = asyncio.Lock()

    async def _get_http_client(self) -> httpx2.AsyncClient:
        """Get or create the pooled HTTP client (lazy-init, thread-safe via asyncio.Lock)."""
        if self._http_client is None:
            async with self._http_client_lock:
                if self._http_client is None:
                    headers = {"Accept": "application/vnd.github+json", "User-Agent": _USER_AGENT}
                    if self.token:
                        headers["Authorization"] = f"token {self.token}"
                    self._http_client = httpx2.AsyncClient(
                        base_url=self.base_url,
                        headers=headers,
                        timeout=10.0,
                        limits=httpx2.Limits(max_connections=self._semaphore._value),
                    )
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

    async def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:  # noqa: ANN401
        """GET ``path`` with retry/backoff on 403/429/5xx, raising on 404 or exhaustion.

        Args:
            path: API path relative to ``base_url`` (e.g. '/repos/owner/repo/tags').
            params: Optional query params.

        Returns:
            Parsed JSON body.

        Raises:
            InvalidRefError: On 404 (caller supplies repo/ref context via subclassed callers).
            AuthError: On 403 that isn't rate-limit related.
            RateLimitExhaustedError: If retries are exhausted while rate-limited.
            NetworkError: On unrecoverable network errors.
        """
        client = await self._get_http_client()
        for attempt in range(self.max_retries):
            try:
                async with self._semaphore:
                    resp = await client.get(path, params=params)
            except httpx2.RequestError as exc:
                if attempt < self.max_retries - 1:
                    await self._backoff(None, attempt)
                    continue
                msg = f"Network error requesting {path}"
                raise NetworkError(msg) from exc

            if resp.status_code == http.HTTPStatus.OK:
                return resp.json()
            if resp.status_code == http.HTTPStatus.NOT_FOUND:
                raise InvalidRefError(self.base_url, path)
            if resp.status_code == http.HTTPStatus.FORBIDDEN and resp.headers.get("x-ratelimit-remaining") == "0":
                await self._backoff(resp, attempt)
                continue
            if resp.status_code == http.HTTPStatus.FORBIDDEN:
                raise AuthError(path)
            if (
                resp.status_code == http.HTTPStatus.TOO_MANY_REQUESTS
                or resp.status_code >= http.HTTPStatus.INTERNAL_SERVER_ERROR
            ):
                await self._backoff(resp, attempt)
                continue
            resp.raise_for_status()

        raise RateLimitExhaustedError(self.base_url, path, self.max_retries)

    @staticmethod
    def _owner_repo(repo: str) -> str:
        """Strip a composite-action subpath (e.g. 'owner/repo/subdir') down to 'owner/repo'."""
        return "/".join(repo.split("/")[:2])

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
        owner_repo = self._owner_repo(repo)
        return await self._tags_cache.get_or_fetch(owner_repo, lambda: self._fetch_all_tags(owner_repo))

    async def _fetch_all_tags(self, owner_repo: str) -> list[tuple[str, str]]:
        """Paginate ``GET /repos/{owner_repo}/tags`` and collect all (name, sha) pairs."""
        path = f"/repos/{owner_repo}/tags"
        tags: list[tuple[str, str]] = []
        for page in range(1, _MAX_TAG_PAGES + 1):
            try:
                data = await self._get_json(path, params={"per_page": _TAGS_PER_PAGE, "page": page})
            except InvalidRefError as exc:
                msg = f"Repository not found: {owner_repo}"
                raise GitHubAPIError(msg) from exc
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

        owner_repo = self._owner_repo(repo)

        async def _fetch() -> str:
            try:
                data = await self._get_json(f"/repos/{owner_repo}/commits/{ref}")
            except InvalidRefError as exc:
                raise InvalidRefError(repo, ref) from exc
            return data["sha"]

        return await self._sha_cache.get_or_fetch((repo, ref), _fetch)

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
        owner_repo = self._owner_repo(repo)

        async def _fetch() -> str:
            try:
                data = await self._get_json(f"/repos/{owner_repo}/commits/{sha}")
            except InvalidRefError as exc:
                raise InvalidRefError(owner_repo, sha) from exc
            return data["commit"]["committer"]["date"]

        return await self._date_cache.get_or_fetch((owner_repo, sha), _fetch)

    async def _backoff(
        self,
        response: httpx2.Response | None,
        attempt: int,
    ) -> None:
        """Wait with exponential backoff, respecting Retry-After / X-RateLimit-Reset headers.

        Args:
            response: HTTP response (None if network error).
            attempt: Current attempt number (0-indexed).
        """
        delay: float = 2**attempt + random.random()  # noqa: S311 -- jitter, not crypto
        if response:
            for header in ("Retry-After", "x-ratelimit-reset"):
                if header not in response.headers:
                    continue
                try:
                    value = float(response.headers[header])
                    delay = max(0.0, value if header == "Retry-After" else value - asyncio.get_event_loop().time())
                except ValueError:
                    continue
                break

        status = f"(status {response.status_code})" if response else "(network error)"
        logger.warning("Retry attempt %d; backing off %.1fs %s", attempt + 1, delay, status)
        await asyncio.sleep(min(delay, 60.0))  # Cap at 60 seconds
