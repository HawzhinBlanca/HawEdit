"""M5.3 — §3 Stage 3 Path B: `VideoChat3-4B` over scenes, and what its output must prove.

    **Path B — visual.** `VideoChat3-4B` over scenes, plus embedding/rerank retrieval. Finds
    reactions, gestures, action, scene changes, non-verbal beats.
    …
    **Prompt schema — SV6D.** Use the six-dimension structure from the Leum-VL paper as your
    output schema… Every label must cite a timestamp. Reject output where a claim has no
    timeline evidence.
    …
    **VideoChat3-4B notes:** … Segmentation is mandatory: the authors report ~17.7 GB at 256
    frames and ~26.7 GB at 512.

`Sv6d` has enforced "cites a timestamp" since M2.2, by searching each label for something that
looks like a time. That check has no idea which scene the label is about, so this passes:

    Sv6d(subject='speaker at 9999s', …)   # on a scene running 5:00 to 5:12

Nine thousand nine hundred and ninety-nine seconds is two and three-quarter hours. The regex is
satisfied, the constructor returns, and the claim is anchored to a moment the model never saw.
"Reject output where a claim has no timeline evidence" was being read as "reject output with no
*string that looks like* timeline evidence" — the same substitution of shape for content this
codebase keeps finding.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from hawedit.clip import DiscoveryPath, Sv6d, assert_sv6d_within_window, parse_timestamps_ms
from hawedit.path_b import (
    MAX_FRAMES_PER_CALL,
    PATH_B_MODEL,
    PathBError,
    SceneReading,
    SceneReadings,
    UnreadableScene,
    discover_visual,
)
from hawedit.registry import WrongRole
from hawedit.visual_index import REFERENCE_FPS, SceneWindow

WINDOW_IN = 300_000
WINDOW_OUT = 312_000


def a_window(
    in_ms: int = WINDOW_IN,
    out_ms: int = WINDOW_OUT,
    *,
    scene_index: int = 0,
    media_id: str = "m1",
) -> SceneWindow:
    return SceneWindow(
        media_id=media_id,
        scene_index=scene_index,
        window_index=0,
        in_ms=in_ms,
        out_ms=out_ms,
        fps=REFERENCE_FPS,
    )


def an_sv6d(at: str = "5:04") -> Sv6d:
    return Sv6d(
        subject=f"speaker gestures at {at}",
        aesthetics=f"warm grade at {at}",
        camera=f"slow push-in at {at}",
        editing=f"hard cut at {at}",
        narrative=f"payoff lands at {at}",
        retention=f"hook at {at}",
    )


def a_reading(
    window: SceneWindow | None = None,
    sv6d: Sv6d | None = None,
    score: float = 0.7,
    model_id: str = PATH_B_MODEL,
) -> SceneReading:
    return SceneReading(
        window=window if window is not None else a_window(),
        sv6d=sv6d if sv6d is not None else an_sv6d(),
        score=score,
        model_id=model_id,
    )


# =========================================================================================
# parse_timestamps_ms — the four forms §3's judges plausibly emit
# =========================================================================================


def test_seconds_with_a_decimal() -> None:
    assert parse_timestamps_ms("gesture at 84.6s") == (84_600,)


def test_milliseconds() -> None:
    assert parse_timestamps_ms("gesture at 84600ms") == (84_600,)


def test_a_two_part_clock_is_minutes_and_seconds() -> None:
    """`1:24` in a video note is a minute and 24 seconds, never an hour and 24 minutes."""
    assert parse_timestamps_ms("cut at 1:24") == (84_000,)


def test_a_three_part_clock_is_hours_minutes_seconds() -> None:
    assert parse_timestamps_ms("cut at 00:01:52") == (112_000,)


def test_several_timestamps_in_one_label_are_all_returned() -> None:
    assert parse_timestamps_ms("push-in from 1:24 to 1:30") == (84_000, 90_000)


def test_a_label_with_no_timestamp_yields_nothing() -> None:
    assert parse_timestamps_ms("the speaker seems pleased") == ()


# =========================================================================================
# assert_sv6d_within_window — the content the presence check could not see
# =========================================================================================


def test_labels_citing_a_time_inside_the_window_pass() -> None:
    assert_sv6d_within_window(an_sv6d("5:04"), WINDOW_IN, WINDOW_OUT)


def test_a_timestamp_far_outside_the_window_is_refused() -> None:
    """The finding. `9999s` is two and three-quarter hours; the scene is twelve seconds."""
    with pytest.raises(ValueError, match="outside"):
        assert_sv6d_within_window(an_sv6d("9999s"), WINDOW_IN, WINDOW_OUT)


def test_one_dimension_out_of_six_is_enough_to_refuse_and_the_error_names_it() -> None:
    sv6d = Sv6d(
        subject="speaker gestures at 5:04",
        aesthetics="warm grade at 5:05",
        camera="slow push-in at 5:06",
        editing="hard cut at 5:07",
        narrative="payoff lands at 5:08",
        retention="hook at 9999s",
    )
    with pytest.raises(ValueError, match="retention"):
        assert_sv6d_within_window(sv6d, WINDOW_IN, WINDOW_OUT)


def test_a_duration_alongside_an_in_range_time_is_allowed() -> None:
    """A label may mention a length as well as a moment.

    "slow push-in over 3s, starting 5:04" cites 3000 ms and 304000 ms. The first is a duration,
    not a point on the timeline, so the rule is that *some* cited time lands in the window —
    not that every number does. Requiring all of them would reject honest labels.
    """
    sv6d = an_sv6d("5:04")
    widened = Sv6d(
        subject=sv6d.subject,
        aesthetics=sv6d.aesthetics,
        camera="slow push-in over 3s, starting 5:04",
        editing=sv6d.editing,
        narrative=sv6d.narrative,
        retention=sv6d.retention,
    )
    assert_sv6d_within_window(widened, WINDOW_IN, WINDOW_OUT)


def test_a_label_citing_only_a_duration_is_refused() -> None:
    """ "over 3s" anchors nothing. §3: reject a claim with no timeline evidence."""
    sv6d = an_sv6d("5:04")
    unanchored = Sv6d(
        subject=sv6d.subject,
        aesthetics=sv6d.aesthetics,
        camera="slow push-in over 3s",
        editing=sv6d.editing,
        narrative=sv6d.narrative,
        retention=sv6d.retention,
    )
    with pytest.raises(ValueError, match="camera"):
        assert_sv6d_within_window(unanchored, WINDOW_IN, WINDOW_OUT)


def test_the_window_bounds_are_inclusive() -> None:
    at_start = an_sv6d("5:00")
    assert_sv6d_within_window(at_start, WINDOW_IN, WINDOW_OUT)
    at_end = an_sv6d("5:12")
    assert_sv6d_within_window(at_end, WINDOW_IN, WINDOW_OUT)


# =========================================================================================
# SceneReading — one scene as VideoChat3 read it
# =========================================================================================


def test_a_reading_from_the_wrong_role_is_refused() -> None:
    """§7 gives VideoChat3 'Local video understanding' and TimeLens2 'Visual temporal
    evidence'. Path B is the first; using the second here would be a different stage."""
    with pytest.raises(WrongRole):
        a_reading(model_id="MCG-NJU/TimeLens2-4B")


