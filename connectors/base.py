"""
connectors/base.py — Minimal contract for external data / tool adapters.

Connectors are **not** LangGraph nodes: they are optional building blocks that
a domain pack (or an agent) can call to pull structured snippets from outside
the LLM (SQL, HTTP APIs, file stores, search indices, etc.).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

#: Maximum number of characters kept in a normalized ``SourceRef.snippet``.
SNIPPET_MAX_CHARS = 500

_ID_KEYS = ("id", "doc_id")
_TITLE_KEYS = ("title", "name")
_URL_KEYS = ("url", "link", "source")
_SNIPPET_KEYS = ("snippet", "text", "content")


class SourceRef(BaseModel):
    """Normalized provenance reference for one connector record.

    Connectors keep returning free-form ``dict`` records (back-compat);
    consumers normalize them with :func:`record_to_source_ref` to obtain a
    stable, auditable citation unit.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str | None = None
    url: str | None = None
    snippet: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    def citation(self) -> str:
        """Stable citation string: ``[id] title — url`` (absent parts omitted)."""
        label = " — ".join(part for part in (self.title, self.url) if part)
        return f"[{self.id}] {label}" if label else f"[{self.id}]"


def _first_str(record: dict[str, Any], keys: tuple[str, ...]) -> tuple[str, str] | None:
    """Return ``(key, value)`` for the first non-empty string-able key."""
    for key in keys:
        value = record.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return key, text
    return None


def record_to_source_ref(record: dict[str, Any], index: int) -> SourceRef:
    """Normalize one free-form connector record into a :class:`SourceRef`.

    Looks up the usual provenance keys (``id``/``doc_id``, ``title``/``name``,
    ``url``/``link``/``source``, ``snippet``/``text``/``content``). Falls back
    to ``doc-{index}`` when no identifier is present. Remaining keys are kept
    in :attr:`SourceRef.metadata`. The snippet is truncated to
    :data:`SNIPPET_MAX_CHARS` characters.
    """
    consumed: set[str] = set()

    found_id = _first_str(record, _ID_KEYS)
    found_title = _first_str(record, _TITLE_KEYS)
    found_url = _first_str(record, _URL_KEYS)
    found_snippet = _first_str(record, _SNIPPET_KEYS)

    for found in (found_id, found_title, found_url, found_snippet):
        if found is not None:
            consumed.add(found[0])

    return SourceRef(
        id=found_id[1] if found_id else f"doc-{index}",
        title=found_title[1] if found_title else None,
        url=found_url[1] if found_url else None,
        snippet=(found_snippet[1] if found_snippet else "")[:SNIPPET_MAX_CHARS],
        metadata={k: v for k, v in record.items() if k not in consumed},
    )


@dataclass(frozen=True, slots=True)
class ConnectorRequest:
    """One invocation: a query string plus optional caps and opaque filters.

    * ``query`` — Free text or a pseudo-query; SQL/API connectors interpret it.
    * ``limit`` — Upper bound on rows/snippets (best-effort).
    * ``filters`` — Backend-specific hints (e.g. column filters, collection id).
    * ``context`` — Call-site metadata (e.g. ``session_id``, ``tenant``).
    """

    query: str
    limit: int = 10
    filters: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConnectorResult:
    """Normalized outcome: tabular-ish rows for downstream prompt formatting.

    Each record is a flat ``dict`` (e.g. ``{"title": "...", "snippet": "..."}``).
    Semantics are connector-specific; packs remain responsible for validation.
    """

    records: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseConnector(abc.ABC):
    """Abstract adapter: one async entry point, optional lifecycle hook.

    Subclasses declare stable ``connector_id`` / ``name`` / ``description``
    for discovery and logging. They implement :meth:`fetch` only; connection
    setup belongs in ``__init__`` or lazy properties — no global registry here.
    """

    connector_id: ClassVar[str]
    name: ClassVar[str]
    description: ClassVar[str] = ""

    @abc.abstractmethod
    async def fetch(self, request: ConnectorRequest) -> ConnectorResult:
        """Return zero or more records for the given request."""

    async def close(self) -> None:
        """Override to close pools, HTTP clients, or file handles."""
