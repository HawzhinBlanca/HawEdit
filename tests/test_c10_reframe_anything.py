"""Unit and synthetic-media tests for Lane B (D-357): ReframeAnything & explicit encoder selection.

Covers:
- AC-B1: Intra-shot rolling-window active-speaker switching with frame-exact hard-cut steps
- AC-B2: Non-face motion-saliency focus tracking (`detect_motion_focus_points`)
- AC-B3: Downscaled fast Haar detection (`<= 960 px`) coordinate accuracy & `resolve_encoder`
"""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from hawedit.reframe import (
    FocusPoint,
    OpenCvFaceTracker,
    detect_motion_focus_points,
    stabilize,
)
from hawedit.render import Encoder, RenderError, crop_filter, resolve_encoder


def test_opencv_face_tracker_switches_active_speaker_mid_wide_shot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-B1: Uncut >=5s 2-person wide shot switches cleanly on sustained >=2.0s speaker change."""
    import cv2
    import numpy as np

    video_path = tmp_path / "wide_two_shot_switch.mp4"
    fourcc = cv2.VideoWriter.fourcc(*"mp4v")
    fps = 5.0
    writer = cv2.VideoWriter(str(video_path), fourcc, fps, (640, 480))
    # 7.0 seconds at 5 fps = 35 frames:
    # - Frames 0..14 (0..3000 ms): Left person (center 125) speaks, Right (center 490) static
    # - Frames 15..34 (3000..7000 ms): Left static, Right speaks continuously (>= 2.0 s)
    for i in range(35):
        frame = np.full((480, 640, 3), 60, dtype=np.uint8)
        # Left face (80, 100, 90, 90) -> center_x = 125
        cv2.rectangle(frame, (80, 100), (170, 190), (160, 160, 160), -1)
        left_mouth = (240 if i % 2 == 0 else 20) if i < 15 else 90
        cv2.rectangle(frame, (85, 148), (165, 186), (left_mouth, left_mouth, left_mouth), -1)
        # Right face (450, 100, 80, 80) -> center_x = 490
        cv2.rectangle(frame, (450, 100), (530, 180), (150, 150, 150), -1)
        right_mouth = (240 if i % 2 == 0 else 20) if i >= 15 else 90
        cv2.rectangle(frame, (455, 145), (525, 178), (right_mouth, right_mouth, right_mouth), -1)
        writer.write(frame)
    writer.release()

    class _TwoFaceClassifier:
        def __init__(self, kind: str) -> None:
            self.kind = kind

        def empty(self) -> bool:
            return False

        def detectMultiScale(self, *args: Any, **kwargs: Any) -> list[tuple[int, int, int, int]]:
            if self.kind != "frontal":
                return []
            return [(80, 100, 90, 90), (450, 100, 80, 80)]

    monkeypatch.setattr(
        cv2,
        "CascadeClassifier",
        lambda p: _TwoFaceClassifier("frontal" if "frontal" in str(p) else "profile"),
    )

    tracker = OpenCvFaceTracker(sample_fps=fps, enable_tracker=False, detector_kind="haar")
    points = tracker.track(video_path, 0, 7_000)

    # Timestamps must remain strictly increasing
    assert len(points) >= 30
    assert all(b.at_ms > a.at_ms for a, b in pairwise(points))

    early = [p for p in points if p.at_ms <= 2_600]
    late = [p for p in points if p.at_ms >= 4_200]
    assert early and all(p.center_x == 125 for p in early)
    assert late and all(p.center_x == 490 for p in late)

    # Transition must be an instant <= 2 ms hard cut step (never a slow pan)
    step_pairs = [(a, b) for a, b in pairwise(points) if a.center_x == 125 and b.center_x == 490]
    assert len(step_pairs) == 1
    assert 1 <= step_pairs[0][1].at_ms - step_pairs[0][0].at_ms <= 2
    assert len(tracker.last_intra_shot_switches_ms) == 1

    # Passing through stabilize() and crop_filter() preserves zero-pan frame-exact hard cut
    steady = stabilize(points, dead_zone_px=40)
    steady_steps = [(a, b) for a, b in pairwise(steady) if a.center_x == 125 and b.center_x == 490]
    assert len(steady_steps) == 1
    assert 1 <= steady_steps[0][1].at_ms - steady_steps[0][0].at_ms <= 2

    filt = crop_filter(
        640,
        480,
        focus_points=[(p.at_ms, p.center_x) for p in steady],
        clip_in_ms=0,
    )
    assert "/0.001" not in filt
    assert "/0.002" not in filt

    # Negative control: brief 1.0 s secondary motion (< 2.0 s dwell) must NOT switch
    brief_path = tmp_path / "wide_two_shot_brief_cough.mp4"
    writer_b = cv2.VideoWriter(str(brief_path), fourcc, fps, (640, 480))
    for i in range(30):  # 6.0 s
        frame = np.full((480, 640, 3), 60, dtype=np.uint8)
        cv2.rectangle(frame, (80, 100), (170, 190), (160, 160, 160), -1)
        # Left speaks except a 1.0 s pause (frames 12..16) where Right briefly coughs
        left_active = not (12 <= i < 17)
        left_mouth = (240 if i % 2 == 0 else 20) if left_active else 90
        cv2.rectangle(frame, (85, 148), (165, 186), (left_mouth, left_mouth, left_mouth), -1)
        cv2.rectangle(frame, (450, 100), (530, 180), (150, 150, 150), -1)
        right_mouth = (240 if i % 2 == 0 else 20) if (12 <= i < 17) else 90
        cv2.rectangle(frame, (455, 145), (525, 178), (right_mouth, right_mouth, right_mouth), -1)
        writer_b.write(frame)
    writer_b.release()

    brief_tracker = OpenCvFaceTracker(sample_fps=fps, enable_tracker=False, detector_kind="haar")
    brief_points = brief_tracker.track(brief_path, 0, 6_000)
    assert brief_points and all(p.center_x == 125 for p in brief_points)
    assert brief_tracker.last_intra_shot_switches_ms == ()


def test_downscaled_haar_preserves_full_source_coordinates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-B3: Width > 960 downscales Haar input to 960 px and maps boxes back within <= 2 px."""
    import cv2
    import numpy as np

    video_1440p = tmp_path / "source_1440p.mp4"
    fourcc = cv2.VideoWriter.fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(video_1440p), fourcc, 5.0, (2560, 1440))
    for _ in range(3):
        writer.write(np.zeros((1440, 2560, 3), dtype=np.uint8))
    writer.release()

    # Full-res target box on 2560x1440: (600, 320, 240, 240) -> center (720, 440), h = 240
    # At scale = 960 / 2560 = 0.375 -> downscaled box is (225, 120, 90, 90)
    seen_widths: list[int] = []
    seen_min_sizes: list[tuple[int, int]] = []

    class _SpyClassifier:
        def __init__(self, kind: str) -> None:
            self.kind = kind

        def empty(self) -> bool:
            return False

        def detectMultiScale(
            self,
            image: Any,
            *args: Any,
            minSize: tuple[int, int] = (40, 40),
            **kwargs: Any,
        ) -> list[tuple[int, int, int, int]]:
            seen_widths.append(int(image.shape[1]))
            seen_min_sizes.append(minSize)
            if self.kind == "frontal":
                return [(225, 120, 90, 90)]
            return []

    monkeypatch.setattr(
        cv2,
        "CascadeClassifier",
        lambda p: _SpyClassifier("frontal" if "frontal" in str(p) else "profile"),
    )

    tracker = OpenCvFaceTracker(sample_fps=5.0, enable_tracker=False, detector_kind="haar")
    points = tracker.track(video_1440p, 0, 600)

    assert len(points) >= 2
    assert seen_widths and all(w == 960 for w in seen_widths)
    assert seen_min_sizes and all(ms == (24, 24) for ms in seen_min_sizes)
    for pt in points:
        assert abs(pt.center_x - 720) <= 2
        assert pt.center_y is not None and abs(pt.center_y - 440) <= 2
        assert pt.face_height is not None and abs(pt.face_height - 240) <= 2

    # Width <= 960 (e.g. 640x480) stays full resolution with original minSize=(40, 40)
    video_640 = tmp_path / "source_640.mp4"
    writer_s = cv2.VideoWriter(str(video_640), fourcc, 5.0, (640, 480))
    for _ in range(2):
        writer_s.write(np.zeros((480, 640, 3), dtype=np.uint8))
    writer_s.release()

    seen_widths.clear()
    seen_min_sizes.clear()
    small_points = tracker.track(video_640, 0, 400)
    assert len(small_points) >= 1
    assert seen_widths and all(w == 640 for w in seen_widths)
    assert seen_min_sizes and all(ms == (40, 40) for ms in seen_min_sizes)


