"""M2.2 (cont.) — §5's clip contract.

"Every stage emits and consumes JSON. Stages are independently testable, replaceable,
re-runnable." (§1) So the contract is a validated structure, not a dictionary passed on trust.

Three §5 rules the type enforces rather than documents:

* `in_ms`/`out_ms` must be the boundary's final points. A record whose top-level span
  disagrees with its own boundary block is a lie the renderer would act on.
* "Rejection is a first-class outcome. Every rejected candidate keeps a `reject_reason` and
  its `discovery_path`." (§5) — rejection is a type, not a `None`.
* SV6D: "Every label must cite a timestamp. Reject output where a claim has no timeline
  evidence." (§3 Stage 3)
"""

from __future__ import annotations

import json

import pytest

from hawedit.boundary import BoundaryInputs, BoundaryInvariantViolated, fuse_boundary
from hawedit.clip import (
    Clip,
    ClipTranscript,
    DiscoveryPath,
    Editorial,
    Output,
    Qc,
    RejectedCandidate,
    Sv6d,
    assert_sv6d_within_window,
)
from hawedit.registry import ModelNotInRegistry
from hawedit.transcripts import AsrProvenance, Word

ANCHOR_IN, ANCHOR_OUT = 84_600, 112_400


def a_boundary(**overrides: object):  # type: ignore[no-untyped-def]
    payload: dict[str, object] = {
        "anchor_in_ms": ANCHOR_IN,
        "anchor_out_ms": ANCHOR_OUT,
        "sentence_complete": True,
    }
    payload.update(overrides)
    return fuse_boundary(BoundaryInputs(**payload), confidence=0.91)  # type: ignore[arg-type]


def a_transcript() -> ClipTranscript:
    return ClipTranscript(
        raw_ckb="ئه‌مه‌ زۆر باشه‌",
        norm_ckb="ئەمە زۆر باشە",
        en_aux="This is very good",
        words=(Word(w="ئه‌مه‌", start_ms=84_600, end_ms=84_920, conf=0.97),),
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi", mean_logprob=-0.21),
    )


def an_sv6d() -> Sv6d:
    return Sv6d(
        subject="speaker at desk [84.6s]",
        aesthetics="warm key light [85.0s]",
        camera="static medium [84.6s]",
        editing="single take [84.6s-112.4s]",
        narrative="payoff of the earlier claim [110.0s]",
        retention="raised voice holds attention [111.2s]",
    )


def an_editorial(**overrides: object) -> Editorial:
    payload: dict[str, object] = {
        "hook_score": 0.88,
        "self_contained": True,
        "meaning_fidelity": 0.94,
        "misleading_edit_risk": 0.03,
        "cultural_landing": 0.86,
        "narrative_role": "payoff",
        "judge": "gemini-2.5-pro",
        "sv6d": an_sv6d(),
    }
    payload.update(overrides)
    return Editorial(**payload)  # type: ignore[arg-type]


def a_clip(**overrides: object) -> Clip:
    boundary = a_boundary()
    payload: dict[str, object] = {
        "clip_id": "c-1",
        "media_id": "m-1",
        "in_ms": boundary.final_in_ms,
        "out_ms": boundary.final_out_ms,
        "discovery_path": DiscoveryPath.VERBAL,
        "boundary": boundary,
        "transcript": a_transcript(),
        "speaker": "SPK_01",
        "editorial": an_editorial(),
        "output": Output(
            title_ckb="ناونیشان",
            description_ckb="وەسف",
            crop_target="speaker_face",
            caption_style="word_highlight",
            durations=(15, 30, 60),
        ),
        "qc": Qc(auto_pass=True, flags=(), human_reviewed=False),
    }
    payload.update(overrides)
    return Clip(**payload)  # type: ignore[arg-type]


# --- the span must agree with its own boundary ----------------------------------------


def test_a_clip_span_must_match_its_boundary() -> None:
    boundary = a_boundary()
    with pytest.raises(ValueError, match="in_ms"):
        a_clip(in_ms=boundary.final_in_ms + 1)


