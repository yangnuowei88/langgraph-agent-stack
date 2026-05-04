"""
platform/base_pack.py — Abstract contract for all domain packs.

Every domain pack MUST inherit from BaseDomainPack and implement the three
abstract methods (run, arun, stream_events).  The class-level attributes
pack_id, name, and description are required metadata used by PackRegistry.
"""

from __future__ import annotations

import abc
from collections.abc import AsyncGenerator
from typing import Any


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
    """

    pack_id: str
    name: str
    description: str

    def __init__(
        self,
        run_id: str | None = None,
        llm: Any | None = None,
        checkpointer: Any | None = None,
    ) -> None:
        self.run_id = run_id
        self._llm = llm
        self._checkpointer = checkpointer

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
    # Optional lifecycle hooks
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Release any resources held by the pack (thread pools, connections)."""

    def __enter__(self) -> BaseDomainPack:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
