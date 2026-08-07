"""§3 Stage 5 — TimeLens2-4B as a producer, and the relevance its number was missing.

§3 Stage 5 opens with a warning rather than a formula:

    **TimeLens2-4B returns intervals containing relevant visual evidence. It does not produce
    editorial cuts and cannot locate a speech-only idea without transcript timing.** Treat its
    output as one input among five.

`boundary.py` honoured the second half of that from the day it was written — the interval is
one of five soft signals and may only extend outward. It could not honour the first half,
because what reached it was `timelens_interval_end_ms`: a bare integer, with no way to ask
which interval produced it or whether that interval was about this clip at all.

That gap has a shape. An interval at 5:00 of a long episode, ending at 5:05, fed to a boundary
anchored at 10–14 s, extends `final_out` to 305 000 ms. Kurdish invariant #2 holds —
`final_out >= anchor_out` is satisfied handsomely. The arithmetic is right, the invariant
passes, and the clip runs from one Kurdish sentence into five minutes of unrelated footage.
The invariant checks *direction*; nothing checked *relevance*.
"""

from __future__ import annotations

import pytest

from hawedit.boundary import BoundaryInputs, fuse_boundary
from hawedit.registry import ModelNotInRegistry, WrongRole
from hawedit.timelens import (
    TIMELENS_MODEL,
    VisualEvidenceInterval,
    interval_end_for_fusion,
)

ANCHOR_IN = 10_000
ANCHOR_OUT = 14_000


def an_interval(
    start_ms: int = 12_000,
    end_ms: int = 16_000,
    *,
    media_id: str = "m1",
    claim: str = "speaker raises both hands at 12.4s",
    confidence: float | None = 0.8,
    model_id: str = TIMELENS_MODEL,
) -> VisualEvidenceInterval:
    return VisualEvidenceInterval(
        media_id=media_id,
        start_ms=start_ms,
        end_ms=end_ms,
        claim=claim,
        confidence=confidence,
        model_id=model_id,
    )


# =========================================================================================
# VisualEvidenceInterval — what the model returns, and what it may not claim to be
# =========================================================================================


def test_a_well_formed_interval_is_accepted() -> None:
    interval = an_interval()
    assert interval.span == (12_000, 16_000)
    assert interval.duration_ms == 4_000


def test_a_model_outside_the_registry_is_refused() -> None:
    with pytest.raises(ModelNotInRegistry):
        an_interval(model_id="some-video-model")


def test_a_registry_model_in_the_wrong_role_is_refused() -> None:
    """§7 lists TimeLens2 as 'Visual temporal evidence' and VideoChat3 as 'Local video
    understanding'. They are different jobs and the registry knows it."""
    with pytest.raises(WrongRole):
        an_interval(model_id="MCG-NJU/VideoChat3-4B")


def test_a_zero_length_interval_is_refused() -> None:
    with pytest.raises(ValueError, match="no length"):
        an_interval(12_000, 12_000)


def test_a_negative_start_is_refused() -> None:
    with pytest.raises(ValueError, match="negative"):
        an_interval(-1, 16_000)


def test_an_interval_with_no_claim_is_refused() -> None:
    """§3 Stage 3's rule for SV6D applies here for the same reason: 'Reject output where a
    claim has no timeline evidence.' An interval carrying no claim is a span of time asserting
    nothing, and it would still extend a boundary."""
    with pytest.raises(ValueError, match="claim"):
        an_interval(claim="   ")


def test_confidence_outside_the_unit_range_is_refused() -> None:
    with pytest.raises(ValueError, match="confidence"):
        an_interval(confidence=1.4)


def test_unmeasured_confidence_is_none_and_is_allowed() -> None:
    """`None` is not the same as 0.0 and must survive: a model that reports no confidence has
    not reported low confidence."""
    assert an_interval(confidence=None).confidence is None


# =========================================================================================
# interval_end_for_fusion — the selection §3 leaves implicit and a naive reading gets wrong
# =========================================================================================


def test_an_interval_overlapping_the_anchor_supplies_its_end() -> None:
    end = interval_end_for_fusion(
        [an_interval(12_000, 16_000)], anchor_in_ms=ANCHOR_IN, anchor_out_ms=ANCHOR_OUT
    )
    assert end == 16_000


def test_an_interval_about_a_different_moment_is_not_eligible() -> None:
    """The core finding. Naively, `latest of {…, timelens_interval_end}` reads as "the largest
    interval end in the episode", and that is a five-minute clip with a passing invariant."""
    end = interval_end_for_fusion(
        [an_interval(300_000, 305_000)], anchor_in_ms=ANCHOR_IN, anchor_out_ms=ANCHOR_OUT
    )
    assert end is None


def test_the_distant_interval_is_ignored_even_when_a_relevant_one_exists() -> None:
    """Selecting by `max(end)` over everything returns 305 000 here. Selecting by relevance
    first returns 16 000. Both are one line of code; only one of them is Stage 5."""
    end = interval_end_for_fusion(
        [an_interval(12_000, 16_000), an_interval(300_000, 305_000)],
        anchor_in_ms=ANCHOR_IN,
        anchor_out_ms=ANCHOR_OUT,
    )
    assert end == 16_000


def test_the_latest_end_among_overlapping_intervals_wins() -> None:
    end = interval_end_for_fusion(
        [an_interval(11_000, 15_000), an_interval(13_000, 18_000)],
        anchor_in_ms=ANCHOR_IN,
        anchor_out_ms=ANCHOR_OUT,
    )
    assert end == 18_000


