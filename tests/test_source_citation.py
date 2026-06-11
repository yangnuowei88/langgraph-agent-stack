"""
tests/test_source_citation.py — End-to-end source traceability (SourceRef).

Covers:
* ``record_to_source_ref`` normalization (usual keys, aliases, fallback,
  snippet truncation).
* ``ResearchAgent`` with a connector → citation-formatted ``sources`` and a
  full ``metadata["source_refs"]`` audit trail; without a connector the
  legacy behaviour is unchanged.
* ``StructuredLLMPack`` connector snippets labelled ``[doc-N]`` in the prompt,
  ``last_source_refs`` populated, and invalid snippets excluded.
* RAG-style pack (HrPolicyQaPack) provenance exposure.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from agents.researcher import ResearchAgent, ResearchResult
from connectors.base import (
    SNIPPET_MAX_CHARS,
    BaseConnector,
    ConnectorRequest,
    ConnectorResult,
    SourceRef,
    record_to_source_ref,
)
from domain_packs.hr.hr_policy_qa.pack import HrPolicyQaPack
from domain_packs.hr.hr_policy_qa.schemas import HrPolicyQaInput

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _StubConnector(BaseConnector):
    """Returns the records it was constructed with."""

    connector_id: ClassVar[str] = "stub"
    name: ClassVar[str] = "Stub connector"
    description: ClassVar[str] = "Canned records for tests."

    def __init__(self, records: tuple[dict[str, Any], ...]) -> None:
        self._records = records
        self.calls: list[ConnectorRequest] = []

    async def fetch(self, request: ConnectorRequest) -> ConnectorResult:
        self.calls.append(request)
        return ConnectorResult(records=self._records, metadata={"stub": True})


def _build_researcher_llm() -> MagicMock:
    """Deterministic mock LLM for the three ResearchAgent nodes."""
    llm = MagicMock()
    llm.bind_tools.return_value = llm

    def smart_invoke(messages: list[Any]) -> AIMessage:
        system_content = str(messages[0].content) if messages else ""
        if "query expander" in system_content.lower():
            return AIMessage(content=json.dumps(["sub-query 1"]))
        if "quality assessor" in system_content.lower():
            return AIMessage(content=json.dumps({"sufficient": True, "reason": "ok"}))
        return AIMessage(
            content=json.dumps({"summary": "A summary.", "confidence": 0.8})
        )

    llm.invoke.side_effect = smart_invoke
    return llm


# ---------------------------------------------------------------------------
# (a) record_to_source_ref
# ---------------------------------------------------------------------------


class TestRecordToSourceRef:
    def test_usual_keys(self) -> None:
        ref = record_to_source_ref(
            {
                "id": "kb-7",
                "title": "Quantum Basics",
                "url": "https://example.com/qb",
                "snippet": "Qubits are cool.",
                "score": 0.91,
            },
            index=1,
        )
        assert ref.id == "kb-7"
        assert ref.title == "Quantum Basics"
        assert ref.url == "https://example.com/qb"
        assert ref.snippet == "Qubits are cool."
        assert ref.metadata == {"score": 0.91}

    def test_alias_keys(self) -> None:
        ref = record_to_source_ref(
            {
                "doc_id": "D-1",
                "name": "Handbook",
                "link": "https://intra/handbook",
                "text": "PTO is 25 days.",
            },
            index=3,
        )
        assert ref.id == "D-1"
        assert ref.title == "Handbook"
        assert ref.url == "https://intra/handbook"
        assert ref.snippet == "PTO is 25 days."

    def test_source_and_content_aliases(self) -> None:
        ref = record_to_source_ref(
            {"source": "rag:0", "content": "Some chunk."}, index=2
        )
        assert ref.url == "rag:0"
        assert ref.snippet == "Some chunk."

    def test_fallback_id_and_empty_record(self) -> None:
        ref = record_to_source_ref({}, index=4)
        assert ref.id == "doc-4"
        assert ref.title is None
        assert ref.url is None
        assert ref.snippet == ""
        assert ref.metadata == {}

    def test_snippet_truncated(self) -> None:
        ref = record_to_source_ref({"snippet": "x" * 2000}, index=1)
        assert len(ref.snippet) == SNIPPET_MAX_CHARS

    def test_blank_values_ignored(self) -> None:
        ref = record_to_source_ref({"id": "  ", "doc_id": "real"}, index=1)
        assert ref.id == "real"

    def test_citation_format(self) -> None:
        full = SourceRef(
            id="kb-7", title="Quantum Basics", url="https://example.com/qb"
        )
        assert full.citation() == "[kb-7] Quantum Basics — https://example.com/qb"
        no_url = SourceRef(id="kb-7", title="Quantum Basics")
        assert no_url.citation() == "[kb-7] Quantum Basics"
        no_title = SourceRef(id="kb-7", url="https://example.com/qb")
        assert no_title.citation() == "[kb-7] https://example.com/qb"
        bare = SourceRef(id="doc-1")
        assert bare.citation() == "[doc-1]"


# ---------------------------------------------------------------------------
# (b) ResearchAgent with / without connector
# ---------------------------------------------------------------------------


class TestResearcherSourceTraceability:
    _RECORDS: tuple[dict[str, Any], ...] = (
        {
            "id": "kb-1",
            "title": "Quantum Basics",
            "url": "https://example.com/qb",
            "snippet": "Qubits superpose.",
        },
        {"snippet": "Entanglement links qubits."},
    )

    def test_with_connector_sources_are_citations(self) -> None:
        connector = _StubConnector(self._RECORDS)
        with patch("agents.base_agent.get_llm", return_value=_build_researcher_llm()):
            agent = ResearchAgent(connector=connector)
            result = agent.run_structured("What is quantum computing?")

        assert isinstance(result, ResearchResult)
        assert "[kb-1] Quantum Basics — https://example.com/qb" in result.sources
        assert "[doc-2]" in result.sources
        # Connector snippets join the findings.
        assert "Qubits superpose." in result.findings
        # Full provenance audit trail in metadata.
        refs = result.metadata["source_refs"]
        assert [r["id"] for r in refs] == ["kb-1", "doc-2"]
        assert refs[0]["url"] == "https://example.com/qb"
        assert refs[1]["snippet"] == "Entanglement links qubits."
        # Each ref round-trips through the SourceRef model.
        assert all(SourceRef.model_validate(r) for r in refs)
        assert connector.calls, "connector.fetch should have been invoked"

    def test_without_connector_behaviour_unchanged(self) -> None:
        with patch("agents.base_agent.get_llm", return_value=_build_researcher_llm()):
            agent = ResearchAgent()
            result = agent.run_structured("What is quantum computing?")

        # Legacy sources: plain URLs from the mock web_search tool.
        assert result.sources
        assert all(src.startswith("https://") for src in result.sources)
        assert "source_refs" not in result.metadata

    def test_connector_failure_is_non_fatal(self) -> None:
        connector = MagicMock(spec=BaseConnector)
        connector.fetch.side_effect = RuntimeError("boom")
        with patch("agents.base_agent.get_llm", return_value=_build_researcher_llm()):
            agent = ResearchAgent(connector=connector)
            result = agent.run_structured("What is quantum computing?")

        assert "source_refs" not in result.metadata
        assert result.summary


# ---------------------------------------------------------------------------
# (c) StructuredLLMPack prompt labelling + last_source_refs
# ---------------------------------------------------------------------------


_HR_PAYLOAD = {
    "question": "How many PTO days?",
    "answer": "25 days per year",
    "citations": ["Handbook §4.2"],
    "confidence": 0.95,
    "escalate_to_hr": False,
    "disclaimer": "Informational only",
    "human_review_required": True,
}


def _mock_llm_json(payload: dict[str, Any]) -> MagicMock:
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content=json.dumps(payload))
    return llm


class TestStructuredLLMPackSourceRefs:
    def test_prompt_labels_and_last_source_refs(self) -> None:
        connector = _StubConnector(
            (
                {"snippet": "PTO is 25 days per year."},
                {
                    "doc_id": "HB-4.2",
                    "title": "Handbook",
                    "snippet": "Carry-over max 5 days.",
                },
            )
        )
        llm = _mock_llm_json(_HR_PAYLOAD)
        pack = HrPolicyQaPack(run_id="src-1", llm=llm, connector=connector)
        result = pack.run_from_input(HrPolicyQaInput(question="How many PTO days?"))

        assert result.answer == "25 days per year"
        prompt = llm.invoke.call_args[0][0]
        assert "[doc-1] PTO is 25 days per year." in prompt
        assert "[HB-4.2] Carry-over max 5 days." in prompt

        assert [ref.id for ref in pack.last_source_refs] == ["doc-1", "HB-4.2"]
        assert all(isinstance(ref, SourceRef) for ref in pack.last_source_refs)
        assert pack.last_source_refs[1].citation() == "[HB-4.2] Handbook"

    def test_invalid_snippet_excluded_from_refs(self) -> None:
        connector = _StubConnector(
            (
                {"snippet": "bad\x00snippet"},  # null byte → validator rejects
                {"snippet": "good snippet"},
            )
        )
        llm = _mock_llm_json(_HR_PAYLOAD)
        pack = HrPolicyQaPack(run_id="src-2", llm=llm, connector=connector)
        pack.run_from_input(HrPolicyQaInput(question="How many PTO days?"))

        assert len(pack.last_source_refs) == 1
        assert pack.last_source_refs[0].snippet == "good snippet"
        prompt = llm.invoke.call_args[0][0]
        assert "bad\x00snippet" not in prompt
        assert "[doc-1] good snippet" in prompt

    def test_no_connector_leaves_refs_empty(self) -> None:
        llm = _mock_llm_json(_HR_PAYLOAD)
        pack = HrPolicyQaPack(run_id="src-3", llm=llm)
        pack.run_from_input(HrPolicyQaInput(question="How many PTO days?"))
        assert pack.last_source_refs == []

    def test_sources_output_field_filled_when_schema_has_it(self) -> None:
        """Generic mechanism: a pack whose output schema declares ``sources``."""
        from pydantic import BaseModel, ConfigDict, Field

        from domain_packs.common.structured_llm import StructuredLLMPack

        class _In(BaseModel):
            model_config = ConfigDict(extra="forbid")
            question: str = Field(min_length=1)

        class _Out(BaseModel):
            model_config = ConfigDict(extra="forbid")
            answer: str
            sources: list[str] = Field(default_factory=list)

        class _SourcedPack(StructuredLLMPack):
            pack_id = "test_sourced_pack"
            name = "Test sourced pack"
            description = "Test-only pack with a sources output field."
            input_schema = _In
            output_schema = _Out
            primary_field = "question"

            @classmethod
            def build_prompt(cls, inp: BaseModel, *, reference_text: str = "") -> str:
                return f"Q: {cls.primary_text(inp)}\n\n{reference_text}"

        connector = _StubConnector(
            (
                {
                    "id": "pol-9",
                    "title": "Policy 9",
                    "url": "https://intra/pol-9",
                    "snippet": "Policy text.",
                },
            )
        )
        llm = _mock_llm_json({"answer": "Yes.", "sources": []})
        pack = _SourcedPack(run_id="src-4", llm=llm, connector=connector)
        result = pack.run_from_input(_In(question="Is policy 9 active?"))

        assert result.sources == ["[pol-9] Policy 9 — https://intra/pol-9"]


# ---------------------------------------------------------------------------
# (d) RAG pack provenance (hr_policy_qa: output has `citations`, no `sources`
#      field — schema unchanged, provenance via last_source_refs)
# ---------------------------------------------------------------------------


class TestHrPolicyQaProvenance:
    def test_output_schema_unchanged(self) -> None:
        from domain_packs.hr.hr_policy_qa.schemas import HrPolicyQaOutput

        assert "sources" not in HrPolicyQaOutput.model_fields
        assert "citations" in HrPolicyQaOutput.model_fields

    def test_provenance_exposed_via_last_source_refs(self) -> None:
        connector = _StubConnector(
            (
                {
                    "id": "HB-1",
                    "title": "Employee Handbook",
                    "url": "https://intra/hb",
                    "snippet": "PTO policy.",
                },
            )
        )
        llm = _mock_llm_json(_HR_PAYLOAD)
        pack = HrPolicyQaPack(run_id="src-5", llm=llm, connector=connector)
        result = pack.run_from_input(HrPolicyQaInput(question="How many PTO days?"))

        assert result.citations == ["Handbook §4.2"]  # untouched (LLM-provided)
        assert [ref.citation() for ref in pack.last_source_refs] == [
            "[HB-1] Employee Handbook — https://intra/hb"
        ]


# ---------------------------------------------------------------------------
# ResearchAnalysisPack merge keeps citation format
# ---------------------------------------------------------------------------


class TestResearchAnalysisMergeCitations:
    def test_merge_produces_citations_and_source_refs(self) -> None:
        from domain_packs.research.research_analysis.pack import ResearchAnalysisPack

        mock_research_agent = MagicMock()
        mock_research_agent.run_structured.return_value = ResearchResult(
            query="demo topic",
            findings=["LLM finding"],
            summary="Summary.",
            sources=["agent-source"],
            confidence=0.8,
            metadata={},
        )
        from agents.models import AnalysisReport

        mock_analyst_agent = MagicMock()
        mock_analyst_agent.run_structured.return_value = AnalysisReport(
            query="demo topic", research_summary="Summary."
        )

        connector = _StubConnector(
            (
                {
                    "id": "ex-1",
                    "title": "Example doc",
                    "url": "https://example.com/doc",
                    "snippet": "Canned snippet.",
                },
            )
        )
        with (
            patch("core.graph.ResearchAgent", return_value=mock_research_agent),
            patch("core.graph.AnalystAgent", return_value=mock_analyst_agent),
        ):
            pack = ResearchAnalysisPack(run_id="src-merge-1", connector=connector)
            pack.run("demo topic")

        passed: ResearchResult = mock_analyst_agent.run_structured.call_args[0][0]
        assert "Canned snippet." in passed.findings
        assert "agent-source" in passed.sources
        assert "[ex-1] Example doc — https://example.com/doc" in passed.sources
        refs = passed.metadata["source_refs"]
        assert refs[0]["id"] == "ex-1"
        assert passed.metadata["connector"]["connector_id"] == "stub"


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