def test_a_reading_whose_sv6d_points_outside_its_own_window_is_refused() -> None:
    with pytest.raises(ValueError, match="outside"):
        a_reading(sv6d=an_sv6d("9999s"))


def test_a_non_finite_score_is_refused() -> None:
    with pytest.raises(ValueError, match="finite"):
        a_reading(score=float("nan"))


# =========================================================================================
# discover_visual — the producer contract
# =========================================================================================


class FakeVideoChat:
    """Stands in for `VideoChat3-4B` (`BLOCKED.md` #2, #6)."""

    def __init__(self, mode: str = "ok") -> None:
        self.mode = mode
        self.seen: tuple[SceneWindow, ...] = ()
        self.calls: list[tuple[SceneWindow, ...]] = []

    def read_scenes(self, windows: Sequence[SceneWindow]) -> SceneReadings:
        self.seen = tuple(windows)
        self.calls.append(self.seen)
        if self.mode == "invent":
            # Internally consistent on purpose: its SV6D is anchored inside its own window, so
            # the reading constructs cleanly and the only thing wrong with it is that this
            # scene was never sent. Otherwise the test would pass for the wrong reason.
            invented = a_window(999_000, 999_500, scene_index=99)
            return SceneReadings(
                (SceneReading(window=invented, sv6d=_sv6d_for(invented), score=0.9),)
            )
        if self.mode == "duplicate":
            first = windows[0]
            return SceneReadings(
                tuple(
                    SceneReading(
                        window=first,
                        sv6d=_sv6d_for(first),
                        score=0.5,
                        model_id=PATH_B_MODEL,
                    )
                    for _ in range(2)
                )
            )
        if self.mode == "omit":
            windows = windows[:-1]
        if self.mode == "alter_window":
            sent = windows[0]
            altered = SceneWindow(
                media_id=sent.media_id,
                scene_index=sent.scene_index,
                window_index=sent.window_index,
                in_ms=sent.in_ms + 1_000,
                out_ms=sent.out_ms,
                fps=sent.fps,
            )
            return SceneReadings(
                (SceneReading(window=altered, sv6d=_sv6d_for(altered), score=0.9),)
            )
        readings = []
        for position, window in enumerate(windows):
            readings.append(
                SceneReading(
                    window=window,
                    sv6d=_sv6d_for(window),
                    score=1.0 - position * 0.1,
                    model_id=PATH_B_MODEL,
                )
            )
        return SceneReadings(tuple(readings))


