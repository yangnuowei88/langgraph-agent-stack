"""domain_packs/contract_reviewer/schemas.py — Typed I/O for ContractReviewerPack."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ContractReviewerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=500, description="Contract label")
    contract_text: str = Field(default="", max_length=50000)
    contract_type: str = Field(default="msa", max_length=100)
    jurisdiction: str = Field(default="", max_length=100)


class ContractReviewerOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str
    risk_score: float = Field(ge=0.0, le=1.0)
    flagged_clauses: list[str]
    deviations_from_playbook: list[str]
    recommended_actions: list[str]
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    human_review_required: bool = Field(
        default=True,
        description="Always true — not legal advice; attorney review required.",
    )
    disclaimer: str = Field(
        default="",
        description="Mandatory compliance disclaimer (injected server-side).",
    )
    cost_usd: float | None = None
