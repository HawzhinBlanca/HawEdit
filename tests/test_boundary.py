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

import itertools
from collections import Counter

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
    """§3 Stage 5: TimeLens2 "does not produce editorial cuts" — one input among five.

    The interval's *start* is supplied alongside its end throughout this file because fusion
    now requires the pair: an end on its own cannot be asked whether the evidence is about
    this clip. `tests/test_timelens.py` covers that refusal and why it exists.
    """
    boundary = fuse_boundary(
        inputs(
            timelens_interval_start_ms=ANCHOR_OUT - 15_000,
            timelens_interval_end_ms=ANCHOR_OUT - 10_000,
        )
    )
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
    boundary = fuse_boundary(
        inputs(
            timelens_interval_start_ms=ANCHOR_OUT - 2_000,
            timelens_interval_end_ms=ANCHOR_OUT + 2_000,
        )
    )
    assert boundary.final_out_ms == ANCHOR_OUT + 2_000
    assert boundary.out_extended_by == "timelens_interval_end"


def test_a_speaker_turn_end_extends_the_out_point() -> None:
    boundary = fuse_boundary(inputs(speaker_turn_end_ms=ANCHOR_OUT + 3_000))
    assert boundary.out_extended_by == "speaker_turn_end"


def test_the_latest_candidate_wins() -> None:
    boundary = fuse_boundary(
        inputs(
            natural_silence_ms=ANCHOR_OUT + 500,
            timelens_interval_start_ms=ANCHOR_OUT - 1_000,
            timelens_interval_end_ms=ANCHOR_OUT + 4_000,
            speaker_turn_end_ms=ANCHOR_OUT + 1_000,
        )
    )
    assert boundary.final_out_ms == ANCHOR_OUT + 4_000
    assert boundary.out_extended_by == "timelens_interval_end"


# --- Kurdish invariant #2 ---------------------------------------------------------------


def test_the_invariant_holds_across_every_combination_of_soft_inputs() -> None:
    """Exhaustive over the sign of every optional input: inward candidates must never win.

    "Exhaustive" is now true. It was not: this swept five of `BoundaryInputs`' seven optional
    fields, omitting `media_duration_ms` and — more to the point — `natural_silence_ms`, which
    D-070 wired into the runner as §3's fourth out-point signal without extending the sweep that
    two ledger rows cite as proof of Kurdish invariant #2. Found by the 2026-08-09 adversarial
    pass; 3,125 combinations became 78,125. D-078.

    The counts are asserted, not just the invariant. A field quietly dropped from the product
    shrinks the space, and a sweep that silently got smaller is exactly how this claim went
    stale in the first place.
    """
    offsets = (-5_000, -300, 0, 300, 5_000)
    built = 0
    refusals: Counter[str] = Counter()
    for vad, cut, turn_start, turn_end, lens, silence, duration in itertools.product(
        offsets, repeat=7
    ):
        try:
            boundary = fuse_boundary(
                inputs(
                    vad_onset_ms=ANCHOR_IN + vad,
                    shot_cuts_ms=(ANCHOR_IN + cut, ANCHOR_OUT + cut),
                    speaker_turn_start_ms=ANCHOR_IN + turn_start,
                    speaker_turn_end_ms=ANCHOR_OUT + turn_end,
                    # Overlapping the anchor for every offset, so this sweep keeps
                    # measuring the invariant rather than the relevance guard.
                    timelens_interval_start_ms=ANCHOR_IN + 100,
                    timelens_interval_end_ms=ANCHOR_OUT + lens,
                    natural_silence_ms=ANCHOR_OUT + silence,
                    media_duration_ms=ANCHOR_OUT + duration,
                )
            )
        except ValueError as exc:
            # A media file that ends before the anchored sentence does is refused by design
            # rather than clamped (clamping an anchor that does not fit would violate the very
            # invariant this sweep checks). Counted, not skipped: a refusal that started
            # happening for some *other* reason must not read as coverage.
            assert "is after the media ends" in str(exc), str(exc)
            refusals[type(exc).__name__] += 1
            continue
        built += 1
        assert boundary.final_in_ms <= boundary.anchor_in_ms
        assert boundary.final_out_ms >= boundary.anchor_out_ms

    # Two of the five duration offsets put the media end before anchor_out, so exactly two
    # fifths of the space is legitimately refused and three fifths must produce a boundary.
    assert built + sum(refusals.values()) == len(offsets) ** 7 == 78_125
    assert built == 46_875, built
    assert refusals == Counter({"ValueError": 31_250}), refusals


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