def test_resolve_encoder_explicit_nvenc_fails_stop_and_auto_reports_choice(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """AC-B3: Explicit NVENC fails-stop when unavailable; auto probes once and reports choice."""
    fake_ffmpeg = tmp_path / "ffmpeg"
    probe_calls: list[Encoder] = []

    def _probe_unavailable(encoder: Encoder, binary: Path) -> bool:
        probe_calls.append(encoder)
        return False

    def _probe_available(encoder: Encoder, binary: Path) -> bool:
        probe_calls.append(encoder)
        return encoder is Encoder.NVENC

    # Explicit libx264 returns X264 immediately without probing NVENC
    monkeypatch.setattr("hawedit.render.encoder_available", _probe_unavailable)
    assert resolve_encoder("libx264", ffmpeg=fake_ffmpeg) is Encoder.X264
    assert resolve_encoder(Encoder.X264, ffmpeg=fake_ffmpeg) is Encoder.X264
    assert probe_calls == []

    # Explicit h264_nvenc when unavailable MUST fail-stop with RenderError (zero silent fallback)
    with pytest.raises(RenderError, match="h264_nvenc"):
        resolve_encoder("h264_nvenc", ffmpeg=fake_ffmpeg)
    assert probe_calls == [Encoder.NVENC]

    probe_calls.clear()
    with pytest.raises(RenderError, match="h264_nvenc"):
        resolve_encoder(Encoder.NVENC, ffmpeg=fake_ffmpeg)
    assert probe_calls == [Encoder.NVENC]

    # Auto when NVENC unavailable probes once and returns X264 explicitly
    probe_calls.clear()
    assert resolve_encoder("auto", ffmpeg=fake_ffmpeg) is Encoder.X264
    assert probe_calls == [Encoder.NVENC]

    # Auto and explicit NVENC when NVENC IS available probe once and return NVENC
    monkeypatch.setattr("hawedit.render.encoder_available", _probe_available)
    probe_calls.clear()
    assert resolve_encoder("auto", ffmpeg=fake_ffmpeg) is Encoder.NVENC
    assert probe_calls == [Encoder.NVENC]

    probe_calls.clear()
    assert resolve_encoder("h264_nvenc", ffmpeg=fake_ffmpeg) is Encoder.NVENC
    assert probe_calls == [Encoder.NVENC]

    # Unknown encoder string raises ValueError
    with pytest.raises(ValueError, match="unknown encoder"):
        resolve_encoder("hevc_nvenc", ffmpeg=fake_ffmpeg)

    # Missing ffmpeg fails-stop for auto and h264_nvenc
    monkeypatch.setattr("hawedit.render.find_ffmpeg", lambda: None)
    with pytest.raises(RenderError, match="no ffmpeg"):
        resolve_encoder("auto")
    with pytest.raises(RenderError, match="no ffmpeg"):
        resolve_encoder("h264_nvenc")


def test_detect_motion_focus_points_tracks_non_face_action(tmp_path: Path) -> None:
    """AC-B2: Pure OpenCV motion saliency tracks non-face action and returns () on static video."""
    import cv2
    import numpy as np

    fourcc = cv2.VideoWriter.fourcc(*"mp4v")

    # 1. Non-face action video: cooking pan/hand moving on right (x ~ 500), then left (x ~ 140)
    action_path = tmp_path / "cooking_action.mp4"
    writer = cv2.VideoWriter(str(action_path), fourcc, 4.0, (640, 360))
    for i in range(20):  # 5.0 seconds at 4 fps
        frame = np.full((360, 640, 3), 30, dtype=np.uint8)
        phase = (i // 2) % 2
        cy = 130 + phase * 60
        color = (230, 200, 140) if phase == 0 else (90, 70, 50)
        if i < 10:
            # Right-side action centered near x=500
            cv2.rectangle(frame, (450, cy - 40), (550, cy + 40), color, -1)
        else:
            # Left-side action centered near x=140
            cv2.rectangle(frame, (90, cy - 40), (190, cy + 40), color, -1)
        writer.write(frame)
    writer.release()

    # Verify no faces exist in this non-face action clip
    assert (
        OpenCvFaceTracker(sample_fps=2.0, detector_kind="haar").track(action_path, 0, 5_000) == ()
    )

    motion_pts = detect_motion_focus_points(action_path, 0, 5_000, sample_fps=2.0)
    assert len(motion_pts) >= 2
    assert all(isinstance(p, FocusPoint) for p in motion_pts)
    assert all(b.at_ms > a.at_ms for a, b in pairwise(motion_pts))
    # First keyframe locks onto right-side action (~500), final keyframe moves to left (~140)
    assert 420 <= motion_pts[0].center_x <= 580
    assert 60 <= motion_pts[-1].center_x <= 220

    # 2. Static non-face video returns empty tuple ()
    static_path = tmp_path / "static_counter.mp4"
    writer_s = cv2.VideoWriter(str(static_path), fourcc, 4.0, (640, 360))
    for _ in range(8):
        frame = np.full((360, 640, 3), 50, dtype=np.uint8)
        cv2.rectangle(frame, (200, 100), (440, 260), (120, 120, 120), -1)
        writer_s.write(frame)
    writer_s.release()

    assert detect_motion_focus_points(static_path, 0, 2_000, sample_fps=2.0) == ()

    # 3. Invalid inputs fail-stop
    with pytest.raises(ValueError, match="no duration"):
        detect_motion_focus_points(static_path, 1_000, 1_000)
    with pytest.raises(ValueError, match="finite and positive"):
        detect_motion_focus_points(static_path, 0, 1_000, sample_fps=0.0)
