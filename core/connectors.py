"""
core/connectors.py — Resolve optional retrieval connectors from settings.

Connectors are not registered in PackRegistry; the API wires a single shared
instance when ``CONNECTOR_ENABLED`` is true and the active pack supports it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from connectors.base import BaseConnector
from connectors.examples.example_connector import ExampleMemoryConnector
from connectors.http_connector import HttpConnector
from connectors.rag_connector import RagConnector

if TYPE_CHECKING:
    from core.config import Settings

_BUILTIN_CONNECTORS: dict[str, type[BaseConnector]] = {
    "example_memory": ExampleMemoryConnector,
    "http": HttpConnector,
    "rag": RagConnector,
}


def create_connector(connector_id: str, settings: Settings) -> BaseConnector:
    """Instantiate a built-in connector by id.

    Raises:
        ValueError: If ``connector_id`` is not registered or required settings are missing.
    """
    connector_cls = _BUILTIN_CONNECTORS.get(connector_id)
    if connector_cls is None:
        known = ", ".join(sorted(_BUILTIN_CONNECTORS))
        raise ValueError(
            f"Unknown CONNECTOR_ID {connector_id!r}. Supported values: {known}"
        )

    if connector_id == "http":
        if not settings.connector_http_url:
            raise ValueError("CONNECTOR_HTTP_URL is required when CONNECTOR_ID=http")
        return HttpConnector(base_url=settings.connector_http_url)

    if connector_id == "rag":
        return RagConnector(settings=settings)

    return connector_cls()


def resolve_connector(settings: Settings) -> BaseConnector | None:
    """Return a connector instance when enabled in settings, else ``None``."""
    if not settings.connector_enabled:
        return None
    return create_connector(settings.connector_id, settings)


def list_connector_ids() -> list[str]:
    """Return sorted built-in connector ids (for docs and validation messages)."""
    return sorted(_BUILTIN_CONNECTORS)
