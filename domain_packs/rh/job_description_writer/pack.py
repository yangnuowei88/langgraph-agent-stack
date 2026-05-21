"""domain_packs/rh/job_description_writer/pack.py — Inclusive job description writer."""

from __future__ import annotations

import json

from pydantic import BaseModel

from domain_packs.common.prompt_safety import format_vertical_prompt
from domain_packs.common.structured_llm import StructuredLLMPack
from domain_packs.rh.job_description_writer.schemas import (
    JobDescriptionWriterInput,
    JobDescriptionWriterOutput,
)


class JobDescriptionWriterPack(StructuredLLMPack):
    pack_id = "job_description_writer"
    name = "Job Description Writer"
    description = (
        "Drafts an inclusive job description, competency matrix, screening rubric, "
        "and bias-check notes from hiring-manager inputs."
    )
    input_schema = JobDescriptionWriterInput
    output_schema = JobDescriptionWriterOutput
    primary_field = "role_title"

    @classmethod
    def build_prompt(cls, inp: BaseModel, *, reference_text: str = "") -> str:
        data = cls._coerce_input(inp).model_dump()
        schema = json.dumps(JobDescriptionWriterOutput.model_json_schema(), indent=2)
        must = ", ".join(data.get("must_haves") or []) or "not specified"
        return format_vertical_prompt(
            task_instructions=(
                "You are an HR business partner writing an inclusive job description."
            ),
            fields={
                "Role": str(data["role_title"]),
                "Seniority": str(data.get("seniority", "mid")),
                "Team context": str(data.get("team_context") or "not provided"),
                "Must-haves": must,
                "Culture notes": str(data.get("culture_notes") or "none"),
            },
            output_schema_json=schema,
            reference_text=reference_text,
            closing_instructions=(
                "jd_markdown should use inclusive language. "
                "Avoid gendered or age-biased terms."
            ),
        )
