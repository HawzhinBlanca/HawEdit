"""M2.2 — §3 Stage 5 boundary fusion, and Kurdish invariant #2.

    #2  Every rendered clip: final_in <= anchor_in AND final_out >= anchor_out.
        sentence_complete == false ⇒ reject, never render.

§3 Stage 5 states the algorithm exactly, and the shape of it is the point: the sentence
anchors are a HARD constraint, and every other signal — VAD onset, shot cuts, speaker turns,
TimeLens2's interval — may only extend the clip **outward**. A soft input that would pull the
boundary inward is discarded, not applied.

§3 Stage 5 on why this one invariant carries so much weight: "This single invariant accounts
for most of the perceived quality gap between an auto-clipper that feels professional and one
that feels broken."
"""

from __future__ import annotations

import pytest

from hawedit.boundary import (
    SHOT_CUT_WINDOW_MS,
    TAIL_MS,
    VAD_LEAD_IN_MS,
    Boundary,
    BoundaryInputs,
    BoundaryInvariantViolated,
    IncompleteSentence,
    assert_boundary_invariant,
    fuse_boundary,
)

ANCHOR_IN = 84_600
ANCHOR_OUT = 112_400


def inputs(**overrides: object) -> BoundaryInputs:
    payload: dict[str, object] = {
        "anchor_in_ms": ANCHOR_IN,
        "anchor_out_ms": ANCHOR_OUT,
        "sentence_complete": True,
    }
    payload.update(overrides)
    return BoundaryInputs(**payload)  # type: ignore[arg-type]


# --- the blueprint's constants ---------------------------------------------------------


def test_the_constants_are_the_ones_section_3_stage_5_states() -> None:
    assert VAD_LEAD_IN_MS == 120
    assert TAIL_MS == 200
    assert SHOT_CUT_WINDOW_MS == 400


# --- with no soft evidence the anchors stand ------------------------------------------


def test_with_no_soft_inputs_the_in_point_is_the_anchor() -> None:
    boundary = fuse_boundary(inputs())
    assert boundary.final_in_ms == ANCHOR_IN
    assert boundary.in_extended_by is None


def test_the_tail_always_extends_the_out_point() -> None:
    """§3 Stage 5's out set includes `anchor_out + 200 ms tail` unconditionally."""
    boundary = fuse_boundary(inputs())
    assert boundary.final_out_ms == ANCHOR_OUT + TAIL_MS
    assert boundary.out_extended_by == "tail"


# --- the in point: earliest of the candidates -----------------------------------------


def test_a_vad_onset_extends_the_in_point_by_its_lead_in() -> None:
    boundary = fuse_boundary(inputs(vad_onset_ms=ANCHOR_IN - 300))
    assert boundary.final_in_ms == ANCHOR_IN - 300 - VAD_LEAD_IN_MS
    assert boundary.in_extended_by == "vad_onset"


def test_a_shot_cut_just_before_the_anchor_extends_the_in_point() -> None:
    cut = ANCHOR_IN - 350
    boundary = fuse_boundary(inputs(shot_cuts_ms=(cut,)))
    assert boundary.final_in_ms == cut
    assert boundary.in_extended_by == "shot_cut"


def test_a_shot_cut_outside_the_window_is_ignored() -> None:
    """§3 Stage 5 says "preceding shot_cut within 400 ms" — 500 ms away is not evidence."""
    boundary = fuse_boundary(inputs(shot_cuts_ms=(ANCHOR_IN - 500,)))
    assert boundary.final_in_ms == ANCHOR_IN
    assert boundary.in_extended_by is None


def test_a_shot_cut_after_the_anchor_is_not_a_preceding_cut() -> None:
    boundary = fuse_boundary(inputs(shot_cuts_ms=(ANCHOR_IN + 100,)))
    assert boundary.final_in_ms == ANCHOR_IN


def test_a_speaker_turn_start_extends_the_in_point() -> None:
    boundary = fuse_boundary(inputs(speaker_turn_start_ms=ANCHOR_IN - 800))
    assert boundary.final_in_ms == ANCHOR_IN - 800
    assert boundary.in_extended_by == "speaker_turn_start"


def test_the_earliest_candidate_wins() -> None:
    boundary = fuse_boundary(
        inputs(
            vad_onset_ms=ANCHOR_IN - 200,
            shot_cuts_ms=(ANCHOR_IN - 350,),
            speaker_turn_start_ms=ANCHOR_IN - 900,
        )
    )
    assert boundary.final_in_ms == ANCHOR_IN - 900
    assert boundary.in_extended_by == "speaker_turn_start"