def _sv6d_for(window: SceneWindow) -> Sv6d:
    """SV6D labels anchored inside `window`, in milliseconds so the arithmetic is obvious."""
    at = f"{window.in_ms + 500}ms"
    return Sv6d(
        subject=f"speaker gestures at {at}",
        aesthetics=f"warm grade at {at}",
        camera=f"slow push-in at {at}",
        editing=f"hard cut at {at}",
        narrative=f"payoff lands at {at}",
        retention=f"hook at {at}",
    )


def _windows(n: int) -> tuple[SceneWindow, ...]:
    return tuple(a_window(i * 10_000, (i + 1) * 10_000, scene_index=i) for i in range(n))


def test_candidates_carry_the_visual_path_and_dense_ranks() -> None:
    candidates = discover_visual(_windows(4), FakeVideoChat(), media_id="m1").candidates
    assert [c.path for c in candidates] == [DiscoveryPath.VISUAL] * 4
    assert [c.rank for c in candidates] == [1, 2, 3, 4]


def test_candidate_spans_are_the_windows_own_never_widened() -> None:
    """§3 Stage 5 owns boundaries. `discovery.py` refuses to widen for the same reason, and a
    path that widened its own spans would pre-empt fusion before the merge ever saw them."""
    windows = _windows(3)
    candidates = discover_visual(windows, FakeVideoChat(), media_id="m1").candidates
    assert [c.span for c in candidates] == [w.span for w in windows]


def test_the_sv6d_survives_onto_the_candidate() -> None:
    candidates = discover_visual(_windows(2), FakeVideoChat(), media_id="m1").candidates
    assert candidates[0].sv6d is not None


def test_a_reading_for_a_window_that_was_never_sent_is_refused() -> None:
    with pytest.raises(PathBError, match="not among"):
        discover_visual(_windows(3), FakeVideoChat("invent"), media_id="m1")


def test_the_same_window_read_twice_is_refused() -> None:
    """§3 Stage 2 is one embedding per scene and Stage 3 is one reading per scene; two would
    give the same footage two chances to survive into Stage 4."""
    with pytest.raises(PathBError, match="twice"):
        discover_visual(_windows(3), FakeVideoChat("duplicate"), media_id="m1")


def test_omitting_a_requested_window_is_refused() -> None:
    """A partial response is not a successful visual pass: the missing scene loses recall."""
    with pytest.raises(PathBError, match="omitted readings"):
        discover_visual(_windows(3), FakeVideoChat("omit"), media_id="m1")


