"""domain_packs/executive_brief/pack.py — Executive summary brief pack."""

from __future__ import annotations

import json

from pydantic import BaseModel

from domain_packs.common.prompt_safety import format_vertical_prompt
from domain_packs.common.structured_llm import StructuredLLMPack
from domain_packs.executive_brief.schemas import (
    ExecutiveBriefInput,
    ExecutiveBriefOutput,
)


class ExecutiveBriefPack(StructuredLLMPack):
    pack_id = "executive_brief"
    name = "Executive Brief"
    description = (
        "Distils long content into executive bullets, a 'so what', "
        "recommended decisions, and risks for a target audience."
    )
    input_schema = ExecutiveBriefInput
    output_schema = ExecutiveBriefOutput
    primary_field = "text"

    @classmethod
    def build_prompt(cls, inp: BaseModel, *, reference_text: str = "") -> str:
        data = cls._coerce_input(inp).model_dump()
        content = str(data.get("text") or reference_text)
        bullet_count = int(data.get("bullet_count") or 5)
        schema = json.dumps(ExecutiveBriefOutput.model_json_schema(), indent=2)
        return format_vertical_prompt(
            task_instructions="You are a chief of staff preparing an executive brief.",
            fields={
                "Target audience": str(data.get("audience", "CEO")),
                "Number of bullets": str(bullet_count),
                "Source material": content,
            },
            output_schema_json=schema,
            closing_instructions=(
                f"Provide exactly {bullet_count} bullets. "
                "so_what must be one sharp paragraph."
            ),
        )
