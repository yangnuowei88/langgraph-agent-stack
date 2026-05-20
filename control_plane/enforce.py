"""
control_plane/enforce.py — Apply registered pack policies at API boundaries.
"""

from __future__ import annotations

from control_plane.registry import PolicyRegistry
from core.config import Settings
from core.security import InputValidator


def effective_budget_usd(pack_id: str, settings: Settings) -> float | None:
    """Resolve per-run budget: global setting overrides pack policy ceiling."""
    if settings.pack_default_budget_usd is not None:
        return settings.pack_default_budget_usd
    policy = PolicyRegistry.get(pack_id)
    if policy is None:
        return None
    return policy.constraints.budget_usd_ceiling


def effective_stream_timeout_seconds(pack_id: str, settings: Settings) -> float:
    """Minimum of global stream timeout and optional pack policy cap."""
    timeout = float(settings.stream_timeout_seconds)
    policy = PolicyRegistry.get(pack_id)
    if policy is None or policy.constraints.stream_timeout_seconds is None:
        return timeout
    return min(timeout, policy.constraints.stream_timeout_seconds)


def validate_query_for_pack(
    query: str,
    pack_id: str,
    validator: InputValidator,
) -> str:
    """Validate and sanitise a query, honouring pack ``max_query_chars`` when set."""
    policy = PolicyRegistry.get(pack_id)
    max_chars = (
        policy.constraints.max_query_chars
        if policy and policy.constraints.max_query_chars is not None
        else None
    )
    if max_chars is not None and len(query) > max_chars:
        raise ValueError(
            f"Query exceeds maximum length of {max_chars} characters for pack {pack_id!r}."
        )
    return validator.validate(query)
