"""
tests/test_connector_pack.py — Connector integration on ResearchAnalysisPack.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agents.researcher import ResearchResult
from connectors.examples.example_connector import ExampleMemoryConnector
from domain_packs.research_analysis.pack import ResearchAnalysisPack


@pytest.fixture()
def mock_research_result() -> ResearchResult:
    return ResearchResult(
        query="demo quantum topic",
        findings=["LLM finding"],
        summary="Summary from agent.",
        sources=["agent-source"],
        confidence=0.8,
        metadata={},
    )


@pytest.fixture()
def mock_analysis_report():
    from agents.analyst import AnalysisReport

    return AnalysisReport(
        query="demo quantum topic",
        executive_summary="Done.",
        key_insights=["insight"],
        patterns=[],
        implications=[],
        confidence=0.75,
        research_summary="Summary from agent.",
        metadata={},
    )


class TestResearchAnalysisPackConnector:
    def test_without_connector_unchanged(
        self,
        mock_research_result: ResearchResult,
        mock_analysis_report,
    ) -> None:
        mock_research_agent = MagicMock()
        mock_research_agent.run_structured.return_value = mock_research_result
        mock_analyst_agent = MagicMock()
        mock_analyst_agent.run_structured.return_value = mock_analysis_report

        with (
            patch("core.graph.ResearchAgent", return_value=mock_research_agent),
            patch("core.graph.AnalystAgent", return_value=mock_analyst_agent),
        ):
            pack = ResearchAnalysisPack(run_id="connector-test-1")
            report = pack.run("demo quantum topic")

        assert report.executive_summary == "Done."
        mock_research_agent.run_structured.assert_called_once()

    def test_connector_merges_demo_snippet(
        self,
        mock_research_result: ResearchResult,
        mock_analysis_report,
    ) -> None:
        mock_research_agent = MagicMock()
        mock_research_agent.run_structured.return_value = mock_research_result
        mock_analyst_agent = MagicMock()
        mock_analyst_agent.run_structured.return_value = mock_analysis_report

        connector = ExampleMemoryConnector()

        with (
            patch("core.graph.ResearchAgent", return_value=mock_research_agent),
            patch("core.graph.AnalystAgent", return_value=mock_analyst_agent),
        ):
            pack = ResearchAnalysisPack(
                run_id="connector-test-2",
                connector=connector,
            )
            pack.run("demo quantum topic")

        passed_research = mock_analyst_agent.run_structured.call_args[0][0]
        assert "This is a canned result for demonstration." in passed_research.findings
        assert passed_research.metadata.get("connector", {}).get("connector_id") == (
            "example_memory"
        )
