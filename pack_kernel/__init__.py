"""
pack_kernel — Platform kernel for the LangGraph agent stack.

Import ``BaseDomainPack`` / ``PackRegistry`` from here. Built-in packs are
registered explicitly via ``register_builtin_packs()`` (see ``api/lifespan.py``
and root ``conftest.py``) — not as a side effect of importing this package.
"""

from pack_kernel.base_pack import BaseDomainPack
from pack_kernel.registry import PackRegistry

__all__ = ["BaseDomainPack", "PackRegistry"]
