"""evals/models.py — Typed dataset cases and evaluation reports."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EvalCase(BaseModel):
    """One golden-dataset case for a pack evaluation."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, description="Unique case identifier.")
    input: dict[str, Any] = Field(
        description="Payload matching the pack's input schema."
    )
    mock_responses: list[str] | None = Field(
        default=None,
        description=(
            "Scripted LLM responses for this case (deterministic, no network). "
            "When omitted, the LLM passed to the runner is used as-is."
        ),
    )
    checks: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Deterministic checks on the output: required_fields (list), "
            "contains / not_contains (field -> substring), min_length "
            "(field -> int), numeric_range (field -> [min, max])."
        ),
    )
    expect_error: str | None = Field(
        default=None,
        description=(
            "When set, the case passes only if the pack raises an error whose "
            "message contains this substring (e.g. output-guard rejections)."
        ),
    )
    judge: str | None = Field(
        default=None,
        description=(
            "Optional rubric for the LLM judge. Scored only when a judge LLM "
            "is supplied to the runner; otherwise skipped."
        ),
    )


class CheckResult(BaseModel):
    """Outcome of a single deterministic check."""

    name: str
    passed: bool
    detail: str = ""


class CaseResult(BaseModel):
    """Outcome of one evaluated case."""

    case_id: str
    passed: bool
    checks: list[CheckResult] = Field(default_factory=list)
    latency_seconds: float = 0.0
    cost_usd: float | None = None
    judge_score: float | None = None
    error: str | None = None


class EvalReport(BaseModel):
    """Aggregate evaluation result for one pack version on one dataset."""

    pack_id: str
    version: str
    cases: list[CaseResult] = Field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.cases if c.passed)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.cases else 0.0

    @property
    def mean_latency_seconds(self) -> float:
        if not self.cases:
            return 0.0
        return sum(c.latency_seconds for c in self.cases) / len(self.cases)

    @property
    def total_cost_usd(self) -> float:
        return sum(c.cost_usd or 0.0 for c in self.cases)

    def summary(self) -> dict[str, Any]:
        """JSON-friendly aggregate view (used by the CLI)."""
        return {
            "pack_id": self.pack_id,
            "version": self.version,
            "total": self.total,
            "passed": self.passed,
            "pass_rate": round(self.pass_rate, 4),
            "mean_latency_seconds": round(self.mean_latency_seconds, 4),
            "total_cost_usd": round(self.total_cost_usd, 6),
        }


class EvalComparison(BaseModel):
    """Side-by-side aggregates for two versions of the same pack."""

    pack_id: str
    baseline: EvalReport
    candidate: EvalReport

    def diff(self) -> dict[str, Any]:
        """Aggregate deltas (candidate minus baseline)."""
        return {
            "pack_id": self.pack_id,
            "baseline_version": self.baseline.version,
            "candidate_version": self.candidate.version,
            "pass_rate_delta": round(
                self.candidate.pass_rate - self.baseline.pass_rate, 4
            ),
            "mean_latency_delta_seconds": round(
                self.candidate.mean_latency_seconds
                - self.baseline.mean_latency_seconds,
                4,
            ),
            "total_cost_delta_usd": round(
                self.candidate.total_cost_usd - self.baseline.total_cost_usd, 6
            ),
        }
