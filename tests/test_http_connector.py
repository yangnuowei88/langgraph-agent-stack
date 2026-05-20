"""tests/test_http_connector.py — HttpConnector behaviour."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from connectors.base import ConnectorRequest
from connectors.http_connector import HttpConnector


@pytest.mark.asyncio
async def test_http_connector_fetch_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "q=quantum" in str(request.url)
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
