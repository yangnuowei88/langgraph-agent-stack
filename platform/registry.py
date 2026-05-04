"""
platform/registry.py — Static pack registry.

Packs are registered explicitly in platform/__init__.py at import time.
No dynamic loading, no auto-discovery, no magic.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from platform.base_pack import BaseDomainPack

logger = logging.getLogger(__name__)


@dataclass
class PackVersion:
    """A versioned entry in the pack registry.

    Attributes:
        version:   Stable string identifier for this version (e.g. "1.0", "2.0", "canary").
        pack_cls:  The domain pack class for this version.
        weight:    Relative weight used for traffic splitting when multiple versions are
                   registered for the same pack_id.  Must be >= 0.
    """

    version: str
    pack_cls: type[BaseDomainPack]
    weight: float = field(default=1.0)

    def __post_init__(self) -> None:
        if self.weight < 0:
            raise ValueError(f"PackVersion.weight must be >= 0, got {self.weight!r}")


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

    _registry: dict[str, list[PackVersion]] = {}

    @classmethod
    def register(cls, pack_cls: type[BaseDomainPack]) -> None:
        """Register a pack class under its pack_id.

        If a PackVersion with the same pack_id and version already exists it
        will be replaced (a warning is emitted).  If the version is new it is
        appended to the list.

        Raises:
            ValueError: If pack_cls does not declare pack_id, name, or description.
        """
        pack_id = getattr(pack_cls, "pack_id", None)
        if not pack_id:
            raise ValueError(
                f"{pack_cls.__name__} must define a non-empty 'pack_id' class attribute."
            )
        if not getattr(pack_cls, "name", None):
            raise ValueError(
                f"{pack_cls.__name__} must define a non-empty 'name' class attribute."
            )
        if not getattr(pack_cls, "description", None):
            raise ValueError(
                f"{pack_cls.__name__} must define a non-empty 'description' class attribute."
            )

        version = getattr(pack_cls, "version", "1.0")
        pv = PackVersion(version=version, pack_cls=pack_cls, weight=1.0)

        if pack_id not in cls._registry:
            cls._registry[pack_id] = [pv]
        else:
            versions = cls._registry[pack_id]
            for i, existing in enumerate(versions):
                if existing.version == version:
                    logger.warning(
                        "PackRegistry: replacing existing pack '%s' version '%s' "
                        "with a new registration.",
                        pack_id,
                        version,
                    )
                    versions[i] = pv
                    break
            else:
                versions.append(pv)

    @classmethod
    def get(cls, pack_id: str, version: str | None = None) -> type[BaseDomainPack]:
        """Return the pack class registered under pack_id.

        When ``version`` is provided the exact matching PackVersion is returned
        directly (no weighted selection).

        When ``version`` is None and a single version is registered the class
        is returned directly.  When multiple versions are registered one is
        selected via ``random.choices`` weighted by each ``PackVersion.weight``.

        Raises:
            KeyError: If pack_id is not registered.
            KeyError: If a specific version is requested but not found.
        """
        if pack_id not in cls._registry:
            available = list(cls._registry)
            raise KeyError(
                f"Pack '{pack_id}' is not registered. "
                f"Available packs: {available}"
            )
        versions = cls._registry[pack_id]

        if version is not None:
            for pv in versions:
                if pv.version == version:
                    return pv.pack_cls
            available_versions = [pv.version for pv in versions]
            raise KeyError(
                f"Pack '{pack_id}' version '{version}' is not registered. "
                f"Available versions: {available_versions}"
            )

        if len(versions) == 1:
            return versions[0].pack_cls
        weights = [pv.weight for pv in versions]
        if sum(weights) == 0.0:
            raise KeyError(
                f"Pack '{pack_id}' has no versions with positive weight."
            )
        (selected,) = random.choices(versions, weights=weights, k=1)
        return selected.pack_cls

    @classmethod
    def set_weights(cls, pack_id: str, weights: dict[str, float]) -> None:
        """Set traffic-split weights for versions of a registered pack.

        Args:
            pack_id: The pack to update.
            weights: Mapping of version string → new weight (must be >= 0).
                     Versions not present in the dict are left unchanged.

        Raises:
            KeyError: If pack_id is not registered.
            KeyError: If a version in weights is not registered for this pack_id.
            ValueError: If any weight value is negative.
        """
        if pack_id not in cls._registry:
            available = list(cls._registry)
            raise KeyError(
                f"Pack '{pack_id}' is not registered. "
                f"Available packs: {available}"
            )
        registry_versions = cls._registry[pack_id]

        for version, weight in weights.items():
            if weight < 0:
                raise ValueError(
                    f"Weight must be >= 0, got {weight!r} for version '{version}'."
                )
            for pv in registry_versions:
                if pv.version == version:
                    pv.weight = weight
                    break
            else:
                available_versions = [pv.version for pv in registry_versions]
                raise KeyError(
                    f"Pack '{pack_id}' version '{version}' is not registered. "
                    f"Available versions: {available_versions}"
                )

    @classmethod
    def _get_versions(cls, pack_id: str) -> list[PackVersion]:
        """Return all registered PackVersion entries for a given pack_id.

        Raises:
            KeyError: If pack_id is not registered.
        """
        if pack_id not in cls._registry:
            available = list(cls._registry)
            raise KeyError(
                f"Pack '{pack_id}' is not registered. "
                f"Available packs: {available}"
            )
        return list(cls._registry[pack_id])

    @classmethod
    def list_packs(cls) -> list[str]:
        """Return a sorted list of all registered pack IDs."""
        return sorted(cls._registry)

    @classmethod
    def get_schemas(cls, pack_id: str) -> tuple[type[BaseModel], type[BaseModel]]:
        """Return (input_schema, output_schema) for the given pack.

        Returns:
            Tuple of (input_schema_class, output_schema_class).

        Raises:
            KeyError: If pack_id is not registered.
        """
        pack_cls = cls.get(pack_id)  # reuses the KeyError logic from get()
        return pack_cls.input_schema, pack_cls.output_schema

    @classmethod
    def list_packs_with_metadata(cls) -> list[dict[str, Any]]:
        """Return metadata for all registered packs including their schemas.

        Returns:
            List of dicts with keys: pack_id, name, description,
            input_schema (JSON schema dict), output_schema (JSON schema dict).
        """
        result = []
        for pack_id in cls.list_packs():
            pack_cls = cls.get(pack_id)
            result.append(
                {
                    "pack_id": pack_id,
                    "name": getattr(pack_cls, "name", ""),
                    "description": getattr(pack_cls, "description", ""),
                    "input_schema": pack_cls.input_schema.model_json_schema(),
                    "output_schema": pack_cls.output_schema.model_json_schema(),
                }
            )
        return result

    @classmethod
    def _reset(cls) -> None:
        """Clear the registry — for use in tests only."""
        cls._registry.clear()
