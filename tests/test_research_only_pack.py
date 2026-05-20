"""tests/test_research_only_pack.py — Unit tests for ResearchOnlyPack."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agents.researcher import ResearchResult
from domain_packs.research_only.pack import ResearchOnlyPack


def test_research_only_run_returns_research_result() -> None:
    mock_result = ResearchResult(
        query="What is AI?",
        findings=["f1"],
        summary="AI summary",
        sources=[],
        confidence=0.7,
    )
    mock_agent = MagicMock()
    mock_agent.run_structured.return_value = mock_result

    with patch("core.graph.ResearchAgent", return_value=mock_agent):
        pack = ResearchOnlyPack(run_id="ro-test-1")
        result = pack.run("What is AI?")

    assert isinstance(result, ResearchResult)
    assert result.summary == "AI summary"
