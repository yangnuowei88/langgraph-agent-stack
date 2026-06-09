"""domain_packs/financial_memo/schemas.py — Typed I/O for FinancialMemoPack."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FinancialMemoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(..., min_length=1, max_length=500)
    hypothesis: str = Field(default="", max_length=2000)
    metrics: str = Field(default="", max_length=2000)
    time_horizon: str = Field(default="12 months", max_length=100)


class FinancialMemoOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    topic: str
    situation: str
    complications: list[str]
    options: list[str]
    recommendation: str
    risks: list[str]
    next_steps: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    human_review_required: bool = Field(
        default=True,
        description="Always true — not financial advice; professional review required.",
    )
    disclaimer: str = Field(
        default="",
        description="Mandatory compliance disclaimer (injected server-side).",
    )
    cost_usd: float | None = None