# --- soft inputs may only extend OUTWARD ----------------------------------------------


def test_a_vad_onset_inside_the_anchor_never_pulls_the_in_point_inward() -> None:
    """ "SOFT ADJUSTMENT — may only extend OUTWARD." A later onset is discarded."""
    boundary = fuse_boundary(inputs(vad_onset_ms=ANCHOR_IN + 5_000))
    assert boundary.final_in_ms == ANCHOR_IN
    assert boundary.in_extended_by is None


def test_a_speaker_turn_start_inside_the_anchor_is_discarded() -> None:
    boundary = fuse_boundary(inputs(speaker_turn_start_ms=ANCHOR_IN + 2_000))
    assert boundary.final_in_ms == ANCHOR_IN


def test_a_speaker_turn_end_inside_the_anchor_is_discarded() -> None:
    boundary = fuse_boundary(inputs(speaker_turn_end_ms=ANCHOR_OUT - 5_000))
    assert boundary.final_out_ms >= ANCHOR_OUT


def test_a_timelens_interval_ending_early_never_shortens_the_clip() -> None:
    """§3 Stage 5: TimeLens2 "does not produce editorial cuts" — one input among five."""
    boundary = fuse_boundary(inputs(timelens_interval_end_ms=ANCHOR_OUT - 10_000))
    assert boundary.final_out_ms >= ANCHOR_OUT


# --- the out point: latest of the candidates ------------------------------------------


def test_a_following_shot_cut_extends_the_out_point() -> None:
    cut = ANCHOR_OUT + 380
    boundary = fuse_boundary(inputs(shot_cuts_ms=(cut,)))
    assert boundary.final_out_ms == cut
    assert boundary.out_extended_by == "shot_cut"


def test_a_following_shot_cut_outside_the_window_is_ignored() -> None:
    boundary = fuse_boundary(inputs(shot_cuts_ms=(ANCHOR_OUT + 900,)))
    assert boundary.final_out_ms == ANCHOR_OUT + TAIL_MS


def test_natural_silence_extends_the_out_point() -> None:
    boundary = fuse_boundary(inputs(natural_silence_ms=ANCHOR_OUT + 1_500))
    assert boundary.final_out_ms == ANCHOR_OUT + 1_500
    assert boundary.out_extended_by == "natural_silence"


def test_a_timelens_interval_end_extends_the_out_point() -> None:
    boundary = fuse_boundary(inputs(timelens_interval_end_ms=ANCHOR_OUT + 2_000))
    assert boundary.final_out_ms == ANCHOR_OUT + 2_000
    assert boundary.out_extended_by == "timelens_interval_end"


def test_a_speaker_turn_end_extends_the_out_point() -> None:
    boundary = fuse_boundary(inputs(speaker_turn_end_ms=ANCHOR_OUT + 3_000))
    assert boundary.out_extended_by == "speaker_turn_end"


def test_the_latest_candidate_wins() -> None:
    boundary = fuse_boundary(
        inputs(
            natural_silence_ms=ANCHOR_OUT + 500,
            timelens_interval_end_ms=ANCHOR_OUT + 4_000,
            speaker_turn_end_ms=ANCHOR_OUT + 1_000,
        )
    )
    assert boundary.final_out_ms == ANCHOR_OUT + 4_000
    assert boundary.out_extended_by == "timelens_interval_end"


# --- Kurdish invariant #2 ---------------------------------------------------------------


def test_the_invariant_holds_across_every_combination_of_soft_inputs() -> None:
    """Exhaustive over the sign of each input: inward candidates must never win."""
    offsets = (-5_000, -300, 0, 300, 5_000)
    for vad in offsets:
        for cut in offsets:
            for turn_start in offsets:
                for turn_end in offsets:
                    for lens in offsets:
                        boundary = fuse_boundary(
                            inputs(
                                vad_onset_ms=ANCHOR_IN + vad,
                                shot_cuts_ms=(ANCHOR_IN + cut, ANCHOR_OUT + cut),
                                speaker_turn_start_ms=ANCHOR_IN + turn_start,
                                speaker_turn_end_ms=ANCHOR_OUT + turn_end,
                                timelens_interval_end_ms=ANCHOR_OUT + lens,
                            )
                        )
                        assert boundary.final_in_ms <= boundary.anchor_in_ms
                        assert boundary.final_out_ms >= boundary.anchor_out_ms


