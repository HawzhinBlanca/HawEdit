"""The live check, tested for the things that must hold before it ever spends anything.

`smoke.py` is the one module that talks to the real API, so its tests are about restraint: it
must refuse without a key, it must not send anything until a human says yes, and its sample
transcript has to be genuine Sorani with coherent timings — a sample with a mistake in it would
make a real failure look like a model problem.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hawedit.smoke import SAMPLE, main
from hawedit.transcripts import normalize_transcript


def test_without_a_key_it_refuses_and_names_the_panel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hawedit.smoke.read_credential", lambda _n=None: None)
    assert main(["--yes"]) == 2


def test_it_sends_nothing_until_a_human_agrees(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Two billed calls behind an unattended default would be a surprise on someone's invoice.

    Carries a `--video` since D-152, so the run it declines is one that could otherwise have
    proceeded — declining a run that would have refused anyway measures nothing.
    """
    video = tmp_path / "sample.mp4"
    video.write_bytes(b"a real file")
    monkeypatch.setattr("hawedit.smoke.read_credential", lambda _n=None: "a-key")
    monkeypatch.setattr("builtins.input", lambda _p="": "n")

    def explode(*_a: object, **_k: object) -> None:
        raise AssertionError("nothing may be sent before the confirmation")

    monkeypatch.setattr("hawedit.smoke.PathADiscovery", explode)
    assert main(["--video", str(video)]) == 0


def test_a_declined_prompt_at_eof_also_sends_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Piped stdin must default to "no", not to "yes"."""
    video = tmp_path / "sample.mp4"
    video.write_bytes(b"a real file")
    monkeypatch.setattr("hawedit.smoke.read_credential", lambda _n=None: "a-key")

    def eof(_prompt: str = "") -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)

    def explode(*_a: object, **_k: object) -> None:
        raise AssertionError("nothing may be sent")

    monkeypatch.setattr("hawedit.smoke.PathADiscovery", explode)
    assert main(["--video", str(video)]) == 0


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


# --- D-152: the documented invocation spent money and then refused ---------------------------
#
# README offers `python -m hawedit.smoke  # two real calls, ~$0.003` and says it "runs §3 Stage 3
# Path A ... and §3 Stage 4 on the top candidate, then prints the Kurdish title it got back".
# Run exactly as documented it made both Path A calls, printed the candidates, and *then* hit
# `Stage 4 needs --video` and exited 1 — having never run Stage 4 and never printed a title.
# `--video` appears nowhere in the README. D-071's shape: a refusal argv settles, placed after
# the billed call. `evidence/the-live-check-spent-money-then-refused.md`.
# =========================================================================================


class _Billed(Exception):
    """Reaching Path A means two real API calls would be made."""


def _nothing_may_be_billed(*_a: object, **_k: object) -> None:
    raise _Billed("a billed call was about to happen")


def test_the_documented_invocation_refuses_before_spending_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The artifact of this fix is a request that never happened.

    `--yes` skips the confirmation, so nothing but the guard can stop it: if the refusal is back
    after Path A, `_Billed` escapes and this errors rather than returning 2.
    """
    monkeypatch.setattr("hawedit.smoke.read_credential", lambda _n=None: "a-key")
    monkeypatch.setattr("hawedit.smoke.PathADiscovery", _nothing_may_be_billed)
    assert main(["--yes"]) == 2


def test_a_video_that_is_not_there_is_also_refused_before_spending(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A path typo must not cost anything either — it is knowable from argv just the same."""
    monkeypatch.setattr("hawedit.smoke.read_credential", lambda _n=None: "a-key")
    monkeypatch.setattr("hawedit.smoke.PathADiscovery", _nothing_may_be_billed)
    assert main(["--yes", "--video", str(tmp_path / "absent.mp4")]) == 2


def test_the_confirmation_is_never_asked_for_a_run_that_cannot_finish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Being asked to authorise spending on a run that will refuse is its own defect."""
    monkeypatch.setattr("hawedit.smoke.read_credential", lambda _n=None: "a-key")
    monkeypatch.setattr("hawedit.smoke.PathADiscovery", _nothing_may_be_billed)

    def asked(_prompt: str = "") -> str:
        raise AssertionError("the user was asked to confirm a run that cannot reach Stage 4")

    monkeypatch.setattr("builtins.input", asked)
    assert main([]) == 2


def test_with_a_video_it_gets_as_far_as_the_billed_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The control, and it has to be one: a `main` that refused *everything* — or one that never
    reached Path A at all — passes all three tests above.

    So this requires the legal invocation to get through the guard and arrive at the spend.
    """
    video = tmp_path / "sample.mp4"
    video.write_bytes(b"a real file, which is all the guard checks")
    monkeypatch.setattr("hawedit.smoke.read_credential", lambda _n=None: "a-key")
    monkeypatch.setattr("hawedit.smoke.PathADiscovery", _nothing_may_be_billed)

    with pytest.raises(_Billed):
        main(["--yes", "--video", str(video)])
