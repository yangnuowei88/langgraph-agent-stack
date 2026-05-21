"""
tests/test_security.py — Unit tests for core/security.py.

Tests cover InputValidator, RateLimiter, sanitize_log_data, and
validate_api_key_format.  All tests are fully isolated and synchronous.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.security import (
    InputValidator,
    RateLimiter,
    rate_limit_client_key,
    resolve_client_ip,
    sanitize_log_data,
    validate_api_key_format,
    validate_outbound_url,
)

# ---------------------------------------------------------------------------
# InputValidator
# ---------------------------------------------------------------------------


class TestInputValidator:
    """Tests for InputValidator.validate()."""

    def setup_method(self) -> None:
        self.validator = InputValidator(max_length=2000)

    def test_input_validator_valid(self) -> None:
        """Normal queries must pass validation and be returned stripped."""
        query = "  What are the latest advancements in quantum computing?  "
        result = self.validator.validate(query)
        assert result == query.strip()

    def test_input_validator_valid_preserves_content(self) -> None:
        """Multi-word queries with punctuation must not be modified beyond stripping."""
        query = "Explain the CAP theorem. Why does it matter in 2026?"
        result = self.validator.validate(query)
        assert result == query

    def test_input_validator_allows_prompt_injection_research_phrasing(self) -> None:
        """Legitimate queries about prompt injection must not be blocked by regex."""
        query = (
            "Explain what 'ignore previous instructions' means in "
            "prompt injection research."
        )
        result = self.validator.validate(query)
        assert result == query

    def test_input_validator_allows_internal_url_in_query_text(self) -> None:
        """SSRF-style strings in LLM queries are not fetch targets — allow them."""
        query = "Compare http://localhost/admin vs public endpoints for SSRF demos."
        result = self.validator.validate(query)
        assert "localhost" in result

    def test_input_validator_rejects_null_byte(self) -> None:
        """Queries containing a null byte must be rejected."""
        with pytest.raises(ValueError, match="null bytes"):
            self.validator.validate("hello\x00world")

    def test_input_validator_max_length(self) -> None:
        """Queries at exactly max_length must pass; one character over must fail."""
        boundary_query = "a" * 2000
        result = self.validator.validate(boundary_query)
        assert result == boundary_query

    def test_input_validator_exceeds_max_length(self) -> None:
        """Queries exceeding max_length must raise ValueError."""
        over_limit = "a" * 2001
        with pytest.raises(ValueError, match="exceeds maximum length"):
            self.validator.validate(over_limit)

    def test_input_validator_non_string_raises(self) -> None:
        """Non-string input must raise ValueError."""
        with pytest.raises(ValueError):
            self.validator.validate(12345)  # type: ignore[arg-type]

    def test_input_validator_collapses_excessive_newlines(self) -> None:
        """Three or more consecutive newlines must be collapsed to two."""
        query = "line one\n\n\n\nline two"
        result = self.validator.validate(query)
        assert "\n\n\n" not in result
        assert "line one" in result
        assert "line two" in result


# ---------------------------------------------------------------------------
# validate_outbound_url (SSRF guard for httpx fetches)
# ---------------------------------------------------------------------------


class TestValidateOutboundUrl:
    """Tests for validate_outbound_url()."""

    def test_allows_public_https_url(self) -> None:
        assert (
            validate_outbound_url("https://api.example.com/search?q=test")
            == "https://api.example.com/search?q=test"
        )

    def test_blocks_localhost(self) -> None:
        with pytest.raises(ValueError, match="not allowed"):
            validate_outbound_url("http://localhost/admin")

    def test_blocks_metadata_ip(self) -> None:
        with pytest.raises(ValueError, match="not allowed"):
            validate_outbound_url("http://169.254.169.254/latest/meta-data/")

    def test_blocks_private_ip(self) -> None:
        with pytest.raises(ValueError, match="not allowed"):
            validate_outbound_url("http://10.0.0.5/internal")

    def test_blocks_non_http_scheme(self) -> None:
        with pytest.raises(ValueError, match="scheme"):
            validate_outbound_url("file:///etc/passwd")


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------


class TestRateLimiter:
    """Tests for RateLimiter.is_allowed()."""

    def test_rate_limiter_allows_under_limit(self) -> None:
        """Requests below max_requests must all be allowed."""
        limiter = RateLimiter(max_requests=5, window_seconds=60.0)
        for _ in range(5):
            assert limiter.is_allowed("192.168.1.1") is True

    def test_rate_limiter_blocks_at_limit(self) -> None:
        """The (max_requests + 1)-th request must be denied."""
        limiter = RateLimiter(max_requests=3, window_seconds=60.0)
        for _ in range(3):
            limiter.is_allowed("10.0.0.1")

        assert limiter.is_allowed("10.0.0.1") is False

    def test_rate_limiter_different_ips_independent(self) -> None:
        """Rate-limit buckets must be per-IP; one IP exhausted must not affect others."""
        limiter = RateLimiter(max_requests=2, window_seconds=60.0)

        limiter.is_allowed("1.1.1.1")
        limiter.is_allowed("1.1.1.1")
        assert limiter.is_allowed("1.1.1.1") is False

        # A different IP must still be allowed
        assert limiter.is_allowed("2.2.2.2") is True

    def test_rate_limiter_resets_after_window(self) -> None:
        """
        After the sliding window expires, the client must be allowed again.

        Time is mocked so the test runs instantly.
        """
        limiter = RateLimiter(max_requests=2, window_seconds=10.0)
        ip = "172.16.0.1"

        # Exhaust the limit at t=0
        with patch("core.security.time.monotonic", return_value=0.0):
            limiter.is_allowed(ip)
            limiter.is_allowed(ip)
            assert limiter.is_allowed(ip) is False

        # Advance time beyond the window
        with patch("core.security.time.monotonic", return_value=11.0):
            assert limiter.is_allowed(ip) is True

    def test_rate_limiter_remaining_decrements(self) -> None:
        """remaining() must decrease with each allowed request."""
        limiter = RateLimiter(max_requests=5, window_seconds=60.0)
        ip = "10.10.10.10"

        assert limiter.remaining(ip) == 5
        limiter.is_allowed(ip)
        assert limiter.remaining(ip) == 4
        limiter.is_allowed(ip)
        assert limiter.remaining(ip) == 3

    def test_rate_limiter_invalid_max_requests(self) -> None:
        """max_requests < 1 must raise ValueError at construction."""
        with pytest.raises(ValueError):
            RateLimiter(max_requests=0, window_seconds=60.0)

    def test_rate_limiter_invalid_window(self) -> None:
        """window_seconds <= 0 must raise ValueError at construction."""
        with pytest.raises(ValueError):
            RateLimiter(max_requests=10, window_seconds=0.0)


# ---------------------------------------------------------------------------
# Proxy-aware client IP / rate-limit keys
# ---------------------------------------------------------------------------


class TestProxyAwareClientIp:
    """Tests for resolve_client_ip() and rate_limit_client_key()."""

    def test_xff_used_when_peer_is_trusted(self) -> None:
        headers = {"X-Forwarded-For": "203.0.0.1, 10.0.0.5"}
        assert (
            resolve_client_ip(
                "10.0.0.5",
                headers,
                trust_proxy=True,
                forwarded_allow_ips="10.0.0.0/8",
            )
            == "203.0.0.1"
        )

    def test_xff_ignored_when_peer_not_trusted(self) -> None:
        headers = {"X-Forwarded-For": "203.0.0.1"}
        assert (
            resolve_client_ip(
                "203.0.0.1",
                headers,
                trust_proxy=True,
                forwarded_allow_ips="10.0.0.0/8",
            )
            == "203.0.0.1"
        )

    def test_rate_limit_key_uses_token_when_auth_enabled(self) -> None:
        headers = {"Authorization": "Bearer tenant-secret-token"}
        key_a = rate_limit_client_key(
            "10.0.0.1",
            headers,
            trust_proxy=False,
            forwarded_allow_ips="",
            api_key="server-api-key",
        )
        key_b = rate_limit_client_key(
            "10.0.0.2",
            headers,
            trust_proxy=False,
            forwarded_allow_ips="",
            api_key="server-api-key",
        )
        assert key_a == key_b
        assert key_a.startswith("token:")

    def test_rate_limit_key_falls_back_to_ip_without_bearer(self) -> None:
        key = rate_limit_client_key(
            "10.0.0.9",
            {},
            trust_proxy=False,
            forwarded_allow_ips="",
            api_key="server-api-key",
        )
        assert key == "ip:10.0.0.9"


# ---------------------------------------------------------------------------
# sanitize_log_data
# ---------------------------------------------------------------------------


class TestSanitizeLogData:
    """Tests for sanitize_log_data()."""

    def test_sanitize_log_data_masks_api_key(self) -> None:
        """Keys containing 'key' must have their value replaced with ***REDACTED***."""
        data = {"api_key": "sk-ant-supersecret", "query": "hello"}
        result = sanitize_log_data(data)
        assert result["api_key"] == "***REDACTED***"
        assert result["query"] == "hello"

    def test_sanitize_log_data_masks_token(self) -> None:
        """Keys containing 'token' must be masked."""
        data = {"access_token": "Bearer abc123", "user": "alice"}
        result = sanitize_log_data(data)
        assert result["access_token"] == "***REDACTED***"
        assert result["user"] == "alice"

    def test_sanitize_log_data_masks_password(self) -> None:
        """Keys containing 'password', 'passwd', and 'pwd' must be masked."""
        data = {"password": "s3cr3t", "passwd": "s3cr3t", "pwd": "s3cr3t"}
        result = sanitize_log_data(data)
        for key in ("password", "passwd", "pwd"):
            assert result[key] == "***REDACTED***"

    def test_sanitize_log_data_masks_secret(self) -> None:
        """Keys containing 'secret' must be masked."""
        data = {"client_secret": "topsecret", "endpoint": "https://example.com"}
        result = sanitize_log_data(data)
        assert result["client_secret"] == "***REDACTED***"
        assert result["endpoint"] == "https://example.com"

    def test_sanitize_log_data_masks_credential(self) -> None:
        """Keys containing 'credential' must be masked."""
        data = {"db_credential": "admin:pass"}
        result = sanitize_log_data(data)
        assert result["db_credential"] == "***REDACTED***"

    def test_sanitize_log_data_nested_dict(self) -> None:
        """Nested dicts must be recursively sanitised."""
        data = {
            "request": {
                "headers": {"authorization": "Bearer token123"},
                "method": "POST",
            },
            "status": "ok",
        }
        result = sanitize_log_data(data)
        assert result["request"]["headers"]["authorization"] == "***REDACTED***"
        assert result["request"]["method"] == "POST"
        assert result["status"] == "ok"

    def test_sanitize_log_data_does_not_mutate_input(self) -> None:
        """The original dict must not be modified."""
        data = {"api_key": "original_value"}
        original_copy = dict(data)
        sanitize_log_data(data)
        assert data == original_copy

    def test_sanitize_log_data_non_sensitive_keys_preserved(self) -> None:
        """Non-sensitive keys must pass through unchanged."""
        data = {"query": "test", "run_id": "abc-123", "status": "ok"}
        result = sanitize_log_data(data)
        assert result == data

    def test_sanitize_list_of_dicts_with_sensitive_keys(self) -> None:
        """sanitize_log_data should recurse into dicts inside lists."""
        data = {
            "items": [
                {"name": "safe", "api_key": "secret123"},
                {"name": "also safe", "password": "hunter2"},
            ]
        }
        result = sanitize_log_data(data)
        assert result["items"][0]["api_key"] == "***REDACTED***"
        assert result["items"][1]["password"] == "***REDACTED***"
        assert result["items"][0]["name"] == "safe"


# ---------------------------------------------------------------------------
# validate_api_key_format
# ---------------------------------------------------------------------------


class TestValidateApiKeyFormat:
    """Tests for validate_api_key_format()."""

    # --- Anthropic (default provider) ---

    def test_valid_key_format(self) -> None:
        """A well-formed Anthropic key must return True."""
        assert validate_api_key_format("sk-ant-test123456789012345") is True

    def test_valid_key_with_hyphens_and_underscores(self) -> None:
        """Keys with hyphens and underscores after the prefix must be accepted."""
        assert validate_api_key_format("sk-ant-api03-abc_DEF-123456") is True

    def test_invalid_key_wrong_prefix(self) -> None:
        """Keys not starting with 'sk-ant-' must return False for Anthropic."""
        assert (
            validate_api_key_format("sk-wrong-1234567890", provider="anthropic")
            is False
        )

    def test_invalid_key_too_short_suffix(self) -> None:
        """Keys with fewer than 10 characters after 'sk-ant-' must return False."""
        assert validate_api_key_format("sk-ant-short") is False

    def test_invalid_key_empty_string(self) -> None:
        """An empty string must return False."""
        assert validate_api_key_format("") is False

    def test_invalid_key_non_string(self) -> None:
        """Non-string input must return False."""
        assert validate_api_key_format(None) is False  # type: ignore[arg-type]

    def test_invalid_key_with_spaces(self) -> None:
        """Keys containing spaces must return False."""
        assert validate_api_key_format("sk-ant-abc 1234567890") is False

    def test_valid_key_minimum_length_suffix(self) -> None:
        """A key with exactly 10 characters after 'sk-ant-' must return True."""
        assert validate_api_key_format("sk-ant-1234567890") is True

    # --- OpenAI ---

    def test_openai_valid_key(self) -> None:
        """A well-formed OpenAI key must return True."""
        assert validate_api_key_format("sk-" + "a" * 48, provider="openai") is True

    def test_openai_invalid_key_wrong_prefix(self) -> None:
        """Keys without 'sk-' prefix must return False for OpenAI."""
        assert validate_api_key_format("pk-" + "a" * 48, provider="openai") is False

    def test_openai_invalid_key_too_short(self) -> None:
        """OpenAI keys shorter than 20 chars after prefix must return False."""
        assert validate_api_key_format("sk-short", provider="openai") is False

    # --- Azure ---

    def test_azure_valid_key(self) -> None:
        """A 32-character hex string must return True for Azure."""
        assert validate_api_key_format("a" * 32, provider="azure") is True

    def test_azure_invalid_key_wrong_format(self) -> None:
        """Non-hex Azure keys must return False."""
        assert (
            validate_api_key_format("not-a-hex-key-at-all!!", provider="azure") is False
        )

    # --- Generic fallback ---

    def test_generic_provider_valid_key(self) -> None:
        """Unknown providers use a generic 8+ char alphanumeric check."""
        assert validate_api_key_format("abcdefgh12345", provider="google") is True

    def test_generic_provider_key_too_short(self) -> None:
        """Keys shorter than 8 chars must return False for unknown providers."""
        assert validate_api_key_format("short", provider="google") is False


# ---------------------------------------------------------------------------
# RateLimiter eviction
# ---------------------------------------------------------------------------


class TestRateLimiterEviction:
    """Tests for stale-bucket eviction in RateLimiter."""

    def test_stale_buckets_are_evicted(self) -> None:
        """After the window expires, stale IP buckets should be cleaned up."""
        import core.security

        limiter = RateLimiter(max_requests=5, window_seconds=10.0)
        for i in range(150):
            limiter.is_allowed(f"192.168.1.{i % 256}")

        original_monotonic = core.security.time.monotonic
        with patch.object(
            core.security.time,
            "monotonic",
            return_value=original_monotonic() + 20.0,
        ):
            for i in range(150):
                limiter.is_allowed(f"10.0.0.{i % 256}")

        assert limiter.is_allowed("192.168.1.1")


# ---------------------------------------------------------------------------
# create_rate_limiter factory
# ---------------------------------------------------------------------------


class TestCreateRateLimiter:
    """Tests for the rate limiter factory function."""

    def test_memory_backend_returns_rate_limiter(self) -> None:
        """Factory with backend='memory' returns an InMemoryRateLimiter."""
        from core.security import InMemoryRateLimiter, create_rate_limiter

        limiter = create_rate_limiter(backend="memory")
        assert isinstance(limiter, InMemoryRateLimiter)

    def test_redis_backend_without_url_falls_back(self) -> None:
        """Factory with backend='redis' but no URL falls back to in-memory."""
        from core.security import InMemoryRateLimiter, create_rate_limiter

        limiter = create_rate_limiter(backend="redis", redis_url="")
        assert isinstance(limiter, InMemoryRateLimiter)

    def test_redis_backend_with_url_creates_redis_limiter(self) -> None:
        """Factory with backend='redis' and a URL creates RedisRateLimiter."""
        from core.security import RedisRateLimiter, create_rate_limiter

        mock_redis = MagicMock()
        mock_redis.register_script.return_value = MagicMock()

        try:
            import redis as redis_lib  # noqa: F811

            with patch.object(redis_lib.Redis, "from_url", return_value=mock_redis):
                limiter = create_rate_limiter(
                    backend="redis",
                    redis_url="redis://localhost:6379/0",
                )
                assert isinstance(limiter, RedisRateLimiter)
        except ImportError:
            pytest.skip("redis package not installed")

    def test_redis_rate_limiter_fails_open_on_error(self) -> None:
        """RedisRateLimiter.is_allowed() returns True when Redis is down."""
        from core.security import RedisRateLimiter

        mock_redis = MagicMock()
        mock_script = MagicMock(side_effect=ConnectionError("Redis down"))
        mock_redis.register_script.return_value = mock_script

        try:
            import redis as redis_lib  # noqa: F811

            with patch.object(redis_lib.Redis, "from_url", return_value=mock_redis):
                limiter = RedisRateLimiter(
                    redis_url="redis://localhost:6379/0",
                )
                assert limiter.is_allowed("192.168.1.1") is True
                mock_script.assert_called_once()
        except ImportError:
            pytest.skip("redis package not installed")
