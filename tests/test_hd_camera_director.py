"""Tests for Lane 2 (D-361): Safe-zone edge-guard follow and zero-face cutaway framing.

Covers:
- T4 / AC-4: Edge-danger fast smooth-follow (`edge_guard_px`, `edge_settle_ms`) in `stabilize()`
- T5 / AC-5: Per-shot zero-face cutaway motion-saliency framing in `OpenCvFaceTracker.track()`
"""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from hawedit.reframe import (
    FocusPoint,
    OpenCvFaceTracker,
    per_shot_face_boxes,
    stabilize,
)


def _track(*centers: int, step_ms: int = 200, start_ms: int = 0) -> tuple[FocusPoint, ...]:
    return tuple(FocusPoint(start_ms + idx * step_ms, center) for idx, center in enumerate(centers))


def test_stabilize_edge_guard_follows_leaning_speaker_without_dead_zone_jitter() -> None:
    """AC-4: Fast smooth follow past edge_guard_px while remaining tripod-locked in dead zone."""
    # 1. Dead-zone wobble remains 100% locked (zero jitter) even with edge_guard_px enabled
    wobble = _track(500, 520, 480, 545, 455, 515, 490)
    assert stabilize(wobble, dead_zone_px=60, edge_guard_px=140, edge_settle_ms=250) == (
        FocusPoint(0, 500),
        FocusPoint(1_200, 500),
    )

    # 2. Single-frame detector spike past edge_guard_px (< edge_settle_ms) is still ignored
    spike = _track(500, 500, 720, 500, 500)
    assert stabilize(spike, dead_zone_px=60, edge_guard_px=140, edge_settle_ms=250) == (
        FocusPoint(0, 500),
        FocusPoint(800, 500),
    )

    # 3. Brief moderate drift outside dead_zone_px but below edge_guard_px (< settle_ms) stays held
    moderate_drift = _track(500, 590, 595, 590, 505, 500)
    assert stabilize(
        moderate_drift,
        dead_zone_px=60,
        settle_ms=600,
        edge_guard_px=140,
        edge_settle_ms=250,
    ) == (
        FocusPoint(0, 500),
        FocusPoint(1_000, 500),
    )

    # 4. Sustained lean past edge_guard_px (400 ms >= edge_settle_ms=250, < settle_ms=600)
    # engages fast smooth follow with move duration min(move_ms, 350) = 350 ms
    lean = (
        FocusPoint(0, 500),
        FocusPoint(200, 515),  # inside dead zone
        FocusPoint(400, 660),  # abs diff = 160 >= edge_guard_px (140)
        FocusPoint(600, 670),  # elapsed 200 ms < 250 ms
        FocusPoint(800, 680),  # elapsed 400 ms >= 250 ms -> commit smooth follow!
        FocusPoint(1_000, 500),
    )
    # Baseline (edge_guard_px=None) ignores this 400 ms lean because 400 < settle_ms (600)
    baseline = stabilize(lean, dead_zone_px=60, move_ms=400, settle_ms=600)
    assert baseline == (FocusPoint(0, 500), FocusPoint(1_000, 500))

    # With edge_guard_px=140, camera smoothly follows from 400 ms to 400 + 350 = 750 ms
    guarded = stabilize(
        lean,
        dead_zone_px=60,
        move_ms=400,
        settle_ms=600,
        edge_guard_px=140,
        edge_settle_ms=250,
    )
    assert all(b.at_ms > a.at_ms for a, b in pairwise(guarded))
    assert FocusPoint(400, 500) in guarded
    assert FocusPoint(750, 670) in guarded

    # Smaller caller move_ms (< 350) is respected rather than lengthened
    faster_move = stabilize(
        lean,
        dead_zone_px=60,
        move_ms=250,
        settle_ms=600,
        edge_guard_px=140,
        edge_settle_ms=250,
    )
    assert FocusPoint(400, 500) in faster_move
    assert FocusPoint(650, 670) in faster_move


