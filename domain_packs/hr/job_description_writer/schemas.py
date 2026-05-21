"""domain_packs/hr/job_description_writer/schemas.py — JobDescriptionWriter I/O."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class JobDescriptionWriterInput(BaseModel):
    role_title: str = Field(..., min_length=1, max_length=200)
    team_context: str = Field(default="", max_length=2000)
    seniority: str = Field(default="mid", max_length=50)
    must_haves: list[str] = Field(default_factory=list)
    culture_notes: str = Field(default="", max_length=2000)


class JobDescriptionWriterOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    role_title: str
    jd_markdown: str
    competency_matrix: list[str]
    screening_rubric: list[str]
    bias_check_notes: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    human_review_required: bool = Field(
        default=True,
        description="Always true — JD must be human-approved before posting.",
    )
    disclaimer: str = Field(
        default="",
        description="Mandatory compliance disclaimer (injected server-side).",
    )
    cost_usd: float | None = None
