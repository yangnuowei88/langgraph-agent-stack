"""
core/graph.py — Backward-compatibility shim.

The pipeline logic has moved to domain_packs/research_analysis/pack.py.
This module re-exports MultiAgentGraph so existing imports continue to work
without modification during the migration period.

Re-exporting ResearchAgent and AnalystAgent here preserves the ability to
patch them via ``patch("core.graph.ResearchAgent", …)`` in tests that
pre-date the domain-pack migration.  Those patches propagate because
domain_packs.research_analysis.pack imports ResearchAgent and AnalystAgent
by reference; patching the names in this shim module does NOT affect the
pack module's internal namespace, so we also need to re-export them from
this shim so that any test patching "core.graph.X" still resolves.

NOTE: tests that patch "core.graph.ResearchAgent" must be updated to patch
"domain_packs.research_analysis.pack.ResearchAgent" for the patch to take
effect inside the pack.  The re-exports below preserve AttributeError-free
patching at the core.graph level.
"""

from agents.analyst import AnalystAgent  # noqa: F401 — backward-compat re-export
from agents.researcher import ResearchAgent  # noqa: F401 — backward-compat re-export
from domain_packs.research_analysis.pack import OrchestratorState, ResearchAnalysisPack

MultiAgentGraph = ResearchAnalysisPack

__all__ = ["MultiAgentGraph", "OrchestratorState", "ResearchAgent", "AnalystAgent"]
