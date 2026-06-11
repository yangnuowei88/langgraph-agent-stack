"""
tests/test_enterprise_connectors.py — SharePoint / Google Drive connectors.

Everything runs against httpx.MockTransport: no network, no credentials.
``validate_outbound_url`` is patched where needed because it performs DNS
resolution on the (real, public) Graph/Drive endpoints.

Covers: OAuth2 client-credentials caching and refresh, Graph search request
shape and record mapping, Drive query escaping and shared-drive scoping,
token-provider callables, resolver wiring, and SourceRef citation output.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from connectors.base import ConnectorRequest, record_to_source_ref
from connectors.gdrive_connector import GoogleDriveConnector, _escape_drive_query
from connectors.oauth import OAuth2ClientCredentials
from connectors.sharepoint_connector import SharePointConnector

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TOKEN_RESPONSE = {"access_token": "tok-123", "expires_in": 3600}

_GRAPH_SEARCH_RESPONSE = {
    "value": [
        {
            "hitsContainers": [
                {
                    "hits": [
                        {
                            "hitId": "hit-1",
                            "summary": "Quarterly results <b>summary</b>.",
                            "resource": {
                                "id": "item-abc",
                                "name": "Q3-results.docx",
                                "webUrl": "https://contoso.sharepoint.com/q3.docx",
                                "lastModifiedDateTime": "2026-05-01T10:00:00Z",
                            },
                        },
                        {
                            "hitId": "hit-2",
                            "summary": "",
                            "resource": {
                                "id": "item-def",
                                "name": "Budget.xlsx",
                                "webUrl": "https://contoso.sharepoint.com/budget.xlsx",
                                "description": "FY26 budget workbook",
                            },
                        },
                    ]
                }
            ]
        }
    ]
}

_DRIVE_FILES_RESPONSE = {
    "files": [
        {
            "id": "gd-1",
            "name": "Handbook.pdf",
            "webViewLink": "https://drive.google.com/file/d/gd-1/view",
            "description": "Employee handbook",
            "modifiedTime": "2026-04-01T08:00:00Z",
            "mimeType": "application/pdf",
        },
        "not-a-dict",
    ]
}

_no_ssrf = patch("core.security.validate_outbound_url", lambda url: None)


def _patch_ssrf():
    """Patch the SSRF validator in every module that imported it."""
    return (
        patch("connectors.oauth.validate_outbound_url", lambda url: None),
        patch(
            "connectors.sharepoint_connector.validate_outbound_url", lambda url: None
        ),
        patch("connectors.gdrive_connector.validate_outbound_url", lambda url: None),
    )


class _RecordingTransport(httpx.MockTransport):
    """MockTransport that also records every request it serves."""

    def __init__(self, handler) -> None:
        self.requests: list[httpx.Request] = []

        def _wrapped(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return handler(request)

        super().__init__(_wrapped)


def _sharepoint_handler(request: httpx.Request) -> httpx.Response:
    if "login.microsoftonline.com" in request.url.host:
        return httpx.Response(200, json=_TOKEN_RESPONSE)
    if request.url.path.endswith("/search/query"):
        return httpx.Response(200, json=_GRAPH_SEARCH_RESPONSE)
    return httpx.Response(404)


# ---------------------------------------------------------------------------
# OAuth2 client credentials
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_oauth_token_is_cached_until_stale() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_TOKEN_RESPONSE)

    p1, p2, p3 = _patch_ssrf()
    with p1, p2, p3:
        source = OAuth2ClientCredentials(
            token_url="https://login.microsoftonline.com/t1/oauth2/v2.0/token",
            client_id="cid",
            client_secret="sec",
            scope="https://graph.microsoft.com/.default",
            transport=httpx.MockTransport(handler),
        )
        assert await source.get_token() == "tok-123"
        assert await source.get_token() == "tok-123"
    assert calls["n"] == 1  # second call served from cache


@pytest.mark.asyncio
async def test_oauth_token_refreshed_when_inside_margin() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        # expires_in below the 60s refresh margin → always considered stale.
        return httpx.Response(
            200, json={"access_token": f"tok-{calls['n']}", "expires_in": 30}
        )

    p1, p2, p3 = _patch_ssrf()
    with p1, p2, p3:
        source = OAuth2ClientCredentials(
            token_url="https://login.microsoftonline.com/t1/oauth2/v2.0/token",
            client_id="cid",
            client_secret="sec",
            scope="s",
            transport=httpx.MockTransport(handler),
        )
        assert await source.get_token() == "tok-1"
        assert await source.get_token() == "tok-2"
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_oauth_missing_access_token_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"expires_in": 3600})

    p1, p2, p3 = _patch_ssrf()
    with p1, p2, p3:
        source = OAuth2ClientCredentials(
            token_url="https://login.microsoftonline.com/t1/oauth2/v2.0/token",
            client_id="cid",
            client_secret="sec",
            scope="s",
            transport=httpx.MockTransport(handler),
        )
        with pytest.raises(ValueError, match="access_token"):
            await source.get_token()


# ---------------------------------------------------------------------------
# SharePoint connector
# ---------------------------------------------------------------------------


def _make_sharepoint(transport: httpx.AsyncBaseTransport) -> SharePointConnector:
    return SharePointConnector(
        tenant_id="tenant-1",
        client_id="cid",
        client_secret="sec",
        transport=transport,
    )


@pytest.mark.asyncio
async def test_sharepoint_fetch_maps_records() -> None:
    transport = _RecordingTransport(_sharepoint_handler)
    p1, p2, p3 = _patch_ssrf()
    with p1, p2, p3:
        connector = _make_sharepoint(transport)
        result = await connector.fetch(ConnectorRequest(query="quarterly results"))

    assert len(result.records) == 2
    first = result.records[0]
    assert first["id"] == "item-abc"
    assert first["title"] == "Q3-results.docx"
    assert first["url"] == "https://contoso.sharepoint.com/q3.docx"
    assert "Quarterly results" in first["snippet"]
    assert first["source"] == "sharepoint"
    # Description used as snippet fallback when summary is empty.
    assert result.records[1]["snippet"] == "FY26 budget workbook"


@pytest.mark.asyncio
async def test_sharepoint_request_shape_and_auth_header() -> None:
    transport = _RecordingTransport(_sharepoint_handler)
    p1, p2, p3 = _patch_ssrf()
    with p1, p2, p3:
        connector = _make_sharepoint(transport)
        await connector.fetch(ConnectorRequest(query="hello", limit=3))

    search_request = transport.requests[-1]
    assert search_request.headers["Authorization"] == "Bearer tok-123"
    payload = json.loads(search_request.content)
    inner = payload["requests"][0]
    assert inner["entityTypes"] == ["driveItem"]
    assert inner["query"]["queryString"] == "hello"
    assert inner["size"] == 3


@pytest.mark.asyncio
async def test_sharepoint_http_error_propagates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "login" in request.url.host:
            return httpx.Response(200, json=_TOKEN_RESPONSE)
        return httpx.Response(403, json={"error": "forbidden"})

    p1, p2, p3 = _patch_ssrf()
    with p1, p2, p3:
        connector = _make_sharepoint(httpx.MockTransport(handler))
        with pytest.raises(httpx.HTTPStatusError):
            await connector.fetch(ConnectorRequest(query="x"))


@pytest.mark.asyncio
async def test_sharepoint_records_produce_citations() -> None:
    """The records integrate with SourceRef without extra mapping."""
    p1, p2, p3 = _patch_ssrf()
    with p1, p2, p3:
        connector = _make_sharepoint(httpx.MockTransport(_sharepoint_handler))
        result = await connector.fetch(ConnectorRequest(query="q"))

    ref = record_to_source_ref(dict(result.records[0]), 0)
    assert ref.citation() == (
        "[item-abc] Q3-results.docx — https://contoso.sharepoint.com/q3.docx"
    )


# ---------------------------------------------------------------------------
# Google Drive connector
# ---------------------------------------------------------------------------


def _drive_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=_DRIVE_FILES_RESPONSE)


@pytest.mark.asyncio
async def test_gdrive_fetch_maps_records_and_skips_non_dicts() -> None:
    transport = _RecordingTransport(_drive_handler)
    p1, p2, p3 = _patch_ssrf()
    with p1, p2, p3:
        connector = GoogleDriveConnector(token="gd-token", transport=transport)
        result = await connector.fetch(ConnectorRequest(query="handbook", limit=5))

    assert len(result.records) == 1
    record = result.records[0]
    assert record["id"] == "gd-1"
    assert record["title"] == "Handbook.pdf"
    assert record["url"] == "https://drive.google.com/file/d/gd-1/view"
    assert record["snippet"] == "Employee handbook"
    assert transport.requests[0].headers["Authorization"] == "Bearer gd-token"


@pytest.mark.asyncio
async def test_gdrive_query_is_escaped() -> None:
    transport = _RecordingTransport(_drive_handler)
    p1, p2, p3 = _patch_ssrf()
    with p1, p2, p3:
        connector = GoogleDriveConnector(token="t", transport=transport)
        await connector.fetch(ConnectorRequest(query="bob's 'report'"))

    q = transport.requests[0].url.params["q"]
    assert q == "fullText contains 'bob\\'s \\'report\\'' and trashed = false"


@pytest.mark.asyncio
async def test_gdrive_shared_drive_scoping() -> None:
    transport = _RecordingTransport(_drive_handler)
    p1, p2, p3 = _patch_ssrf()
    with p1, p2, p3:
        connector = GoogleDriveConnector(
            token="t", drive_id="drive-9", transport=transport
        )
        await connector.fetch(ConnectorRequest(query="x"))

    params = transport.requests[0].url.params
    assert params["corpora"] == "drive"
    assert params["driveId"] == "drive-9"
    assert params["includeItemsFromAllDrives"] == "true"


@pytest.mark.asyncio
async def test_gdrive_async_token_provider() -> None:
    transport = _RecordingTransport(_drive_handler)

    async def minter() -> str:
        return "minted-token"

    p1, p2, p3 = _patch_ssrf()
    with p1, p2, p3:
        connector = GoogleDriveConnector(token=minter, transport=transport)
        await connector.fetch(ConnectorRequest(query="x"))

    assert transport.requests[0].headers["Authorization"] == "Bearer minted-token"


def test_escape_drive_query_handles_backslashes() -> None:
    assert _escape_drive_query(r"a\b'c") == r"a\\b\'c"


# ---------------------------------------------------------------------------
# Resolver wiring
# ---------------------------------------------------------------------------


def _settings(**overrides: Any):
    from core.config import Settings

    return Settings(
        llm_provider="anthropic",
        anthropic_api_key="sk-ant-test123456789012345",
        **overrides,
    )


class TestResolver:
    def test_sharepoint_missing_settings_lists_vars(self) -> None:
        from connectors.resolver import create_connector

        with pytest.raises(ValueError, match="CONNECTOR_SHAREPOINT_TENANT_ID"):
            create_connector("sharepoint", _settings())

    def test_sharepoint_resolves_with_settings(self) -> None:
        from connectors.resolver import create_connector

        p1, p2, p3 = _patch_ssrf()
        with p1, p2, p3:
            connector = create_connector(
                "sharepoint",
                _settings(
                    connector_sharepoint_tenant_id="t1",
                    connector_sharepoint_client_id="cid",
                    connector_sharepoint_client_secret="sec",
                ),
            )
        assert isinstance(connector, SharePointConnector)

    def test_gdrive_missing_token_raises(self) -> None:
        from connectors.resolver import create_connector

        with pytest.raises(ValueError, match="CONNECTOR_GDRIVE_ACCESS_TOKEN"):
            create_connector("gdrive", _settings())

    def test_gdrive_resolves_with_settings(self) -> None:
        from connectors.resolver import create_connector

        p1, p2, p3 = _patch_ssrf()
        with p1, p2, p3:
            connector = create_connector(
                "gdrive",
                _settings(
                    connector_gdrive_access_token="tok",
                    connector_gdrive_drive_id="d1",
                ),
            )
        assert isinstance(connector, GoogleDriveConnector)

    def test_new_ids_listed(self) -> None:
        from connectors.resolver import list_connector_ids

        ids = list_connector_ids()
        assert "sharepoint" in ids
        assert "gdrive" in ids
