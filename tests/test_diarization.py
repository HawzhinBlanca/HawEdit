"""M0.10 — §8.1's diarization arm: Community-1 vs 3.1, DER and boundary reconciliation.

§3 Stage 0 chose Community-1 over `speaker-diarization-3.1` for exclusive diarization,
"which makes reconciliation with transcript timestamps materially easier — directly relevant
to Stage 5". So the benchmark measures both things: the DER the literature reports, and the
property this pipeline actually consumes — whether turn boundaries land on words.
"""

from __future__ import annotations

import pytest

from hawedit2.diarization import (
    OverlappingSegments,
    Segment,
    boundary_reconciliation,
    diarization_error_rate,
)
from hawedit2.transcripts import Word

REFERENCE = (
    Segment(0, 10_000, "A"),
    Segment(10_000, 20_000, "B"),
)


def words(*spans: tuple[int, int]) -> tuple[Word, ...]:
    return tuple(Word(w="w", start_ms=s, end_ms=e, conf=0.9) for s, e in spans)


# --- DER -------------------------------------------------------------------------------


def test_a_perfect_diarization_scores_zero() -> None:
    error = diarization_error_rate(REFERENCE, REFERENCE)
    assert error is not None
    assert error.der == 0.0


def test_speaker_labels_are_arbitrary_so_a_relabelling_is_not_an_error() -> None:
    """Diarizers invent their own labels; scoring SPK_01 vs A as confusion measures nothing."""
    relabelled = (Segment(0, 10_000, "SPK_07"), Segment(10_000, 20_000, "SPK_02"))
    error = diarization_error_rate(REFERENCE, relabelled)
    assert error is not None
    assert error.der == 0.0


def test_missed_speech_is_counted() -> None:
    partial = (Segment(0, 10_000, "A"),)
    error = diarization_error_rate(REFERENCE, partial)
    assert error is not None
    assert error.missed_ms == 10_000
    assert error.der == pytest.approx(0.5)


def test_false_alarm_is_counted() -> None:
    over_eager = (*REFERENCE, Segment(20_000, 25_000, "C"))
    error = diarization_error_rate(REFERENCE, over_eager)
    assert error is not None
    assert error.false_alarm_ms == 5_000
    assert error.der == pytest.approx(0.25)


def test_speaker_confusion_is_counted() -> None:
    """One speaker for the whole file: half the reference speech goes to the wrong person."""
    merged = (Segment(0, 20_000, "A"),)
    error = diarization_error_rate(REFERENCE, merged)
    assert error is not None
    assert error.confusion_ms == 10_000
    assert error.der == pytest.approx(0.5)


def test_the_breakdown_is_reported_not_just_the_rate() -> None:
    """Missed speech and confusion call for different fixes; one number hides which."""
    error = diarization_error_rate(REFERENCE, (Segment(0, 10_000, "A"),))
    assert error is not None
    assert (error.missed_ms, error.false_alarm_ms, error.confusion_ms) == (10_000, 0, 0)


def test_the_chosen_speaker_mapping_is_reported() -> None:
    relabelled = (Segment(0, 10_000, "SPK_07"), Segment(10_000, 20_000, "SPK_02"))
    error = diarization_error_rate(REFERENCE, relabelled)
    assert error is not None
    assert dict(error.speaker_mapping) == {"SPK_07": "A", "SPK_02": "B"}


def test_overlapping_reference_segments_are_refused() -> None:
    """§3 Stage 0 expects exclusive diarization — that is why Community-1 was chosen."""
    with pytest.raises(OverlappingSegments):
        diarization_error_rate((Segment(0, 10_000, "A"), Segment(5_000, 15_000, "B")), REFERENCE)


def test_overlapping_hypothesis_segments_are_refused() -> None:
    with pytest.raises(OverlappingSegments):
        diarization_error_rate(REFERENCE, (Segment(0, 10_000, "A"), Segment(5_000, 15_000, "B")))


def test_a_reference_with_no_speech_is_none_not_zero() -> None:
    assert diarization_error_rate((), REFERENCE) is None


def test_a_zero_length_segment_is_refused() -> None:
    with pytest.raises(ValueError, match="before it starts"):
        Segment(1_000, 1_000, "A")


# --- boundary reconciliation ----------------------------------------------------------


def test_turn_boundaries_on_word_boundaries_score_perfectly() -> None:
    aligned_words = words((0, 4_000), (4_000, 10_000), (10_000, 16_000), (16_000, 20_000))
    result = boundary_reconciliation(REFERENCE, aligned_words)
    assert result is not None
    assert result.mean_abs_error_ms == 0.0
    assert result.within_tolerance_rate == 1.0


def test_a_turn_boundary_landing_mid_word_is_measured() -> None:
    """§3 Stage 5 uses speaker_turn_start as a boundary input; mid-word is unusable."""
    drifting = words((0, 4_000), (4_000, 9_500), (10_500, 16_000), (16_000, 19_000))
    result = boundary_reconciliation(REFERENCE, drifting, tolerance_ms=120)
    assert result is not None
    assert result.mean_abs_error_ms > 0.0
    assert result.within_tolerance_rate < 1.0


def test_the_tolerance_is_recorded_with_the_result() -> None:
    result = boundary_reconciliation(REFERENCE, words((0, 20_000)), tolerance_ms=250)
    assert result is not None
    assert result.tolerance_ms == 250


def test_reconciliation_needs_both_turns_and_words() -> None:
    assert boundary_reconciliation((), words((0, 1_000))) is None
    assert boundary_reconciliation(REFERENCE, ()) is None


def test_every_turn_contributes_two_boundaries() -> None:
    result = boundary_reconciliation(REFERENCE, words((0, 20_000)))
    assert result is not None
    assert result.boundaries == 2 * len(REFERENCE)
