"""Unit tests for examples/custom_pack tutorial pack."""

from __future__ import annotations

from examples.custom_pack import EchoInput, EchoPack


def test_echo_pack_run_from_input() -> None:
    pack = EchoPack(run_id="tutorial-1")
    result = pack.run_from_input(EchoInput(text="hello world"))
    assert result.echoed == "HELLO WORLD"
    assert result.word_count == 2


def test_echo_pack_run_string_api() -> None:
    pack = EchoPack()
    result = pack.run("ping")
    assert result.echoed == "PING"
    assert result.word_count == 1
