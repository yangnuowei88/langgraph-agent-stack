"""domain_packs/research_analysis/schemas.py — Typed I/O schemas for ResearchAnalysisPack."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ResearchAnalysisInput(BaseModel):
    """Input schema for the Research + Analysis pipeline."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        ...,
        description="Research question to investigate",
        min_length=1,
        max_length=2000,  # matches InputValidator.MAX_LENGTH
    )
    max_sources: int = Field(
        default=5, ge=1, le=50, description="Maximum number of sources to retrieve"
    )


class ResearchAnalysisOutput(BaseModel):
    """Output schema for the Research + Analysis pipeline."""

    model_config = ConfigDict(extra="forbid")

    query: str
    executive_summary: str
    key_insights: list[str]
    patterns: list[str]
    implications: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    research_summary: str
    cost_usd: float | None = None

    @classmethod
    def from_analysis_report(
        cls, report: Any, cost_usd: float | None = None
    ) -> ResearchAnalysisOutput:
        """Build output from an AnalysisReport dataclass."""
        # Deferred to break circular import: schemas ← pack ← agents.models
        from agents.models import AnalysisReport

        if not isinstance(report, AnalysisReport):
            raise TypeError(f"Expected AnalysisReport, got {type(report).__name__!r}")
        return cls(
            query=report.query,
            executive_summary=report.executive_summary,
            key_insights=report.key_insights,
            patterns=report.patterns,
            implications=report.implications,
            confidence=report.confidence,
            research_summary=report.research_summary,
            cost_usd=cost_usd,
        )
