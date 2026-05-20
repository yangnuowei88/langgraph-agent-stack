"""
connectors/http_connector.py — HTTP GET connector for JSON or text retrieval APIs.

Expects ``CONNECTOR_HTTP_URL`` (base URL). Appends ``q`` and ``limit`` query params.
"""

from __future__ import annotations

from typing import Any, ClassVar
from urllib.parse import urlencode, urlparse, urlunparse

import httpx

from connectors.base import BaseConnector, ConnectorRequest, ConnectorResult


class HttpConnector(BaseConnector):
    """Fetches retrieval snippets from a configurable HTTP endpoint."""

    connector_id: ClassVar[str] = "http"
    name: ClassVar[str] = "HTTP retrieval connector"
    description: ClassVar[str] = (
        "GET request to CONNECTOR_HTTP_URL with query/limit parameters."
    )

    def __init__(self, base_url: str, timeout_seconds: float = 10.0) -> None:
        if not base_url or not base_url.strip():
            raise ValueError("HttpConnector requires a non-empty base_url")
        self._base_url = base_url.strip().rstrip("/")
        self._timeout = timeout_seconds

    async def fetch(self, request: ConnectorRequest) -> ConnectorResult:
        params = {
            "q": request.query,
            "limit": str(request.limit),
            **{k: str(v) for k, v in request.filters.items()},
        }
        url = self._build_url(params)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(url)
            response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            records = _parse_json_payload(response.json())
        else:
            records = _parse_text_payload(response.text)

        return ConnectorResult(
            records=tuple(records[: request.limit]),
            metadata={"url": url, "status_code": response.status_code},
        )

    def _build_url(self, params: dict[str, str]) -> str:
        parsed = urlparse(self._base_url)
        query = urlencode(params)
        if parsed.query:
            query = f"{parsed.query}&{query}"
        return urlunparse(parsed._replace(query=query))


def _parse_json_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [_normalize_record(item) for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("results", "records", "items", "data"):
            items = payload.get(key)
            if isinstance(items, list):
                return [
                    _normalize_record(item) for item in items if isinstance(item, dict)
                ]
        if "snippet" in payload or "text" in payload:
            return [_normalize_record(payload)]
    return []


def _parse_text_payload(text: str) -> list[dict[str, Any]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return [{"source": "http", "snippet": line} for line in lines]


def _normalize_record(item: dict[str, Any]) -> dict[str, Any]:
    snippet = item.get("snippet") or item.get("text") or item.get("content")
    if snippet is None and len(item) == 1:
        snippet = next(iter(item.values()))
    record = dict(item)
    if snippet is not None:
        record.setdefault("snippet", str(snippet))
    record.setdefault("source", str(record.get("source", "http")))
    return record
