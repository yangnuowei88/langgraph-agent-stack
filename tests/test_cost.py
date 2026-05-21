"""
tests/test_cost.py — Unit tests for core/cost.py.

Covers:
- _compute_cost() for known and unknown models
- CostTracker.on_llm_end() token extraction, cost accumulation, budget enforcement
- load_cost_table() with and without an override file
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from core.cost import (
    BudgetExceededError,
    CostTracker,
    UnknownModelPricingError,
    _compute_cost,
    compute_call_cost,
    estimate_worst_case_call_cost,
    load_cost_table,
    resolve_model_pricing,
)

# ---------------------------------------------------------------------------
# Autouse fixture — reset module-level cache between every test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_cost_table():
    """Reset the effective cost table cache between tests."""
    from core.cost import _reset_effective_table

    yield
    _reset_effective_table()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_llm_result(model: str, input_tokens: int, output_tokens: int) -> LLMResult:
    """Build a realistic LLMResult carrying usage_metadata on the AIMessage."""
    msg = AIMessage(content="test")
    msg.usage_metadata = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }
    gen = ChatGeneration(message=msg)
    return LLMResult(
        generations=[[gen]],
        llm_output={"model_name": model},
    )


def _make_llm_result_openai_style(
    model: str, prompt_tokens: int, completion_tokens: int
) -> LLMResult:
    """Build an LLMResult that uses OpenAI-style token_usage (no usage_metadata)."""
    gen = ChatGeneration(message=AIMessage(content="test"))
    return LLMResult(
        generations=[[gen]],
        llm_output={
            "model_name": model,
            "token_usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        },
    )


def _make_llm_result_no_usage(model: str) -> LLMResult:
    """Build an LLMResult with no usage information at all."""
    gen = ChatGeneration(message=AIMessage(content="test"))
    return LLMResult(
        generations=[[gen]],
        llm_output={"model_name": model},
    )


# ---------------------------------------------------------------------------
# Test 1 — _compute_cost: known model
# ---------------------------------------------------------------------------


def test_compute_cost_known_model() -> None:
    """_compute_cost returns the correct USD value for a known model.

    claude-3-5-sonnet-20241022 is priced at $0.003 / 1k input, $0.015 / 1k output.
    1000 input + 500 output → $0.003 + $0.0075 = $0.0105
    """
    cost = _compute_cost("claude-3-5-sonnet-20241022", 1000, 500)
    assert abs(cost - 0.0105) < 1e-9


# ---------------------------------------------------------------------------
# Test 2 — _compute_cost: unknown model returns 0.0
# ---------------------------------------------------------------------------


def test_compute_cost_unknown_model_returns_zero_in_development() -> None:
    """Unknown models cost $0 in development with a warning — never raises."""
    cost = _compute_cost("totally-unknown-model-xyz", 1000, 1000)
    assert cost == 0.0


def test_compute_cost_unknown_model_raises_in_production(monkeypatch) -> None:
    """Production must fail fast on unknown models so budget caps stay meaningful."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    from core.config import get_settings

    get_settings.cache_clear()
    try:
        with pytest.raises(UnknownModelPricingError, match="totally-unknown-model"):
            compute_call_cost("totally-unknown-model-xyz", 100, 100, strict=True)
    finally:
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        get_settings.cache_clear()


def test_resolve_model_pricing_dated_claude_sonnet_4_variant() -> None:
    """Dated Claude Sonnet 4 IDs resolve via prefix alias."""
    pricing = resolve_model_pricing("claude-sonnet-4-7-20260301")
    assert pricing is not None
    assert pricing.input_per_1k == pytest.approx(0.003)


def test_compute_call_cost_applies_cache_read_discount() -> None:
    """Cache hits bill at ~10% of uncached input rate by default."""
    full = compute_call_cost("claude-3-5-sonnet-20241022", 1000, 0)
    cached = compute_call_cost(
        "claude-3-5-sonnet-20241022",
        1000,
        0,
        cache_read_tokens=1000,
    )
    assert cached == pytest.approx(full * 0.1)


def test_compute_call_cost_applies_batch_multiplier() -> None:
    """Batch API calls use the model's batch multiplier (default 50%)."""
    regular = compute_call_cost("gpt-4o", 1000, 1000)
    batch = compute_call_cost("gpt-4o", 1000, 1000, batch=True)
    assert batch == pytest.approx(regular * 0.5)


def test_pre_call_budget_blocks_before_llm_end() -> None:
    """on_chat_model_start rejects calls whose worst-case estimate exceeds budget."""
    tracker = CostTracker(budget_usd=0.0001)
    serialized = {"kwargs": {"model": "gpt-4o", "max_tokens": 4096}}
    messages = [[type("M", (), {"content": "x" * 8000})()]]
    with pytest.raises(BudgetExceededError):
        tracker.on_chat_model_start(
            serialized,
            messages,
            invocation_params={"model": "gpt-4o", "max_tokens": 4096},
        )


