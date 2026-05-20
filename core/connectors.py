"""
core/connectors.py — Resolve optional retrieval connectors from settings.

Connectors are not registered in PackRegistry; the API wires a single shared
instance when ``CONNECTOR_ENABLED`` is true and the active pack supports it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from connectors.base import BaseConnector
from connectors.examples.example_connector import ExampleMemoryConnector

if TYPE_CHECKING:
    from core.config import Settings

_BUILTIN_CONNECTORS: dict[str, type[BaseConnector]] = {
    "example_memory": ExampleMemoryConnector,
}


def create_connector(connector_id: str) -> BaseConnector:
    """Instantiate a built-in connector by id.

    Raises:
        ValueError: If ``connector_id`` is not registered.
    """
    connector_cls = _BUILTIN_CONNECTORS.get(connector_id)
    if connector_cls is None:
        known = ", ".join(sorted(_BUILTIN_CONNECTORS))
        raise ValueError(
            f"Unknown CONNECTOR_ID {connector_id!r}. Supported values: {known}"
        )
    return connector_cls()


def resolve_connector(settings: Settings) -> BaseConnector | None:
    """Return a connector instance when enabled in settings, else ``None``."""
    if not settings.connector_enabled:
        return None
    return create_connector(settings.connector_id)


def list_connector_ids() -> list[str]:
    """Return sorted built-in connector ids (for docs and validation messages)."""
    return sorted(_BUILTIN_CONNECTORS)