def test_stabilize_edge_guard_validation_and_default_parity() -> None:
    """Invalid edge-guard arguments raise ValueError; edge_guard_px=None matches legacy path."""
    sample = _track(500, 500, 750, 760, 755, 750, step_ms=500)
    assert stabilize(sample, dead_zone_px=60) == stabilize(
        sample, dead_zone_px=60, edge_guard_px=None
    )

    for bad_guard in (0, -10):
        with pytest.raises(ValueError, match="edge guard must be positive"):
            stabilize(sample, dead_zone_px=60, edge_guard_px=bad_guard)

    for bad_settle in (0, -50):
        with pytest.raises(ValueError, match="edge settle duration must be positive"):
            stabilize(sample, dead_zone_px=60, edge_guard_px=140, edge_settle_ms=bad_settle)


def test_face_tracker_frames_zero_face_cutaway_shot_via_motion_saliency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-5: Zero-face cutaway shot inside a multi-shot clip frames motion with <= 1 ms hard cut."""
    import cv2
    import numpy as np

    fourcc = cv2.VideoWriter.fourcc(*"mp4v")
    fps = 5.0

    # 3-shot synthetic video (6.4 s @ 5 fps = 32 frames):
    # - Shot 0 (frames 0..9,   0..2000 ms): Speaker on left (x ~ 140), static background
    # - Shot 1 (frames 10..21, 2000..4400 ms): Zero-face cooking cutaway moving on right (x ~ 500)
    # - Shot 2 (frames 22..31, 4400..6400 ms): Speaker on left (x ~ 140) returns
    video_path = tmp_path / "speaker_cutaway_speaker.mp4"
    writer = cv2.VideoWriter(str(video_path), fourcc, fps, (640, 360))
    for i in range(32):
        frame = np.full((360, 640, 3), 35, dtype=np.uint8)
        if i < 10 or i >= 22:
            # Left speaker block (100, 90, 80, 80) -> center (140, 130)
            cv2.rectangle(frame, (100, 90), (180, 170), (180, 180, 180), -1)
        else:
            # Zero-face cutaway: brisk motion on right side centered around x = 500
            phase = i % 2
            cy = 140 + phase * 60
            color = (235, 200, 130) if phase == 0 else (70, 55, 40)
            cv2.rectangle(frame, (450, cy - 45), (550, cy + 45), color, -1)
        writer.write(frame)
    writer.release()

    # Classify faces ONLY on Shot 0 and Shot 2 (zero faces during Shot 1 cutaway)
    class _ShotAwareClassifier:
        def __init__(self, kind: str) -> None:
            self.kind = kind

        def empty(self) -> bool:
            return False

        def detectMultiScale(
            self, image: Any, *args: Any, **kwargs: Any
        ) -> list[tuple[int, int, int, int]]:
            if self.kind != "frontal":
                return []
            # Detect the left speaker rectangle (bright patch at x=100..180, y=90..170)
            if float(image[100:160, 110:170].mean()) > 120.0:
                return [(100, 90, 80, 80)]
            return []

    monkeypatch.setattr(
        cv2,
        "CascadeClassifier",
        lambda p: _ShotAwareClassifier("frontal" if "frontal" in str(p) else "profile"),
    )

    tracker = OpenCvFaceTracker(sample_fps=fps, enable_tracker=False, detector_kind="haar")
    cuts = (2_000, 4_400)
    points = tracker.track(video_path, 0, 6_400, shot_cuts_ms=cuts)

    assert len(points) >= 15
    assert all(b.at_ms > a.at_ms for a, b in pairwise(points))

    shot0 = [p for p in points if p.at_ms < 2_000]
    shot1 = [p for p in points if 2_000 <= p.at_ms < 4_400]
    shot2 = [p for p in points if p.at_ms >= 4_400]

    assert shot0 and all(p.center_x == 140 for p in shot0)
    assert shot1, "zero-face cutaway shot must emit motion-saliency focus points"
    assert all(420 <= p.center_x <= 580 for p in shot1), (
        f"cutaway must frame right-side motion (~500), not hold prior speaker (140): {shot1}"
    )
    assert all(p.center_y is None and p.face_height is None for p in shot1)
    assert shot2 and all(p.center_x == 140 for p in shot2)

    # Entry into the cutaway must be a clean <= 1 ms hard-cut step from prior speaker x
    cut_in_pairs = [
        (a, b) for a, b in pairwise(points) if a.center_x == 140 and 420 <= b.center_x <= 580
    ]
    assert len(cut_in_pairs) == 1
    assert cut_in_pairs[0][1].at_ms - cut_in_pairs[0][0].at_ms == 1
    assert cut_in_pairs[0][1].at_ms == 2_000

    # Downstream stabilize() and per_shot_face_boxes() stay valid and unpolluted
    steady = stabilize(points, dead_zone_px=40, shot_cuts_ms=cuts)
    assert all(b.at_ms > a.at_ms for a, b in pairwise(steady))
    assert any(420 <= p.center_x <= 580 for p in steady)
    boxes = per_shot_face_boxes(points, shot_cuts_ms=cuts, clip_in_ms=0, clip_out_ms=6_400)
    assert len(boxes) == 3
    assert boxes[0][2:] == (130, 80)
    assert boxes[2][2:] == (130, 80)

    # Zero faces across the ENTIRE multi-shot clip must STILL return () for blurred_fill / fail-stop
    all_broll_path = tmp_path / "all_cutaway_multishot.mp4"
    writer_b = cv2.VideoWriter(str(all_broll_path), fourcc, fps, (640, 360))
    for i in range(20):  # 4.0 s across 2 shots, zero faces anywhere
        frame = np.full((360, 640, 3), 35, dtype=np.uint8)
        phase = i % 2
        cy = 140 + phase * 60
        color = (235, 200, 130) if phase == 0 else (70, 55, 40)
        cv2.rectangle(frame, (450, cy - 45), (550, cy + 45), color, -1)
        writer_b.write(frame)
    writer_b.release()

    assert tracker.track(all_broll_path, 0, 4_000, shot_cuts_ms=(2_000,)) == ()


def test_face_tracker_handles_leading_zero_face_cutaway_and_static_cutaway(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Leading zero-face cutaway frames motion; static zero-face cutaway fabricates nothing."""
    import cv2
    import numpy as np

    fourcc = cv2.VideoWriter.fourcc(*"mp4v")
    fps = 5.0

    # Shot 0 (0..2000 ms): moving right-side pan cutaway (zero faces)
    # Shot 1 (2000..4000 ms): speaker face on left (x=140)
    # Shot 2 (4000..6000 ms): completely static zero-face title card
    video_path = tmp_path / "leading_and_static_cutaways.mp4"
    writer = cv2.VideoWriter(str(video_path), fourcc, fps, (640, 360))
    for i in range(30):
        frame = np.full((360, 640, 3), 35, dtype=np.uint8)
        if i < 10:
            phase = i % 2
            cy = 140 + phase * 60
            color = (235, 200, 130) if phase == 0 else (70, 55, 40)
            cv2.rectangle(frame, (450, cy - 45), (550, cy + 45), color, -1)
        elif i < 20:
            cv2.rectangle(frame, (100, 90), (180, 170), (180, 180, 180), -1)
        else:
            # Completely static rectangle across all frames of Shot 2
            cv2.rectangle(frame, (260, 120), (380, 240), (110, 110, 110), -1)
        writer.write(frame)
    writer.release()

    class _FacePatchClassifier:
        def __init__(self, kind: str) -> None:
            self.kind = kind

        def empty(self) -> bool:
            return False

        def detectMultiScale(
            self, image: Any, *args: Any, **kwargs: Any
        ) -> list[tuple[int, int, int, int]]:
            if self.kind != "frontal":
                return []
            if float(image[100:160, 110:170].mean()) > 120.0:
                return [(100, 90, 80, 80)]
            return []

    monkeypatch.setattr(
        cv2,
        "CascadeClassifier",
        lambda p: _FacePatchClassifier("frontal" if "frontal" in str(p) else "profile"),
    )

    tracker = OpenCvFaceTracker(sample_fps=fps, enable_tracker=False, detector_kind="haar")
    points = tracker.track(video_path, 0, 6_000, shot_cuts_ms=(2_000, 4_000))

    assert all(b.at_ms > a.at_ms for a, b in pairwise(points))
    shot0 = [p for p in points if p.at_ms < 2_000]
    shot1 = [p for p in points if 2_000 <= p.at_ms < 4_000]
    shot2 = [p for p in points if p.at_ms >= 4_000]

    assert shot0 and all(420 <= p.center_x <= 580 for p in shot0)
    assert shot1 and all(p.center_x == 140 for p in shot1)
    assert shot2 == [], "static zero-face cutaway must not fabricate motion points"
