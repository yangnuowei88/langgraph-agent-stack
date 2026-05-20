"""
control_plane/registry.py — Static registry of pack-level policies (Approach B).
"""

from __future__ import annotations

from control_plane.policies import PackPolicy


class PolicyRegistry:
    """Explicit policy registration keyed by ``pack_id`` (mirrors PackRegistry)."""

    _policies: dict[str, PackPolicy] = {}

    @classmethod
    def register(cls, policy: PackPolicy) -> None:
        if not policy.pack_id:
            raise ValueError("PackPolicy.pack_id must not be empty")
        cls._policies[policy.pack_id] = policy

    @classmethod
    def get(cls, pack_id: str) -> PackPolicy | None:
        return cls._policies.get(pack_id)

    @classmethod
    def list_policies(cls) -> list[str]:
        return sorted(cls._policies)

    @classmethod
    def _reset(cls) -> None:
        """Clear all policies — tests only."""
        cls._policies.clear()