def test_a_clip_out_point_must_match_its_boundary() -> None:
    boundary = a_boundary()
    with pytest.raises(ValueError, match="out_ms"):
        a_clip(out_ms=boundary.final_out_ms - 1)


def test_a_well_formed_clip_is_accepted() -> None:
    assert a_clip().in_ms == a_boundary().final_in_ms


# --- invariant #2 at the render gate ---------------------------------------------------


def test_a_renderable_clip_passes_the_gate() -> None:
    a_clip().assert_renderable()


def test_a_clip_whose_boundary_violates_the_invariant_is_not_renderable() -> None:
    from hawedit.boundary import Boundary

    smuggled = Boundary(
        anchor_in_ms=ANCHOR_IN,
        anchor_out_ms=ANCHOR_OUT,
        final_in_ms=ANCHOR_IN + 50,
        final_out_ms=ANCHOR_OUT + 200,
        in_extended_by=None,
        out_extended_by="tail",
        sentence_complete=True,
    )
    clip = a_clip(boundary=smuggled, in_ms=smuggled.final_in_ms, out_ms=smuggled.final_out_ms)
    with pytest.raises(BoundaryInvariantViolated):
        clip.assert_renderable()


def test_a_clip_awaiting_human_review_is_not_renderable() -> None:
    """§2's diagram puts a HUMAN QC GATE before output, always."""
    clip = a_clip(qc=Qc(auto_pass=False, flags=("low confidence",), human_reviewed=False))
    with pytest.raises(ValueError, match="QC"):
        clip.assert_renderable()


def test_a_human_reviewed_clip_is_renderable_even_without_auto_pass() -> None:
    clip = a_clip(qc=Qc(auto_pass=False, flags=("checked",), human_reviewed=True))
    clip.assert_renderable()


def test_direct_qc_construction_refuses_truthy_string_booleans() -> None:
    with pytest.raises(ValueError, match="boolean"):
        Qc(auto_pass="false", flags=(), human_reviewed=False)  # type: ignore[arg-type]


def test_persisted_qc_refuses_scalar_flags() -> None:
    with pytest.raises(ValueError, match="JSON array"):
        Qc.from_dict({"auto_pass": False, "flags": "reviewed", "human_reviewed": True})


# --- editorial ---------------------------------------------------------------------------


def test_the_judge_must_be_a_routable_model() -> None:
    """§4: the shadow is "evaluated, not routed". Recording it as the judge would mean a
    clip was scored by a model the blueprint says must not be in the path."""
    with pytest.raises(ValueError, match="routable"):
        an_editorial(judge="gemini-3.1-pro")


def test_an_unregistered_judge_is_refused() -> None:
    with pytest.raises(ModelNotInRegistry):
        an_editorial(judge="gpt-4o")


def test_scores_outside_zero_to_one_are_refused() -> None:
    with pytest.raises(ValueError, match="hook_score"):
        an_editorial(hook_score=1.5)
    with pytest.raises(ValueError, match="misleading_edit_risk"):
        an_editorial(misleading_edit_risk=-0.1)


def test_every_sv6d_label_must_cite_a_timestamp() -> None:
    """§3 Stage 3: "Every label must cite a timestamp. Reject output where a claim has no
    timeline evidence." """
    with pytest.raises(ValueError, match="timestamp"):
        Sv6d(
            subject="a speaker",  # no timestamp
            aesthetics="warm key light [85.0s]",
            camera="static medium [84.6s]",
            editing="single take [84.6s-112.4s]",
            narrative="payoff [110.0s]",
            retention="raised voice [111.2s]",
        )


def test_several_timestamp_formats_are_accepted() -> None:
    Sv6d(
        subject="speaker [84.6s]",
        aesthetics="light [1:24]",
        camera="static [84600ms]",
        editing="cut [84.6s-112.4s]",
        narrative="payoff [110s]",
        retention="voice [00:01:52]",
    )


# --- rejection is first-class ------------------------------------------------------------


def test_a_rejected_candidate_keeps_its_reason_and_discovery_path() -> None:
    """§5: "Every rejected candidate keeps a reject_reason and its discovery_path. That set
    is your only measure of recall." """
    rejected = RejectedCandidate(
        media_id="m-1",
        in_ms=1000,
        out_ms=2000,
        discovery_path=DiscoveryPath.VISUAL,
        reject_reason="sentence_complete was false",
    )
    assert rejected.discovery_path is DiscoveryPath.VISUAL
    assert "sentence_complete" in rejected.reject_reason


