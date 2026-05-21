"""
core/cost.py — LLM cost tracking and budget enforcement.

This module provides:

1. **Per-model pricing table** with a fallback to an external JSON override
   controlled by the ``LLM_COST_TABLE_PATH`` environment variable.

2. **_compute_cost()** — pure-function cost calculator that gracefully handles
   unknown model IDs (returns 0.0, never raises).

3. **BudgetExceededError** — raised when accumulated spend exceeds the
   configured budget ceiling.

4. **CostTracker** — a LangChain ``BaseCallbackHandler`` that hooks into
   ``on_llm_end`` to accumulate token counts and USD cost, and optionally
   increments a Prometheus counter.

5. **load_cost_table()** — merges the built-in pricing table with an optional
   external JSON override file.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

# ---------------------------------------------------------------------------
# Built-in pricing table
# (input_$/1k_tokens, output_$/1k_tokens)
# ---------------------------------------------------------------------------

COST_PER_1K: dict[str, tuple[float, float]] = {
    "claude-3-5-sonnet-20241022": (0.003, 0.015),
    "claude-opus-4-7": (0.015, 0.075),
    "gpt-4o": (0.005, 0.015),
    "gpt-4o-mini": (0.00015, 0.0006),
    "gemini-1.5-pro": (0.00125, 0.005),
}

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prometheus counter (optional — exact pattern from core/observability.py)
# ---------------------------------------------------------------------------

pack_run_cost_usd_total: Any | None
try:
    from prometheus_client import Counter

    pack_run_cost_usd_total = Counter(
        "pack_run_cost_usd_total",
        "Cumulative LLM cost in USD per model",
        ["model"],
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    pack_run_cost_usd_total = None
    _PROMETHEUS_AVAILABLE = False


# ---------------------------------------------------------------------------
# load_cost_table
# ---------------------------------------------------------------------------


def load_cost_table(path: Path | None = None) -> dict[str, tuple[float, float]]:
    """Return the effective pricing table, optionally merged with an external file.

    The external file (JSON) takes precedence over the built-in table for any
    model IDs it defines.  Model IDs not present in the external file fall back
    to the built-in values.

    Args:
        path: Path to an optional JSON override file.  When ``None`` or the
            file does not exist, the built-in ``COST_PER_1K`` table is returned
            unchanged.

    Returns:
        A dict mapping model ID (str) to ``(input_per_1k, output_per_1k)``
        tuples.

    Note:
        Expected JSON format::

            {"model-id": [input_per_1k, output_per_1k], ...}
    """
    if path is None or not path.exists():
        return dict(COST_PER_1K)

    try:
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        overrides: dict[str, tuple[float, float]] = {
            k: (float(v[0]), float(v[1])) for k, v in raw.items()
        }
        merged = dict(COST_PER_1K)
        merged.update(overrides)
        return merged
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            "Failed to load external cost table from %s: %s — using built-in table",
            path,
            exc,
        )
        return dict(COST_PER_1K)


# ---------------------------------------------------------------------------
# _compute_cost
# ---------------------------------------------------------------------------

_effective_table: dict[str, tuple[float, float]] | None = None


def _reset_effective_table() -> None:
    """Reset the cached effective cost table. For testing only."""
    global _effective_table
    _effective_table = None


def _get_effective_table() -> dict[str, tuple[float, float]]:
    """Return the cost table, lazily loading an override file if configured."""
    global _effective_table
    if _effective_table is not None:
        return _effective_table

    env_path = os.environ.get("LLM_COST_TABLE_PATH", "")
    override_path = Path(env_path) if env_path else None
    _effective_table = load_cost_table(override_path)
    return _effective_table


def _compute_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate the USD cost for a single LLM call.

    Args:
        model_id: The model identifier string (normalised to lowercase + stripped).
        input_tokens: Number of prompt tokens consumed.
        output_tokens: Number of completion tokens generated.

    Returns:
        USD cost as a float.  Returns ``0.0`` for unknown model IDs
        (logs a WARNING) without raising any exception.
    """
    normalised = model_id.lower().strip()
    table = _get_effective_table()

    if normalised not in table:
        if normalised:
            _log.warning(
                "Unknown model ID '%s' — cost will be reported as $0.00",
                normalised,
            )
        return 0.0

    input_rate, output_rate = table[normalised]
    cost = (input_tokens / 1_000.0) * input_rate + (
        output_tokens / 1_000.0
    ) * output_rate
    return cost


# ---------------------------------------------------------------------------
# BudgetExceededError
# ---------------------------------------------------------------------------


class BudgetExceededError(Exception):
    """Raised by CostTracker when accumulated spend exceeds the budget ceiling.

    Inherits directly from ``Exception`` — intentionally NOT part of the
    ``AgentError`` hierarchy so that ``core/cost.py`` has zero dependency on
    ``agents/``.
    """

    def __init__(self, budget: float, actual: float) -> None:
        super().__init__(
            f"Budget ceiling ${budget:.4f} exceeded (this run: ${actual:.4f})"
        )
        self.budget = budget
        self.actual = actual


