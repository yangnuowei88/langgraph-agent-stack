"""
connectors/http_connector.py — HTTP GET connector for JSON or text retrieval APIs.

Expects ``CONNECTOR_HTTP_URL`` (base URL). Appends ``q`` and ``limit`` query params.

Outbound hardening: SSRF validation on every hop (including redirects), bounded
response reads, explicit redirect cap, and a identifiable User-Agent.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar
from urllib.parse import urlencode, urlparse, urlunparse

import httpx

from connectors.base import BaseConnector, ConnectorRequest, ConnectorResult
from core.security import validate_outbound_url

DEFAULT_HTTP_CONNECTOR_USER_AGENT = "langgraph-agent-stack/HttpConnector"
DEFAULT_MAX_RESPONSE_BYTES = 1_048_576  # 1 MiB
DEFAULT_MAX_REDIRECTS = 5
DEFAULT_TIMEOUT_SECONDS = 10.0


async def _validate_outbound_request(request: httpx.Request) -> None:
    """Event hook: SSRF-check every URL (initial request and redirect targets)."""
    validate_outbound_url(str(request.url))


async def _read_response_body_bounded(
    response: httpx.Response,
    max_bytes: int,
) -> bytes:
    """Read response body with a streaming cap to avoid OOM on huge payloads."""
    content_length = response.headers.get("content-length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError as exc:
            raise ValueError("Invalid Content-Length on connector response.") from exc
        if declared > max_bytes:
            raise ValueError(
                f"Connector response too large. Maximum size is {max_bytes} bytes."
            )

    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > max_bytes:
            raise ValueError(
                f"Connector response too large. Maximum size is {max_bytes} bytes."
            )
        chunks.append(chunk)
    return b"".join(chunks)


class HttpConnector(BaseConnector):
    """Fetches retrieval snippets from a configurable HTTP endpoint."""

    connector_id: ClassVar[str] = "http"
    name: ClassVar[str] = "HTTP retrieval connector"
    description: ClassVar[str] = (
        "GET request to CONNECTOR_HTTP_URL with query/limit parameters."
    )

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        *,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        max_redirects: int = DEFAULT_MAX_REDIRECTS,
        user_agent: str = DEFAULT_HTTP_CONNECTOR_USER_AGENT,
    ) -> None:
        if not base_url or not base_url.strip():
            raise ValueError("HttpConnector requires a non-empty base_url")
        if max_response_bytes < 1024:
            raise ValueError("max_response_bytes must be >= 1024")
        if max_redirects < 0:
            raise ValueError("max_redirects must be >= 0")
        if not user_agent.strip():
            raise ValueError("user_agent must be non-empty")

        self._base_url = base_url.strip().rstrip("/")
        self._timeout = timeout_seconds
        self._max_response_bytes = max_response_bytes
        self._max_redirects = max_redirects
        self._user_agent = user_agent.strip()
        validate_outbound_url(self._base_url)

    async def fetch(self, request: ConnectorRequest) -> ConnectorResult:
        params = {
            "q": request.query,
            "limit": str(request.limit),
            **{k: str(v) for k, v in request.filters.items()},
        }
        url = self._build_url(params)
        validate_outbound_url(url)

        async with httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=True,
            max_redirects=self._max_redirects,
            headers={"User-Agent": self._user_agent},
            event_hooks={"request": [_validate_outbound_request]},
        ) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                body = await _read_response_body_bounded(
                    response,
                    self._max_response_bytes,
                )

        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            records = _parse_json_payload(json.loads(body))
        else:
            records = _parse_text_payload(body.decode("utf-8", errors="replace"))

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
