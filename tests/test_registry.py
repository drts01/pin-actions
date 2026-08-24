"""Tests for pin_actions.registry (container image digest resolution)."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx2
import pytest
from pin_actions.errors import NetworkError, UnsupportedRegistryError
from pin_actions.registry import ContainerRegistryClient, is_image_digest, parse_image_ref


class TestIsImageDigest:
    """Test is_image_digest."""

    def test_valid_digest(self) -> None:
        """Accept sha256: + 64 hex chars."""
        assert is_image_digest("sha256:" + "a" * 64)

    def test_missing_prefix(self) -> None:
        """Reject strings without sha256: prefix."""
        assert not is_image_digest("latest")

    def test_wrong_length(self) -> None:
        """Reject digest with wrong length."""
        assert not is_image_digest("sha256:abc123")

    def test_non_hex(self) -> None:
        """Reject digest with non-hex characters."""
        assert not is_image_digest("sha256:" + "g" * 64)


class TestParseImageRef:
    """Test parse_image_ref."""

    def test_docker_hub_short_name(self) -> None:
        """Bare image name normalizes to Docker Hub + library/ prefix."""
        assert parse_image_ref("postgres:15") == ("registry-1.docker.io", "library/postgres", "15")

    def test_docker_hub_namespaced(self) -> None:
        """user/image on Docker Hub, no library/ prefix added."""
        assert parse_image_ref("bitnami/postgres:15") == ("registry-1.docker.io", "bitnami/postgres", "15")

    def test_ghcr_ref(self) -> None:
        """ghcr.io/owner/image:tag parses registry correctly."""
        assert parse_image_ref("ghcr.io/owner/image:tag") == ("ghcr.io", "owner/image", "tag")

    def test_docker_prefix_stripped(self) -> None:
        """docker:// prefix is stripped."""
        assert parse_image_ref("docker://alpine:3.18") == ("registry-1.docker.io", "library/alpine", "3.18")

    def test_digest_suffix(self) -> None:
        """@sha256:... digest suffix parsed as ref."""
        digest = "sha256:" + "a" * 64
        assert parse_image_ref(f"ubuntu@{digest}") == ("registry-1.docker.io", "library/ubuntu", digest)

    def test_default_tag_latest(self) -> None:
        """No tag defaults to 'latest'."""
        assert parse_image_ref("ubuntu") == ("registry-1.docker.io", "library/ubuntu", "latest")

    def test_registry_with_port(self) -> None:
        """Registry host with port is recognized as registry, not name."""
        assert parse_image_ref("localhost:5000/myimage:v1") == ("localhost:5000", "myimage", "v1")

    def test_empty_string(self) -> None:
        """Empty string returns None."""
        assert parse_image_ref("") is None

    def test_empty_after_docker_prefix(self) -> None:
        """Bare docker:// prefix with nothing after returns None."""
        assert parse_image_ref("docker://") is None


class TestContainerRegistryClientChallenge:
    """Test _parse_challenge static method."""

    def test_valid_bearer_challenge(self) -> None:
        """Parse a valid Bearer challenge header."""
        header = 'Bearer realm="https://auth.docker.io/token",service="registry.docker.io",scope="repository:library/ubuntu:pull"'
        result = ContainerRegistryClient._parse_challenge(header)
        assert result == ("https://auth.docker.io/token", "registry.docker.io", "repository:library/ubuntu:pull")

    def test_non_bearer_challenge(self) -> None:
        """Non-Bearer challenge returns None."""
        assert ContainerRegistryClient._parse_challenge('Basic realm="test"') is None

    def test_missing_realm(self) -> None:
        """Bearer header without realm returns None."""
        assert ContainerRegistryClient._parse_challenge('Bearer service="x"') is None


def _mock_http_client(head_side_effect, get_side_effect=None) -> MagicMock:
    """Build a MagicMock standing in for httpx2.AsyncClient."""
    mock = MagicMock()
    mock.head = AsyncMock(side_effect=head_side_effect)
    if get_side_effect is not None:
        mock.get = AsyncMock(side_effect=get_side_effect)
    mock.aclose = AsyncMock(return_value=None)
    return mock


def _resp(status_code: int, headers: dict | None = None, json_data: dict | None = None) -> MagicMock:
    resp = MagicMock(status_code=status_code, headers=headers or {})
    if json_data is not None:
        resp.json = MagicMock(return_value=json_data)
    resp.raise_for_status = MagicMock()
    return resp


