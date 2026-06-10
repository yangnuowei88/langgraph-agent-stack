"""
tests/test_multi_tenant_auth.py — Multi-key (multi-tenant) Bearer authentication.

Covers:
- ``Settings.resolved_api_keys`` merging/dedup of API_KEY + API_KEYS.
- ``core.security.verify_bearer_token`` (any-key match).
- End-to-end auth: multiple keys accepted, unknown key rejected, legacy
  single API_KEY unchanged, zero-downtime rotation (old + new accepted).
- Rate-limit scoping: per-token buckets with 2+ keys, per-IP with one key.

All agent calls are mocked; no real LLM requests are made.
"""

from __future__ import annotations

import hashlib
import os
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from starlette.requests import Request

from agents.models import AnalysisReport
from core.config import Settings
from core.security import RateLimiter, verify_bearer_token
from tests.legacy_pack_override import override_legacy_pack_cls

# ---------------------------------------------------------------------------
# Unit: Settings.resolved_api_keys
# ---------------------------------------------------------------------------


def _settings(**kwargs: object) -> Settings:
    base: dict[str, object] = {
        "llm_provider": "anthropic",
        "anthropic_api_key": "sk-ant-test123456789012345",
    }
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


class TestResolvedApiKeys:
    def test_empty_when_nothing_configured(self) -> None:
        assert _settings(api_key=None, api_keys=None).resolved_api_keys == ()

    def test_legacy_single_key_only(self) -> None:
        settings = _settings(api_key="legacy-secret", api_keys=None)
        assert settings.resolved_api_keys == ("legacy-secret",)

    def test_api_keys_only_with_spaces(self) -> None:
        settings = _settings(api_key=None, api_keys=" key-a , key-b ,key-c")
        assert settings.resolved_api_keys == ("key-a", "key-b", "key-c")

    def test_merges_legacy_and_list(self) -> None:
        settings = _settings(api_key="legacy-secret", api_keys="key-a,key-b")
        assert settings.resolved_api_keys == ("legacy-secret", "key-a", "key-b")

    def test_dedup_preserves_order(self) -> None:
        settings = _settings(api_key="key-a", api_keys="key-b, key-a ,key-b")
        assert settings.resolved_api_keys == ("key-a", "key-b")

    def test_filters_empty_entries(self) -> None:
        settings = _settings(api_key="  ", api_keys="key-a,, ,key-b,")
        assert settings.resolved_api_keys == ("key-a", "key-b")

    def test_empty_strings_disable_auth(self) -> None:
        assert _settings(api_key="", api_keys="").resolved_api_keys == ()


# ---------------------------------------------------------------------------
# Unit: verify_bearer_token
# ---------------------------------------------------------------------------


class TestVerifyBearerToken:
    def test_matches_any_configured_key(self) -> None:
        keys = ("key-a", "key-b", "key-c")
        assert verify_bearer_token("key-a", keys)
        assert verify_bearer_token("key-b", keys)
        assert verify_bearer_token("key-c", keys)

    def test_rejects_unknown_token(self) -> None:
        assert not verify_bearer_token("key-x", ("key-a", "key-b"))

    def test_rejects_empty_token(self) -> None:
        assert not verify_bearer_token("", ("key-a",))

    def test_rejects_when_no_keys(self) -> None:
        assert not verify_bearer_token("key-a", ())


# ---------------------------------------------------------------------------
# Integration harness — TestClient with auth env configured via env overlay
# ---------------------------------------------------------------------------


def _multi_key_client_ctx(
    mock_analysis_report: AnalysisReport,
    *,
    api_key: str = "",
    api_keys: str = "",
):
    """TestClient with API_KEY / API_KEYS set via env + get_settings cache_clear.

    Empty strings effectively unset a variable (filtered by resolved_api_keys)
    while shadowing any value inherited from the host environment.
    """
    from core.config import get_settings as _gs

    @contextmanager
    def _ctx():
        permissive = RateLimiter(max_requests=10_000, window_seconds=60.0)
        mock_graph_instance = MagicMock()
        mock_graph_instance.run.return_value = mock_analysis_report
        mock_graph_instance.__enter__ = MagicMock(return_value=mock_graph_instance)
        mock_graph_instance.__exit__ = MagicMock(return_value=False)
        mock_graph_cls = MagicMock(return_value=mock_graph_instance)

        env_overlay = {"API_KEY": api_key, "API_KEYS": api_keys}
        _gs.cache_clear()
        try:
            with (
                patch.dict(os.environ, env_overlay, clear=False),
                override_legacy_pack_cls(mock_graph_cls),
                patch("api.state.rate_limiter", permissive),
                patch("api.state.get_shared_llm", return_value=MagicMock(spec=True)),
                patch("api.state.get_shared_checkpointer", return_value=MagicMock()),
            ):
                from api.main import app

                with TestClient(app, raise_server_exceptions=False) as client:
                    yield client
        finally:
            _gs.cache_clear()

    return _ctx()


def _post_run(client: TestClient, token: str | None) -> int:
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    return client.post("/run", json={"query": "test"}, headers=headers).status_code


# ---------------------------------------------------------------------------
# Integration: multi-key auth
# ---------------------------------------------------------------------------


def test_two_keys_each_accepted_third_rejected(
    mock_analysis_report: AnalysisReport,
) -> None:
    """With API_KEYS=a,b both keys pass; an unknown key gets 401."""
    with _multi_key_client_ctx(
        mock_analysis_report, api_keys="tenant-a-key, tenant-b-key"
    ) as client:
        assert _post_run(client, "tenant-a-key") == 200
        assert _post_run(client, "tenant-b-key") == 200
        assert _post_run(client, "tenant-c-key") == 401
        assert _post_run(client, None) == 401


