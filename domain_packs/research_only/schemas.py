"""domain_packs/research_only/schemas.py — Typed I/O schemas for ResearchOnlyPack."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ResearchOnlyInput(BaseModel):
    """Input schema for the research-only pipeline."""

    query: str = Field(
        ...,
        description="Research question to investigate",
        min_length=1,
        max_length=2000,
    )


class ResearchOnlyOutput(BaseModel):
    """Output schema for the research-only pipeline."""

    query: str
    findings: list[str]
    summary: str
    sources: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    cost_usd: float | None = None

    @classmethod
    def from_research_result(
        cls, result: Any, cost_usd: float | None = None
    ) -> ResearchOnlyOutput:
        """Build output from a ``ResearchResult`` dataclass."""
        from agents.models import ResearchResult

        if not isinstance(result, ResearchResult):
            raise TypeError(f"Expected ResearchResult, got {type(result).__name__!r}")
        return cls(
            query=result.query,
            findings=result.findings,
            summary=result.summary,
            sources=result.sources,
            confidence=result.confidence,
            cost_usd=cost_usd,
        )