# --- the media has an end, and §3's soft extensions do not know it ----------------------
#
# `fuse_boundary` clamps `final_in` at 0 with the note "a clip cannot start before the media
# does". There was no matching upper clamp, because the function was never told where the media
# stops. So §3's `anchor_out + 200 ms tail` pushed `final_out` past the end of the file, and
# nothing downstream noticed until the encoded artifact was measured: the project's own
# end-to-end fixture asked for 4300 ms of a 4162 ms video and shipped a clip 138 ms short.


def test_the_tail_is_clamped_to_the_end_of_the_media() -> None:
    boundary = fuse_boundary(inputs(anchor_in_ms=0, anchor_out_ms=4_100, media_duration_ms=4_162))
    assert boundary.final_out_ms == 4_162
    assert boundary.final_out_ms >= boundary.anchor_out_ms


def test_without_a_duration_the_tail_still_overshoots_and_that_is_honest() -> None:
    """Absence is not permission, but it is not knowledge either: a caller that does not say
    how long the media is gets the §3 formula unclamped, and `render_clip` is the net."""
    boundary = fuse_boundary(inputs(anchor_in_ms=0, anchor_out_ms=4_100))
    assert boundary.final_out_ms == 4_300


def test_an_anchor_past_the_end_of_the_media_is_refused_not_clamped() -> None:
    """Clamping the *tail* is safe for Kurdish invariant #2 because the anchor still fits.
    An anchor that does not fit is a transcript claiming speech after the file ends, and
    clamping it would produce final_out < anchor_out — the invariant, violated by the fix."""
    with pytest.raises(ValueError, match="after the media ends"):
        fuse_boundary(inputs(anchor_in_ms=0, anchor_out_ms=5_000, media_duration_ms=4_162))


def test_every_soft_signal_is_clamped_not_just_the_tail() -> None:
    boundary = fuse_boundary(
        inputs(
            anchor_in_ms=0,
            anchor_out_ms=4_000,
            media_duration_ms=4_162,
            natural_silence_ms=9_000,
            speaker_turn_end_ms=8_000,
        )
    )
    assert boundary.final_out_ms == 4_162


def test_a_clamped_boundary_still_records_which_input_moved_it() -> None:
    """The clamp changes the number, not the provenance: §8.2 still asks which signal won."""
    boundary = fuse_boundary(
        inputs(
            anchor_in_ms=0, anchor_out_ms=4_000, media_duration_ms=4_162, natural_silence_ms=9_000
        )
    )
    assert boundary.out_extended_by == "natural_silence"


def test_a_non_positive_media_duration_is_refused() -> None:
    with pytest.raises(ValueError, match="media_duration_ms"):
        fuse_boundary(inputs(anchor_in_ms=0, anchor_out_ms=1_000, media_duration_ms=0))


# --- TimeLens is evidence for the OUT point only, and only about this clip ----------------
#
# §3 Stage 5's formula names `timelens_interval_end` in `final_out` and nowhere in `final_in`:
#
#   final_in  = earliest of { anchor_in, vad_onset − 120 ms,
#                             preceding shot_cut within 400 ms, speaker_turn_start }
#   final_out = latest   of { anchor_out + 200 ms tail, natural silence,
#                             following shot_cut within 400 ms,
#                             speaker_turn_end, timelens_interval_end }
#
# Nothing tested that asymmetry: adding the interval's start to the in-point candidate set left
# the whole suite green. Found by the second adversarial pass. D-092.


def test_timelens_never_moves_the_in_point() -> None:
    """The interval's start is not a §3 in-point candidate, however far back it reaches."""
    boundary = fuse_boundary(
        inputs(
            timelens_interval_start_ms=ANCHOR_IN - 30_000,
            timelens_interval_end_ms=ANCHOR_OUT + 5_000,
        )
    )
    assert boundary.final_in_ms == ANCHOR_IN, (
        "TimeLens moved the in point. §3 Stage 5 lists timelens_interval_end in final_out only; "
        "the interval is evidence about where a moment ends, not a cut."
    )
    assert boundary.in_extended_by is None
    # The control: it must still move the OUT point, or this test would pass for a boundary
    # that ignored TimeLens entirely.
    assert boundary.final_out_ms == ANCHOR_OUT + 5_000
    assert boundary.out_extended_by == "timelens_interval_end"
