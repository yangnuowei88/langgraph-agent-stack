"""
platform/base_pack.py — Abstract contract for all domain packs.

Every domain pack MUST inherit from BaseDomainPack and implement the three
abstract methods (run, arun, stream_events).  The class-level attributes
pack_id, name, and description are required metadata used by PackRegistry.
"""

from __future__ import annotations

import abc
from collections.abc import AsyncGenerator
from typing import Any, ClassVar

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Default schemas — used when a concrete pack does not declare its own
# ---------------------------------------------------------------------------


class _DefaultPackInput(BaseModel):
    query: str


class _DefaultPackOutput(BaseModel):
    result: dict[str, Any]


class BaseDomainPack(abc.ABC):
    """
    Abstract base class for all domain packs.

    A domain pack encapsulates a complete multi-agent pipeline as a deployable
    unit.  It owns its LangGraph graph, its agents, and its output schema.

    Class-level attributes (MUST be set on every concrete subclass):
        pack_id:     Unique stable identifier used by PackRegistry (e.g. "research_analysis").
        name:        Human-readable display name.
        description: One-sentence description of what this pack does.

    Constructor args (same contract as the former MultiAgentGraph):
        run_id:      Optional stable identifier for the pipeline run.
        llm:         Optional pre-built LangChain chat model (injected by API at startup).
        checkpointer: Optional pre-built LangGraph checkpointer.
        budget_usd:  Per-agent USD cost ceiling for LLM calls.
                     Each agent in the pipeline enforces this limit independently —
                     the total pipeline cost may reach ``budget_usd * number_of_agents``.
                     Set to ``None`` to disable budget enforcement (default).
    """

    pack_id: ClassVar[str]
    name: ClassVar[str]
    description: ClassVar[str]
    version: ClassVar[str] = "1.0"
    input_schema: ClassVar[type[BaseModel]] = _DefaultPackInput
    output_schema: ClassVar[type[BaseModel]] = _DefaultPackOutput

    def __init__(
        self,
        run_id: str | None = None,
        llm: Any | None = None,
        checkpointer: Any | None = None,
        budget_usd: float | None = None,
    ) -> None:
        if budget_usd is not None and budget_usd < 0:
            raise ValueError(f"budget_usd must be non-negative, got {budget_usd!r}")
        self.run_id = run_id
        self._llm = llm
        self._checkpointer = checkpointer
        self._budget_usd = budget_usd

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def run(self, query: str) -> Any:
        """Execute the pack pipeline synchronously and return a structured result."""

    @abc.abstractmethod
    async def arun(self, query: str) -> Any:
        """Execute the pack pipeline asynchronously and return a structured result."""

    @abc.abstractmethod
    async def stream_events(self, query: str) -> AsyncGenerator[dict[str, Any], None]:
        """Stream pipeline execution events as dicts."""

    # ------------------------------------------------------------------
    # Cost tracking
    # ------------------------------------------------------------------

    @property
    def cost_usd(self) -> float:
        """Total USD spent on LLM calls during this run.

        Subclasses should override this to aggregate costs across all
        internal agents. Returns 0.0 by default.
        """
        return 0.0

    # ------------------------------------------------------------------
    # Optional lifecycle hooks
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Release any resources held by the pack (thread pools, connections)."""

    def __enter__(self) -> BaseDomainPack:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
