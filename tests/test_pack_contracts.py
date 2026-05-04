"""
tests/test_pack_contracts.py — Contract tests for the platform kernel.

Verifies that:
1. PackRegistry correctly registers and retrieves pack classes.
2. ResearchAnalysisPack satisfies the BaseDomainPack contract.
3. DEFAULT_PACK_ID resolves to a registered pack.
"""

from __future__ import annotations

import inspect
import platform as _platform_pkg  # noqa: F401 — side-effect: registers packs
from platform.base_pack import BaseDomainPack
from platform.registry import PackRegistry

import pytest

from domain_packs.research_analysis.pack import ResearchAnalysisPack

# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


def test_research_analysis_pack_is_registered():
    assert "research_analysis" in PackRegistry.list_packs()


def test_registry_get_returns_correct_class():
    cls = PackRegistry.get("research_analysis")
    assert cls is ResearchAnalysisPack


def test_registry_get_unknown_raises_key_error():
    with pytest.raises(KeyError, match="not registered"):
        PackRegistry.get("nonexistent_pack_xyz")


def test_registry_list_packs_returns_sorted_list():
    packs = PackRegistry.list_packs()
    assert isinstance(packs, list)
    assert packs == sorted(packs)


def test_registry_register_without_pack_id_raises():
    class BadPack(BaseDomainPack):
        pass

    with pytest.raises(ValueError, match="pack_id"):
        PackRegistry.register(BadPack)


# ---------------------------------------------------------------------------
# BaseDomainPack contract tests
# ---------------------------------------------------------------------------


def test_research_analysis_pack_inherits_base():
    assert issubclass(ResearchAnalysisPack, BaseDomainPack)


def test_research_analysis_pack_has_required_class_attrs():
    assert ResearchAnalysisPack.pack_id == "research_analysis"
    assert isinstance(ResearchAnalysisPack.name, str) and ResearchAnalysisPack.name
    assert isinstance(ResearchAnalysisPack.description, str) and ResearchAnalysisPack.description


def test_research_analysis_pack_implements_abstract_methods():
    abstract_methods = {"run", "arun", "stream_events"}
    pack_methods = set(dir(ResearchAnalysisPack))
    missing = abstract_methods - pack_methods
    assert not missing, f"Missing abstract method implementations: {missing}"


def test_research_analysis_pack_run_is_not_abstract():
    assert not getattr(ResearchAnalysisPack.run, "__isabstractmethod__", False)


def test_research_analysis_pack_arun_is_coroutine():
    assert inspect.iscoroutinefunction(ResearchAnalysisPack.arun)


def test_research_analysis_pack_stream_events_is_async_gen():
    assert inspect.isasyncgenfunction(ResearchAnalysisPack.stream_events)


def test_research_analysis_pack_supports_context_manager():
    assert hasattr(ResearchAnalysisPack, "__enter__")
    assert hasattr(ResearchAnalysisPack, "__exit__")


# ---------------------------------------------------------------------------
# Config integration test
# ---------------------------------------------------------------------------


def test_default_pack_id_resolves_to_registered_pack():
    from core.config import get_settings

    settings = get_settings()
    pack_id = settings.default_pack_id
    cls = PackRegistry.get(pack_id)
    assert issubclass(cls, BaseDomainPack)
