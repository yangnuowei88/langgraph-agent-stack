"""tests/test_memory_sticky_redis.py — Sticky pack version on Redis run history."""

from __future__ import annotations

from unittest.mock import MagicMock

from core.memory import RedisRunHistory


def test_redis_get_pack_version_from_session_pack_index() -> None:
    history = RedisRunHistory.__new__(RedisRunHistory)
    history._prefix = "runhistory"
    history._redis = MagicMock()
    history._redis.zrevrange.return_value = ["run-latest"]
    history.get_run = MagicMock(
        return_value={
            "metadata": {"pack_version": "2.0", "pack_id": "research_analysis"}
        }
    )

    version = history.get_pack_version_for_session("sess-1", "research_analysis")

    assert version == "2.0"
    history._redis.zrevrange.assert_called_once()