def test_a_matching_id_cannot_hide_changed_window_data() -> None:
    """The id excludes timestamps and fps, so matching it alone does not identify footage."""
    with pytest.raises(PathBError, match="window data that differs"):
        discover_visual(_windows(1), FakeVideoChat("alter_window"), media_id="m1")


def test_a_window_from_another_media_is_refused_before_the_model_is_called() -> None:
    model = FakeVideoChat()
    with pytest.raises(PathBError, match="media"):
        discover_visual((a_window(0, 10_000, media_id="other"),), model, media_id="m1")
    assert model.seen == (), "the model was called with footage from the wrong episode"


def test_an_episode_over_the_frame_budget_is_split_into_bounded_calls() -> None:
    """§3: "Segmentation is mandatory: the authors report ~17.7 GB at 256 frames and ~26.7 GB
    at 512." Five scene windows of 64 frames is 320 — past the 256 the note is written about,
    and the failure is an out-of-memory kill on a 24 GB card rather than a wrong answer."""
    windows = tuple(
        SceneWindow(
            media_id="m1",
            scene_index=i,
            window_index=0,
            in_ms=i * 64_000,
            out_ms=(i + 1) * 64_000,
            fps=REFERENCE_FPS,
        )
        for i in range(5)
    )
    assert sum(w.frame_count for w in windows) == 320
    model = FakeVideoChat()
    assert len(discover_visual(windows, model, media_id="m1").candidates) == 5
    assert [sum(w.frame_count for w in call) for call in model.calls] == [256, 64]


def test_a_call_at_exactly_the_budget_is_allowed() -> None:
    windows = tuple(
        SceneWindow(
            media_id="m1",
            scene_index=i,
            window_index=0,
            in_ms=i * 64_000,
            out_ms=(i + 1) * 64_000,
            fps=REFERENCE_FPS,
        )
        for i in range(4)
    )
    assert sum(w.frame_count for w in windows) == MAX_FRAMES_PER_CALL
    model = FakeVideoChat()
    assert len(discover_visual(windows, model, media_id="m1").candidates) == 4
    assert len(model.calls) == 1


def test_no_windows_at_all_is_an_empty_result_not_a_call() -> None:
    model = FakeVideoChat()
    assert discover_visual((), model, media_id="m1").candidates == ()
    assert model.seen == ()


def test_candidates_are_ordered_by_score_descending() -> None:
    candidates = discover_visual(_windows(4), FakeVideoChat(), media_id="m1").candidates
    scores = [c.score for c in candidates]
    assert scores == sorted(scores, reverse=True)  # type: ignore[type-var]


def test_path_b_never_claims_both() -> None:
    """`DiscoveryPath.BOTH` is the merge's conclusion, never a path's claim about itself."""
    candidates = discover_visual(_windows(2), FakeVideoChat(), media_id="m1").candidates
    assert all(c.path is not DiscoveryPath.BOTH for c in candidates)


# --- D-156: one unreadable survivor discarded all of Path B -----------------------------------


class PartlyUnreadable:
    """Reads every window but the ones named, which it refuses with a stated reason."""

    def __init__(self, refuse: set[int]) -> None:
        self.refuse = refuse

    def read_scenes(self, windows: Sequence[SceneWindow]) -> SceneReadings:
        readings: list[SceneReading] = []
        unreadable: list[UnreadableScene] = []
        for position, window in enumerate(windows):
            if position in self.refuse:
                unreadable.append(
                    UnreadableScene(
                        window_id=window.window_id,
                        in_ms=window.in_ms,
                        out_ms=window.out_ms,
                        reason="PathBError: the model returned no usable line for ['subject', …]",
                    )
                )
                continue
            readings.append(
                SceneReading(
                    window=window,
                    sv6d=_sv6d_for(window),
                    score=1.0 - position * 0.1,
                    model_id=PATH_B_MODEL,
                )
            )
        return SceneReadings(tuple(readings), tuple(unreadable))


