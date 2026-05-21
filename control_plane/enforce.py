"""
control_plane/enforce.py — Apply registered pack policies at API boundaries.
"""

from __future__ import annotations

from typing import Any

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


def validate_pack_body(
    body: Any,
    pack_id: str,
    validator: InputValidator,
) -> None:
    """Run content-safety checks on every string field in a typed pack request body.

    Pydantic enforces field ``max_length`` at parse time; this applies the same
    dangerous-pattern rules as ``InputValidator`` to document-sized fields
    (``contract_text``, ``rfp_text``, ``resume_text``, etc.) that are not used
    as the pack primary query label.
    """
    from pydantic import BaseModel

    if not isinstance(body, BaseModel):
        return

    model_cls = type(body)
    policy = PolicyRegistry.get(pack_id)
    fallback_max = (
        policy.constraints.max_query_chars
        if policy and policy.constraints.max_query_chars is not None
        else validator.max_length
    )
    schema_props = model_cls.model_json_schema().get("properties", {})

    def _check_string(field_name: str, value: str) -> None:
        field_schema = schema_props.get(field_name, {})
        field_max = field_schema.get("maxLength")
        cap = int(field_max) if field_max is not None else fallback_max
        validator.check_content_safety(value, max_length=cap)

    for name, value in body.model_dump().items():
        if isinstance(value, str) and value:
            _check_string(name, value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item:
                    validator.check_content_safety(item, max_length=fallback_max)
