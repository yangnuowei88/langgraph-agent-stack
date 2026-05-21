"""Tests for HTTP request body size limits in core/security.py."""

from __future__ import annotations

import pytest
from starlette.requests import Request

from core.security import ensure_request_body_within_limit


def _build_request(
    *,
    method: str = "POST",
    headers: list[tuple[bytes, bytes]] | None = None,
    body: bytes = b"",
) -> Request:
    sent = False

    async def receive() -> dict[str, object]:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http",
        "asgi": {"spec_version": "2.3", "version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "path": "/run",
        "raw_path": b"/run",
        "root_path": "",
        "scheme": "http",
        "query_string": b"",
        "headers": headers or [],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }
    return Request(scope, receive)


@pytest.mark.asyncio
async def test_content_length_over_limit_rejected() -> None:
    request = _build_request(
        headers=[(b"content-length", b"2048")],
    )
    bounded, error = await ensure_request_body_within_limit(request, max_bytes=1024)
    assert bounded is None
    assert error is not None
    assert "too large" in error


@pytest.mark.asyncio
async def test_streaming_body_over_limit_rejected() -> None:
    request = _build_request(body=b"x" * 2048)
    bounded, error = await ensure_request_body_within_limit(request, max_bytes=1024)
    assert bounded is None
    assert error is not None


@pytest.mark.asyncio
async def test_valid_body_with_content_length_passes_through() -> None:
    payload = b'{"query":"hello"}'
    request = _build_request(
        headers=[(b"content-length", str(len(payload)).encode())],
        body=payload,
    )
    bounded, error = await ensure_request_body_within_limit(request, max_bytes=1024)
    assert error is None
    assert bounded is request
    assert await bounded.body() == payload


@pytest.mark.asyncio
async def test_chunked_body_replayable_by_downstream() -> None:
    payload = b'{"query":"hello"}'
    request = _build_request(body=payload)
    bounded, error = await ensure_request_body_within_limit(request, max_bytes=1024)
    assert error is None
    assert bounded is not None
    assert bounded is not request
    assert await bounded.body() == payload


@pytest.mark.asyncio
async def test_get_requests_skip_body_limit() -> None:
    request = _build_request(method="GET")
    bounded, error = await ensure_request_body_within_limit(request, max_bytes=16)
    assert error is None
    assert bounded is request


@pytest.mark.asyncio
async def test_invalid_content_length_rejected() -> None:
    request = _build_request(headers=[(b"content-length", b"not-a-number")])
    bounded, error = await ensure_request_body_within_limit(request, max_bytes=1024)
    assert bounded is None
    assert error == "Invalid Content-Length header."
