"""examples/custom_pack/schemas.py — I/O schemas for SummariserPack."""

from pydantic import BaseModel, Field


class SummaryInput(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000, description="Text to summarise")
    bullet_count: int = Field(default=3, ge=1, le=10, description="Number of bullet points")


class SummaryOutput(BaseModel):
    original_length: int
    bullets: list[str]
    cost_usd: float | None = None
