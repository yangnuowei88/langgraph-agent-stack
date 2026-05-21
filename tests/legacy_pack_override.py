"""Override ``get_legacy_pack_cls`` for legacy ``/run`` route tests."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any


@contextmanager
def override_legacy_pack_cls(mock_cls: type[Any]) -> Generator[None, None, None]:
    """Replace the FastAPI dependency that selects the legacy pipeline pack class."""
    from api.main import app, get_legacy_pack_cls

    app.dependency_overrides[get_legacy_pack_cls] = lambda: mock_cls
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_legacy_pack_cls, None)
