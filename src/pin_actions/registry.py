"""Async container registry client for resolving image tags to content digests.

Implements the OCI Distribution Spec / Docker Registry v2 Bearer-token auth
flow, which is shared by all public registries (Docker Hub, GHCR, Quay.io,
MCR, registry.k8s.io, etc.). The token endpoint is discovered dynamically
from the ``WWW-Authenticate`` challenge on an initial anonymous request, so
no registry is special-cased. Registries using non-Bearer auth (ECR, GCR)
raise :class:`UnsupportedRegistryError`.
"""

import asyncio
import http
import logging
import re
from typing import Self

import httpx2

from pin_actions.client import _Cache
from pin_actions.errors import NetworkError, UnsupportedRegistryError

logger = logging.getLogger(__name__)

_DIGEST_LENGTH = 64
_HEX = frozenset("0123456789abcdefABCDEF")
_DOCKER_HUB_REGISTRY = "registry-1.docker.io"
_AUTH_CHALLENGE_RE = re.compile(r'(\w+)="([^"]*)"')
_USER_AGENT = "pin-actions"


def is_image_digest(ref: str) -> bool:
    """Check if ``ref`` is already a pinned ``sha256:<64-hex>`` content digest.

    Args:
        ref: Image reference tag or digest string.

    Returns:
        True if ``ref`` is ``sha256:`` followed by exactly 64 hex characters.

    Example:
        >>> is_image_digest("sha256:" + "a" * 64)
        True
        >>> is_image_digest("latest")
        False
    """
    prefix = "sha256:"
    if not ref.startswith(prefix):
        return False
    digest = ref[len(prefix) :]
    return len(digest) == _DIGEST_LENGTH and _HEX.issuperset(digest)


def parse_image_ref(image_str: str) -> tuple[str, str, str] | None:
    """Parse an image reference into (registry, name, tag_or_digest).

    Normalizes Docker Hub short names (no registry prefix, or single-segment
    official images) to ``registry-1.docker.io``.

    Args:
        image_str: Image string, e.g. ``postgres:15``, ``ubuntu:22.04``,
            ``ghcr.io/owner/image:tag``, or ``docker://alpine:3.18``.

    Returns:
        (registry, name, tag_or_digest) tuple, or None if unparsable.

    Example:
        >>> parse_image_ref("postgres:15")
        ('registry-1.docker.io', 'library/postgres', '15')
        >>> parse_image_ref("ghcr.io/owner/image:v1")
        ('ghcr.io', 'owner/image', 'v1')
        >>> parse_image_ref("docker://alpine:3.18")
        ('registry-1.docker.io', 'library/alpine', '3.18')
    """
    image_str = image_str.removeprefix("docker://")
    if not image_str:
        return None

    ref = "latest"
    if "@" in image_str:
        image_str, ref = image_str.rsplit("@", 1)
    else:
        # Split off a :tag, but don't confuse it with a :port in a registry host.
        path_part = image_str.split("/", 1)[-1]
        if ":" in path_part:
            image_str, _, tag = image_str.rpartition(":")
            ref = tag

    if not image_str or not ref:
        return None

    first_segment, _, rest = image_str.partition("/")
    if rest and ("." in first_segment or ":" in first_segment or first_segment == "localhost"):
        registry, name = first_segment, rest
    else:
        registry, name = _DOCKER_HUB_REGISTRY, image_str
        if "/" not in name:
            name = f"library/{name}"

    if not name:
        return None
    return registry, name, ref


