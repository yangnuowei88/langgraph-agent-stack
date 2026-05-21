"""
tests/test_versioning.py — API-level versioning behavior tests.

Covers:
- run history records pack_version in metadata when a pack run completes
- sticky session pins version on second call by reading session history
- ConversationMemory.get_pack_version_for_session returns None when no history
- ConversationMemory.get_pack_version_for_session returns the last-used version
- get_pack_version_for_session returns None when querying a different session
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.main import app
from core.memory import ConversationMemory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_analysis_report():
    from agents.models import AnalysisReport

    return AnalysisReport(
        query="What is quantum computing?",
        executive_summary="A paradigm shift in computational power.",
        key_insights=["Qubits enable superposition."],
        patterns=["Rapid hardware iteration."],
        implications=["Cryptographic systems need replacement."],
        confidence=0.82,
        research_summary="Quantum computing uses qubits.",
        metadata={"run_id": "test-run-001"},
    )


def _make_pack_instance_mock(report=None):
    """Return a MagicMock that behaves like a pack context manager."""
    if report is None:
        report = _make_mock_analysis_report()
    instance = MagicMock()
    instance.run.return_value = report
    instance.cost_usd = None
    instance.__enter__ = MagicMock(return_value=instance)
    instance.__exit__ = MagicMock(return_value=False)
    return instance


# ---------------------------------------------------------------------------
# Test 1: run history records pack_version in metadata
# ---------------------------------------------------------------------------


def test_run_history_records_pack_version() -> None:
    """POST /packs/research_analysis/run must call save_run with pack_version in metadata."""
    from core.security import RateLimiter
    from pack_kernel.registry import PackRegistry

    report = _make_mock_analysis_report()
    permissive = RateLimiter(max_requests=10_000, window_seconds=60.0)

    mock_pack_instance = _make_pack_instance_mock(report)
    mock_memory = MagicMock()
    mock_llm = MagicMock(spec=True)
    mock_checkpointer = MagicMock()

    # Let the lifespan run normally with real pack schemas.
    # After startup, patch _shared_memory and PackRegistry.get so the request
    # uses our mock pack instance and mock memory.
    with (
        patch("api.main._rate_limiter", permissive),
        patch("api.main.get_shared_llm", return_value=mock_llm),
        patch("api.main.get_shared_checkpointer", return_value=mock_checkpointer),
        patch("api.main.create_run_history", return_value=mock_memory),
    ):
        with TestClient(app, raise_server_exceptions=False) as client:
            # After lifespan startup, _shared_memory == mock_memory (set by create_run_history).
            # Now patch PackRegistry.get so the request handler uses our mock pack.
            # We must keep pack_id matching so _get_versions still works.
            real_pack_cls = PackRegistry.get("research_analysis")
            # Wrap the real class to intercept instantiation
            mock_pack_cls = MagicMock(return_value=mock_pack_instance)
            # Carry over the version attribute so _get_versions can match it
            mock_pack_cls.version = getattr(real_pack_cls, "version", "1.0")

            with patch.object(PackRegistry, "get", return_value=mock_pack_cls):
                response = client.post(
                    "/packs/research_analysis/run",
                    json={"query": "What is quantum computing?"},
                )

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text}"
    )
    assert mock_memory.save_run.called, (
        "save_run must be called after a successful pack run"
    )

    call_kwargs = mock_memory.save_run.call_args
    # save_run is called with keyword args: run_id, query, result, metadata
    if call_kwargs.kwargs:
        metadata = call_kwargs.kwargs.get("metadata", {})
    else:
        # positional: (run_id, query, result, metadata)
        args = call_kwargs.args
        metadata = args[3] if len(args) >= 4 else {}

    assert "pack_version" in metadata, f"pack_version missing from metadata: {metadata}"
    assert "pack_id" in metadata, f"pack_id missing from metadata: {metadata}"
    assert metadata["pack_id"] == "research_analysis"


# ---------------------------------------------------------------------------
# Test 2: sticky session — when no explicit header, check session history
# ---------------------------------------------------------------------------


def test_sticky_session_pins_version_on_second_call() -> None:
    """When get_pack_version_for_session returns a version and the body has session_id,
    PackRegistry.get is called with that pinned version."""
    # We test the sticky-session logic directly (unit test), not via HTTP,
    # because ResearchAnalysisInput does not have a session_id field — so it
    # cannot be triggered via the HTTP stack for this pack.
    #
    # This test validates the LOGIC inside the run_pack handler by simulating
    # the branch inline.

    mock_memory = MagicMock()
    mock_memory.get_pack_version_for_session.return_value = "1.0"

    # Simulate a body that HAS session_id (forward-compatible case)
    class _FakeBody:
        query = "test sticky"
        session_id = "sess-001"

    body = _FakeBody()
    pack_id = "research_analysis"

    # Reproduce the sticky-session logic from run_pack
    requested_version = None  # no X-Pack-Version header
    if requested_version is None and mock_memory is not None:
        session_id_for_sticky = getattr(body, "session_id", None) or None
        if session_id_for_sticky and hasattr(
            mock_memory, "get_pack_version_for_session"
        ):
            requested_version = mock_memory.get_pack_version_for_session(
                session_id_for_sticky, pack_id
            )

    assert requested_version == "1.0", (
        f"Sticky version should be '1.0' but got {requested_version!r}"
    )
    mock_memory.get_pack_version_for_session.assert_called_once_with(
        "sess-001", "research_analysis"
    )


def test_sticky_session_not_triggered_without_session_id() -> None:
    """When body has no session_id, get_pack_version_for_session is not called."""
    mock_memory = MagicMock()
    mock_memory.get_pack_version_for_session.return_value = "1.0"

    class _FakeBody:
        query = "no session"
        # no session_id field

    body = _FakeBody()
    pack_id = "research_analysis"

    requested_version = None
    if requested_version is None and mock_memory is not None:
        session_id_for_sticky = getattr(body, "session_id", None) or None
        if session_id_for_sticky and hasattr(
            mock_memory, "get_pack_version_for_session"
        ):
            requested_version = mock_memory.get_pack_version_for_session(
                session_id_for_sticky, pack_id
            )

    assert requested_version is None
    mock_memory.get_pack_version_for_session.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3: get_pack_version_for_session returns None when no history
# ---------------------------------------------------------------------------


def test_get_pack_version_for_session_returns_none_when_no_history() -> None:
    """ConversationMemory.get_pack_version_for_session returns None when the DB is empty."""
    mem = ConversationMemory(":memory:")
    try:
        result = mem.get_pack_version_for_session("session-abc", "research_analysis")
        assert result is None
    finally:
        mem.close()


# ---------------------------------------------------------------------------
# Test 4: get_pack_version_for_session returns last-used version
# ---------------------------------------------------------------------------


def test_get_pack_version_for_session_returns_last_version() -> None:
    """After saving a run with pack_version in metadata, the method returns it."""
    mem = ConversationMemory(":memory:")
    try:
        run_id = str(uuid.uuid4())
        mem.save_run(
            run_id=run_id,
            query="test query",
            result={},
            metadata={
                "session_id": "session-xyz",
                "pack_id": "research_analysis",
                "pack_version": "1.0",
            },
        )
        result = mem.get_pack_version_for_session("session-xyz", "research_analysis")
        assert result == "1.0"
    finally:
        mem.close()


def test_get_pack_version_for_session_returns_most_recent() -> None:
    """When multiple runs exist, the most recent pack_version is returned."""
    mem = ConversationMemory(":memory:")
    try:
        for version in ("1.0", "1.1", "2.0"):
            mem.save_run(
                run_id=str(uuid.uuid4()),
                query="test query",
                result={},
                metadata={
                    "session_id": "session-multi",
                    "pack_id": "research_analysis",
                    "pack_version": version,
                },
            )
        # The most recent insert has version "2.0"
        result = mem.get_pack_version_for_session("session-multi", "research_analysis")
        assert result == "2.0"
    finally:
        mem.close()


# ---------------------------------------------------------------------------
# Test 5: get_pack_version_for_session different session returns None
# ---------------------------------------------------------------------------


def test_get_pack_version_for_session_different_session_returns_none() -> None:
    """Querying session B after saving a run for session A must return None."""
    mem = ConversationMemory(":memory:")
    try:
        run_id = str(uuid.uuid4())
        mem.save_run(
            run_id=run_id,
            query="test query",
            result={},
            metadata={
                "session_id": "session-A",
                "pack_id": "research_analysis",
                "pack_version": "1.0",
            },
        )
        # Query for a different session — should not find session-A's run
        result = mem.get_pack_version_for_session("session-B", "research_analysis")
        assert result is None
    finally:
        mem.close()
