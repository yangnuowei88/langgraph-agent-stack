"""evals — Golden-dataset evaluation harness for domain packs.

Measures whether a pack version actually works (and whether a new version is
better than the old one) by running curated cases through the real pack code
with scripted LLM responses, then applying deterministic checks and an
optional LLM judge.

This is the proof loop behind the PackRegistry canary routing: before
shifting traffic weights to a new pack version, run
``python -m evals --pack <id> --compare <new_version>`` and look at the diff.
"""

from evals.models import (
    CaseResult,
    CheckResult,
    EvalCase,
    EvalComparison,
    EvalReport,
)
from evals.runner import (
    compare_versions,
    load_dataset,
    run_pack_eval,
)

__all__ = [
    "CaseResult",
    "CheckResult",
    "EvalCase",
    "EvalComparison",
    "EvalReport",
    "compare_versions",
    "load_dataset",
    "run_pack_eval",
]
