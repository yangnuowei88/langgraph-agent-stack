"""pack_kernel/plugins.py — Distributable pack discovery via Python entry points.

Third-party packs are shipped as regular Python packages declaring an entry
point in the ``langgraph_agent_stack.packs`` group::

    [project.entry-points."langgraph_agent_stack.packs"]
    sentiment = "acme_packs.sentiment:SentimentPack"

Loading third-party code is code execution, so discovery is **opt-in and
allowlisted**: nothing is loaded unless ``PACK_PLUGINS_ENABLED=true`` AND the
entry-point name appears in ``PACK_PLUGINS_ALLOWLIST``. Supply-chain
integrity (pinning, hashes, provenance) belongs to the package installation
step — use a vetted internal index and locked requirements; this module
verifies the *contract*, not the distribution.

Every candidate class is validated against the pack contract before
registration (see :func:`validate_plugin_pack_class`); third-party schemas
must additionally be strict (``extra="forbid"``) so plugin packs cannot relax
the input/output hygiene the built-in packs guarantee. A broken plugin is
logged and skipped — it can never take down startup.
"""

from __future__ import annotations

import logging
from importlib.metadata import EntryPoint, entry_points
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from pack_kernel.base_pack import BaseDomainPack

logger = logging.getLogger(__name__)

#: Entry-point group third-party packs must register under.
ENTRY_POINT_GROUP = "langgraph_agent_stack.packs"


class PluginPackError(ValueError):
    """Raised when a plugin pack class violates the pack contract."""


def _schema_is_strict(schema: type[BaseModel]) -> bool:
    return (schema.model_config or {}).get("extra") == "forbid"


def validate_plugin_pack_class(pack_cls: Any) -> type[BaseDomainPack]:
    """Validate a candidate plugin class against the pack contract.

    Checks (stricter than ``PackRegistry.register``, because the code is
    third-party):
        * subclass of ``BaseDomainPack``;
        * non-empty ``pack_id``, ``name``, ``description``, ``version``;
        * ``input_schema`` / ``output_schema`` are Pydantic models declaring
          ``extra="forbid"``.

    Returns the class unchanged when valid.

    Raises:
        PluginPackError: describing the first contract violation found.
    """
    from pack_kernel.base_pack import BaseDomainPack

    if not isinstance(pack_cls, type) or not issubclass(pack_cls, BaseDomainPack):
        raise PluginPackError(f"{pack_cls!r} is not a BaseDomainPack subclass.")
    for attr in ("pack_id", "name", "description", "version"):
        if not getattr(pack_cls, attr, None):
            raise PluginPackError(
                f"{pack_cls.__name__} must define a non-empty {attr!r} class attribute."
            )
    for attr in ("input_schema", "output_schema"):
        schema = getattr(pack_cls, attr, None)
        if not (isinstance(schema, type) and issubclass(schema, BaseModel)):
            raise PluginPackError(
                f"{pack_cls.__name__}.{attr} must be a Pydantic BaseModel subclass."
            )
        if not _schema_is_strict(schema):
            raise PluginPackError(
                f"{pack_cls.__name__}.{attr} ({schema.__name__}) must declare "
                'model_config = ConfigDict(extra="forbid") — plugin pack schemas '
                "must be strict."
            )
    return pack_cls


def _iter_entry_points() -> tuple[EntryPoint, ...]:
    """Indirection point for tests; returns the group's entry points."""
    return tuple(entry_points(group=ENTRY_POINT_GROUP))


def discover_plugin_packs(
    allowlist: tuple[str, ...],
) -> list[type[BaseDomainPack]]:
    """Load and validate allowlisted plugin pack classes.

    Args:
        allowlist: Entry-point names the operator explicitly trusts. Empty
            means nothing is loaded (deny by default).

    Returns:
        Validated pack classes, in entry-point order. Invalid or broken
        plugins are logged and skipped.
    """
    if not allowlist:
        return []

    allowed = set(allowlist)
    loaded: list[type[BaseDomainPack]] = []
    for ep in _iter_entry_points():
        if ep.name not in allowed:
            logger.info(
                "Plugin pack not in allowlist — skipping",
                extra={"entry_point": ep.name, "target": ep.value},
            )
            continue
        try:
            pack_cls = validate_plugin_pack_class(ep.load())
        except PluginPackError as exc:
            logger.error(
                "Plugin pack rejected (contract violation)",
                extra={"entry_point": ep.name, "error": str(exc)},
            )
            continue
        except Exception as exc:
            logger.error(
                "Plugin pack failed to import — skipping",
                extra={"entry_point": ep.name, "target": ep.value, "error": str(exc)},
            )
            continue
        loaded.append(pack_cls)
    return loaded


def register_plugin_packs(
    *,
    enabled: bool,
    allowlist: tuple[str, ...],
) -> list[str]:
    """Discover, validate, and register allowlisted plugin packs.

    Built-in pack ids cannot be overridden: a plugin whose ``pack_id``
    already exists in the registry is rejected (a plugin may still ship a
    NEW pack id with multiple versions of its own).

    Returns:
        The pack_ids successfully registered.
    """
    if not enabled:
        return []
    if not allowlist:
        logger.warning(
            "PACK_PLUGINS_ENABLED=true but PACK_PLUGINS_ALLOWLIST is empty — "
            "no plugin packs will be loaded (deny by default)."
        )
        return []

    from pack_kernel.registry import PackRegistry

    existing = set(PackRegistry.list_packs())
    registered: list[str] = []
    for pack_cls in discover_plugin_packs(allowlist):
        pack_id = pack_cls.pack_id
        if pack_id in existing and pack_id not in registered:
            logger.error(
                "Plugin pack rejected: pack_id collides with an already "
                "registered pack",
                extra={"pack_id": pack_id, "pack_cls": pack_cls.__name__},
            )
            continue
        PackRegistry.register(pack_cls)
        if pack_id not in registered:
            registered.append(pack_id)
        logger.info(
            "Plugin pack registered",
            extra={"pack_id": pack_id, "version": pack_cls.version},
        )
    return registered
