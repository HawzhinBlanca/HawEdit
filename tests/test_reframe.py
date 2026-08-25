from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, cast

import pytest

from hawedit.diarization import Segment
from hawedit.reframe import (
    FocusPoint,
    OpenCvFaceTracker,
    SpeakerAssociationError,
    SpeakerFocusPoint,
    choose_face,
    stabilize,
    validate_speaker_focus_points,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "kurdish-speech-3cuts.mp4"


def test_face_choice_prefers_area_then_preserves_subject_continuity() -> None:
    near = (90, 10, 50, 50)
    far = (500, 10, 100, 100)
    assert choose_face((near, far), previous_x=None) == far
    assert choose_face((near, far), previous_x=115) == near


def test_speaker_focus_evidence_is_exact_and_carries_a_safe_label() -> None:
    assert SpeakerFocusPoint(100, 320, "SPEAKER_00").speaker == "SPEAKER_00"

    for bad in (True, 1.0, "1"):
        with pytest.raises(TypeError, match="exact integer"):
            SpeakerFocusPoint(cast(Any, bad), 320, "SPEAKER_00")
        with pytest.raises(TypeError, match="exact integer"):
            SpeakerFocusPoint(100, cast(Any, bad), "SPEAKER_00")

    for bad in ("", " SPEAKER_00", "SPEAKER_00\n"):
        with pytest.raises(ValueError, match="speaker label"):
            SpeakerFocusPoint(100, 320, bad)


def test_speaker_focus_points_must_match_the_exclusive_turn_active_at_that_instant() -> None:
    turns = (
        Segment(0, 1_000, "SPEAKER_00"),
        Segment(1_200, 2_000, "SPEAKER_01"),
    )
    points = (
        SpeakerFocusPoint(100, 200, "SPEAKER_00"),
        SpeakerFocusPoint(1_200, 500, "SPEAKER_01"),
    )
    assert validate_speaker_focus_points(points, turns, 50, 1_900) == (
        FocusPoint(100, 200),
        FocusPoint(1_200, 500),
    )

    with pytest.raises(SpeakerAssociationError, match="no active diarization turn"):
        validate_speaker_focus_points(
            (SpeakerFocusPoint(1_100, 300, "SPEAKER_00"),), turns, 50, 1_900
        )
    with pytest.raises(SpeakerAssociationError, match="active speaker is 'SPEAKER_01'"):
        validate_speaker_focus_points(
            (SpeakerFocusPoint(1_300, 300, "SPEAKER_00"),), turns, 50, 1_900
        )


def test_speaker_focus_points_are_strictly_ordered_and_inside_the_final_clip() -> None:
    turns = (Segment(0, 2_000, "SPEAKER_00"),)
    with pytest.raises(SpeakerAssociationError, match="strictly increasing"):
        validate_speaker_focus_points(
            (
                SpeakerFocusPoint(500, 100, "SPEAKER_00"),
                SpeakerFocusPoint(500, 120, "SPEAKER_00"),
            ),
            turns,
            100,
            1_000,
        )
    with pytest.raises(SpeakerAssociationError, match="outside the final clip"):
        validate_speaker_focus_points(
            (SpeakerFocusPoint(1_000, 100, "SPEAKER_00"),), turns, 100, 1_000
        )


def test_face_tracker_runs_on_real_media_and_reports_no_invented_subject() -> None:
    # The fixture contains only large digits, not faces. Empty is evidence that no face was
    # detected; fabricating a centre point here would make a static shot look tracked.
    assert OpenCvFaceTracker(sample_fps=2.0).track(FIXTURE, 0, 1_000) == ()


# --- the six refusals the two tests above did not hold ----------------------------------------
#
# Measured by mutation against a shadow copy of `src/hawedit`: of the seven refusals in this
# module, only `choose_face`'s empty-list return was held, and that only incidentally. Every
# other one could be deleted with tests/test_reframe.py green. The three that need OpenCV are
# exercised against a stand-in placed in `sys.modules`, because `track` imports cv2 inside the
# function — the real tracker test above still runs against the real library.


class _FakeDetector:
    def __init__(self, is_empty: bool) -> None:
        self._is_empty = is_empty

    def empty(self) -> bool:
        return self._is_empty

    def detectMultiScale(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        return ()


class _FakeCapture:
    def __init__(self, opened: bool) -> None:
        self._opened = opened
        self.released = False

    def isOpened(self) -> bool:
        return self._opened

    def release(self) -> None:
        self.released = True


def _install_fake_cv2(
    monkeypatch: pytest.MonkeyPatch, *, detector_empty: bool = False, capture_opened: bool = True
) -> None:
    fake = SimpleNamespace(
        data=SimpleNamespace(haarcascades=str(ROOT / "no-such-cascade-dir")),
        CascadeClassifier=lambda path: _FakeDetector(detector_empty),
        VideoCapture=lambda path: _FakeCapture(capture_opened),
        CAP_PROP_POS_MSEC=0,
        COLOR_BGR2GRAY=0,
        cvtColor=lambda frame, code: frame,
    )
    monkeypatch.setitem(sys.modules, "cv2", cast(ModuleType, fake))


def test_a_focus_point_with_negative_coordinates_is_refused() -> None:
    """A focus point becomes the centre of the crop window burned into the encode.

    A negative `center_x` would place the window off the left of the frame; a negative `at_ms`
    would place it before the clip. Both are arithmetic errors upstream, and both are silent if
    the crop filter clamps them.
    """
    with pytest.raises(ValueError, match="non-negative"):
        FocusPoint(at_ms=-1, center_x=100)
    with pytest.raises(ValueError, match="non-negative"):
        FocusPoint(at_ms=0, center_x=-1)
    assert FocusPoint(at_ms=0, center_x=0).center_x == 0


def test_a_non_positive_or_infinite_sampling_rate_is_refused() -> None:
    """`step_ms = 1000 / sample_fps` at reframe.py:72 is the loop's only advance.

    At infinity the step is 0.0 and `at += step_ms` never moves, so `while at < out_ms` never
    ends; negative walks `at` backwards past zero, where a capture keeps returning decodable
    frames, and also never ends. Neither terminates, so this refusal is what stands between a
    bad argument and a Stage 6 that hangs rather than fails.
    """
    for bad in (0.0, -1.0, float("inf"), float("nan")):
        with pytest.raises(ValueError, match="finite and positive"):
            OpenCvFaceTracker(sample_fps=bad)


def test_the_tracker_reports_detected_centres_and_never_an_average_of_two_faces() -> None:
    """The running mean this replaced could only ever be wrong on the material that matters.

    An interview is two people facing each other. When detection alternates between a face at
    145 and one at 495, the mean of the two is 320 — the empty window *between* the speakers,
    where there is no face at all, and the crop lands on the set dressing. Measured on the real
    38-minute source, that is exactly what shipped.

    Smoothing still happens, in `stabilize`, using a median: a median of observed positions is
    always a position something was observed at, and no mean has that property.
    """
    assert not hasattr(OpenCvFaceTracker(), "smoothing"), "the averaging knob is gone"

    two_shot = (FocusPoint(0, 145), FocusPoint(500, 495), FocusPoint(1_000, 145))
    committed = {point.center_x for point in stabilize(two_shot, dead_zone_px=20, settle_ms=1)}
    assert 320 not in committed, "the empty middle is never a camera position"
    assert committed <= {145, 495}, "every camera position is one a face was detected at"


def test_a_reframe_span_with_no_duration_is_refused() -> None:
    """`while at < out_ms` is false on entry for an inverted or empty span, so without this the
    function returns `()` — the same value that means "no subject was found".

    `pipeline.py:1418` feeds it `boundary.final_in_ms, boundary.final_out_ms`, so a boundary bug
    that inverts or collapses a clip would be absorbed here and reported as a static shot.
    """
    with pytest.raises(ValueError, match="no duration"):
        OpenCvFaceTracker().track(FIXTURE, 1_000, 1_000)
    with pytest.raises(ValueError, match="no duration"):
        OpenCvFaceTracker().track(FIXTURE, 2_000, 1_000)


def test_missing_opencv_is_reported_as_a_missing_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    """`None` in `sys.modules` is what the import system treats as "this module is unavailable".

    Face tracking is optional — `pipeline.py:1445` falls back to a static centre crop — so the
    message has to say which extra is missing rather than surfacing a bare ImportError.
    """
    monkeypatch.setitem(sys.modules, "cv2", cast(ModuleType, None))
    with pytest.raises(RuntimeError, match="media extra"):
        OpenCvFaceTracker().track(FIXTURE, 0, 1_000)


def test_a_face_detector_that_will_not_load_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty cascade detects nothing, so every frame would report no face.

    That is indistinguishable from a genuinely faceless shot, which is exactly what the real
    fixture test above asserts as the honest empty result — so without this refusal a broken
    OpenCV install reads as "no subject in this clip".
    """
    _install_fake_cv2(monkeypatch, detector_empty=True)
    with pytest.raises(RuntimeError, match="could not load its face detector"):
        OpenCvFaceTracker().track(FIXTURE, 0, 1_000)


def test_a_source_opencv_cannot_open_is_refused_rather_than_read_as_no_face(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sharpest of the three: `()` is the value the tracker returns for "no face here".

    A source that was never opened produces the same `()`, and `pipeline.py:1417-1421` assigns it
    to the clip's focus points — so an unreadable file ships as a centre crop and the run reports
    a static shot rather than a failure.
    """
    _install_fake_cv2(monkeypatch, capture_opened=False)
    with pytest.raises(RuntimeError, match="could not open"):
        OpenCvFaceTracker().track(FIXTURE, 0, 1_000)


def _track(*centers: int, step_ms: int = 500, start_ms: int = 0) -> tuple[FocusPoint, ...]:
    return tuple(
        FocusPoint(start_ms + index * step_ms, center) for index, center in enumerate(centers)
    )


def test_stabilize_holds_through_detector_wobble() -> None:
    """A face that jitters inside the dead zone must not move the camera at all.

    This is the defect the whole function exists for: `OpenCvFaceTracker` samples twice a
    second, and passing its raw output to the crop moved the frame twice a second.
    """
    wobble = _track(500, 508, 494, 511, 497, 505)
    assert stabilize(wobble, dead_zone_px=60) == (FocusPoint(0, 500), FocusPoint(2_500, 500))


def test_stabilize_commits_a_sustained_move_as_two_keyframes() -> None:
    """A real move becomes hold-end plus move-end, which is a ramp once interpolated."""
    moved = _track(500, 500, 900, 910, 905, 900)
    keyframes = stabilize(moved, dead_zone_px=60, move_ms=400, settle_ms=600)
    assert keyframes[0] == FocusPoint(0, 500)
    # The hold runs to the first sample outside the dead zone, then eases over `move_ms`.
    assert FocusPoint(1_000, 500) in keyframes
    assert FocusPoint(1_400, 905) in keyframes
    assert [point.at_ms for point in keyframes] == sorted({point.at_ms for point in keyframes}), (
        "keyframe timestamps must be strictly increasing"
    )


def test_stabilize_ignores_a_spike_that_does_not_last() -> None:
    """One mis-detected frame is not a camera move, however far away it lands."""
    spike = _track(500, 500, 1_400, 500, 500, 500)
    assert stabilize(spike, dead_zone_px=60, settle_ms=600) == (
        FocusPoint(0, 500),
        FocusPoint(2_500, 500),
    )


def test_stabilize_takes_the_median_so_one_wild_sample_cannot_drag_the_camera() -> None:
    """The committed position is the median of the settle window, never its mean.

    A detector that reports one frame at the far edge of a 1920-wide source would pull a mean
    most of the way there and swing the camera off the speaker for the rest of the clip.
    """
    outlier = _track(500, 900, 905, 5_000, 900, 900)
    keyframes = stabilize(outlier, dead_zone_px=60, move_ms=400, settle_ms=1_000)
    committed = [point.center_x for point in keyframes][-1]
    assert committed == 905, "the settle window is 900, 905, 5000 and its median is 905"
    assert committed < (900 + 905 + 5_000) // 3, "a mean would have followed the outlier"


def test_stabilize_refuses_input_it_cannot_order() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        stabilize((FocusPoint(500, 100), FocusPoint(500, 200)), dead_zone_px=60)
    with pytest.raises(ValueError, match="dead zone must be positive"):
        stabilize(_track(500, 500), dead_zone_px=0)
    with pytest.raises(ValueError, match="move duration must be positive"):
        stabilize(_track(500, 500), dead_zone_px=60, move_ms=0)
    with pytest.raises(ValueError, match="settle duration must be positive"):
        stabilize(_track(500, 500), dead_zone_px=60, settle_ms=0)


def test_stabilize_invents_no_camera_path_from_an_empty_track() -> None:
    """No track means a static centre crop, which is an honest label. Never a fabricated pan."""
    assert stabilize((), dead_zone_px=60) == ()
