"""evals/runner.py — Execute golden datasets against pack versions."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import yaml
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from evals.checks import run_checks
from evals.judge import judge_case
from evals.models import CaseResult, EvalCase, EvalComparison, EvalReport
from pack_kernel.registry import PackRegistry

logger = logging.getLogger(__name__)

#: Directory holding the built-in golden datasets (one YAML file per pack_id).
DATASETS_DIR = Path(__file__).parent / "datasets"

#: Free-text fields probed (in order) for packs whose entrypoint is run(query).
_PRIMARY_TEXT_FIELDS = ("query", "text", "topic", "question")


class ScriptedChatModel(FakeListChatModel):
    """Deterministic chat model replaying scripted responses.

    Unlike the stock ``FakeListChatModel`` it tolerates ``bind_tools`` (the
    research pipeline binds tools to its LLM), simply returning itself.
    """

    def bind_tools(self, tools: Any, **kwargs: Any) -> ScriptedChatModel:
        return self


def load_dataset(path: str | Path) -> list[EvalCase]:
    """Load and validate a YAML golden dataset.

    Expected layout::

        cases:
          - id: basic
            input: {text: "..."}
            mock_responses: ["- bullet"]
            checks: {required_fields: [bullets]}
    """
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "cases" not in raw:
        raise ValueError(f"Dataset {path} must be a mapping with a 'cases' list.")
    return [EvalCase.model_validate(case) for case in raw["cases"]]


def dataset_path_for(pack_id: str) -> Path:
    """Return the built-in dataset path for *pack_id* (may not exist)."""
    return DATASETS_DIR / f"{pack_id}.yaml"


def list_builtin_datasets() -> list[str]:
    """Pack ids that ship a built-in golden dataset."""
    return sorted(p.stem for p in DATASETS_DIR.glob("*.yaml"))


def _primary_text(case_input: dict[str, Any]) -> str:
    for field in _PRIMARY_TEXT_FIELDS:
        value = case_input.get(field)
        if isinstance(value, str) and value:
            return value
    for value in case_input.values():
        if isinstance(value, str) and value:
            return value
    raise ValueError("Case input has no free-text field to run the pack with.")


def _result_to_dict(result: Any) -> dict[str, Any]:
    if hasattr(result, "to_dict"):
        return result.to_dict()
    if hasattr(result, "model_dump"):
        return result.model_dump()
    return dict(result) if isinstance(result, dict) else {"result": str(result)}


def _run_one_case(
    pack_cls: type,
    input_model: type,
    case: EvalCase,
    llm: Any,
    judge_llm: Any,
) -> CaseResult:
    case_llm = (
        ScriptedChatModel(responses=list(case.mock_responses))
        if case.mock_responses
        else llm
    )
    if case_llm is None:
        return CaseResult(
            case_id=case.id,
            passed=False,
            error="No LLM available: case has no mock_responses and no LLM was given.",
        )

    started = time.monotonic()
    try:
        body = input_model(**case.input)
        with pack_cls(run_id=f"eval-{case.id}", llm=case_llm) as pipeline:
            if hasattr(pipeline, "run_from_input"):
                result = pipeline.run_from_input(body)
            else:
                result = pipeline.run(_primary_text(case.input))
            cost_usd = getattr(pipeline, "cost_usd", None)
    except Exception as exc:
        latency = time.monotonic() - started
        if case.expect_error is not None and case.expect_error in str(exc):
            return CaseResult(case_id=case.id, passed=True, latency_seconds=latency)
        return CaseResult(
            case_id=case.id,
            passed=False,
            latency_seconds=latency,
            error=f"{type(exc).__name__}: {exc}",
        )
    latency = time.monotonic() - started

    if case.expect_error is not None:
        return CaseResult(
            case_id=case.id,
            passed=False,
            latency_seconds=latency,
            cost_usd=cost_usd,
            error=f"Expected an error containing {case.expect_error!r}, got success.",
        )

    output = _result_to_dict(result)
    checks = run_checks(output, case.checks)
    passed = all(c.passed for c in checks)

    judge_score: float | None = None
    if judge_llm is not None and case.judge:
        try:
            judge_score = judge_case(
                judge_llm, rubric=case.judge, case_input=case.input, output=output
            ).score
        except ValueError as exc:
            return CaseResult(
                case_id=case.id,
                passed=False,
                checks=checks,
                latency_seconds=latency,
                cost_usd=cost_usd,
                error=str(exc),
            )

    return CaseResult(
        case_id=case.id,
        passed=passed,
        checks=checks,
        latency_seconds=latency,
        cost_usd=cost_usd,
        judge_score=judge_score,
    )


def run_pack_eval(
    pack_id: str,
    cases: list[EvalCase],
    *,
    version: str | None = None,
    llm: Any = None,
    judge_llm: Any = None,
) -> EvalReport:
    """Run *cases* against one version of *pack_id* and aggregate the results.

    Args:
        pack_id: Registered pack identifier.
        cases: Golden dataset cases (see :func:`load_dataset`).
        version: Specific registered version; default uses registry routing.
        llm: Fallback LLM for cases without ``mock_responses``.
        judge_llm: Optional judge; activates rubric scoring on cases that
            declare one.
    """
    pack_cls = PackRegistry.get(pack_id, version=version)
    input_model, _ = PackRegistry.get_schemas(pack_id)
    report = EvalReport(pack_id=pack_id, version=version or "default")
    for case in cases:
        result = _run_one_case(pack_cls, input_model, case, llm, judge_llm)
        report.cases.append(result)
        logger.info(
            "Eval case finished",
            extra={
                "pack_id": pack_id,
                "case_id": case.id,
                "passed": result.passed,
                "latency_seconds": round(result.latency_seconds, 3),
            },
        )
    return report


def compare_versions(
    pack_id: str,
    cases: list[EvalCase],
    *,
    baseline_version: str | None = None,
    candidate_version: str,
    llm: Any = None,
    judge_llm: Any = None,
) -> EvalComparison:
    """Evaluate two versions of the same pack on the same dataset."""
    baseline = run_pack_eval(
        pack_id, cases, version=baseline_version, llm=llm, judge_llm=judge_llm
    )
    candidate = run_pack_eval(
        pack_id, cases, version=candidate_version, llm=llm, judge_llm=judge_llm
    )
    return EvalComparison(pack_id=pack_id, baseline=baseline, candidate=candidate)
