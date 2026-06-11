"""connectors/sharepoint_connector.py — SharePoint retrieval via Microsoft Graph.

Searches driveItems (documents) with the Microsoft Graph Search API using an
app-only client-credentials token. **ACL model**: results are scoped by the
service principal's application permissions — grant ``Sites.Selected`` on the
specific SharePoint sites the agent may read, and Graph enforces the ACLs;
this connector never widens access beyond what the principal can see.

Records carry ``id`` / ``title`` / ``url`` / ``snippet`` keys, so
``connectors.base.record_to_source_ref`` produces audit-grade citations
without any extra mapping.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

import httpx

from connectors.base import BaseConnector, ConnectorRequest, ConnectorResult
from connectors.http_connector import _read_response_body_bounded
from connectors.oauth import OAuth2ClientCredentials
from core.security import validate_outbound_url

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
LOGIN_BASE_URL = "https://login.microsoftonline.com"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"

DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_RESPONSE_BYTES = 2_097_152  # 2 MiB
_USER_AGENT = "langgraph-agent-stack/SharePointConnector"


async def _validate_outbound_request(request: httpx.Request) -> None:
    validate_outbound_url(str(request.url))


class SharePointConnector(BaseConnector):
    """Document search over SharePoint / OneDrive via Microsoft Graph."""

    connector_id: ClassVar[str] = "sharepoint"
    name: ClassVar[str] = "SharePoint (Microsoft Graph) connector"
    description: ClassVar[str] = (
        "App-only Graph Search over driveItems; ACLs enforced by the "
        "service principal's Sites.Selected permissions."
    )

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        *,
        graph_base_url: str = GRAPH_BASE_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not tenant_id.strip():
            raise ValueError("SharePointConnector requires a non-empty tenant_id")
        self._graph_base_url = graph_base_url.rstrip("/")
        validate_outbound_url(self._graph_base_url)
        self._timeout = timeout_seconds
        self._max_response_bytes = max_response_bytes
        self._transport = transport
        self._token_source = OAuth2ClientCredentials(
            token_url=f"{LOGIN_BASE_URL}/{tenant_id}/oauth2/v2.0/token",
            client_id=client_id,
            client_secret=client_secret,
            scope=GRAPH_SCOPE,
            timeout_seconds=timeout_seconds,
            transport=transport,
        )

    async def fetch(self, request: ConnectorRequest) -> ConnectorResult:
        token = await self._token_source.get_token()
        url = f"{self._graph_base_url}/search/query"
        validate_outbound_url(url)
        payload = {
            "requests": [
                {
                    "entityTypes": ["driveItem"],
                    "query": {"queryString": request.query},
                    "from": 0,
                    "size": request.limit,
                }
            ]
        }

        async with httpx.AsyncClient(
            timeout=self._timeout,
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": _USER_AGENT,
            },
            event_hooks={"request": [_validate_outbound_request]},
            transport=self._transport,
        ) as client:
            async with client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                body = await _read_response_body_bounded(
                    response, self._max_response_bytes
                )

        records = _parse_graph_search_response(json.loads(body))
        return ConnectorResult(
            records=tuple(records[: request.limit]),
            metadata={
                "connector": self.connector_id,
                "status_code": response.status_code,
            },
        )


def _parse_graph_search_response(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten a Graph /search/query response into citation-ready records."""
    records: list[dict[str, Any]] = []
    for value in payload.get("value", []):
        for container in value.get("hitsContainers", []):
            for hit in container.get("hits", []):
                resource = hit.get("resource", {}) or {}
                records.append(
                    {
                        "id": str(resource.get("id") or hit.get("hitId") or ""),
                        "title": resource.get("name"),
                        "url": resource.get("webUrl"),
                        "snippet": hit.get("summary")
                        or resource.get("description")
                        or "",
                        "last_modified": resource.get("lastModifiedDateTime"),
                        "source": "sharepoint",
                    }
                )
    return records