def test_estimate_worst_case_call_cost_uses_max_output() -> None:
    est = estimate_worst_case_call_cost("gpt-4o-mini", 1000, 2000)
    assert est == pytest.approx((1000 / 1000) * 0.00015 + (2000 / 1000) * 0.0006)


# ---------------------------------------------------------------------------
# Test 3 — CostTracker raises BudgetExceededError when over budget
# ---------------------------------------------------------------------------


def test_budget_exceeded_raises() -> None:
    """CostTracker raises BudgetExceededError when spend crosses budget_usd.

    claude-3-5-sonnet-20241022: $0.003/1k input, $0.015/1k output.
    100k input + 100k output → $0.30 + $1.50 = $1.80 >> budget of $0.001.
    """
    tracker = CostTracker(budget_usd=0.001)
    result = _make_llm_result("claude-3-5-sonnet-20241022", 100_000, 100_000)

    with pytest.raises(BudgetExceededError) as exc_info:
        tracker.on_llm_end(result)

    assert exc_info.value.budget == pytest.approx(0.001)
    assert exc_info.value.actual > 0.001
    # Ensure total_cost_usd was updated before the exception
    assert tracker.total_cost_usd > 0.001


# ---------------------------------------------------------------------------
# Test 4 — CostTracker with no budget does NOT raise, total_cost_usd > 0
# ---------------------------------------------------------------------------


def test_no_budget_no_exception() -> None:
    """CostTracker(budget_usd=None) accumulates cost without raising."""
    tracker = CostTracker(budget_usd=None)
    result = _make_llm_result("claude-3-5-sonnet-20241022", 1000, 500)

    tracker.on_llm_end(result)  # Must not raise

    expected = _compute_cost("claude-3-5-sonnet-20241022", 1000, 500)
    assert tracker.total_cost_usd == pytest.approx(expected)
    assert tracker.total_cost_usd > 0.0
    assert tracker.input_tokens == 1000
    assert tracker.output_tokens == 500


# ---------------------------------------------------------------------------
# Test 5 — Missing usage metadata → cost = 0.0, no exception
# ---------------------------------------------------------------------------


def test_missing_usage_metadata_returns_zero_cost() -> None:
    """on_llm_end with no usage data in the LLMResult does not raise and costs $0."""
    tracker = CostTracker(budget_usd=None)
    result = _make_llm_result_no_usage("claude-3-5-sonnet-20241022")

    tracker.on_llm_end(result)  # Must not raise

    assert tracker.total_cost_usd == 0.0
    assert tracker.input_tokens == 0
    assert tracker.output_tokens == 0


# ---------------------------------------------------------------------------
# Test 6 — Cost accumulates across multiple on_llm_end calls
# ---------------------------------------------------------------------------


def test_cost_accumulates_across_multiple_calls() -> None:
    """Calling on_llm_end twice sums costs correctly."""
    tracker = CostTracker(budget_usd=None)

    result_a = _make_llm_result("claude-3-5-sonnet-20241022", 1000, 500)
    result_b = _make_llm_result("gpt-4o", 2000, 1000)

    tracker.on_llm_end(result_a)
    tracker.on_llm_end(result_b)

    expected = _compute_cost("claude-3-5-sonnet-20241022", 1000, 500) + _compute_cost(
        "gpt-4o", 2000, 1000
    )
    assert tracker.total_cost_usd == pytest.approx(expected)
    assert tracker.input_tokens == 3000
    assert tracker.output_tokens == 1500


# ---------------------------------------------------------------------------
# Test 7 — OpenAI-style token_usage fallback
# ---------------------------------------------------------------------------


def test_openai_style_token_usage_extracted() -> None:
    """CostTracker correctly reads prompt_tokens/completion_tokens from llm_output."""
    tracker = CostTracker(budget_usd=None)
    result = _make_llm_result_openai_style("gpt-4o-mini", 500, 250)

    tracker.on_llm_end(result)

    expected = _compute_cost("gpt-4o-mini", 500, 250)
    assert tracker.total_cost_usd == pytest.approx(expected)
    assert tracker.input_tokens == 500
    assert tracker.output_tokens == 250


# ---------------------------------------------------------------------------
# Test 8 — load_cost_table merges external JSON override
# ---------------------------------------------------------------------------


def test_load_cost_table_merges_override(tmp_path: Path) -> None:
    """load_cost_table merges an external JSON file and gives it precedence."""
    override_file = tmp_path / "costs.json"
    override_file.write_text(
        json.dumps(
            {
                "gpt-4o": [0.009, 0.030],
                "my-custom-model": [0.001, 0.002],
            }
        ),
        encoding="utf-8",
    )

    table = load_cost_table(override_file)

    assert table["gpt-4o"].input_per_1k == pytest.approx(0.009)
    assert table["gpt-4o"].output_per_1k == pytest.approx(0.030)
    assert table["my-custom-model"].input_per_1k == pytest.approx(0.001)
    assert "claude-3-5-sonnet-20241022" in table