def test_a_rejection_without_a_reason_is_refused() -> None:
    """A rejection set with blank reasons cannot measure recall, which is its only job."""
    with pytest.raises(ValueError, match="reject_reason"):
        RejectedCandidate(
            media_id="m-1",
            in_ms=1000,
            out_ms=2000,
            discovery_path=DiscoveryPath.VERBAL,
            reject_reason="   ",
        )


def test_a_rejection_serialises_with_its_path() -> None:
    rejected = RejectedCandidate(
        media_id="m-1",
        in_ms=1,
        out_ms=2,
        discovery_path=DiscoveryPath.BOTH,
        reject_reason="no complete sentence in tolerance",
    )
    assert rejected.to_dict()["discovery_path"] == "both"


# --- the §5 JSON shape --------------------------------------------------------------------


def test_the_clip_serialises_to_the_section_5_shape() -> None:
    record = a_clip().to_dict()
    assert set(record) == {
        "clip_id",
        "media_id",
        "in_ms",
        "out_ms",
        "discovery_path",
        "boundary",
        "transcript",
        "speaker",
        "editorial",
        "output",
        "qc",
    }
    assert record["discovery_path"] == "verbal"
    assert record["boundary"]["sentence_complete"] is True
    assert record["transcript"]["asr"]["aligner"] == "ctc_viterbi"
    assert record["editorial"]["sv6d"]["subject"].endswith("[84.6s]")
    assert record["output"]["durations"] == [15, 30, 60]


def test_the_clip_round_trips_through_json() -> None:
    original = a_clip()
    restored = Clip.from_dict(json.loads(json.dumps(original.to_dict())))
    assert restored == original


def test_the_raw_transcript_survives_serialisation_unmodified() -> None:
    """Invariant #1 reaches the client through this field — byte for byte."""
    record = a_clip().to_dict()
    assert record["transcript"]["raw_ckb"] == "ئه‌مه‌ زۆر باشه‌"


def test_the_discovery_path_values_are_the_three_section_5_allows() -> None:
    assert {p.value for p in DiscoveryPath} == {"verbal", "visual", "both"}


def test_a_clip_may_omit_the_editorial_block_before_the_judge_has_run() -> None:
    """Stage 5 produces boundaries before Stage 4 has scored anything."""
    clip = a_clip(editorial=None, output=None)
    assert clip.to_dict()["editorial"] is None
    assert Clip.from_dict(clip.to_dict()) == clip


# --- the 9999s claim could ride in on a duration phrase -----------------------------------
#
# "Some cited time inside the window" is a deliberate, documented tradeoff: a label may name a
# length as well as a moment. But pair `9999s` with a duration the window happens to contain and
# the claim rides through. Measured on the three windows Stage 0 actually plans for the fixture,
# 'speaker gestures at 9999s, held over 1s' was ACCEPTED on 0..1400 ms, and the same trick works
# on 1400..2800 ("over 2s") and 2800..4162 ("over 3s"). The cited tests used only a
# 300000..312000 window — the one distance from zero where 1000 ms falls outside. D-088.


def _sv6d_all(label: str) -> Sv6d:
    return Sv6d(**{dimension: label for dimension in Sv6d.DIMENSIONS})


@pytest.mark.parametrize(
    ("in_ms", "out_ms", "duration"),
    [(0, 1_400, "1s"), (1_400, 2_800, "2s"), (2_800, 4_162, "3s")],
)
def test_a_far_claim_cannot_ride_in_on_a_duration_the_window_contains(
    in_ms: int, out_ms: int, duration: str
) -> None:
    """These are the windows this pipeline plans, not a window chosen to make the rule bite."""
    label = f"speaker gestures at 9999s, held over {duration}"
    with pytest.raises(ValueError, match="too large to be a duration"):
        assert_sv6d_within_window(_sv6d_all(label), in_ms, out_ms)