def test_legacy_single_api_key_unchanged(
    mock_analysis_report: AnalysisReport,
) -> None:
    """API_KEY alone keeps the historical behaviour."""
    with _multi_key_client_ctx(mock_analysis_report, api_key="legacy-secret") as client:
        assert _post_run(client, "legacy-secret") == 200
        assert _post_run(client, "wrong-token") == 401
        assert _post_run(client, None) == 401
        # Exempt paths stay open.
        assert client.get("/health").status_code == 200


def test_api_key_and_api_keys_are_merged(
    mock_analysis_report: AnalysisReport,
) -> None:
    """Legacy API_KEY and API_KEYS entries are all accepted simultaneously."""
    with _multi_key_client_ctx(
        mock_analysis_report, api_key="legacy-secret", api_keys="tenant-a-key"
    ) as client:
        assert _post_run(client, "legacy-secret") == 200
        assert _post_run(client, "tenant-a-key") == 200
        assert _post_run(client, "tenant-b-key") == 401


def test_zero_downtime_rotation_old_and_new_accepted(
    mock_analysis_report: AnalysisReport,
) -> None:
    """During rotation, old + new keys listed together are both accepted."""
    with _multi_key_client_ctx(
        mock_analysis_report, api_keys="old-rotated-key,new-rotated-key"
    ) as client:
        assert _post_run(client, "old-rotated-key") == 200
        assert _post_run(client, "new-rotated-key") == 200

    # After rotation completes, the old key is removed and rejected.
    with _multi_key_client_ctx(
        mock_analysis_report, api_keys="new-rotated-key"
    ) as client:
        assert _post_run(client, "new-rotated-key") == 200
        assert _post_run(client, "old-rotated-key") == 401


# ---------------------------------------------------------------------------
# Rate-limit scoping — per-token with 2+ keys, per-IP with a single key
# ---------------------------------------------------------------------------


def _make_request(headers: dict[str, str], client_host: str = "10.0.0.1") -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/run",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (client_host, 12345),
        "query_string": b"",
    }
    return Request(scope)


def test_rate_limit_key_per_token_when_multiple_keys() -> None:
    """With 2+ configured keys, the bucket key is the sha256 token fingerprint."""
    from api.dependencies import _rate_limit_key

    settings = _settings(api_key=None, api_keys="tenant-a-key,tenant-b-key")
    with patch("api.dependencies.get_settings", return_value=settings):
        key_a = _rate_limit_key(_make_request({"Authorization": "Bearer tenant-a-key"}))
        key_b = _rate_limit_key(_make_request({"Authorization": "Bearer tenant-b-key"}))

    expected_a = "token:" + hashlib.sha256(b"tenant-a-key").hexdigest()[:16]
    expected_b = "token:" + hashlib.sha256(b"tenant-b-key").hexdigest()[:16]
    assert key_a == expected_a
    assert key_b == expected_b
    assert key_a != key_b


def test_rate_limit_key_per_ip_with_single_key() -> None:
    """With a single shared key, the bucket stays scoped per client IP."""
    from api.dependencies import _rate_limit_key

    settings = _settings(api_key="legacy-secret", api_keys=None)
    with patch("api.dependencies.get_settings", return_value=settings):
        key = _rate_limit_key(_make_request({"Authorization": "Bearer legacy-secret"}))
        key_other_peer = _rate_limit_key(
            _make_request(
                {"Authorization": "Bearer legacy-secret"}, client_host="10.0.0.2"
            )
        )

    assert key == "ip:10.0.0.1"
    assert key_other_peer == "ip:10.0.0.2"


def test_rate_limit_key_per_ip_without_auth() -> None:
    """With no keys configured, scoping is per client IP."""
    from api.dependencies import _rate_limit_key

    settings = _settings(api_key=None, api_keys=None)
    with patch("api.dependencies.get_settings", return_value=settings):
        key = _rate_limit_key(_make_request({}))

    assert key == "ip:10.0.0.1"


def test_rate_limiting_isolated_per_token_with_two_keys(
    mock_analysis_report: AnalysisReport,
) -> None:
    """With 2 keys, exhausting tenant A's bucket must not throttle tenant B."""
    tight_limiter = RateLimiter(max_requests=2, window_seconds=60.0)
    settings = _settings(api_key=None, api_keys="tenant-a-key,tenant-b-key")

    mock_graph_instance = MagicMock()
    mock_graph_instance.run.return_value = mock_analysis_report
    mock_graph_instance.__enter__ = MagicMock(return_value=mock_graph_instance)
    mock_graph_instance.__exit__ = MagicMock(return_value=False)
    mock_graph_cls = MagicMock(return_value=mock_graph_instance)

    with (
        override_legacy_pack_cls(mock_graph_cls),
        patch("api.state.rate_limiter", tight_limiter),
        patch("api.dependencies.get_settings", return_value=settings),
        patch("api.middleware.get_settings", return_value=settings),
        patch("api.state.get_shared_llm", return_value=MagicMock(spec=True)),
        patch("api.state.get_shared_checkpointer", return_value=MagicMock()),
    ):
        from api.main import app

        with TestClient(app, raise_server_exceptions=False) as client:
            for _ in range(2):
                assert _post_run(client, "tenant-a-key") == 200
            blocked = _post_run(client, "tenant-a-key")
            other_tenant = _post_run(client, "tenant-b-key")

    assert blocked == 429
    assert other_tenant == 200