def test_load_cost_table_none_path_returns_builtin() -> None:
    """load_cost_table(None) returns a copy of COST_PER_1K unchanged."""
    from core.cost import COST_PER_1K

    table = load_cost_table(None)

    assert table == COST_PER_1K
    assert table is not COST_PER_1K


# ---------------------------------------------------------------------------
# Test 10 — BudgetExceededError message format
# ---------------------------------------------------------------------------


def test_budget_exceeded_error_message_format() -> None:
    """BudgetExceededError carries correctly formatted budget and actual fields."""
    err = BudgetExceededError(budget=0.0050, actual=0.0123)

    assert err.budget == pytest.approx(0.005)
    assert err.actual == pytest.approx(0.0123)
    assert "0.0050" in str(err)
    assert "0.0123" in str(err)


# ---------------------------------------------------------------------------
# Test 11 — model_id normalisation (case-insensitive, whitespace stripped)
# ---------------------------------------------------------------------------


def test_compute_cost_normalises_model_id() -> None:
    """_compute_cost normalises model IDs to lowercase with stripped whitespace."""
    cost_lower = _compute_cost("claude-3-5-sonnet-20241022", 1000, 0)
    cost_upper = _compute_cost("  Claude-3-5-Sonnet-20241022  ", 1000, 0)

    assert cost_lower == pytest.approx(cost_upper)
    assert cost_lower > 0.0


# ---------------------------------------------------------------------------
# Test 12 — raise_error=True ensures BudgetExceededError propagates
# ---------------------------------------------------------------------------


def test_budget_exceeded_propagates_through_langchain_callback_pipeline() -> None:
    """Verify BudgetExceededError is not swallowed by LangChain's handle_event.

    LangChain wraps callbacks in a try/except and only re-raises when
    handler.raise_error is True.  Without this flag set the budget guard
    silently logs a WARNING and execution continues.
    """
    tracker = CostTracker(budget_usd=0.000001)
    result = _make_llm_result("gpt-4o", input_tokens=100, output_tokens=100)

    # Direct call must still raise — confirms the flag does not suppress raises
    with pytest.raises(BudgetExceededError):
        tracker.on_llm_end(result)

    # Verify the flag itself is set on a fresh instance
    fresh_tracker = CostTracker(budget_usd=1.0)
    assert fresh_tracker.raise_error is True


# ---------------------------------------------------------------------------
# Test 13 — BudgetExceededError message is in English
# ---------------------------------------------------------------------------


def test_budget_exceeded_error_message_is_english() -> None:
    """BudgetExceededError message must be in English (no French text)."""
    err = BudgetExceededError(budget=0.005, actual=0.010)

    msg = str(err)
    assert "exceeded" in msg.lower()
    assert "budget" in msg.lower() or "ceiling" in msg.lower()
    # Ensure no French words crept in
    assert "dépassé" not in msg
    assert "actuel" not in msg


# ---------------------------------------------------------------------------
# Test 14 — Anthropic response_metadata model ID fallback
# ---------------------------------------------------------------------------


def test_cache_read_tokens_reduce_cost_on_llm_end() -> None:
    """on_llm_end applies cache_read_input_tokens when providers report them."""
    msg = AIMessage(content="test")
    msg.usage_metadata = {
        "input_tokens": 1000,
        "output_tokens": 0,
        "cache_read_input_tokens": 1000,
    }
    gen = ChatGeneration(message=msg)
    result = LLMResult(
        generations=[[gen]],
        llm_output={"model_name": "claude-3-5-sonnet-20241022"},
    )
    tracker = CostTracker(budget_usd=None)
    tracker.on_llm_end(result)
    full = compute_call_cost("claude-3-5-sonnet-20241022", 1000, 0)
    assert tracker.total_cost_usd == pytest.approx(full * 0.1)


def test_anthropic_response_metadata_model_id_extracted() -> None:
    """CostTracker resolves model ID from response_metadata when llm_output omits it.

    Anthropic sometimes places the model ID in
    generation.message.response_metadata["model_id"] rather than
    llm_output["model_name"].
    """
    msg = AIMessage(content="test")
    msg.usage_metadata = {
        "input_tokens": 500,
        "output_tokens": 250,
        "total_tokens": 750,
    }
    msg.response_metadata = {"model_id": "claude-3-5-sonnet-20241022"}

    gen = ChatGeneration(message=msg)
    result = LLMResult(
        generations=[[gen]],
        llm_output={},
    )

    tracker = CostTracker(budget_usd=None)
    tracker.on_llm_end(result)

    expected = _compute_cost("claude-3-5-sonnet-20241022", 500, 250)
    assert tracker.total_cost_usd == pytest.approx(expected)
    assert tracker.total_cost_usd > 0.0
