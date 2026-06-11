"""connectors/resolver.py — Resolve optional retrieval connectors from settings."""

from __future__ import annotations

from typing import TYPE_CHECKING

from connectors.base import BaseConnector
from connectors.examples.example_connector import ExampleMemoryConnector
from connectors.gdrive_connector import GoogleDriveConnector
from connectors.http_connector import HttpConnector
from connectors.rag_connector import RagConnector
from connectors.sharepoint_connector import SharePointConnector

if TYPE_CHECKING:
    from core.config import Settings

_BUILTIN_CONNECTORS: dict[str, type[BaseConnector]] = {
    "example_memory": ExampleMemoryConnector,
    "gdrive": GoogleDriveConnector,
    "http": HttpConnector,
    "rag": RagConnector,
    "sharepoint": SharePointConnector,
}


def create_connector(connector_id: str, settings: Settings) -> BaseConnector:
    """Instantiate a built-in connector by id."""
    connector_cls = _BUILTIN_CONNECTORS.get(connector_id)
    if connector_cls is None:
        known = ", ".join(sorted(_BUILTIN_CONNECTORS))
        raise ValueError(
            f"Unknown CONNECTOR_ID {connector_id!r}. Supported values: {known}"
        )

    if connector_id == "http":
        if not settings.connector_http_url:
            raise ValueError("CONNECTOR_HTTP_URL is required when CONNECTOR_ID=http")
        return HttpConnector(
            base_url=settings.connector_http_url,
            timeout_seconds=settings.connector_http_timeout_seconds,
            max_response_bytes=settings.connector_http_max_response_bytes,
            max_redirects=settings.connector_http_max_redirects,
        )

    if connector_id == "rag":
        return RagConnector(settings=settings)

    if connector_id == "sharepoint":
        missing = [
            name
            for name, value in (
                (
                    "CONNECTOR_SHAREPOINT_TENANT_ID",
                    settings.connector_sharepoint_tenant_id,
                ),
                (
                    "CONNECTOR_SHAREPOINT_CLIENT_ID",
                    settings.connector_sharepoint_client_id,
                ),
                (
                    "CONNECTOR_SHAREPOINT_CLIENT_SECRET",
                    settings.connector_sharepoint_client_secret,
                ),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"CONNECTOR_ID=sharepoint requires: {', '.join(missing)}")
        return SharePointConnector(
            tenant_id=settings.connector_sharepoint_tenant_id or "",
            client_id=settings.connector_sharepoint_client_id or "",
            client_secret=settings.connector_sharepoint_client_secret or "",
        )

    if connector_id == "gdrive":
        if not settings.connector_gdrive_access_token:
            raise ValueError(
                "CONNECTOR_ID=gdrive requires CONNECTOR_GDRIVE_ACCESS_TOKEN "
                "(short-lived token minted by Workload Identity or a sidecar)."
            )
        return GoogleDriveConnector(
            token=settings.connector_gdrive_access_token,
            drive_id=settings.connector_gdrive_drive_id,
        )

    return connector_cls()


def resolve_connector(settings: Settings) -> BaseConnector | None:
    """Return a connector instance when enabled in settings, else None."""
    if not settings.connector_enabled:
        return None
    return create_connector(settings.connector_id, settings)


def list_connector_ids() -> list[str]:
    """Return sorted built-in connector ids."""
    return sorted(_BUILTIN_CONNECTORS)
