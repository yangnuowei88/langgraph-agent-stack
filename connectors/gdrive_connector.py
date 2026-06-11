"""connectors/gdrive_connector.py — Google Drive retrieval (Drive API v3).

Full-text search over files the authenticated principal can read. **ACL
model**: Drive only returns files visible to the supplied credentials —
scope the service account (or shared-drive membership) to exactly the
corpora the agent may read, and Drive enforces the ACLs.

**Auth**: Google service accounts use a signed-JWT grant, which would pull a
crypto dependency into the stack. Instead this connector takes a *bearer
token provider* — typically GKE Workload Identity, a sidecar, or any infra
component that mints short-lived access tokens — keeping the connector
SDK-free. Pass either a static token (rotated by the env) or an async
callable returning a fresh token per fetch.

Records carry ``id`` / ``title`` / ``url`` / ``snippet`` keys so
``record_to_source_ref`` produces audit-grade citations directly.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any, ClassVar

import httpx

from connectors.base import BaseConnector, ConnectorRequest, ConnectorResult
from connectors.http_connector import _read_response_body_bounded
from core.security import validate_outbound_url

DRIVE_BASE_URL = "https://www.googleapis.com/drive/v3"
DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_RESPONSE_BYTES = 2_097_152  # 2 MiB
_USER_AGENT = "langgraph-agent-stack/GoogleDriveConnector"

_FILE_FIELDS = "files(id,name,webViewLink,description,modifiedTime,mimeType)"

TokenProvider = Callable[[], Awaitable[str]]


async def _validate_outbound_request(request: httpx.Request) -> None:
    validate_outbound_url(str(request.url))


def _escape_drive_query(text: str) -> str:
    """Escape user text for embedding in a Drive ``q`` string literal."""
    return text.replace("\\", "\\\\").replace("'", "\\'")


class GoogleDriveConnector(BaseConnector):
    """Full-text file search over Google Drive / shared drives."""

    connector_id: ClassVar[str] = "gdrive"
    name: ClassVar[str] = "Google Drive connector"
    description: ClassVar[str] = (
        "Drive v3 fullText search; ACLs enforced by the supplied "
        "credentials' visibility."
    )

    def __init__(
        self,
        token: str | TokenProvider,
        *,
        drive_id: str | None = None,
        drive_base_url: str = DRIVE_BASE_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if isinstance(token, str) and not token.strip():
            raise ValueError("GoogleDriveConnector requires a non-empty token")
        self._token = token
        self._drive_id = drive_id
        self._drive_base_url = drive_base_url.rstrip("/")
        validate_outbound_url(self._drive_base_url)
        self._timeout = timeout_seconds
        self._max_response_bytes = max_response_bytes
        self._transport = transport

    async def _resolve_token(self) -> str:
        if callable(self._token):
            return await self._token()
        return self._token

    async def fetch(self, request: ConnectorRequest) -> ConnectorResult:
        token = await self._resolve_token()
        url = f"{self._drive_base_url}/files"
        validate_outbound_url(url)

        escaped = _escape_drive_query(request.query)
        params: dict[str, str] = {
            "q": f"fullText contains '{escaped}' and trashed = false",
            "pageSize": str(request.limit),
            "fields": _FILE_FIELDS,
        }
        if self._drive_id:
            params.update(
                {
                    "corpora": "drive",
                    "driveId": self._drive_id,
                    "includeItemsFromAllDrives": "true",
                    "supportsAllDrives": "true",
                }
            )

        async with httpx.AsyncClient(
            timeout=self._timeout,
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": _USER_AGENT,
            },
            event_hooks={"request": [_validate_outbound_request]},
            transport=self._transport,
        ) as client:
            async with client.stream("GET", url, params=params) as response:
                response.raise_for_status()
                body = await _read_response_body_bounded(
                    response, self._max_response_bytes
                )

        records = _parse_drive_files_response(json.loads(body))
        return ConnectorResult(
            records=tuple(records[: request.limit]),
            metadata={
                "connector": self.connector_id,
                "status_code": response.status_code,
            },
        )


def _parse_drive_files_response(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in payload.get("files", []):
        if not isinstance(item, dict):
            continue
        records.append(
            {
                "id": str(item.get("id") or ""),
                "title": item.get("name"),
                "url": item.get("webViewLink"),
                "snippet": item.get("description") or item.get("name") or "",
                "last_modified": item.get("modifiedTime"),
                "mime_type": item.get("mimeType"),
                "source": "gdrive",
            }
        )
    return records
