"""tests/test_prompt_safety.py — Prompt delimiter and guard tests."""

from __future__ import annotations

from domain_packs.common.prompt_safety import (
    format_vertical_prompt,
    wrap_untrusted_content,
)


def test_wrap_untrusted_content_adds_markers() -> None:
    wrapped = wrap_untrusted_content("Document", "Some user text")
    assert "BEGIN UNTRUSTED USER CONTENT" in wrapped
    assert "Some user text" in wrapped
    assert "END UNTRUSTED USER CONTENT" in wrapped


def test_format_vertical_prompt_includes_guard_and_schema() -> None:
    prompt = format_vertical_prompt(
        task_instructions="Do the task.",
        fields={"Field A": "value"},
        output_schema_json='{"type": "object"}',
        reference_text="ref doc",
        closing_instructions="Be concise.",
    )
    assert "Security rules" in prompt
    assert "BEGIN UNTRUSTED USER CONTENT" in prompt
    assert "Field A" in prompt
    assert "ref doc" in prompt
    assert "Be concise." in prompt