def test_one_unreadable_survivor_no_longer_discards_the_others() -> None:
    """Measured on the real 38-minute file: one survivor of seven — a static logo card —
    answered with a time *range* where the prompt asks for "the number alone", and that single
    refusal discarded all seven candidates after Stage 0, 641 embeddings, retrieval and
    reranking had run. The same shape D-103 fixed in Stage 1."""
    windows = _windows(3)
    discovery = discover_visual(windows, PartlyUnreadable({1}), media_id="m1")

    assert len(discovery.candidates) == 2
    assert len(discovery.unreadable) == 1
    assert discovery.unreadable[0].window_id == windows[1].window_id
    assert "no usable line" in discovery.unreadable[0].reason
    # Ranks are dense over what was read: a gap would misreport Path B's own ordering.
    assert [c.rank for c in discovery.candidates] == [1, 2]


def test_nothing_readable_at_all_is_still_refused() -> None:
    """The control. Swallowing every refusal satisfies the test above and would report a Path B
    result for a media nothing could be read from — the one bound that needs no chosen threshold,
    exactly as D-103 drew it for a transcript where no region aligned."""
    with pytest.raises(PathBError, match="not one of the 3 survivor"):
        discover_visual(_windows(3), PartlyUnreadable({0, 1, 2}), media_id="m1")


def test_a_refusal_for_a_window_that_was_never_sent_is_refused() -> None:
    """The second control: an invented failure is as corrosive as an invented reading, and the
    reading side has been checked since M5.3."""

    class InventsAFailure:
        def read_scenes(self, windows: Sequence[SceneWindow]) -> SceneReadings:
            ghost = a_window(999_000, 999_500, scene_index=99)
            return SceneReadings(
                tuple(
                    SceneReading(window=w, sv6d=_sv6d_for(w), score=0.5, model_id=PATH_B_MODEL)
                    for w in windows
                ),
                (
                    UnreadableScene(
                        window_id=ghost.window_id,
                        in_ms=ghost.in_ms,
                        out_ms=ghost.out_ms,
                        reason="never shown to it",
                    ),
                ),
            )

    with pytest.raises(PathBError, match="unreadable, which is not among"):
        discover_visual(_windows(2), InventsAFailure(), media_id="m1")


def test_a_window_both_read_and_refused_is_refused() -> None:
    """Two answers about one scene, with nothing choosing between them."""

    class Both:
        def read_scenes(self, windows: Sequence[SceneWindow]) -> SceneReadings:
            first = windows[0]
            return SceneReadings(
                tuple(
                    SceneReading(window=w, sv6d=_sv6d_for(w), score=0.5, model_id=PATH_B_MODEL)
                    for w in windows
                ),
                (
                    UnreadableScene(
                        window_id=first.window_id,
                        in_ms=first.in_ms,
                        out_ms=first.out_ms,
                        reason="also refused",
                    ),
                ),
            )

    with pytest.raises(PathBError, match="accounted for .* twice"):
        discover_visual(_windows(2), Both(), media_id="m1")


def test_a_refusal_with_no_reason_is_refused_at_construction() -> None:
    """A window dropped for no stated reason is a window silently dropped."""
    with pytest.raises(ValueError, match="carries no reason"):
        UnreadableScene(window_id="m1:s0:w0", in_ms=0, out_ms=1_000, reason="   ")


@pytest.mark.parametrize(("in_ms", "out_ms"), [(1_000, 1_000), (2_000, 1_000)])
def test_a_refusal_that_spans_nothing_is_refused_at_construction(in_ms: int, out_ms: int) -> None:
    """The sibling guard, and the only refusal in this module no test held.

    Measured across tests/test_path_b.py, test_visual_pipeline.py, test_clip.py and
    test_judge.py: the other nine redden something; this one could be deleted with all four
    green.

    `UnreadableScene` exists, by its own docstring, to keep "six candidates" from being
    indistinguishable from "seven, and one vanished". The span is how a reader knows *which*
    window vanished — a zero-length or inverted one makes the accounting record point at
    nothing, which is the failure this type was introduced to prevent, reappearing inside the
    record itself.
    """
    with pytest.raises(ValueError, match="has no length"):
        UnreadableScene(
            window_id="m1:s0:w0", in_ms=in_ms, out_ms=out_ms, reason="the model refused"
        )
