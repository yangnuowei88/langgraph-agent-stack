"""Tests for core/observability.py — structured logging and OTel tracing."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest


class TestConfigureLogging:
    """Tests for ``configure_logging``."""

    def test_sets_root_logger_level(self) -> None:
        from core.observability import configure_logging

        configure_logging(level="WARNING")
        root = logging.getLogger()
        assert root.level == logging.WARNING

    def test_adds_handler_to_root_logger(self) -> None:
        from core.observability import configure_logging

        configure_logging(level="INFO")
        root = logging.getLogger()
        assert len(root.handlers) >= 1
        assert isinstance(root.handlers[-1], logging.StreamHandler)

    def test_fallback_formatter_when_json_logger_missing(self) -> None:
        from core.observability import configure_logging

        with patch.dict(
            "sys.modules", {"pythonjsonlogger": None, "pythonjsonlogger.json": None}
        ):
            configure_logging(level="DEBUG")
        root = logging.getLogger()
        handler = root.handlers[-1]
        assert isinstance(handler.formatter, logging.Formatter)


class TestInitTracing:
    """Tests for ``init_tracing``."""

    def test_noop_when_otel_not_available(self) -> None:
        from core.observability import init_tracing

        with patch("core.observability._OTEL_AVAILABLE", False):
            init_tracing()

    def test_noop_when_otel_disabled(self) -> None:
        from core.observability import init_tracing

        with (
            patch("core.observability._OTEL_AVAILABLE", True),
            patch.dict("os.environ", {"OTEL_ENABLED": "false"}),
        ):
            init_tracing()


class TestGetTracer:
    """Tests for ``get_tracer``."""

    def test_returns_noop_tracer_when_otel_unavailable(self) -> None:
        from core.observability import get_tracer

        with (
            patch("core.observability._tracer", None),
            patch("core.observability._OTEL_AVAILABLE", False),
        ):
            tracer = get_tracer()
            assert tracer is not None
            assert hasattr(tracer, "start_as_current_span")

    def test_returns_module_tracer_when_set(self) -> None:
        from core.observability import get_tracer

        sentinel = MagicMock()
        with patch("core.observability._tracer", sentinel):
            assert get_tracer() is sentinel


class TestSanitizingFilter:
    """Tests for ``SanitizingFilter``."""

    def test_redacts_sensitive_dict_extras(self) -> None:
        from core.observability import SanitizingFilter

        filt = SanitizingFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=None,
            exc_info=None,
        )
        record.extra_data = {"password": "s3cret", "user": "alice"}  # type: ignore[attr-defined]
        filt.filter(record)
        assert record.extra_data["password"] == "***REDACTED***"  # type: ignore[attr-defined]
        assert record.extra_data["user"] == "alice"  # type: ignore[attr-defined]

    def test_leaves_non_sensitive_extras_untouched(self) -> None:
        from core.observability import SanitizingFilter

        filt = SanitizingFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=None,
            exc_info=None,
        )
        record.run_id = "abc-123"  # type: ignore[attr-defined]
        filt.filter(record)
        assert record.run_id == "abc-123"  # type: ignore[attr-defined]

    def test_redacts_scalar_sensitive_extras(self) -> None:
        """Scalar extras with sensitive key names are redacted."""
        from core.observability import SanitizingFilter

        filt = SanitizingFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=None,
            exc_info=None,
        )
        record.api_key = "sk-live-abc123"  # type: ignore[attr-defined]
        record.token = "tok_secret"  # type: ignore[attr-defined]
        record.user = "alice"  # type: ignore[attr-defined]
        filt.filter(record)
        assert record.api_key == "***REDACTED***"  # type: ignore[attr-defined]
        assert record.token == "***REDACTED***"  # type: ignore[attr-defined]
        assert record.user == "alice"  # type: ignore[attr-defined]


class TestTraceSpan:
    """Tests for ``trace_span``."""

    def test_context_manager_works_without_otel(self) -> None:
        from core.observability import trace_span

        with (
            patch("core.observability._tracer", None),
            patch("core.observability._OTEL_AVAILABLE", False),
        ):
            with trace_span("test-span", attributes={"key": "value"}) as span:
                assert span is None

    def test_context_manager_propagates_exceptions(self) -> None:
        from core.observability import trace_span

        with (
            patch("core.observability._tracer", None),
            patch("core.observability._OTEL_AVAILABLE", False),
            pytest.raises(ValueError, match="boom"),
        ):
            with trace_span("failing-span"):
                raise ValueError("boom")


class TestMetricsPathLabel:
    """Tests for ``metrics_path_label`` — bounded Prometheus cardinality."""

    def test_returns_api_route_template(self) -> None:
        from fastapi.routing import APIRoute

        from core.observability import metrics_path_label

        route = APIRoute(
            path="/packs/{pack_id}/run", endpoint=lambda: None, methods=["POST"]
        )
        label = metrics_path_label({"route": route})
        assert label == "/packs/{pack_id}/run"

    def test_returns_unknown_when_route_missing(self) -> None:
        from core.observability import metrics_path_label

        assert metrics_path_label({}) == "unknown"

    def test_starlette_route_with_path_attribute(self) -> None:
        from starlette.routing import Route

        from core.observability import metrics_path_label

        route = Route("/sessions/{session_id}", endpoint=lambda: None)
        assert metrics_path_label({"route": route}) == "/sessions/{session_id}"


_prometheus_available = False
try:
    import prometheus_client  # noqa: F401

    _prometheus_available = True
except ImportError:
    pass


@pytest.mark.skipif(not _prometheus_available, reason="prometheus-client not installed")
class TestPrometheusHistogramBuckets:
    """HTTP/LLM histogram buckets cover long-running agent workloads."""

    def test_http_duration_buckets_include_stream_timeout_range(self) -> None:
        from core.observability import http_request_duration_seconds

        assert http_request_duration_seconds is not None
        bounds = list(http_request_duration_seconds._upper_bounds)
        assert bounds[-2] == 300.0
        assert 120.0 in bounds

    def test_llm_duration_buckets_include_long_calls(self) -> None:
        from core.observability import llm_request_duration_seconds

        assert llm_request_duration_seconds is not None
        bounds = list(llm_request_duration_seconds._upper_bounds)
        assert bounds[-2] == 300.0
        assert 120.0 in bounds