class ContainerRegistryClient:
    """Async client resolving image tags to ``sha256:`` content digests.

    Anonymous-first: public images resolve with zero credentials. An
    optional GitHub token is used only for ``ghcr.io`` token exchanges,
    enabling private GHCR image resolution.
    """

    def __init__(
        self,
        github_token: str | None = None,
        concurrency: int = 5,
        max_cache_size: int = 1000,
    ) -> None:
        """Initialize container registry client.

        Args:
            github_token: Optional GitHub token, used only for ``ghcr.io`` auth.
            concurrency: Max concurrent requests via asyncio.Semaphore.
            max_cache_size: Max entries in in-memory digest cache (0 = unbounded).
        """
        self._github_token = github_token
        self._semaphore = asyncio.Semaphore(concurrency)
        self._digest_cache = _Cache[str](max_cache_size)
        self._http_client: httpx2.AsyncClient | None = None
        self._http_client_lock = asyncio.Lock()

    async def _get_http_client(self) -> httpx2.AsyncClient:
        """Get or create the pooled HTTP client (lazy-init, thread-safe via asyncio.Lock)."""
        if self._http_client is None:
            async with self._http_client_lock:
                if self._http_client is None:
                    self._http_client = httpx2.AsyncClient(
                        headers={"User-Agent": _USER_AGENT},
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

    @staticmethod
    def _parse_challenge(header: str) -> tuple[str, str, str] | None:
        """Parse a 'Bearer realm="...",service="...",scope="..."' WWW-Authenticate header."""
        if not header.startswith("Bearer "):
            return None
        params = dict(_AUTH_CHALLENGE_RE.findall(header))
        realm, service, scope = params.get("realm"), params.get("service", ""), params.get("scope", "")
        if not realm:
            return None
        return realm, service, scope

    async def _get_token(self, registry: str, realm: str, service: str, scope: str) -> str:
        """Exchange a Bearer challenge for a token, anonymous unless registry is ghcr.io."""
        client = await self._get_http_client()
        headers = {}
        if registry == "ghcr.io" and self._github_token:
            headers["Authorization"] = f"Bearer {self._github_token}"
        resp = await client.get(realm, params={"service": service, "scope": scope}, headers=headers)
        resp.raise_for_status()
        return resp.json()["token"]

    async def _fetch_digest(self, registry: str, name: str, ref: str) -> str:
        """HEAD the manifest, resolving the auth challenge first, and return its digest."""
        client = await self._get_http_client()
        manifest_url = f"https://{registry}/v2/{name}/manifests/{ref}"
        accept = "application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.v2+json"

        async with self._semaphore:
            try:
                resp = await client.head(manifest_url, headers={"Accept": accept})
            except httpx2.RequestError as exc:
                msg = f"Network error requesting manifest for {registry}/{name}:{ref}"
                raise NetworkError(msg) from exc

            if resp.status_code == http.HTTPStatus.UNAUTHORIZED:
                challenge = self._parse_challenge(resp.headers.get("WWW-Authenticate", ""))
                if challenge is None:
                    msg = f"{registry} does not support anonymous Bearer auth (unsupported registry)"
                    raise UnsupportedRegistryError(registry, msg)
                token = await self._get_token(registry, *challenge)
                try:
                    resp = await client.head(
                        manifest_url,
                        headers={"Accept": accept, "Authorization": f"Bearer {token}"},
                    )
                except httpx2.RequestError as exc:
                    msg = f"Network error requesting manifest for {registry}/{name}:{ref}"
                    raise NetworkError(msg) from exc

        resp.raise_for_status()
        digest = resp.headers.get("Docker-Content-Digest")
        if not digest:
            msg = f"No Docker-Content-Digest header returned for {registry}/{name}:{ref}"
            raise UnsupportedRegistryError(registry, msg)
        return digest

    async def resolve_digest(self, image: str, ref: str) -> str:
        """Resolve an image tag/branch to its immutable ``sha256:`` content digest.

        Args:
            image: Image name in normalized ``registry/name`` or bare ``name`` form
                (as produced by :func:`parse_image_ref`, without the tag).
            ref: Tag to resolve (ignored if already a digest).

        Returns:
            ``sha256:<64-hex>`` content digest.

        Raises:
            UnsupportedRegistryError: If the registry doesn't use Bearer auth,
                or returns no digest header.
            NetworkError: On unrecoverable network errors.
        """
        if is_image_digest(ref):
            return ref

        parsed = parse_image_ref(f"{image}:{ref}")
        if parsed is None:
            msg = f"Could not parse image reference: {image}:{ref}"
            raise UnsupportedRegistryError(image, msg)
        registry, name, tag = parsed

        return await self._digest_cache.get_or_fetch(
            (registry, name, tag),
            lambda: self._fetch_digest(registry, name, tag),
        )
