"""Tests for agents/llm_retry.py — transient LLM error classification."""

from __future__ import annotations

import httpx
import pytest

from agents.llm_retry import is_retryable_llm_error, retry_if_transient_llm_error


class _StatusOnlyError(Exception):
    """Minimal APIStatusError-like exception for tests."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


class TestIsRetryableLlmError:
    def test_connection_and_timeout_builtin(self) -> None:
        assert is_retryable_llm_error(TimeoutError("timed out"))
        assert is_retryable_llm_error(ConnectionError("refused"))

    def test_httpx_timeout(self) -> None:
        assert is_retryable_llm_error(httpx.ReadTimeout("read timed out"))

    def test_anthropic_rate_limit_type(self) -> None:
        anthropic = pytest.importorskip("anthropic")
        assert is_retryable_llm_error(
            anthropic.RateLimitError.__new__(anthropic.RateLimitError)
        )

    def test_openai_rate_limit_type(self) -> None:
        openai = pytest.importorskip("openai")
        assert is_retryable_llm_error(
            openai.RateLimitError.__new__(openai.RateLimitError)
        )

    def test_transient_http_status_without_rate_string(self) -> None:
        """503 must retry even when the message is not English and has no '429'."""
        assert is_retryable_llm_error(_StatusOnlyError(503))
        assert is_retryable_llm_error(_StatusOnlyError(504))

    def test_non_transient_http_status(self) -> None:
        assert not is_retryable_llm_error(_StatusOnlyError(400))
        assert not is_retryable_llm_error(_StatusOnlyError(401))

    def test_localized_message_without_keywords_not_retried(self) -> None:
        assert not is_retryable_llm_error(RuntimeError("Limite de débit dépassée"))

    def test_budget_excluded_from_retry_predicate(self) -> None:
        from core.cost import BudgetExceededError

        assert not retry_if_transient_llm_error(
            BudgetExceededError(budget=1.0, actual=2.0)
        )

    def test_sdk_rate_limit_retried_by_predicate(self) -> None:
        anthropic = pytest.importorskip("anthropic")
        assert retry_if_transient_llm_error(
            anthropic.RateLimitError.__new__(anthropic.RateLimitError)
        )
