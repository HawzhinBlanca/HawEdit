"""M0.8 — "alignment accuracy from CTC emissions" (§8.1), and Kurdish invariant #5.

    #5  Word timings come from OmniASR CTC Viterbi alignment only.

§4.2 makes this the second of the three things that decide whether the system works: "ASR
gives you text, not reliable word timing. Boundaries that don't land on sentence edges
produce clips that feel broken regardless of model quality." Everything downstream leans on
these numbers — §5's sentence anchors, and through them the hard boundary invariant in §3
Stage 5.

So invariant #5 is enforced where word timings are constructed, not merely described: a
transcript that carries words must declare `ctc_viterbi` as its aligner, and any other value
is refused. Timings sourced from a decoder's guess, or from an NC-licensed aligner §4.2
explicitly forbids, cannot enter the system and be discovered later.
"""

from __future__ import annotations

import pytest

from hawedit.alignment import CTC_VITERBI, score_alignment
from hawedit.transcripts import AsrProvenance, RawTranscript, Word

CTC = AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner=CTC_VITERBI)


def words(*specs: tuple[str, int, int]) -> tuple[Word, ...]:
    return tuple(Word(w=w, start_ms=s, end_ms=e, conf=0.9) for w, s, e in specs)


REFERENCE = words(("ئەمە", 1000, 1300), ("زۆر", 1300, 1600), ("باشە", 1600, 2000))


# --- invariant #5 ---------------------------------------------------------------------


def test_word_timings_from_a_non_ctc_aligner_are_refused() -> None:
    """§4.2 forbids mms-300m-1130-forced-aligner and ctc-forced-aligner (CC-BY-NC-4.0),
    and invariant #5 admits exactly one source of timings."""
    with pytest.raises(ValueError, match="ctc_viterbi"):
        AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="mms-300m-1130-forced-aligner")


def test_a_transcript_with_words_must_declare_an_aligner() -> None:
    with pytest.raises(ValueError, match="aligner"):
        RawTranscript(
            media_id="m",
            text_ckb="ئەمە",
            words=words(("ئەمە", 0, 100)),
            asr=AsrProvenance(canonical="omniASR_LLM_7B_v2"),
        )


def test_a_transcript_without_words_needs_no_aligner() -> None:
    RawTranscript(
        media_id="m",
        text_ckb="ئەمە",
        words=(),
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2"),
    )


def test_scoring_refuses_timings_that_did_not_come_from_ctc_viterbi() -> None:
    with pytest.raises(ValueError, match="ctc_viterbi"):
        score_alignment(REFERENCE, REFERENCE, AsrProvenance(canonical="omniASR_LLM_7B_v2"))


# --- accuracy -------------------------------------------------------------------------


def test_perfect_timings_score_zero_error() -> None:
    accuracy = score_alignment(REFERENCE, REFERENCE, CTC)
    assert accuracy is not None
    assert accuracy.mean_onset_abs_error_ms == 0.0
    assert accuracy.mean_offset_abs_error_ms == 0.0
    assert accuracy.within_tolerance_rate == 1.0
    assert accuracy.coverage == 1.0


def test_a_small_shift_stays_within_tolerance() -> None:
    shifted = words(("ئەمە", 1030, 1330), ("زۆر", 1330, 1630), ("باشە", 1630, 2030))
    accuracy = score_alignment(REFERENCE, shifted, CTC, tolerance_ms=50)
    assert accuracy is not None
    assert accuracy.mean_onset_abs_error_ms == pytest.approx(30.0)
    assert accuracy.within_tolerance_rate == 1.0


def test_a_large_shift_falls_outside_tolerance() -> None:
    shifted = words(("ئەمە", 1200, 1500), ("زۆر", 1500, 1800), ("باشە", 1800, 2200))
    accuracy = score_alignment(REFERENCE, shifted, CTC, tolerance_ms=50)
    assert accuracy is not None
    assert accuracy.within_tolerance_rate == 0.0
    assert accuracy.mean_onset_abs_error_ms == pytest.approx(200.0)


def test_only_words_that_actually_match_are_timed() -> None:
    """Comparing timings of words the model never produced would measure nothing."""
    partly_wrong = words(("ئەمە", 1000, 1300), ("خراپ", 1300, 1600), ("باشە", 1600, 2000))
    accuracy = score_alignment(REFERENCE, partly_wrong, CTC)
    assert accuracy is not None
    assert accuracy.matched_words == 2
    assert accuracy.reference_words == 3
    assert accuracy.coverage == pytest.approx(2 / 3)
    assert accuracy.mean_onset_abs_error_ms == 0.0


def test_word_matching_is_normalization_insensitive() -> None:
    """A §4.1 keyboard difference must not be read as a word the model failed to produce."""
    other_encoding = words(("ئەمە", 1000, 1300), ("زۆر", 1300, 1600), ("باشه‌", 1600, 2000))
    accuracy = score_alignment(
        words(("ئەمە", 1000, 1300), ("زۆر", 1300, 1600), ("باشە", 1600, 2000)),
        other_encoding,
        CTC,
    )
    assert accuracy is not None
    assert accuracy.matched_words == 3


def test_nothing_matched_is_none_not_zero_error() -> None:
    """Zero error over zero matched words would be the best score in the report."""
    assert score_alignment(REFERENCE, words(("هیچ", 0, 100)), CTC) is None


def test_an_empty_reference_is_none() -> None:
    assert score_alignment((), REFERENCE, CTC) is None


def test_tolerance_is_recorded_with_the_result() -> None:
    """A within-tolerance rate is meaningless without the tolerance it used."""
    accuracy = score_alignment(REFERENCE, REFERENCE, CTC, tolerance_ms=20)
    assert accuracy is not None
    assert accuracy.tolerance_ms == 20
