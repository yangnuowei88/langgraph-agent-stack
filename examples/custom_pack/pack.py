"""
examples/custom_pack/pack.py — Minimal custom domain pack demonstrating the BaseDomainPack contract.

Register manually before use:
    from platform.registry import PackRegistry
    from examples.custom_pack.pack import SummariserPack
    PackRegistry.register(SummariserPack)
"""

import uuid
from collections.abc import AsyncGenerator
from typing import Any, ClassVar

from platform.base_pack import BaseDomainPack

from examples.custom_pack.schemas import SummaryInput, SummaryOutput


class SummariserPack(BaseDomainPack):
    pack_id = "summariser"
    name = "Text Summariser"
    description = "Summarises text into a configurable number of bullet points."

    input_schema: ClassVar[type[SummaryInput]] = SummaryInput
    output_schema: ClassVar[type[SummaryOutput]] = SummaryOutput

    def __init__(
        self,
        run_id: str | None = None,
        llm: Any | None = None,
        checkpointer: Any | None = None,
        budget_usd: float | None = None,
    ) -> None:
        super().__init__(run_id=run_id, llm=llm, checkpointer=checkpointer, budget_usd=budget_usd)
        self.run_id = run_id or str(uuid.uuid4())

    def _build_prompt(self, inp: SummaryInput) -> str:
        return (
            f"Summarise the following text into exactly {inp.bullet_count} concise bullet points.\n"
            f"Return only the bullet points, one per line, each starting with '- '.\n\n"
            f"Text:\n{inp.text}"
        )

    def _parse_bullets(self, raw: str, expected: int) -> list[str]:
        lines = [line.strip() for line in raw.strip().splitlines() if line.strip()]
        bullets = [line.lstrip("- ").strip() for line in lines if line.startswith("-")]
        # Fall back to all non-empty lines if the LLM did not use bullet syntax
        if not bullets:
            bullets = lines
        return bullets[:expected]

    def run(self, query: str) -> SummaryOutput:
        inp = SummaryInput(text=query)
        prompt = self._build_prompt(inp)
        response = self._llm.invoke(prompt)
        # LangChain chat models return an AIMessage; plain strings are also acceptable
        raw = response.content if hasattr(response, "content") else str(response)
        bullets = self._parse_bullets(raw, inp.bullet_count)
        return SummaryOutput(original_length=len(query), bullets=bullets)

    async def arun(self, query: str) -> SummaryOutput:
        inp = SummaryInput(text=query)
        prompt = self._build_prompt(inp)
        response = await self._llm.ainvoke(prompt)
        raw = response.content if hasattr(response, "content") else str(response)
        bullets = self._parse_bullets(raw, inp.bullet_count)
        return SummaryOutput(original_length=len(query), bullets=bullets)

    async def stream_events(self, query: str) -> AsyncGenerator[dict[str, Any], None]:
        result = await self.arun(query)
        yield {"event": "pipeline_completed", "data": result.model_dump()}
