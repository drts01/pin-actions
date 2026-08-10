"""Async GitHub API client with rate limiting and caching."""

import asyncio
import random
import threading

import httpx2

from pin_actions.errors import InvalidRefError, NetworkError, RateLimitExhaustedError


class GitHubClient:
    """Async GitHub API client with thread-safe caching, rate limiting, and backoff."""

    def __init__(
        self,
        token: str | None = None,
        base_url: str = "https://api.github.com",
        concurrency: int = 5,
        max_retries: int = 5,
    ) -> None:
        """Initialize GitHub client.

        Args:
            token: GitHub API token (optional, uses unauthenticated rate limit if None).
            base_url: GitHub API base URL.
            concurrency: Max concurrent requests via asyncio.Semaphore.
            max_retries: Max retry attempts on 403/429 errors.
        """
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.max_retries = max_retries
        self._semaphore = asyncio.Semaphore(concurrency)
        self._cache: dict[tuple[str, str], str] = {}
        self._cache_lock = threading.Lock()

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
        # Fast path: already a full SHA
        if len(ref) == 40 and all(c in "0123456789abcdefABCDEF" for c in ref):
            return ref

        # Check cache (thread-safe)
        cache_key = (repo, ref)
        with self._cache_lock:
            if cache_key in self._cache:
                return self._cache[cache_key]

        # Request with rate-limit backoff
        async with self._semaphore:
            sha = await self._request_with_backoff(repo, ref)

        # Store in cache (thread-safe)
        with self._cache_lock:
            self._cache[cache_key] = sha

        return sha

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
        headers = {}
        if self.token:
            headers["Authorization"] = f"token {self.token}"

        # `repo` may include a composite-action subpath (e.g. 'owner/repo/subdir'
        # from 'uses: owner/repo/subdir@ref'); the commits API only accepts
        # 'owner/repo', so strip anything past the second path segment.
        owner_repo = "/".join(repo.split("/")[:2])
        url = f"{self.base_url}/repos/{owner_repo}/commits/{ref}"

        async with httpx2.AsyncClient() as client:
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

        await asyncio.sleep(min(delay, 60.0))  # Cap at 60 seconds
