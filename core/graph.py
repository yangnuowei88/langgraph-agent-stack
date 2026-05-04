"""
core/graph.py — Backward-compatibility shim.

The pipeline logic has moved to domain_packs/research_analysis/pack.py.
This module re-exports MultiAgentGraph so existing imports continue to work
without modification during the migration period.

Re-exporting ResearchAgent and AnalystAgent here preserves the ability to
patch them via ``patch("core.graph.ResearchAgent", …)`` in tests that
pre-date the domain-pack migration.  Those patches propagate because the
pack's _research_node and _analysis_node resolve agent classes via the
core.graph module namespace at runtime (using sys.modules), so patching
"core.graph.ResearchAgent" correctly intercepts agent instantiation.
"""

from agents.analyst import AnalystAgent  # noqa: F401 — backward-compat re-export
from agents.researcher import ResearchAgent  # noqa: F401 — backward-compat re-export
from domain_packs.research_analysis.pack import OrchestratorState, ResearchAnalysisPack

MultiAgentGraph = ResearchAnalysisPack

__all__ = ["MultiAgentGraph", "OrchestratorState", "ResearchAgent", "AnalystAgent"]
