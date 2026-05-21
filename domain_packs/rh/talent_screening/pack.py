"""domain_packs/rh/talent_screening/pack.py — CV vs job description screening pack."""

from __future__ import annotations

import json

from pydantic import BaseModel

from domain_packs.common.prompt_safety import format_vertical_prompt
from domain_packs.common.structured_llm import StructuredLLMPack
from domain_packs.rh.talent_screening.schemas import (
    TalentScreeningInput,
    TalentScreeningOutput,
)


class TalentScreeningPack(StructuredLLMPack):
    pack_id = "talent_screening"
    name = "Talent Screening"
    description = (
        "Screens a candidate resume against a job description: fit score, "
        "skill gaps, interview questions, and red flags."
    )
    input_schema = TalentScreeningInput
    output_schema = TalentScreeningOutput

    @classmethod
    def primary_text(cls, inp: BaseModel) -> str:
        data = cls._coerce_input(inp).model_dump()
        return str(data["job_description"])[:500]

    @classmethod
    def build_prompt(cls, inp: BaseModel, *, reference_text: str = "") -> str:
        data = cls._coerce_input(inp).model_dump()
        schema = json.dumps(TalentScreeningOutput.model_json_schema(), indent=2)
        must = ", ".join(data.get("must_have_skills") or []) or "not specified"
        nice = ", ".join(data.get("nice_to_have_skills") or []) or "not specified"
        return format_vertical_prompt(
            task_instructions="You are an expert technical recruiter. Screen this candidate.",
            fields={
                "Must-have skills": must,
                "Nice-to-have skills": nice,
                "Job description": str(data["job_description"]),
                "Resume": str(data["resume_text"]),
            },
            output_schema_json=schema,
            reference_text=reference_text,
            closing_instructions=(
                "fit_score: 0=poor fit, 1=excellent fit. Be objective and cite evidence."
            ),
        )
