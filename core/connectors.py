"""core/connectors.py — Backward-compat shim. Use connectors.resolver instead."""

from connectors.resolver import create_connector, list_connector_ids, resolve_connector

__all__ = ["create_connector", "list_connector_ids", "resolve_connector"]