class TestResolveDigestAnonymous:
    """Test resolve_digest anonymous flow (public registries)."""

    @pytest.mark.asyncio
    async def test_already_digest_returns_as_is(self) -> None:
        """Already-pinned digest is returned without any HTTP call."""
        client = ContainerRegistryClient()
        digest = "sha256:" + "a" * 64

        result = await client.resolve_digest("ubuntu", digest)

        assert result == digest

    @pytest.mark.asyncio
    async def test_anonymous_digest_header_present(self) -> None:
        """Anonymous HEAD returns Docker-Content-Digest directly (no auth needed)."""
        client = ContainerRegistryClient(concurrency=1)
        digest = "sha256:" + "b" * 64
        mock_http = _mock_http_client(lambda *_a, **_k: _resp(200, {"Docker-Content-Digest": digest}))

        with patch.object(client, "_get_http_client", new=AsyncMock(return_value=mock_http)):
            result = await client.resolve_digest("ubuntu", "latest")

        assert result == digest

    @pytest.mark.asyncio
    async def test_bearer_challenge_flow(self) -> None:
        """401 challenge triggers token exchange, then retried HEAD succeeds."""
        client = ContainerRegistryClient(concurrency=1)
        digest = "sha256:" + "c" * 64
        challenge = 'Bearer realm="https://auth.docker.io/token",service="registry.docker.io",scope="repository:library/ubuntu:pull"'

        head_responses = iter(
            [
                _resp(401, {"WWW-Authenticate": challenge}),
                _resp(200, {"Docker-Content-Digest": digest}),
            ]
        )
        mock_http = _mock_http_client(
            lambda *_a, **_k: next(head_responses),
            get_side_effect=lambda *_a, **_k: _resp(200, json_data={"token": "anon-token"}),
        )

        with patch.object(client, "_get_http_client", new=AsyncMock(return_value=mock_http)):
            result = await client.resolve_digest("ubuntu", "latest")

        assert result == digest
        assert mock_http.head.call_count == 2

    @pytest.mark.asyncio
    async def test_ghcr_token_injection(self) -> None:
        """ghcr.io token exchange includes GitHub token in Authorization header."""
        client = ContainerRegistryClient(github_token="gh-secret", concurrency=1)
        digest = "sha256:" + "d" * 64
        challenge = 'Bearer realm="https://ghcr.io/token",service="ghcr.io",scope="repository:owner/repo:pull"'

        head_responses = iter(
            [
                _resp(401, {"WWW-Authenticate": challenge}),
                _resp(200, {"Docker-Content-Digest": digest}),
            ]
        )
        get_mock = AsyncMock(return_value=_resp(200, json_data={"token": "gh-token"}))
        mock_http = _mock_http_client(lambda *_a, **_k: next(head_responses))
        mock_http.get = get_mock

        with patch.object(client, "_get_http_client", new=AsyncMock(return_value=mock_http)):
            result = await client.resolve_digest("ghcr.io/owner/repo", "latest")

        assert result == digest
        _, kwargs = get_mock.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer gh-secret"


class TestResolveDigestErrors:
    """Test resolve_digest error paths."""

    @pytest.mark.asyncio
    async def test_non_bearer_challenge_raises_unsupported(self) -> None:
        """Non-Bearer 401 challenge (e.g. ECR/GCR) raises UnsupportedRegistryError."""
        client = ContainerRegistryClient(concurrency=1)
        mock_http = _mock_http_client(lambda *_a, **_k: _resp(401, {"WWW-Authenticate": 'Basic realm="x"'}))

        with (
            patch.object(client, "_get_http_client", new=AsyncMock(return_value=mock_http)),
            pytest.raises(UnsupportedRegistryError),
        ):
            await client.resolve_digest("my.ecr.registry/image", "latest")

    @pytest.mark.asyncio
    async def test_missing_digest_header_raises_unsupported(self) -> None:
        """Missing Docker-Content-Digest header raises UnsupportedRegistryError."""
        client = ContainerRegistryClient(concurrency=1)
        mock_http = _mock_http_client(lambda *_a, **_k: _resp(200, {}))

        with (
            patch.object(client, "_get_http_client", new=AsyncMock(return_value=mock_http)),
            pytest.raises(UnsupportedRegistryError),
        ):
            await client.resolve_digest("ubuntu", "latest")

    @pytest.mark.asyncio
    async def test_network_error_raises(self) -> None:
        """httpx2.RequestError on HEAD raises NetworkError."""
        client = ContainerRegistryClient(concurrency=1)

        async def raise_request_error(*_a: object, **_k: object) -> None:
            msg = "boom"
            raise httpx2.RequestError(msg)

        mock_http = _mock_http_client(raise_request_error)

        with (
            patch.object(client, "_get_http_client", new=AsyncMock(return_value=mock_http)),
            pytest.raises(NetworkError),
        ):
            await client.resolve_digest("ubuntu", "latest")

    @pytest.mark.asyncio
    async def test_unparsable_image_raises_unsupported(self) -> None:
        """Unparsable image reference raises UnsupportedRegistryError."""
        client = ContainerRegistryClient()

        with pytest.raises(UnsupportedRegistryError):
            await client.resolve_digest("docker://", "latest")


class TestResolveDigestCaching:
    """Test resolve_digest caching/dedup behavior."""

    @pytest.mark.asyncio
    async def test_cache_hit_no_second_http_call(self) -> None:
        """Second resolve_digest for same image/tag hits cache, no extra HTTP call."""
        client = ContainerRegistryClient(concurrency=1)
        digest = "sha256:" + "e" * 64
        mock_http = _mock_http_client(lambda *_a, **_k: _resp(200, {"Docker-Content-Digest": digest}))

        with patch.object(client, "_get_http_client", new=AsyncMock(return_value=mock_http)):
            result1 = await client.resolve_digest("ubuntu", "latest")
            result2 = await client.resolve_digest("ubuntu", "latest")

        assert result1 == digest
        assert result2 == digest
        assert mock_http.head.call_count == 1


class TestContextManager:
    """Test async context manager interface."""

    @pytest.mark.asyncio
    async def test_context_manager_cleanup(self) -> None:
        """Async context manager returns self and closes pooled client on exit."""
        client = ContainerRegistryClient()

        async with client as ctx:
            assert ctx is client
