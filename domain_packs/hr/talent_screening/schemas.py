"""domain_packs/hr/talent_screening/schemas.py — Typed I/O for TalentScreeningPack."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TalentScreeningInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_description: str = Field(..., min_length=1, max_length=10000)
    resume_text: str = Field(..., min_length=1, max_length=15000)
    must_have_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)


class TalentScreeningOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    fit_score: float = Field(ge=0.0, le=1.0)
    matched_skills: list[str]
    gaps: list[str]
    interview_questions: list[str]
    red_flags: list[str]
    summary_for_hiring_manager: str
    confidence: float = Field(ge=0.0, le=1.0)
    human_review_required: bool = Field(
        default=True,
        description="Always true — output is assistive only, not a hiring decision.",
    )
    disclaimer: str = Field(
        default="",
        description="Mandatory compliance disclaimer (injected server-side).",
    )
    cost_usd: float | None = None
