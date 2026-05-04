"""
platform/registry.py — Static pack registry.

Packs are registered explicitly in platform/__init__.py at import time.
No dynamic loading, no auto-discovery, no magic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from platform.base_pack import BaseDomainPack


class PackRegistry:
    """
    Explicit, dict-based registry of available domain packs.

    Usage::

        from platform.registry import PackRegistry
        from my_pack import MyPack

        PackRegistry.register(MyPack)
        cls = PackRegistry.get("my_pack")
        instance = cls(run_id="abc", llm=llm, checkpointer=cp)

    All registration happens at startup in platform/__init__.py; the registry
    is a class-level dict and is shared across the process lifetime.
    """

    _registry: dict[str, type[BaseDomainPack]] = {}

    @classmethod
    def register(cls, pack_cls: type[BaseDomainPack]) -> None:
        """Register a pack class under its pack_id.

        Raises:
            ValueError: If pack_cls does not declare a pack_id.
        """
        pack_id = getattr(pack_cls, "pack_id", None)
        if not pack_id:
            raise ValueError(
                f"{pack_cls.__name__} must define a non-empty 'pack_id' class attribute."
            )
        cls._registry[pack_id] = pack_cls

    @classmethod
    def get(cls, pack_id: str) -> type[BaseDomainPack]:
        """Return the pack class registered under pack_id.

        Raises:
            KeyError: If pack_id is not registered.
        """
        if pack_id not in cls._registry:
            available = list(cls._registry)
            raise KeyError(
                f"Pack '{pack_id}' is not registered. "
                f"Available packs: {available}"
            )
        return cls._registry[pack_id]

    @classmethod
    def list_packs(cls) -> list[str]:
        """Return a sorted list of all registered pack IDs."""
        return sorted(cls._registry)

    @classmethod
    def _reset(cls) -> None:
        """Clear the registry — for use in tests only."""
        cls._registry.clear()
