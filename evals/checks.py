"""evals/checks.py — Deterministic output checks for eval cases."""

from __future__ import annotations

from typing import Any

from evals.models import CheckResult


def _field_as_text(value: Any) -> str:
    """Render a field for substring checks (lists are joined)."""
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    return str(value)


def run_checks(output: dict[str, Any], checks: dict[str, Any]) -> list[CheckResult]:
    """Apply the case's deterministic checks to a pack output dict.

    Supported check types (all optional):
        required_fields: list[str] — field must exist and be non-None.
        contains: dict[field, substring] — substring must appear in the field.
        not_contains: dict[field, substring] — substring must NOT appear.
        min_length: dict[field, int] — ``len(field)`` must be >= the bound.
        numeric_range: dict[field, [min, max]] — numeric field within bounds.
    """
    results: list[CheckResult] = []

    for field in checks.get("required_fields", []):
        present = field in output and output[field] is not None
        results.append(
            CheckResult(
                name=f"required_fields:{field}",
                passed=present,
                detail="" if present else f"field {field!r} missing or None",
            )
        )

    for field, needle in (checks.get("contains") or {}).items():
        text = _field_as_text(output.get(field, ""))
        ok = str(needle) in text
        results.append(
            CheckResult(
                name=f"contains:{field}",
                passed=ok,
                detail="" if ok else f"{needle!r} not found in {field!r}",
            )
        )

    for field, needle in (checks.get("not_contains") or {}).items():
        text = _field_as_text(output.get(field, ""))
        ok = str(needle) not in text
        results.append(
            CheckResult(
                name=f"not_contains:{field}",
                passed=ok,
                detail="" if ok else f"forbidden {needle!r} found in {field!r}",
            )
        )

    for field, bound in (checks.get("min_length") or {}).items():
        value = output.get(field)
        try:
            length = len(value)  # type: ignore[arg-type]
        except TypeError:
            length = -1
        ok = length >= int(bound)
        results.append(
            CheckResult(
                name=f"min_length:{field}",
                passed=ok,
                detail="" if ok else f"len({field})={length} < {bound}",
            )
        )

    for field, bounds in (checks.get("numeric_range") or {}).items():
        value = output.get(field)
        low, high = float(bounds[0]), float(bounds[1])
        ok = isinstance(value, (int, float)) and low <= float(value) <= high
        results.append(
            CheckResult(
                name=f"numeric_range:{field}",
                passed=ok,
                detail="" if ok else f"{field}={value!r} outside [{low}, {high}]",
            )
        )

    return results
