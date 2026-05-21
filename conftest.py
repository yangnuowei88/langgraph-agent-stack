"""
Root conftest.py — executed by pytest before any test collection.

Registers built-in domain packs so tests can use PackRegistry without
importing the FastAPI app first.
"""

from __future__ import annotations

from pack_kernel.builtin_packs import register_builtin_packs

register_builtin_packs()