# ---------------------------------------------------------------------------
# CostTracker
# ---------------------------------------------------------------------------


class CostTracker(BaseCallbackHandler):
    """LangChain callback handler that accumulates LLM token usage and cost.

    Attach this handler to any LangChain LLM or chain to automatically
    track per-call and cumulative costs.  Optionally enforces a hard USD
    budget ceiling.

    Args:
        budget_usd: Optional spending limit in USD.  When the accumulated
            ``total_cost_usd`` exceeds this value after any call,
            ``BudgetExceededError`` is raised.  Pass ``None`` to disable
            budget enforcement.

    Attributes:
        total_cost_usd: Cumulative spend in USD across all tracked calls.
        input_tokens: Total prompt tokens consumed.
        output_tokens: Total completion tokens generated.
    """

    def __init__(self, budget_usd: float | None = None) -> None:
        super().__init__()
        self.raise_error = (
            True  # required: LangChain re-raises only if raise_error=True
        )
        self.budget_usd: float | None = budget_usd
        self.total_cost_usd: float = 0.0
        self.input_tokens: int = 0
        self.output_tokens: int = 0

    # ------------------------------------------------------------------
    # Token extraction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_tokens_from_result(
        response: LLMResult,
    ) -> tuple[str, int, int]:
        """Extract model ID and token counts from an LLMResult.

        Tries three extraction strategies in priority order:

        1. ``generation.message.usage_metadata`` (langchain_core standard).
        2. ``response.llm_output["token_usage"]`` or ``["usage"]``
           (OpenAI-style compatibility).
        3. Silently returns zeros when no usage data is present.

        Returns:
            A ``(model_id, input_tokens, output_tokens)`` tuple.
        """
        model_id: str = ""
        input_tokens: int = 0
        output_tokens: int = 0

        # Resolve model ID from llm_output
        llm_output: dict[str, Any] = response.llm_output or {}
        model_id = llm_output.get("model_name", "") or llm_output.get("model", "") or ""

        # Resolve model ID from response_metadata (Anthropic places it here)
        if not model_id:
            for row in response.generations:
                for gen in row:
                    message = getattr(gen, "message", None)
                    if message is not None:
                        rm = getattr(message, "response_metadata", {}) or {}
                        model_id = rm.get("model_id", "") or rm.get("model", "") or ""
                        if model_id:
                            break
                if model_id:
                    break

        # Priority 1 — iterate over all generations looking for usage_metadata
        for row in response.generations:
            for gen in row:
                message = getattr(gen, "message", None)
                if message is None:
                    continue
                usage_meta: dict[str, Any] | None = getattr(
                    message, "usage_metadata", None
                )
                if usage_meta:
                    input_tokens = int(usage_meta.get("input_tokens", 0))
                    output_tokens = int(usage_meta.get("output_tokens", 0))
                    return model_id, input_tokens, output_tokens

        # Priority 2 — OpenAI-compatible llm_output keys
        token_usage: dict[str, Any] = llm_output.get(
            "token_usage", llm_output.get("usage", {})
        )
        if token_usage:
            input_tokens = int(
                token_usage.get("prompt_tokens", token_usage.get("input_tokens", 0))
            )
            output_tokens = int(
                token_usage.get(
                    "completion_tokens", token_usage.get("output_tokens", 0)
                )
            )

        # Priority 3 — silent fallback (zeros already set above)
        return model_id, input_tokens, output_tokens

    # ------------------------------------------------------------------
    # BaseCallbackHandler interface
    # ------------------------------------------------------------------

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Called by LangChain when an LLM call completes.

        Extracts token usage, computes cost, updates accumulators, increments
        the Prometheus counter (if available), and enforces the budget ceiling.

        Args:
            response: The completed LLM result containing generation data.
            **kwargs: Additional keyword arguments passed by LangChain.

        Raises:
            BudgetExceededError: When ``budget_usd`` is set and
                ``total_cost_usd`` would exceed it after this call.
        """
        model_id, call_input, call_output = self._extract_tokens_from_result(response)

        call_cost = _compute_cost(model_id, call_input, call_output)

        self.input_tokens += call_input
        self.output_tokens += call_output
        self.total_cost_usd += call_cost

        if _PROMETHEUS_AVAILABLE and pack_run_cost_usd_total is not None:
            pack_run_cost_usd_total.labels(model=model_id or "unknown").inc(call_cost)

        _log.debug(
            "LLM call cost",
            extra={
                "model": model_id,
                "input_tokens": call_input,
                "output_tokens": call_output,
                "call_cost_usd": call_cost,
                "total_cost_usd": self.total_cost_usd,
            },
        )

        if self.budget_usd is not None and self.total_cost_usd > self.budget_usd:
            raise BudgetExceededError(
                budget=self.budget_usd,
                actual=self.total_cost_usd,
            )