def test_a_label_naming_a_length_and_a_moment_is_still_accepted() -> None:
    """The control, and it is the case the guard's docstring exists to permit.

    "slow push-in over 3s, starting 5:04" cites 3 000 ms and 304 000 ms. The first is a duration
    shorter than the 12 s window, the second is the moment. Rejecting this would be the opposite
    defect: honest labels refused, which is what "requiring all of them" would have caused.
    """
    assert_sv6d_within_window(_sv6d_all("slow push-in over 3s, starting 5:04"), 300_000, 312_000)
    # And an ordinary short label on a short window.
    assert_sv6d_within_window(_sv6d_all("a red number 0 centred, 0.4s"), 0, 1_400)


def test_the_original_headline_defect_is_still_refused() -> None:
    """`9999s` with no in-window time at all — the case M5.3's row was written about."""
    with pytest.raises(ValueError, match="all outside the scene"):
        assert_sv6d_within_window(_sv6d_all("speaker gestures at 9999s"), 300_000, 312_000)


# --- D-101: the artifact could mislabel which path found the clip ---------------------------


@pytest.mark.parametrize("path", list(DiscoveryPath))
def test_the_emitted_clip_names_the_path_that_actually_found_it(path: DiscoveryPath) -> None:
    """Measured by adversarial pass #6: hardcoding `DiscoveryPath.VERBAL.value` in
    `Clip.to_dict` left `tests/test_clip.py`, `test_pipeline.py`, `test_path_a.py`,
    `test_delivery.py` and `test_boundary.py` entirely green.

    The reason is the shared fixture: `a_clip()` builds a **verbal** clip, so the shape test and
    the round-trip test both compared "verbal" against "verbal" and could not see the field stop
    reading the object. Correct tests, blind because the fixture happened to satisfy the rule —
    the shape of D-086 and D-088.

    It matters beyond the label. §8.2's `recall_at_k_by_path` and `path_unique_wins` partition on
    `discovery_path in (path, DiscoveryPath.BOTH)`, and `Clip.from_dict` rebuilds the enum from
    this field, so a run resumed from a mislabelled artifact carries the wrong attribution into
    the numbers M2.5's row says still mean something. Parametrized over every member, because a
    single fixture is how this got here. D-101.
    """
    emitted = json.loads(json.dumps(a_clip(discovery_path=path).to_dict()))
    assert emitted["discovery_path"] == path.value
    assert Clip.from_dict(emitted).discovery_path is path


@pytest.mark.parametrize("path", list(DiscoveryPath))
def test_a_rejected_candidate_names_its_own_path_too(path: DiscoveryPath) -> None:
    """The sibling site. `RejectedCandidate.to_dict` emits the same field, and §8.2's
    unique-wins figures are exactly about which path found what — a rejection filed under the
    wrong path is a win credited to the wrong producer.
    """
    rejected = RejectedCandidate(
        media_id="m-1",
        in_ms=1_000,
        out_ms=5_000,
        discovery_path=path,
        reject_reason="below the editorial floor",
    )
    emitted = json.loads(json.dumps(rejected.to_dict()))
    assert emitted["discovery_path"] == path.value


def test_every_discovery_path_member_is_distinguishable_in_the_artifact() -> None:
    """The control. Both tests above pass if `to_dict` emits a constant *per call site* that
    happens to match — what they cannot see alone is two members rendering identically.

    Three members must produce three distinct strings, or the artifact cannot express the
    distinction §8.2 partitions on however faithfully it copies the field.
    """
    rendered = {a_clip(discovery_path=p).to_dict()["discovery_path"] for p in DiscoveryPath}
    assert len(rendered) == len(list(DiscoveryPath)) == 3, (
        f"{len(list(DiscoveryPath))} paths collapsed to {sorted(rendered)} in the artifact"
    )


# =========================================================================================
# The four refusals a guard-revert sweep over `clip.py` found held by nothing: every `raise`
# deleted one at a time against a green baseline, whole suite each time. 11 of 15 held; these
# are the rest, and two of them sit inside `assert_renderable` — the gate `render_clip` calls
# before it starts an encoder. D-195.
# =========================================================================================


