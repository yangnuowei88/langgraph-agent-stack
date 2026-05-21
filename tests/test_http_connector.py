"""tests/test_http_connector.py — HttpConnector behaviour."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from connectors.base import ConnectorRequest
from connectors.http_connector import (
    DEFAULT_HTTP_CONNECTOR_USER_AGENT,
    HttpConnector,
)


@pytest.mark.asyncio
async def test_http_connector_blocks_localhost_base_url() -> None:
    with pytest.raises(ValueError, match="not allowed"):
        HttpConnector("http://localhost/search")


@pytest.mark.asyncio
async def test_http_connector_fetch_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "q=quantum" in str(request.url)
        assert request.headers.get("user-agent") == DEFAULT_HTTP_CONNECTOR_USER_AGENT
        return httpx.Response(
            200,
            json={"results": [{"snippet": "from api", "source": "test"}]},
        )

    transport = httpx.MockTransport(handler)
    connector = HttpConnector("https://api.example.com/search")

    class _Client(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    with patch("connectors.http_connector.httpx.AsyncClient", _Client):
        result = await connector.fetch(ConnectorRequest(query="quantum"))

    assert result.records[0]["snippet"] == "from api"


@pytest.mark.asyncio
async def test_http_connector_rejects_redirect_to_blocked_host() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.example.com":
            return httpx.Response(
                302,
                headers={"Location": "http://127.0.0.1/internal"},
            )
        return httpx.Response(200, json={"results": []})

    transport = httpx.MockTransport(handler)
    connector = HttpConnector("https://api.example.com/search")

    class _Client(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    with patch("connectors.http_connector.httpx.AsyncClient", _Client):
        with pytest.raises(ValueError, match="not allowed"):
            await connector.fetch(ConnectorRequest(query="quantum"))


@pytest.mark.asyncio
async def test_http_connector_follows_allowed_redirect() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/search":
            return httpx.Response(
                302,
                headers={"Location": "https://api.example.com/final?q=quantum&limit=5"},
            )
        return httpx.Response(
            200,
            json={"results": [{"snippet": "after redirect", "source": "test"}]},
        )

    transport = httpx.MockTransport(handler)
    connector = HttpConnector("https://api.example.com/search")

    class _Client(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    with patch("connectors.http_connector.httpx.AsyncClient", _Client):
        result = await connector.fetch(ConnectorRequest(query="quantum"))

    assert result.records[0]["snippet"] == "after redirect"


@pytest.mark.asyncio
async def test_http_connector_rejects_oversized_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 2048)

    transport = httpx.MockTransport(handler)
    connector = HttpConnector(
        "https://api.example.com/search",
        max_response_bytes=1024,
    )

    class _Client(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    with patch("connectors.http_connector.httpx.AsyncClient", _Client):
        with pytest.raises(ValueError, match="too large"):
            await connector.fetch(ConnectorRequest(query="quantum"))


@pytest.mark.asyncio
async def test_http_connector_rejects_oversized_content_length_header() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Length": "999999"},
            content=b"{}",
        )

    transport = httpx.MockTransport(handler)
    connector = HttpConnector(
        "https://api.example.com/search",
        max_response_bytes=1024,
    )

    class _Client(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    with patch("connectors.http_connector.httpx.AsyncClient", _Client):
        with pytest.raises(ValueError, match="too large"):
            await connector.fetch(ConnectorRequest(query="quantum"))
