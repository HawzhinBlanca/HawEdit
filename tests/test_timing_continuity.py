"""Tests for timing tightening, protected pause preservation, and reaction validation (VE-09)."""

from __future__ import annotations

import pytest

from hawedit.timing_continuity import (
    ProtectedPause,
    ReactionCutaway,
    ReactionFabricationError,
    SpeechTruncationError,
    TightenedTimeline,
    tighten_with_continuity_protection,
    validate_reaction_cutaway,
)
from hawedit.transcripts import Word


def test_edit_cannot_fabricate_reaction_timing_or_cut_protected_pause() -> None:
    """VE-09: Timing tightening preserves complete speech, protected pauses, and reaction timing.

    WHEN timing is tightened or a reaction is selected, THE system SHALL preserve complete speech,
    protected pauses and the source's relevant temporal/causal relationships.
    """
    # Sample words with a dramatic pause between words 1 & 2,
    # and normal dead air between words 3 & 4
    # Word 1: 1000 - 1800 ms
    # Pause 1 (dramatic): 1800 - 4000 ms (2200 ms gap)
    # Word 2: 4000 - 4600 ms
    # Word 3: 4650 - 5200 ms
    # Pause 2 (dead air): 5200 - 7000 ms (1800 ms gap)
    # Word 4: 7000 - 7800 ms
    words = (
        Word("ئەمە", 1000, 1800, 0.98),
        Word("ڕاستییەکەیە", 4000, 4600, 0.97),
        Word("بۆیە", 4650, 5200, 0.99),
        Word("گرنگە", 7000, 7800, 0.96),
    )

    dramatic_pause = ProtectedPause(
        pause_id="dramatic_landing_beat",
        start_ms=1800,
        end_ms=4000,
        reason="Dramatic silence before revealing the core truth",
        min_retained_duration_ms=2000,
    )

    # 1. Tightening preserves the protected pause, while excising ordinary dead air
    timeline: TightenedTimeline = tighten_with_continuity_protection(
        words,
        clip_in_ms=500,
        clip_out_ms=8500,
        protected_pauses=(dramatic_pause,),
        silence_threshold_ms=600,
        target_gap_ms=150,
        word_boundary_buffer_ms=50,
    )

    assert "dramatic_landing_beat" in timeline.protected_pauses_preserved
    assert isinstance(timeline.to_dict(), dict)
    # Check that dramatic pause gap remains substantially retained (at least 2000ms preserved)
    # Interval between 1800 and 4000 must NOT be collapsed to 150ms!
    dramatic_excised = [
        (c_in, c_out) for c_in, c_out in timeline.excised_intervals if 1800 <= c_in < 4000
    ]
    total_dramatic_excised = sum(c_out - c_in for c_in, c_out in dramatic_excised)
    # Pause is 2200ms, min_retained is 2000ms => at most 200ms excised
    assert total_dramatic_excised <= 200

    # Conversely, unprotected dead air between 5200 and 7000 (1800ms) is tightened down
    dead_air_excised = [
        (c_in, c_out) for c_in, c_out in timeline.excised_intervals if 5200 <= c_in < 7000
    ]
    assert len(dead_air_excised) > 0
    total_dead_air_excised = sum(c_out - c_in for c_in, c_out in dead_air_excised)
    # Dead air of 1800ms is tightened by > 1400ms
    assert total_dead_air_excised > 1400

    # 2. Complete speech protection: No cut slices into word boundaries
    for cut_in, cut_out in timeline.excised_intervals:
        for w in words:
            assert not (max(cut_in, w.start_ms) < min(cut_out, w.end_ms))

    # Test that an edit slicing into words triggers SpeechTruncationError
    overlapping_words = (
        Word("وشە", 1000, 2000, 0.95),
        Word("دووەم", 2100, 3000, 0.95),
    )
    # Word gap is only 100ms, so normal silence threshold won't cut it.
    # But if an invalid configuration forces a cut inside the word, SpeechTruncationError is raised.
    with pytest.raises(SpeechTruncationError, match="speech truncation is strictly forbidden"):
        tighten_with_continuity_protection(
            overlapping_words,
            clip_in_ms=500,
            clip_out_ms=4000,
            silence_threshold_ms=50,
            target_gap_ms=0,
            word_boundary_buffer_ms=-200,  # Negative buffer forces cut into word!
        )

    # 3. Contemporaneous reaction validation: Valid reaction near speech is approved
    valid_reaction = ReactionCutaway(
        reaction_id="listener_nod_01",
        reaction_in_ms=4500,
        reaction_out_ms=6000,
        subject_id="listener_host",
        stimulus_in_ms=4000,
        stimulus_out_ms=4600,
        max_causal_delta_ms=3000,
    )
    validate_reaction_cutaway(valid_reaction)  # Must pass without error

    # 4. Reaction timing fabrication rejection:
    # Reaction from distant source time is strictly forbidden!
    # Example: Speech at minute 10 (600,000ms) paired with reaction from minute 40 (2,400,000ms)
    fabricated_reaction = ReactionCutaway(
        reaction_id="listener_laugh_fake",
        reaction_in_ms=2_400_000,  # Minute 40
        reaction_out_ms=2_403_000,
        subject_id="listener_guest",
        stimulus_in_ms=600_000,  # Minute 10
        stimulus_out_ms=605_000,
        max_causal_delta_ms=4000,
    )
    with pytest.raises(ReactionFabricationError, match="Fabricating contemporaneous reactions"):
        validate_reaction_cutaway(fabricated_reaction)

    with pytest.raises(ReactionFabricationError, match="Fabricating contemporaneous reactions"):
        tighten_with_continuity_protection(
            words,
            clip_in_ms=500,
            clip_out_ms=8500,
            reactions=(fabricated_reaction,),
        )


def test_protected_pause_and_reaction_data_models() -> None:
    """Validate data models, error handling, and serialization for timing continuity."""
    # Invalid pause: min_retained exceeds duration
    with pytest.raises(ValueError, match="cannot exceed total pause duration"):
        ProtectedPause(
            pause_id="invalid_pause",
            start_ms=1000,
            end_ms=2000,  # duration = 1000ms
            reason="Invalid",
            min_retained_duration_ms=1500,  # 1500 > 1000!
        )

    # Invalid reaction timestamps
    with pytest.raises(ValueError, match="reaction_out_ms must be > reaction_in_ms"):
        ReactionCutaway(
            reaction_id="invalid_rx",
            reaction_in_ms=5000,
            reaction_out_ms=4000,  # inverted
            subject_id="sub_01",
            stimulus_in_ms=1000,
            stimulus_out_ms=2000,
        )

    pause = ProtectedPause(
        pause_id="p1",
        start_ms=1000,
        end_ms=3000,
        reason="Dramatic hesitation",
        min_retained_duration_ms=1500,
    )
    assert pause.duration_ms == 2000
    p_dict = pause.to_dict()
    assert p_dict["duration_ms"] == 2000

    rx = ReactionCutaway(
        reaction_id="rx1",
        reaction_in_ms=2500,
        reaction_out_ms=4000,
        subject_id="sub_01",
        stimulus_in_ms=1000,
        stimulus_out_ms=2000,
    )
    assert rx.duration_ms == 1500
    rx_dict = rx.to_dict()
    assert rx_dict["duration_ms"] == 1500
