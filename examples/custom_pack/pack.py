"""
Pack tutoriel autonome — démontre le contrat BaseDomainPack sans LLM.

Ce fichier est volontairement minimal : pas de LangGraph, pas d'appel API.
Pour un pack vertical piloté par un LLM structuré, voir StructuredLLMPack
dans domain_packs/common/structured_llm.py.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import ClassVar

from pydantic import BaseModel

from examples.custom_pack.schemas import EchoInput, EchoOutput
from pack_kernel.base_pack import BaseDomainPack, pack_stream_event


class EchoPack(BaseDomainPack):
    """Exemple pédagogique : normalise le texte et renvoie un écho en majuscules."""

    pack_id: ClassVar[str] = "echo_tutorial"
    name: ClassVar[str] = "Echo Tutorial Pack"
    description: ClassVar[str] = (
        "Tutorial pack that uppercases input and counts words (no LLM)."
    )
    version: ClassVar[str] = "1.0"
    input_schema: ClassVar[type[BaseModel]] = EchoInput
    output_schema: ClassVar[type[BaseModel]] = EchoOutput
    primary_field: ClassVar[str] = "text"

    def run_from_input(self, body: BaseModel) -> EchoOutput:
        """Exécution typée — même contrat que les routes POST /packs/{id}/run."""
        inp = (
            body
            if isinstance(body, EchoInput)
            else EchoInput.model_validate(body)
        )
        words = inp.text.split()
        echoed = inp.text.strip().upper()
        return EchoOutput(
            original=inp.text,
            echoed=echoed,
            word_count=len(words),
        )

    def run(self, query: str) -> EchoOutput:
        """Interface legacy : une seule chaîne mappée sur ``primary_field``."""
        if not query or not query.strip():
            raise ValueError("EchoPack.run() requires non-empty text.")
        return self.run_from_input(EchoInput(text=query.strip()))

    async def arun(self, query: str) -> EchoOutput:
        return await asyncio.to_thread(self.run, query)

    async def _iter_stream_events(self, query: str) -> AsyncIterator[dict[str, object]]:
        yield pack_stream_event("phase_started", phase="echo")
        result = await self.arun(query)
        yield pack_stream_event("phase_completed", phase="echo")
        yield pack_stream_event("pipeline_completed", result=result)
