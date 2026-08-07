"""The live check, tested for the things that must hold before it ever spends anything.

`smoke.py` is the one module that talks to the real API, so its tests are about restraint: it
must refuse without a key, it must not send anything until a human says yes, and its sample
transcript has to be genuine Sorani with coherent timings — a sample with a mistake in it would
make a real failure look like a model problem.
"""

from __future__ import annotations

import pytest

from hawedit2.smoke import SAMPLE, main
from hawedit2.transcripts import normalize_transcript


def test_without_a_key_it_refuses_and_names_the_panel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hawedit2.smoke.read_credential", lambda _n=None: None)
    assert main(["--yes"]) == 2


def test_it_sends_nothing_until_a_human_agrees(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two billed calls behind an unattended default would be a surprise on someone's invoice."""
    monkeypatch.setattr("hawedit2.smoke.read_credential", lambda _n=None: "a-key")
    monkeypatch.setattr("builtins.input", lambda _p="": "n")

    def explode(*_a: object, **_k: object) -> None:
        raise AssertionError("nothing may be sent before the confirmation")

    monkeypatch.setattr("hawedit2.smoke.PathADiscovery", explode)
    assert main([]) == 0


def test_a_declined_prompt_at_eof_also_sends_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Piped stdin must default to "no", not to "yes"."""
    monkeypatch.setattr("hawedit2.smoke.read_credential", lambda _n=None: "a-key")

    def eof(_prompt: str = "") -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)

    def explode(*_a: object, **_k: object) -> None:
        raise AssertionError("nothing may be sent")

    monkeypatch.setattr("hawedit2.smoke.PathADiscovery", explode)
    assert main([]) == 0


def test_the_sample_is_real_sorani_with_coherent_timings() -> None:
    """A sample with a mistake in it would make a real failure look like a model problem."""
    assert SAMPLE.words, "the sample carries no word timings, so Path A cannot locate a span"
    for earlier, later in zip(SAMPLE.words, SAMPLE.words[1:], strict=False):
        assert earlier.end_ms <= later.start_ms, f"{earlier.w} overlaps {later.w}"
        assert earlier.start_ms < earlier.end_ms
    assert all(any("؀" <= ch <= "ۿ" for ch in word.w) for word in SAMPLE.words)


def test_the_sample_is_already_in_the_section_4_1_normal_form() -> None:
    """§4.1 runs before the judge sees it; a non-normal sample would make the live check
    measure normalization rather than the model."""
    assert normalize_transcript(SAMPLE).text_ckb == SAMPLE.text_ckb