def test_a_clip_that_was_never_judged_is_not_renderable() -> None:
    """§2 puts the QC gate before output *always*, and the judge is half of that gate.

    The QC-record and QC-not-cleared refusals above this one in `assert_renderable` are each
    held by a test. These two were not, so a clip with no editorial block — no meaning-fidelity
    and no misleading-edit score, the number §8.2 calls the one that matters for a media
    organisation — could have reached an encoder if the check were ever refactored away.
    """
    unjudged = a_clip(editorial=None)
    assert unjudged.qc is not None and unjudged.qc.auto_pass, (
        "the fixture must clear QC, or this would pass on the QC refusal above instead"
    )

    with pytest.raises(ValueError, match="never judged"):
        unjudged.assert_renderable()

    # The control: the same clip with its editorial block is renderable, so this measures the
    # missing block and not a fixture that could never render.
    a_clip().assert_renderable()


def test_a_clip_with_no_output_block_is_not_renderable() -> None:
    """The last of `assert_renderable`'s four refusals, and the one with nothing to render
    *with*: no title, no crop target, no caption style. Reached only once QC and the judge have
    both passed, so the fixture has to clear those to arrive here at all."""
    unnamed = a_clip(output=None)
    assert unnamed.editorial is not None, "this must fail on the output block, not the judge"

    with pytest.raises(ValueError, match="no output block"):
        unnamed.assert_renderable()

    a_clip().assert_renderable()  # the control, as above


def test_a_non_positive_output_duration_is_refused() -> None:
    """`durations` are §5's delivery lengths in seconds. A zero or negative one is not a short
    clip, it is an ffmpeg `-t 0` and an empty file, and the refusal was held by nothing."""
    for durations in ((0,), (-15,), (15, 0, 60)):
        with pytest.raises(ValueError, match="positive seconds"):
            Output(
                title_ckb="ناونیشان",
                description_ckb="وەسف",
                crop_target="speaker_face",
                caption_style="word_highlight",
                durations=durations,
            )

    # The control: §5's own three lengths are accepted, so this measures the sign and not a
    # constructor that refuses every duration.
    assert Output(
        title_ckb="ناونیشان",
        description_ckb="وەسف",
        crop_target="speaker_face",
        caption_style="word_highlight",
        durations=(15, 30, 60),
    ).durations == (15, 30, 60)


def test_qc_flags_must_be_a_tuple_of_non_empty_strings() -> None:
    """`Qc.from_dict`'s refusal of a scalar `flags` is held by a test; the constructor's own was
    not. They are different doors to the same field: a flag list built in memory never passes
    through `from_dict`, and an empty-string flag is a review reason that names nothing.
    """
    # A tuple holding an empty flag, a tuple holding a blank one, a real tuple with a non-string
    # in it, and a bare string — which `any(...)` iterates character by character and would
    # otherwise accept, since every character of a non-empty string is a non-empty string.
    for flags in (("",), ("needs_review", "   "), ("needs_review", 7), "not a tuple at all"):
        with pytest.raises(ValueError, match="qc.flags"):
            Qc(auto_pass=False, flags=flags, human_reviewed=False)  # type: ignore[arg-type]

    # The control: a real flag tuple, and the empty tuple that means "nothing flagged".
    assert Qc(auto_pass=False, flags=("needs_review",), human_reviewed=True).flags == (
        "needs_review",
    )
    assert Qc(auto_pass=True, flags=(), human_reviewed=False).flags == ()


# =========================================================================================
# D-196: every key of the shipped sidecar has to be load-bearing.
#
# D-101 found this defect once by hand — `Clip.to_dict` hardcoding `DiscoveryPath.VERBAL.value`
# left five test files green, because `a_clip()` builds a verbal clip and the round-trip test
# compared "verbal" against "verbal". D-181 found it again: `AsrProvenance.adapter` was missing
# from the hand-enumerated dict and the delivered clip would have named stock weights.
#
# Both are the same defect, and a round-trip can only see a dropped field when the value it
# carries differs from what `from_dict` supplies in its absence. Measured on `a_clip()`, four
# keys were invisible: `Editorial.payoff_at_ms` (None), `Output.hashtags_ckb` ([]), `Qc.flags`
# ([]) and `Qc.human_reviewed` (False) — including whether a human reviewed the clip at all.
#
# Two of the four turned out to be held elsewhere: D-033's projection test asserts `payoff_at_ms`
# and `hashtags_ckb` explicitly. `Qc.flags` and `Qc.human_reviewed` were held by nothing, and a
# mutation audit proved it by deleting each from `Qc.to_dict` with the whole suite still green.
# The fix is a fixture whose optional fields are all non-default, run through the round-trip that
# already existed — not a cleverer property. The first attempt here WAS a cleverer property, and
# it could not see a dropped key at all: it iterated the keys `to_dict` emits, so a key that
# stopped being emitted was never examined. The audit caught that, which is what audits are for.
# =========================================================================================


