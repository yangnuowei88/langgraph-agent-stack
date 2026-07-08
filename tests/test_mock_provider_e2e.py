"""tests/test_mock_provider_e2e.py — Regression test for LLM_PROVIDER=mock.

Unlike ``tests/test_api.py`` (which mocks the whole pack/agent classes) or
``tests/test_integration_real.py`` (which patches ``get_llm`` with a
``MagicMock``), this test exercises the *real* code path taken by an operator
who follows the README quickstart: ``LLM_PROVIDER=mock`` with no API key,
hitting ``POST /run`` through the actual pack and agent stack.

This is a regression test for a bug where ``BaseAgent.__init__`` called
``self.llm.bind_tools(self.tools)`` unconditionally whenever tools were
present, which raises ``NotImplementedError`` on ``FakeListChatModel`` (the
model returned by ``core.llm.get_llm`` for ``LLM_PROVIDER=mock``) and caused
a 500 on every real request in mock mode.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def mock_provider_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
    """TestClient wired to the real app with LLM_PROVIDER=mock, nothing patched."""
    from core.config import get_settings

    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.delenv("API_KEY", raising=False)
    get_settings.cache_clear()

    import api.state as api_state

    api_state.shared_llm = None
    api_state.shared_checkpointer = None

    from api.main import app

    with TestClient(app) as client:
        yield client

    api_state.shared_llm = None
    api_state.shared_checkpointer = None
    get_settings.cache_clear()


class TestMockProviderRealRun:
    """POST /run must succeed end-to-end when LLM_PROVIDER=mock (no API key)."""

    def test_run_returns_200_with_coherent_report(
        self, mock_provider_client: TestClient
    ) -> None:
        response = mock_provider_client.post(
            "/run",
            json={"query": "What is quantum computing?"},
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["executive_summary"]
        assert isinstance(data["key_insights"], list)
        assert len(data["key_insights"]) > 0
        assert 0.0 <= data["confidence"] <= 1.0