def test_an_incomplete_sentence_is_rejected_never_rendered() -> None:
    """§5: `sentence_complete == false ⇒ reject`. Not "clamp", not "warn"."""
    with pytest.raises(IncompleteSentence) as exc:
        fuse_boundary(inputs(sentence_complete=False))
    assert "sentence_complete" in str(exc.value)


def test_the_render_gate_catches_a_violating_boundary_from_anywhere() -> None:
    """ "assert before render" must work on a Boundary this module did not build — a
    deserialized one, or one from a future stage. Hence a standalone assertion."""
    smuggled = Boundary(
        anchor_in_ms=ANCHOR_IN,
        anchor_out_ms=ANCHOR_OUT,
        final_in_ms=ANCHOR_IN + 1,  # inside the anchor: mid-sentence start
        final_out_ms=ANCHOR_OUT + TAIL_MS,
        in_extended_by=None,
        out_extended_by="tail",
        sentence_complete=True,
    )
    with pytest.raises(BoundaryInvariantViolated, match="final_in"):
        assert_boundary_invariant(smuggled)


def test_the_render_gate_catches_a_truncated_out_point() -> None:
    smuggled = Boundary(
        anchor_in_ms=ANCHOR_IN,
        anchor_out_ms=ANCHOR_OUT,
        final_in_ms=ANCHOR_IN,
        final_out_ms=ANCHOR_OUT - 1,
        in_extended_by=None,
        out_extended_by=None,
        sentence_complete=True,
    )
    with pytest.raises(BoundaryInvariantViolated, match="final_out"):
        assert_boundary_invariant(smuggled)


def test_the_render_gate_rejects_an_incomplete_sentence() -> None:
    smuggled = Boundary(
        anchor_in_ms=ANCHOR_IN,
        anchor_out_ms=ANCHOR_OUT,
        final_in_ms=ANCHOR_IN,
        final_out_ms=ANCHOR_OUT + TAIL_MS,
        in_extended_by=None,
        out_extended_by="tail",
        sentence_complete=False,
    )
    with pytest.raises(BoundaryInvariantViolated, match="sentence_complete"):
        assert_boundary_invariant(smuggled)


def test_a_boundary_built_by_fusion_always_passes_the_render_gate() -> None:
    assert_boundary_invariant(fuse_boundary(inputs(vad_onset_ms=ANCHOR_IN - 400)))


# --- malformed anchors ------------------------------------------------------------------


def test_anchors_that_do_not_move_forward_are_refused() -> None:
    with pytest.raises(ValueError, match="anchor"):
        fuse_boundary(inputs(anchor_out_ms=ANCHOR_IN))


def test_a_negative_anchor_is_refused() -> None:
    with pytest.raises(ValueError, match="negative"):
        fuse_boundary(inputs(anchor_in_ms=-1))


def test_an_in_point_never_goes_below_zero() -> None:
    """A clip cannot start before the media does, however far a soft input reaches back."""
    boundary = fuse_boundary(
        BoundaryInputs(
            anchor_in_ms=50,
            anchor_out_ms=10_000,
            sentence_complete=True,
            vad_onset_ms=10,
        )
    )
    assert boundary.final_in_ms == 0


# --- the §5 record ----------------------------------------------------------------------


def test_the_boundary_serialises_to_the_section_5_shape() -> None:
    payload = fuse_boundary(inputs(vad_onset_ms=ANCHOR_IN - 300, shot_cuts_ms=(ANCHOR_OUT + 100,)))
    record = payload.to_dict()
    assert set(record) == {
        "anchor_in_ms",
        "anchor_out_ms",
        "in_extended_by",
        "out_extended_by",
        "sentence_complete",
        "confidence",
        "final_in_ms",
        "final_out_ms",
    }
    assert record["in_extended_by"] == "vad_onset"
    assert record["sentence_complete"] is True


def test_confidence_is_carried_through() -> None:
    boundary = fuse_boundary(inputs(), confidence=0.91)
    assert boundary.confidence == pytest.approx(0.91)


def test_confidence_outside_zero_to_one_is_refused() -> None:
    with pytest.raises(ValueError, match="confidence"):
        fuse_boundary(inputs(), confidence=1.4)
