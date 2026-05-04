"""
Root conftest.py — executed by pytest before any test collection.

Ensures the local 'platform' package (platform/) is registered in sys.modules
before test modules are collected.  Without this, the stdlib 'platform' module
(already cached in sys.modules at interpreter start) would shadow our package,
causing 'ModuleNotFoundError: No module named platform.base_pack' during
collection of tests/test_pack_contracts.py.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys


def _bootstrap_local_platform() -> None:
    """Replace sys.modules['platform'] with our local package if not already done."""
    import os

    project_root = os.path.dirname(__file__)
    local_pkg_init = os.path.join(project_root, "platform", "__init__.py")

    # Already bootstrapped — nothing to do.
    current = sys.modules.get("platform")
    if current is not None and getattr(current, "__file__", None) == local_pkg_init:
        return

    # Build a package module object for our local 'platform' package.
    spec = importlib.util.spec_from_file_location(
        "platform",
        local_pkg_init,
        submodule_search_locations=[os.path.join(project_root, "platform")],
    )
    if spec is None or spec.loader is None:
        return

    pkg = importlib.util.module_from_spec(spec)
    pkg.__package__ = "platform"
    pkg.__path__ = [os.path.join(project_root, "platform")]  # type: ignore[attr-defined]

    # Register before exec so that intra-package imports (from platform.base_pack …)
    # resolve correctly during __init__.py execution.
    sys.modules["platform"] = pkg
    spec.loader.exec_module(pkg)  # type: ignore[attr-defined]


_bootstrap_local_platform()
