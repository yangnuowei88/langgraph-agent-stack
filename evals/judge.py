"""evals/judge.py — Optional LLM-as-judge scoring for eval cases.

Never active by default: a case is judged only when the runner is given a
judge LLM AND the case declares a ``judge`` rubric. The judged content is
wrapped in untrusted-content delimiters and the verdict is validated against
a strict schema (same hardening pattern as the output-guard cross-check).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agents.base_agent import extract_text_content
from core.security import wrap_untrusted_content

logger = logging.getLogger(__name__)

_JUDGE_PROMPT = """You are an evaluation judge for AI pack outputs.

Score how well the OUTPUT satisfies the RUBRIC for the given INPUT.
Respond with ONLY a JSON object: {{"score": <float 0.0-1.0>, "reasoning": "<one sentence>"}}

RUBRIC:
{rubric}

{input_block}

{output_block}"""


class JudgeVerdict(BaseModel):
    """Strictly validated judge response."""

    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""


def judge_case(
    judge_llm: Any,
    *,
    rubric: str,
    case_input: dict[str, Any],
    output: dict[str, Any],
) -> JudgeVerdict:
    """Score one case output against its rubric with the judge LLM.

    Raises:
        ValueError: when the judge response is not valid JSON or violates
            the strict verdict schema.
    """
    prompt = _JUDGE_PROMPT.format(
        rubric=rubric,
        input_block=wrap_untrusted_content(
            "INPUT", json.dumps(case_input, default=str)[:4000]
        ),
        output_block=wrap_untrusted_content(
            "OUTPUT", json.dumps(output, default=str)[:8000]
        ),
    )
    response = judge_llm.invoke(prompt)
    text = extract_text_content(getattr(response, "content", response)).strip()
    try:
        return JudgeVerdict.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValidationError) as exc:
        logger.warning("Judge returned an invalid verdict", extra={"error": str(exc)})
        raise ValueError(f"Invalid judge verdict: {exc}") from exc