def a_fully_populated_clip() -> Clip:
    """A clip where every optional field carries a NON-DEFAULT value.

    That is the whole point: a fixture that leaves an optional field at its default cannot tell
    a dropped key from an absent one, because `from_dict` reconstructs the same object either
    way. Every default in these five blocks is deliberately avoided here.
    """
    return a_clip(
        speaker="SPK_02",
        editorial=an_editorial(payoff_at_ms=87_400),
        output=Output(
            title_ckb="ناونیشان",
            description_ckb="وەسف",
            crop_target="speaker_face",
            caption_style="word_highlight",
            durations=(15, 30, 60),
            hashtags_ckb=("#کوردی", "#هەواڵ"),
        ),
        qc=Qc(auto_pass=False, flags=("low_confidence",), human_reviewed=True),
    )


def test_the_fully_populated_clip_round_trips_through_json() -> None:
    """The same round-trip as `test_the_clip_round_trips_through_json`, on a fixture that can
    actually fail it.

    `a_clip()` leaves four fields at their defaults, so `from_dict` reconstructs them identically
    whether the key was emitted or not: measured, `Editorial.payoff_at_ms`, `Output.hashtags_ckb`,
    `Qc.flags` and `Qc.human_reviewed` could each be deleted from `to_dict` and the round-trip
    would still compare equal. `Qc.flags` and `Qc.human_reviewed` — the review reasons, and
    whether a human looked at the clip at all — could be deleted with the **whole suite** green.

    Per-block as well as whole-clip, so a failure names which block lost the field rather than
    only that some nested dict differs.
    """
    original = a_fully_populated_clip()
    assert original.editorial is not None
    assert original.output is not None
    assert original.qc is not None

    restored = Clip.from_dict(json.loads(json.dumps(original.to_dict())))
    assert restored == original

    for label, block, rebuild in (
        ("Editorial", original.editorial, Editorial.from_dict),
        ("Output", original.output, Output.from_dict),
        ("ClipTranscript", original.transcript, ClipTranscript.from_dict),
        ("Qc", original.qc, Qc.from_dict),
    ):
        assert rebuild(json.loads(json.dumps(block.to_dict()))) == block, (
            f"{label} did not survive its own round trip"
        )


def test_the_fully_populated_clip_leaves_no_field_at_its_default() -> None:
    """The control for the property above, and the reason it keeps working.

    If `a_fully_populated_clip` ever fell back to a default, the key for that field would become
    invisible again and the test above would go green by *losing* coverage rather than by gaining
    it — a check that stops measuring is worse than one that fails.
    """
    clip = a_fully_populated_clip()
    assert clip.editorial is not None and clip.output is not None and clip.qc is not None

    defaults = {
        "Editorial.payoff_at_ms": (clip.editorial.payoff_at_ms, None),
        "Editorial.sv6d": (clip.editorial.sv6d, None),
        "Output.hashtags_ckb": (clip.output.hashtags_ckb, ()),
        "Qc.flags": (clip.qc.flags, ()),
        "Qc.human_reviewed": (clip.qc.human_reviewed, False),
        "ClipTranscript.en_aux": (clip.transcript.en_aux, None),
    }
    left_at_default = [name for name, (actual, default) in defaults.items() if actual == default]
    assert not left_at_default, (
        f"{left_at_default} carry their default value, so a `to_dict` that dropped them would "
        f"round-trip identically and the property test above would not see it"
    )
