"""domain_packs/contract_reviewer/pack.py — Contract review and risk flagging pack."""

from __future__ import annotations

import json

from pydantic import BaseModel

from domain_packs.common.prompt_safety import format_vertical_prompt
from domain_packs.common.structured_llm import StructuredLLMPack
from domain_packs.legal.contract_reviewer.schemas import (
    ContractReviewerInput,
    ContractReviewerOutput,
)


class ContractReviewerPack(StructuredLLMPack):
    pack_id = "contract_reviewer"
    name = "Contract Reviewer"
    description = (
        "Reviews a contract against standard playbook expectations: "
        "flags risky clauses, deviations, and recommended actions."
    )
    input_schema = ContractReviewerInput
    output_schema = ContractReviewerOutput
    primary_field = "query"

    @classmethod
    def build_prompt(cls, inp: BaseModel, *, reference_text: str = "") -> str:
        data = cls._coerce_input(inp).model_dump()
        contract = str(data.get("contract_text") or reference_text)
        schema = json.dumps(ContractReviewerOutput.model_json_schema(), indent=2)
        return format_vertical_prompt(
            task_instructions="You are a commercial legal reviewer. Analyse the contract.",
            fields={
                "Label": str(data["query"]),
                "Contract type": str(data.get("contract_type", "msa")),
                "Jurisdiction": str(data.get("jurisdiction") or "unspecified"),
                "Contract text": contract or "(no text provided)",
            },
            output_schema_json=schema,
            closing_instructions=(
                "Set query to the label. risk_score: 0=low risk, 1=critical risk."
            ),
        )
