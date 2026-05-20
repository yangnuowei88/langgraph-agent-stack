"""tests/test_core_connectors.py — Connector factory and settings integration."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from connectors.examples.example_connector import ExampleMemoryConnector
from core.connectors import create_connector, resolve_connector


def test_create_connector_example_memory() -> None:
    connector = create_connector("example_memory")
    assert isinstance(connector, ExampleMemoryConnector)


def test_create_connector_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown CONNECTOR_ID"):
        create_connector("does_not_exist")


def test_resolve_connector_disabled() -> None:
    from core.config import Settings

    settings = Settings(
        llm_provider="mock",
        connector_enabled=False,
    )
    assert resolve_connector(settings) is None


def test_resolve_connector_enabled() -> None:
    from core.config import Settings

    env = {
        "LLM_PROVIDER": "mock",
        "CONNECTOR_ENABLED": "true",
        "CONNECTOR_ID": "example_memory",
    }
    with patch.dict(os.environ, env, clear=False):
        settings = Settings()
    connector = resolve_connector(settings)
    assert isinstance(connector, ExampleMemoryConnector)


def test_settings_rejects_unknown_connector_id() -> None:
    from core.config import Settings

    env = {
        "LLM_PROVIDER": "mock",
        "CONNECTOR_ENABLED": "true",
        "CONNECTOR_ID": "unknown_connector",
    }
    with patch.dict(os.environ, env, clear=False):
        with pytest.raises(ValidationError, match="CONNECTOR_ID"):
            Settings()


def test_settings_connector_enabled_via_env() -> None:
    from core.config import get_settings

    env = {
        "LLM_PROVIDER": "mock",
        "CONNECTOR_ENABLED": "true",
        "CONNECTOR_ID": "example_memory",
    }
    with patch.dict(os.environ, env, clear=False):
        get_settings.cache_clear()
        try:
            settings = get_settings()
            assert settings.connector_enabled is True
            assert resolve_connector(settings) is not None
        finally:
            get_settings.cache_clear()
