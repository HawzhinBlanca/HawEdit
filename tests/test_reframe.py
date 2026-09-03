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
    _create_tracker,
    choose_face,
    median_face_box,
    probe_first_frame_face,
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


# --- reframe-composition T2: the box the tracker measured survives the trip -------------------


def test_the_median_face_box_is_one_placement_for_the_whole_clip() -> None:
    """The horizontal crop moves because people take turns talking; the vertical one does not.

    A per-sample vertical path would reintroduce exactly the shimmer `stabilize` exists to
    remove, in the axis where there is nothing to follow — nobody stands up mid-sentence at a
    podcast table. So the medians are taken once over the raw track, where a single wild
    detection cannot drag either. D-258.
    """
    track = (
        FocusPoint(0, 500, 360, 300),
        FocusPoint(500, 510, 370, 310),
        FocusPoint(1_000, 505, 9_000, 4_000),  # one wild detection
    )
    assert median_face_box(track) == (370, 310), "a single bad sample moved the framing"


def test_an_unmeasured_track_asks_for_no_vertical_placement() -> None:
    """Every `FocusPoint` built before vertical framing existed carries two arguments, and the
    crop those callers get must not move. `(None, None)` is what says so."""
    assert median_face_box((FocusPoint(0, 500), FocusPoint(500, 520))) == (None, None)
    assert median_face_box(()) == (None, None)


def test_a_focus_point_cannot_claim_a_face_of_no_height() -> None:
    """Zero is not a measurement. `render.vertical_framing` divides by it, and a detector bug
    that reported it would zoom straight to the cap instead of being refused at the door."""
    with pytest.raises(ValueError, match="face height cannot be zero"):
        FocusPoint(0, 500, 360, 0)


def test_stabilize_steps_instantaneously_at_shot_cuts_without_panning() -> None:
    """Across a shot cut, reframing must be an instant cut step, never a 400ms pan."""
    track = (
        FocusPoint(0, 500),
        FocusPoint(500, 500),
        FocusPoint(1_000, 200),  # shot cut happens at 1000ms
        FocusPoint(1_500, 200),
        FocusPoint(2_000, 200),
    )
    keyframes = stabilize(track, dead_zone_px=60, shot_cuts_ms=(1_000,))
    assert FocusPoint(1_000, 500) in keyframes
    assert FocusPoint(1_001, 200) in keyframes
    # Ensure there is no 400ms pan keyframe like 1400ms
    assert not any(1_001 < k.at_ms < 1_500 for k in keyframes)


def test_stabilize_prevents_slow_panning_across_distant_empty_space_on_wide_shots() -> None:
    """Within a single continuous shot, the camera must not slowly pan across empty furniture."""
    # A single-shot wide table detection switching from left speaker 300 to right listener 900
    wide_track = (
        FocusPoint(0, 300),
        FocusPoint(500, 300),
        FocusPoint(1_000, 300),
        FocusPoint(1_500, 900),
        FocusPoint(2_000, 900),
        FocusPoint(2_500, 900),
        FocusPoint(3_000, 300),
    )
    keyframes = stabilize(wide_track, dead_zone_px=60, max_pan_px=250)
    # The camera should hold at 300 without panning across the empty table to 900
    positions = {k.center_x for k in keyframes}
    assert positions == {300}


def test_probe_first_frame_face_reports_no_face_on_digit_fixture() -> None:
    # The fixture contains large digits rather than human faces, so probe_first_frame_face
    # accurately reports (False, None) rather than fabricating a face.
    has_face, pt = probe_first_frame_face(FIXTURE, timestamp_ms=500)
    assert has_face is False
    assert pt is None


def test_probe_first_frame_face_detects_face_and_respects_spatial_anchor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import numpy as np

    class _MockCapture:
        def __init__(self, *args: Any) -> None:
            pass

        def isOpened(self) -> bool:
            return True

        def set(self, prop: int, val: float) -> None:
            pass

        def read(self) -> tuple[bool, Any]:
            frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
            return True, frame

        def release(self) -> None:
            pass

    class _MockDetector:
        def __init__(self, faces: list[tuple[int, int, int, int]]) -> None:
            self._faces = faces

        def empty(self) -> bool:
            return False

        def detectMultiScale(self, *args: Any, **kwargs: Any) -> list[tuple[int, int, int, int]]:
            return self._faces

    import cv2

    monkeypatch.setattr(cv2, "VideoCapture", _MockCapture)
    mock_frontal = _MockDetector([(400, 200, 200, 200)])
    mock_profile = _MockDetector([])

    def _mock_cascade(path: str) -> Any:
        if "frontal" in path:
            return mock_frontal
        return mock_profile

    monkeypatch.setattr(cv2, "CascadeClassifier", _mock_cascade)

    # Within expected x
    ok, pt = probe_first_frame_face(
        FIXTURE, timestamp_ms=500, expected_center_x=520, max_x_drift=50
    )
    assert ok is True
    assert pt is not None
    assert pt.center_x == 500
    assert pt.center_y == 300
    assert pt.face_height == 200

    # Beyond expected x (drift too large)
    ok_drift, pt_drift = probe_first_frame_face(
        FIXTURE, timestamp_ms=500, expected_center_x=800, max_x_drift=50
    )
    assert ok_drift is False
    assert pt_drift is None


def test_opencv_face_tracker_defaults_to_5fps_and_enabled_tracker() -> None:
    tracker = OpenCvFaceTracker()
    assert tracker.sample_fps == 5.0
    assert tracker.enable_tracker is True


def test_create_tracker_returns_valid_cv2_tracker() -> None:
    import cv2

    tracker = _create_tracker(cv2)
    assert tracker is not None


def test_face_tracker_bridges_detection_dropouts_via_tracker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When face detection drops out for a frame, between-sample tracking bridges the gap."""
    import cv2
    import numpy as np

    video_path = tmp_path / "synthetic_test.mp4"
    fourcc = cv2.VideoWriter.fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(video_path), fourcc, 5.0, (640, 480))
    for i in range(3):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        x = 100 + i * 20
        cv2.rectangle(frame, (x, 100), (x + 80, 180), (255, 255, 255), -1)
        writer.write(frame)
    writer.release()

    call_count = {"frontal": 0}

    class _DropoutClassifier:
        def __init__(self, kind: str) -> None:
            self.kind = kind

        def empty(self) -> bool:
            return False

        def detectMultiScale(self, *args: Any, **kwargs: Any) -> list[tuple[int, int, int, int]]:
            if self.kind == "frontal":
                count = call_count["frontal"]
                call_count["frontal"] += 1
                if count == 0:
                    return [(100, 100, 80, 80)]
                elif count == 1:
                    return []  # Dropout!
                else:
                    return [(140, 100, 80, 80)]
            return []

    monkeypatch.setattr(
        cv2,
        "CascadeClassifier",
        lambda p: _DropoutClassifier("frontal" if "frontal" in str(p) else "profile"),
    )

    tracker = OpenCvFaceTracker(sample_fps=5.0, enable_tracker=True)
    points = tracker.track(video_path, 0, 600)
    assert len(points) == 3
    assert points[0].center_x == 140
    assert 145 <= points[1].center_x <= 170
    assert points[2].center_x == 180
