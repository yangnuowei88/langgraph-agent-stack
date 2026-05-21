"""Tests for domain_packs.common.structured_llm.extract_json_object."""

from __future__ import annotations

import pytest

from domain_packs.common.structured_llm import extract_json_object


def test_extract_json_object_plain_object() -> None:
    raw = '{"summary": "ok", "score": 1}'
    assert extract_json_object(raw) == {"summary": "ok", "score": 1}


def test_extract_json_object_fenced_block() -> None:
    raw = 'Here is the result:\n```json\n{"a": 1}\n```\n'
    assert extract_json_object(raw) == {"a": 1}


def test_extract_json_object_top_level_array_picks_first_object() -> None:
    raw = '[{"first": true}, {"second": true}]'
    assert extract_json_object(raw) == {"first": True}


def test_extract_json_object_backticks_inside_string_values() -> None:
    raw = '{"note": "use `code` blocks in markdown"}'
    assert extract_json_object(raw)["note"] == "use `code` blocks in markdown"


def test_extract_json_object_invalid_raises() -> None:
    with pytest.raises(ValueError, match="parse JSON"):
        extract_json_object("not json at all")
