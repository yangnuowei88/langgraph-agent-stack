"""domain_packs/rh/hr_policy_qa/pack.py — HR handbook / policy Q&A pack."""

from __future__ import annotations

import json

from pydantic import BaseModel

from domain_packs.common.prompt_safety import format_vertical_prompt
from domain_packs.common.structured_llm import StructuredLLMPack
from domain_packs.rh.hr_policy_qa.schemas import HrPolicyQaInput, HrPolicyQaOutput


class HrPolicyQaPack(StructuredLLMPack):
    pack_id = "hr_policy_qa"
    name = "HR Policy Q&A"
    description = (
        "Answers employee HR policy questions with citations, confidence, "
        "and escalation guidance when sensitive."
    )
    input_schema = HrPolicyQaInput
    output_schema = HrPolicyQaOutput

    @classmethod
    def build_prompt(cls, inp: BaseModel, *, reference_text: str = "") -> str:
        data = cls._coerce_input(inp).model_dump()
        policy = str(data.get("document_text") or reference_text)
        schema = json.dumps(HrPolicyQaOutput.model_json_schema(), indent=2)
        return format_vertical_prompt(
            task_instructions=(
                "You are an HR policy assistant. Answer ONLY from the policy material."
            ),
            fields={
                "Employee context": str(data.get("employee_context") or "not provided"),
                "Question": str(data["question"]),
                "Policy material": policy
                or "(no policy document — answer with low confidence)",
            },
            output_schema_json=schema,
            closing_instructions=(
                "Set question from input. escalate_to_hr=true for legal/sensitive topics. "
                "disclaimer must state this is informational, not legal advice."
            ),
        )