def test_an_interval_that_ends_before_the_anchor_does_supplies_nothing() -> None:
    """It overlaps, so it is about this moment — but it cannot extend outward, and §3 Stage 5
    allows soft signals to extend only outward. Returning it would be noise in
    `out_extended_by`, claiming TimeLens2 moved a boundary it did not move."""
    end = interval_end_for_fusion(
        [an_interval(10_500, 12_000)], anchor_in_ms=ANCHOR_IN, anchor_out_ms=ANCHOR_OUT
    )
    assert end is None


def test_no_intervals_at_all_is_none_rather_than_zero() -> None:
    assert interval_end_for_fusion([], anchor_in_ms=ANCHOR_IN, anchor_out_ms=ANCHOR_OUT) is None


def test_an_interval_from_another_media_is_refused_not_skipped() -> None:
    """Skipping it quietly would let a whole episode's evidence be silently discarded because
    of a media_id typo, and the run would look identical to one with no visual evidence."""
    with pytest.raises(ValueError, match="media"):
        interval_end_for_fusion(
            [an_interval(12_000, 16_000, media_id="other")],
            anchor_in_ms=ANCHOR_IN,
            anchor_out_ms=ANCHOR_OUT,
            media_id="m1",
        )


def test_touching_at_a_single_instant_is_not_overlap() -> None:
    """An interval starting exactly where the anchor ends shares no footage with the clip."""
    end = interval_end_for_fusion(
        [an_interval(ANCHOR_OUT, 20_000)], anchor_in_ms=ANCHOR_IN, anchor_out_ms=ANCHOR_OUT
    )
    assert end is None


def test_malformed_anchors_are_refused() -> None:
    with pytest.raises(ValueError, match="anchor"):
        interval_end_for_fusion([an_interval()], anchor_in_ms=14_000, anchor_out_ms=10_000)


# =========================================================================================
# The fusion site itself — a naked end number can no longer arrive
# =========================================================================================


def test_fusion_refuses_a_timelens_end_with_no_interval_start() -> None:
    """The fix has to land where the value is *consumed*, not one module away.

    Putting relevance only in `interval_end_for_fusion` would leave `BoundaryInputs` accepting
    the same bare integer it always did, and the next caller to build inputs by hand would
    reintroduce the five-minute clip while every test above still passed.
    """
    with pytest.raises(ValueError, match="timelens_interval_start_ms"):
        fuse_boundary(
            BoundaryInputs(
                anchor_in_ms=ANCHOR_IN,
                anchor_out_ms=ANCHOR_OUT,
                sentence_complete=True,
                timelens_interval_end_ms=305_000,
            )
        )


def test_fusion_refuses_an_interval_that_does_not_overlap_the_anchor() -> None:
    with pytest.raises(ValueError, match="does not overlap"):
        fuse_boundary(
            BoundaryInputs(
                anchor_in_ms=ANCHOR_IN,
                anchor_out_ms=ANCHOR_OUT,
                sentence_complete=True,
                timelens_interval_start_ms=300_000,
                timelens_interval_end_ms=305_000,
            )
        )


def test_fusion_accepts_an_overlapping_interval_and_extends_outward() -> None:
    boundary = fuse_boundary(
        BoundaryInputs(
            anchor_in_ms=ANCHOR_IN,
            anchor_out_ms=ANCHOR_OUT,
            sentence_complete=True,
            timelens_interval_start_ms=12_000,
            timelens_interval_end_ms=18_000,
        )
    )
    assert boundary.final_out_ms == 18_000
    assert boundary.out_extended_by == "timelens_interval_end"
    assert boundary.final_out_ms >= boundary.anchor_out_ms


def test_fusion_refuses_a_backwards_interval() -> None:
    with pytest.raises(ValueError, match="no length"):
        fuse_boundary(
            BoundaryInputs(
                anchor_in_ms=ANCHOR_IN,
                anchor_out_ms=ANCHOR_OUT,
                sentence_complete=True,
                timelens_interval_start_ms=18_000,
                timelens_interval_end_ms=12_000,
            )
        )


def test_an_interval_start_without_an_end_is_refused() -> None:
    """Half an interval is not an interval, and silently ignoring the start would hide a
    producer that lost its end."""
    with pytest.raises(ValueError, match="timelens_interval_end_ms"):
        fuse_boundary(
            BoundaryInputs(
                anchor_in_ms=ANCHOR_IN,
                anchor_out_ms=ANCHOR_OUT,
                sentence_complete=True,
                timelens_interval_start_ms=12_000,
            )
        )


def test_the_producer_and_the_fusion_site_agree() -> None:
    """End to end: the module that selects and the module that consumes reach the same clip."""
    intervals = [an_interval(12_000, 18_000), an_interval(300_000, 305_000)]
    end = interval_end_for_fusion(intervals, anchor_in_ms=ANCHOR_IN, anchor_out_ms=ANCHOR_OUT)
    assert end == 18_000
    chosen = next(i for i in intervals if i.end_ms == end)
    boundary = fuse_boundary(
        BoundaryInputs(
            anchor_in_ms=ANCHOR_IN,
            anchor_out_ms=ANCHOR_OUT,
            sentence_complete=True,
            timelens_interval_start_ms=chosen.start_ms,
            timelens_interval_end_ms=chosen.end_ms,
        )
    )
    assert boundary.final_out_ms == 18_000
