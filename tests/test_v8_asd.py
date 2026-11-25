"""Unit and end-to-end synthetic AV tests for V8 Module 4 (src/hawedit/v8/asd.py, D-385)."""

from __future__ import annotations

import math
import sys
import types
import wave
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest
from numpy.typing import NDArray

from hawedit.render import crop_filter
from hawedit.v8.asd import (
    ActiveSpeakerError,
    ActiveSpeakerScore,
    FaceDetectionFrame,
    LockedShotCrop,
    compute_locked_shot_crops,
    detect_exact_assembled_cuts_ms,
    detect_exact_shot_cuts_ms,
    locked_crops_to_focus_points,
    locked_crops_to_render_inputs,
    score_active_speakers,
    snap_locked_crops_to_cuts,
)


def _write_pcm16_wav(path: Path, samples: NDArray[np.float32], sample_rate: int = 16_000) -> None:
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())


def _draw_synthetic_face(
    frame: NDArray[np.uint8],
    *,
    cx: float,
    cy: float,
    size: float,
    mouth_open: float,
) -> None:
    """Draw a high-contrast synthetic face whose mouth opens by ``mouth_open`` in [0, 1]."""
    ix, iy = int(round(cx)), int(round(cy))
    r = int(round(size * 0.48))
    # Bright face oval on dark background
    cv2.ellipse(frame, (ix, iy), (int(r * 0.85), r), 0, 0, 360, (215, 200, 185), -1)
    # Eyes (stable features)
    eye_y = int(round(iy - size * 0.16))
    eye_dx = int(round(size * 0.18))
    eye_r = max(2, int(round(size * 0.05)))
    cv2.circle(frame, (ix - eye_dx, eye_y), eye_r, (40, 40, 40), -1)
    cv2.circle(frame, (ix + eye_dx, eye_y), eye_r, (40, 40, 40), -1)
    # Mouth inside lower third y in [0.58h, 0.90h] -> center at y0 + 0.74h = cy + 0.24h
    mouth_y = int(round(iy + size * 0.24))
    mouth_w = max(4, int(round(size * 0.18)))
    # Closed mouth = thin dark lip line; open mouth = tall dark cavity with white teeth bar
    open_h = max(1, int(round(size * (0.015 + 0.11 * max(0.0, min(1.0, mouth_open))))))
    cv2.ellipse(frame, (ix, mouth_y), (mouth_w, open_h), 0, 0, 360, (20, 15, 15), -1)
    if mouth_open > 0.25:
        teeth_h = max(1, open_h // 3)
        cv2.rectangle(
            frame,
            (ix - mouth_w // 2, mouth_y - open_h + 1),
            (ix + mouth_w // 2, mouth_y - open_h + 1 + teeth_h),
            (245, 245, 245),
            -1,
        )


def _build_two_speaker_av_clip(
    tmp_path: Path,
    *,
    duration_s: float,
    fps: int,
    speech_envelope_fn: Callable[[float], float],
    face_a_mouth_fn: Callable[[float], float],
    face_b_mouth_fn: Callable[[float], float],
    face_a_nod_px: float = 0.0,
) -> tuple[Path, Path, list[FaceDetectionFrame]]:
    """Create a real MJPG video + 16 kHz WAV with Large Face A (track 0) and Small Face B (1)."""
    width, height = 640, 360
    video_path = tmp_path / "two_speaker.avi"
    wav_path = tmp_path / "two_speaker.wav"

    fourcc = cv2.VideoWriter_fourcc(*"MJPG")  # type: ignore[attr-defined]
    writer = cv2.VideoWriter(str(video_path), fourcc, float(fps), (width, height))
    assert writer.isOpened()

    n_frames = int(round(duration_s * fps))
    detections: list[FaceDetectionFrame] = []
    face_a_cx, face_a_cy, face_a_size = 170.0, 180.0, 200.0  # LARGE face (40,000 px^2)
    face_b_cx, face_b_cy, face_b_size = 480.0, 180.0, 96.0  # SMALL face (9,216 px^2)

    try:
        for idx in range(n_frames):
            t = idx / float(fps)
            at_ms = int(round(t * 1000.0))
            frame = np.full((height, width, 3), 35, dtype=np.uint8)
            nod = face_a_nod_px * math.sin(2.0 * math.pi * 1.3 * t)
            _draw_synthetic_face(
                frame,
                cx=face_a_cx,
                cy=face_a_cy + nod,
                size=face_a_size,
                mouth_open=face_a_mouth_fn(t),
            )
            _draw_synthetic_face(
                frame,
                cx=face_b_cx,
                cy=face_b_cy,
                size=face_b_size,
                mouth_open=face_b_mouth_fn(t),
            )
            writer.write(frame)
            detections.append(
                FaceDetectionFrame(
                    at_ms=at_ms,
                    track_id=0,
                    cx=face_a_cx,
                    cy=face_a_cy,
                    w=face_a_size,
                    h=face_a_size,
                )
            )
            detections.append(
                FaceDetectionFrame(
                    at_ms=at_ms,
                    track_id=1,
                    cx=face_b_cx,
                    cy=face_b_cy,
                    w=face_b_size,
                    h=face_b_size,
                )
            )
    finally:
        writer.release()

    sr = 16_000
    n_samples = int(round(duration_s * sr))
    t_audio = np.arange(n_samples, dtype=np.float64) / float(sr)
    env = np.array([speech_envelope_fn(float(ts)) for ts in t_audio], dtype=np.float64)
    # Speech-band harmonic carrier (450 Hz + 950 Hz + 1600 Hz inside 300-3400 Hz band)
    carrier = (
        0.50 * np.sin(2.0 * math.pi * 450.0 * t_audio)
        + 0.35 * np.sin(2.0 * math.pi * 950.0 * t_audio)
        + 0.15 * np.sin(2.0 * math.pi * 1600.0 * t_audio)
    )
    _write_pcm16_wav(wav_path, (0.45 * env * carrier).astype(np.float32), sample_rate=sr)
    return video_path, wav_path, detections


# ---------------------------------------------------------------------------
# 1. Dataclass validation tests
# ---------------------------------------------------------------------------


def test_dataclasses_frozen_and_validated() -> None:
    det = FaceDetectionFrame(at_ms=100, track_id=1, cx=320.0, cy=180.0, w=120.0, h=140.0)
    assert det.mouth_activity == 0.0
    with pytest.raises(AttributeError):
        det.cx = 0.0  # type: ignore[misc]

    with pytest.raises(TypeError):
        FaceDetectionFrame(at_ms=True, track_id=0, cx=1.0, cy=1.0, w=10.0, h=10.0)
    with pytest.raises(ValueError):
        FaceDetectionFrame(at_ms=0, track_id=0, cx=1.0, cy=1.0, w=0.0, h=10.0)
    with pytest.raises(ValueError):
        FaceDetectionFrame(at_ms=0, track_id=0, cx=1.0, cy=1.0, w=10.0, h=10.0, mouth_activity=-0.1)

    score = ActiveSpeakerScore(
        at_ms=100, track_id=1, score=0.85, is_speaking=True, backend="mouth_av_corr"
    )
    assert score.backend == "mouth_av_corr"
    with pytest.raises(TypeError):
        ActiveSpeakerScore(
            at_ms=100,
            track_id=1,
            score=0.5,
            is_speaking=1,  # type: ignore[arg-type]
            backend="mouth_av_corr",
        )
    with pytest.raises(ValueError):
        ActiveSpeakerScore(
            at_ms=100,
            track_id=1,
            score=0.5,
            is_speaking=True,
            backend="bogus",  # type: ignore[arg-type]
        )

    crop = LockedShotCrop(
        start_ms=0,
        end_ms=3_000,
        focus_x_px=480,
        face_center_y_px=180,
        face_height_px=96,
        active_track_id=1,
    )
    assert crop.active_track_id == 1
    with pytest.raises(ValueError):
        LockedShotCrop(0, 0, 100, 100, 50, 0)
    with pytest.raises(ValueError):
        LockedShotCrop(0, 1000, 100, 100, 0, active_track_id=0)
    # Zero-face B-roll crop allows face_height_px=0 when active_track_id is None
    broll = LockedShotCrop(0, 1000, 320, 180, 0, active_track_id=None)
    assert broll.active_track_id is None


# ---------------------------------------------------------------------------
# 2. Synthetic 2-speaker AV sync tests (smaller speaking face beats larger silent face)
# ---------------------------------------------------------------------------


def _syllable_burst(t: float) -> float:
    """Periodic 0.45 s speech bursts with 0.35 s pauses, modulated at 4 Hz."""
    cycle = t % 0.80
    if cycle > 0.45:
        return 0.0
    return 0.5 * (1.0 - math.cos(2.0 * math.pi * (cycle / 0.45)))


def _mouth_syllable_motion(t: float) -> float:
    """Lip opening/closing synchronized to ``_syllable_burst(t)``."""
    env = _syllable_burst(t)
    if env <= 0.02:
        return 0.0
    # Rapid lip articulation while syllable is active
    return env * (0.5 + 0.5 * math.sin(2.0 * math.pi * 6.0 * t))


def test_smaller_speaking_face_beats_larger_silent_nodding_face(tmp_path: Path) -> None:
    """Small Face B (96x96) speaking cleanly beats Large Face A (200x200) nodding silently."""
    duration_s = 4.8

    def audio_env(t: float) -> float:
        # Active speech in [0.0, 3.2 s], complete silence in [3.2, 4.8 s]
        return _syllable_burst(t) if t < 3.2 else 0.0

    def face_b_mouth(t: float) -> float:
        return _mouth_syllable_motion(t) if t < 3.2 else 0.0

    video_path, wav_path, detections = _build_two_speaker_av_clip(
        tmp_path,
        duration_s=duration_s,
        fps=25,
        speech_envelope_fn=audio_env,
        face_a_mouth_fn=lambda _t: 0.0,  # Large Face A stays silent
        face_b_mouth_fn=face_b_mouth,  # Small Face B talks in sync
        face_a_nod_px=3.0,  # Head nods must NOT fool translation-compensated scorer!
    )

    scores = score_active_speakers(video_path, wav_path, detections)
    assert len(scores) == len(detections)
    assert all(sc.backend == "mouth_av_corr" for sc in scores)

    # Active speech window [300 ms, 2900 ms]
    a_speech = [sc for sc in scores if sc.track_id == 0 and 300 <= sc.at_ms <= 2_900]
    b_speech = [sc for sc in scores if sc.track_id == 1 and 300 <= sc.at_ms <= 2_900]
    mean_a = sum(sc.score for sc in a_speech) / len(a_speech)
    mean_b = sum(sc.score for sc in b_speech) / len(b_speech)
    b_speaking_ratio = sum(1 for sc in b_speech if sc.is_speaking) / len(b_speech)
    a_speaking_ratio = sum(1 for sc in a_speech if sc.is_speaking) / len(a_speech)

    assert mean_b > mean_a + 0.30, (
        f"Small speaking face ({mean_b:.3f}) must beat large ({mean_a:.3f})"
    )
    assert b_speaking_ratio >= 0.40
    assert a_speaking_ratio == 0.0

    # Silence window [3600 ms, 4600 ms]: nobody should be marked speaking
    silence_scores = [sc for sc in scores if 3_600 <= sc.at_ms <= 4_600]
    assert silence_scores
    assert all(not sc.is_speaking for sc in silence_scores)

    # End-to-end locked crop MUST frame Small Face B (cx=480, h=96), NOT Large Face A (cx=170)
    crops = compute_locked_shot_crops(
        detections,
        scores,
        source_width=640,
        source_height=360,
        clip_duration_ms=4_800,
    )
    assert len(crops) == 1
    assert crops[0].active_track_id == 1
    assert crops[0].focus_x_px == 480
    assert crops[0].face_center_y_px == 180
    assert crops[0].face_height_px == 96


def test_two_speaker_handoff_end_to_end(tmp_path: Path) -> None:
    """Small Face B speaks [0..3.2s], then Large Face A speaks [3.2..6.4s] -> 2 locked crops."""
    duration_s = 6.4

    video_path, wav_path, detections = _build_two_speaker_av_clip(
        tmp_path,
        duration_s=duration_s,
        fps=25,
        speech_envelope_fn=_syllable_burst,
        face_a_mouth_fn=lambda t: _mouth_syllable_motion(t) if t >= 3.2 else 0.0,
        face_b_mouth_fn=lambda t: _mouth_syllable_motion(t) if t < 3.2 else 0.0,
    )

    scores = score_active_speakers(video_path, wav_path, detections)
    crops = compute_locked_shot_crops(
        detections,
        scores,
        source_width=640,
        source_height=360,
        clip_duration_ms=6_400,
        min_switch_hold_ms=2_200,
    )

    assert len(crops) == 2
    assert crops[0].start_ms == 0
    assert crops[0].active_track_id == 1
    assert crops[0].focus_x_px == 480
    assert crops[1].start_ms == crops[0].end_ms
    assert crops[1].end_ms == 6_400
    assert crops[1].active_track_id == 0
    assert crops[1].focus_x_px == 170
    # Switch occurs near the 3.2 s handoff (within one burst margin)
    assert 2_400 <= crops[0].end_ms <= 4_000


def test_antiphase_mouth_motion_loses_to_synced_speaker(tmp_path: Path) -> None:
    """Face A moving out-of-phase during pauses loses cleanly to in-sync Face B."""
    video_path, wav_path, detections = _build_two_speaker_av_clip(
        tmp_path,
        duration_s=4.0,
        fps=25,
        speech_envelope_fn=_syllable_burst,
        # Face A moves strictly during the pauses (shifted by half cycle = 0.40 s)
        face_a_mouth_fn=lambda t: _mouth_syllable_motion(t + 0.40),
        face_b_mouth_fn=_mouth_syllable_motion,
    )

    scores = score_active_speakers(video_path, wav_path, detections)
    a_scores = [sc.score for sc in scores if sc.track_id == 0 and 400 <= sc.at_ms <= 3_600]
    b_scores = [sc.score for sc in scores if sc.track_id == 1 and 400 <= sc.at_ms <= 3_600]
    assert sum(b_scores) / len(b_scores) > sum(a_scores) / len(a_scores) + 0.25


# ---------------------------------------------------------------------------
# 3. ONNX Light-ASD backend + strict fail-stop tests
# ---------------------------------------------------------------------------


def test_onnx_missing_model_fails_loudly_no_fallback(tmp_path: Path) -> None:
    video_path, wav_path, detections = _build_two_speaker_av_clip(
        tmp_path,
        duration_s=0.4,
        fps=10,
        speech_envelope_fn=lambda _t: 0.2,
        face_a_mouth_fn=lambda _t: 0.0,
        face_b_mouth_fn=lambda _t: 0.5,
    )
    missing_model = tmp_path / "does_not_exist_light_asd.onnx"
    with pytest.raises(FileNotFoundError, match="Light-ASD ONNX model not found"):
        score_active_speakers(video_path, wav_path, detections, onnx_model_path=missing_model)


def test_onnx_corrupt_model_fails_loudly_no_fallback(tmp_path: Path) -> None:
    video_path, wav_path, detections = _build_two_speaker_av_clip(
        tmp_path,
        duration_s=0.4,
        fps=10,
        speech_envelope_fn=lambda _t: 0.2,
        face_a_mouth_fn=lambda _t: 0.0,
        face_b_mouth_fn=lambda _t: 0.5,
    )
    corrupt_model = tmp_path / "corrupt_light_asd.onnx"
    corrupt_model.write_bytes(b"not a valid onnx protobuf payload")
    with pytest.raises(ActiveSpeakerError, match="Failed to load Light-ASD ONNX model"):
        score_active_speakers(video_path, wav_path, detections, onnx_model_path=corrupt_model)


def test_missing_media_files_fail_loudly(tmp_path: Path) -> None:
    fake_wav = tmp_path / "good.wav"
    _write_pcm16_wav(fake_wav, np.zeros(1600, dtype=np.float32))
    with pytest.raises(FileNotFoundError, match="Video file not found"):
        score_active_speakers(tmp_path / "missing.avi", fake_wav, ())

    bad_wav = tmp_path / "bad.wav"
    bad_wav.write_bytes(b"RIFFbad")
    video_path, _, _ = _build_two_speaker_av_clip(
        tmp_path,
        duration_s=0.2,
        fps=10,
        speech_envelope_fn=lambda _t: 0.0,
        face_a_mouth_fn=lambda _t: 0.0,
        face_b_mouth_fn=lambda _t: 0.0,
    )
    with pytest.raises(ActiveSpeakerError, match="Failed to read WAV"):
        score_active_speakers(video_path, bad_wav, ())


def test_onnx_light_asd_session_contract_and_gpu_provider_preference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify ONNX backend feeds 112x112 gray + 13-dim MFCC and prefers CUDA on GPU 1."""
    video_path, wav_path, detections = _build_two_speaker_av_clip(
        tmp_path,
        duration_s=0.5,
        fps=10,
        speech_envelope_fn=_syllable_burst,
        face_a_mouth_fn=lambda _t: 0.0,
        face_b_mouth_fn=_mouth_syllable_motion,
    )
    dummy_model = tmp_path / "light_asd.onnx"
    dummy_model.write_bytes(b"placeholder")

    captured: dict[str, Any] = {"providers": None, "calls": []}

    class _FakeInput:
        def __init__(self, name: str, shape: list[Any]) -> None:
            self.name = name
            self.shape = shape

    class _FakeSession:
        def __init__(self, path: str, providers: list[Any]) -> None:
            captured["path"] = path
            captured["providers"] = providers

        def get_inputs(self) -> list[_FakeInput]:
            return [
                _FakeInput("video", [1, "T", 112, 112]),
                _FakeInput("audio", [1, "4T", 13]),
            ]

        def run(
            self,
            _output_names: Any,
            feed: dict[str, NDArray[np.float32]],
        ) -> list[NDArray[np.float32]]:
            vis = feed["video"]
            aud = feed["audio"]
            captured["calls"].append((vis.shape, aud.shape, vis.dtype, aud.dtype))
            t_len = int(vis.shape[1])
            # Return 2-class logits: track with higher visual variance gets positive speaking margin
            vis_std = float(np.std(np.diff(vis[0], axis=0))) if t_len > 1 else 0.0
            margin = 2.5 if vis_std > 0.01 else -2.5
            logits = np.zeros((1, t_len, 2), dtype=np.float32)
            logits[..., 0] = -margin / 2.0
            logits[..., 1] = margin / 2.0
            return [logits]

    fake_ort = types.SimpleNamespace(
        get_available_providers=lambda: ["CUDAExecutionProvider", "CPUExecutionProvider"],
        InferenceSession=_FakeSession,
    )
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_ort)

    scores = score_active_speakers(
        video_path,
        wav_path,
        detections,
        onnx_model_path=dummy_model,
        gpu_device_id=1,
    )
    assert len(scores) == len(detections)
    assert all(sc.backend == "light_asd_onnx" for sc in scores)
    assert captured["providers"] == [
        ("CUDAExecutionProvider", {"device_id": 1}),
        "CPUExecutionProvider",
    ]
    assert len(captured["calls"]) == 2  # Two tracks
    for vis_shape, aud_shape, vis_dtype, aud_dtype in captured["calls"]:
        assert vis_shape == (1, 5, 112, 112)
        assert aud_shape == (1, 20, 13)
        assert vis_dtype == np.float32
        assert aud_dtype == np.float32


# ---------------------------------------------------------------------------
# 4. Rock-steady locked per-shot crop planner & hysteresis tests
# ---------------------------------------------------------------------------


def _make_detections(
    track_specs: dict[int, tuple[float, float, float, float]],
    duration_ms: int,
    step_ms: int = 100,
    jitter_fn: Callable[[int, int], tuple[float, float]] | None = None,
) -> list[FaceDetectionFrame]:
    dets: list[FaceDetectionFrame] = []
    for at_ms in range(0, duration_ms, step_ms):
        for tid, (cx, cy, w, h) in track_specs.items():
            dx, dy = jitter_fn(tid, at_ms) if jitter_fn is not None else (0.0, 0.0)
            dets.append(
                FaceDetectionFrame(at_ms=at_ms, track_id=tid, cx=cx + dx, cy=cy + dy, w=w, h=h)
            )
    return dets


def test_locked_shot_crops_hysteresis_blocks_ping_pong() -> None:
    """Brief backchannels (< min_switch_hold_ms) must NEVER cause camera ping-pong."""
    dets = _make_detections(
        {0: (300.0, 260.0, 180.0, 180.0), 1: (1500.0, 280.0, 150.0, 150.0)},
        duration_ms=10_000,
    )
    scores: list[ActiveSpeakerScore] = []
    for at_ms in range(0, 10_000, 100):
        # Track 0 dominates; Track 1 briefly interjects for 700 ms twice (< 2200 ms hold)
        t1_interject = (2_500 <= at_ms < 3_200) or (6_200 <= at_ms < 6_900)
        scores.append(
            ActiveSpeakerScore(
                at_ms, 0, 0.1 if t1_interject else 0.9, not t1_interject, "mouth_av_corr"
            )
        )
        scores.append(
            ActiveSpeakerScore(
                at_ms, 1, 0.9 if t1_interject else 0.1, t1_interject, "mouth_av_corr"
            )
        )

    crops = compute_locked_shot_crops(
        dets,
        scores,
        source_width=1920,
        source_height=1080,
        clip_duration_ms=10_000,
        min_switch_hold_ms=2_200,
    )
    assert len(crops) == 1
    assert crops[0] == LockedShotCrop(
        start_ms=0,
        end_ms=10_000,
        focus_x_px=300,
        face_center_y_px=260,
        face_height_px=180,
        active_track_id=0,
    )


def test_locked_shot_crops_rapid_alternating_ping_pong_collapses_to_majority() -> None:
    """1-second alternating ping-pong must collapse to ONE rock-steady crop."""
    dets = _make_detections(
        {0: (350.0, 300.0, 160.0, 160.0), 1: (1450.0, 300.0, 160.0, 160.0)},
        duration_ms=5_000,
    )
    scores: list[ActiveSpeakerScore] = []
    for at_ms in range(0, 5_000, 100):
        # 0..1s T0, 1..2s T1, 2..3s T0, 3..4s T1, 4..5s T0 -> T0 has 3s vs T1 2s
        active = (at_ms // 1_000) % 2
        for tid in (0, 1):
            scores.append(
                ActiveSpeakerScore(
                    at_ms, tid, 0.85 if tid == active else 0.05, tid == active, "mouth_av_corr"
                )
            )

    crops = compute_locked_shot_crops(
        dets,
        scores,
        source_width=1920,
        source_height=1080,
        clip_duration_ms=5_000,
        min_switch_hold_ms=2_200,
    )
    assert len(crops) == 1
    assert crops[0].active_track_id == 0


def test_locked_shot_crops_zero_jitter_median_and_shot_cuts() -> None:
    """Noisy detections collapse to ONE exact median per shot; hard shot cuts always split."""
    dets = _make_detections(
        {0: (400.0, 300.0, 160.0, 160.0)},
        duration_ms=4_000,
        jitter_fn=lambda _tid, ms: (12.0 * math.sin(ms * 0.015), 8.0 * math.cos(ms * 0.02)),
    )
    # Shot 2 [4000..5200): zero-face B-roll (even though < min_switch_hold_ms, shot cut honored!)
    # Shot 3 [5200..8000): Track 2 at cx=1300
    for at_ms in range(5_200, 8_000, 100):
        dets.append(
            FaceDetectionFrame(at_ms=at_ms, track_id=2, cx=1300.0, cy=320.0, w=200.0, h=200.0)
        )

    scores = [ActiveSpeakerScore(d.at_ms, d.track_id, 0.8, True, "mouth_av_corr") for d in dets]

    crops = compute_locked_shot_crops(
        dets,
        scores,
        source_width=1920,
        source_height=1080,
        shot_cuts_ms=(4_000, 5_200),
        clip_duration_ms=8_000,
        min_switch_hold_ms=2_200,
    )
    assert len(crops) == 3
    # Shot 1: rock-steady median near (400, 300, 160)
    assert crops[0].start_ms == 0
    assert crops[0].end_ms == 4_000
    assert crops[0].active_track_id == 0
    assert abs(crops[0].focus_x_px - 400) <= 3
    assert abs(crops[0].face_center_y_px - 300) <= 3
    assert crops[0].face_height_px == 160

    # Shot 2: zero-face B-roll centered cleanly
    assert crops[1] == LockedShotCrop(
        start_ms=4_000,
        end_ms=5_200,
        focus_x_px=960,
        face_center_y_px=540,
        face_height_px=0,
        active_track_id=None,
    )

    # Shot 3: Track 2 locked
    assert crops[2] == LockedShotCrop(
        start_ms=5_200,
        end_ms=8_000,
        focus_x_px=1300,
        face_center_y_px=320,
        face_height_px=200,
        active_track_id=2,
    )

    # Verify zero-skew hold-and-step FocusPoint conversion ((cut_ms, old_x), (cut_ms + 1, new_x))
    focus_pts = locked_crops_to_focus_points(crops)
    assert len(focus_pts) == 6
    assert [p.at_ms for p in focus_pts] == [0, 4_000, 4_001, 5_200, 5_201, 8_000]
    assert focus_pts[0].center_x == focus_pts[1].center_x == crops[0].focus_x_px
    assert focus_pts[2].face_height is None
    assert focus_pts[4].center_x == focus_pts[5].center_x == 1300


def test_lag_tolerance_and_48k_stereo_wav_resampling(tmp_path: Path) -> None:
    """Audio shifted by +60 ms (within +-80 ms max_lag_ms) and 48 kHz stereo WAV still sync."""
    duration_s = 3.2
    video_path, _, detections = _build_two_speaker_av_clip(
        tmp_path,
        duration_s=duration_s,
        fps=25,
        speech_envelope_fn=_syllable_burst,
        face_a_mouth_fn=lambda _t: 0.0,
        face_b_mouth_fn=_mouth_syllable_motion,
    )
    # Write a 48 kHz stereo WAV shifted by +60 ms relative to video
    sr = 48_000
    t_audio = np.arange(int(round(duration_s * sr)), dtype=np.float64) / float(sr)
    env = np.array(
        [_syllable_burst(max(0.0, float(ts) - 0.060)) for ts in t_audio], dtype=np.float64
    )
    carrier = 0.6 * np.sin(2.0 * math.pi * 600.0 * t_audio)
    mono = np.clip(0.45 * env * carrier, -1.0, 1.0)
    stereo = np.stack([mono, mono], axis=1)
    pcm = (stereo * 32767.0).astype("<i2")
    wav_48k = tmp_path / "stereo_48k.wav"
    with wave.open(str(wav_48k), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())

    scores = score_active_speakers(video_path, wav_48k, detections)
    a_mean = float(
        np.mean([sc.score for sc in scores if sc.track_id == 0 and 400 <= sc.at_ms <= 2_800])
    )
    b_mean = float(
        np.mean([sc.score for sc in scores if sc.track_id == 1 and 400 <= sc.at_ms <= 2_800])
    )
    assert b_mean > a_mean + 0.30


def test_empty_detections_returns_empty_but_still_validates_onnx(tmp_path: Path) -> None:
    video_path, wav_path, _ = _build_two_speaker_av_clip(
        tmp_path,
        duration_s=0.3,
        fps=10,
        speech_envelope_fn=lambda _t: 0.0,
        face_a_mouth_fn=lambda _t: 0.0,
        face_b_mouth_fn=lambda _t: 0.0,
    )
    assert score_active_speakers(video_path, wav_path, ()) == ()
    with pytest.raises(FileNotFoundError, match="Light-ASD ONNX model not found"):
        score_active_speakers(
            video_path,
            wav_path,
            (),
            onnx_model_path=tmp_path / "missing.onnx",
        )


def test_onnx_inference_runtime_error_fails_loudly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    video_path, wav_path, detections = _build_two_speaker_av_clip(
        tmp_path,
        duration_s=0.3,
        fps=10,
        speech_envelope_fn=_syllable_burst,
        face_a_mouth_fn=lambda _t: 0.0,
        face_b_mouth_fn=_mouth_syllable_motion,
    )
    dummy_model = tmp_path / "boom.onnx"
    dummy_model.write_bytes(b"placeholder")

    class _FakeInput:
        def __init__(self, name: str, shape: list[Any]) -> None:
            self.name = name
            self.shape = shape

    class _FailingSession:
        def __init__(self, _path: str, providers: list[Any]) -> None:
            _ = providers

        def get_inputs(self) -> list[_FakeInput]:
            return [_FakeInput("video", [1, "T", 112, 112]), _FakeInput("audio", [1, "4T", 13])]

        def run(
            self,
            _output_names: Any,
            _feed: dict[str, NDArray[np.float32]],
        ) -> list[NDArray[np.float32]]:
            raise RuntimeError("CUDA OOM")

    fake_ort = types.SimpleNamespace(
        get_available_providers=lambda: ["CPUExecutionProvider"],
        InferenceSession=_FailingSession,
    )
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_ort)

    with pytest.raises(ActiveSpeakerError, match="Light-ASD ONNX inference failed"):
        score_active_speakers(video_path, wav_path, detections, onnx_model_path=dummy_model)


def test_locked_shot_crops_silent_shot_holds_best_visible_face() -> None:
    """When nobody speaks in a shot with visible faces, hold the best-scored visible face."""
    dets = _make_detections(
        {0: (300.0, 260.0, 180.0, 180.0), 1: (1500.0, 280.0, 140.0, 140.0)},
        duration_ms=3_000,
    )
    scores = [
        ActiveSpeakerScore(
            d.at_ms, d.track_id, 0.12 if d.track_id == 1 else 0.02, False, "mouth_av_corr"
        )
        for d in dets
    ]
    crops = compute_locked_shot_crops(
        dets,
        scores,
        source_width=1920,
        source_height=1080,
        clip_duration_ms=3_000,
    )
    assert len(crops) == 1
    assert crops[0].active_track_id == 1
    assert crops[0].focus_x_px == 1500


# ---------------------------------------------------------------------------
# 5. D-387 zero-double-cut regression tests (native-FPS cuts + zero x/y/w/h skew)
# ---------------------------------------------------------------------------


def test_locked_crops_to_render_inputs_zero_skew_with_crop_filter() -> None:
    """x, y, w, and h must transition at the EXACT same millisecond in render.crop_filter."""
    clip_in_ms = 309_162
    crops = (
        LockedShotCrop(
            0, 8_966, focus_x_px=1_940, face_center_y_px=456, face_height_px=208, active_track_id=1
        ),
        LockedShotCrop(
            8_966,
            26_997,
            focus_x_px=672,
            face_center_y_px=536,
            face_height_px=252,
            active_track_id=2,
        ),
        LockedShotCrop(
            26_997,
            33_034,
            focus_x_px=1_392,
            face_center_y_px=440,
            face_height_px=404,
            active_track_id=3,
        ),
    )
    focus_points, per_shot_boxes = locked_crops_to_render_inputs(crops, clip_in_ms=clip_in_ms)
    flt = crop_filter(
        2560,
        1440,
        focus_points=focus_points,
        per_shot_boxes=per_shot_boxes,
        clip_in_ms=clip_in_ms,
    )
    # Cut 1 (8966 ms -> 8.964 s) and Cut 2 (26997 ms -> 26.995 s) must match across x, y, w, h!
    # Crucially, NO 8.963 or 26.994 1-ms split-transition timestamps may appear.
    assert "lt(t\\,8.964)" in flt
    assert "8.964 crop w" in flt
    assert "8.964 crop h" in flt
    assert "8.963" not in flt
    assert "lt(t\\,26.995)" in flt
    assert "26.995 crop w" in flt
    assert "26.995 crop h" in flt
    assert "26.994" not in flt


def _build_multishot_25fps_video(
    tmp_path: Path,
    *,
    shot_frame_ranges: Sequence[tuple[int, tuple[int, int, int]]],
    fps: int = 25,
) -> Path:
    """Create a 25 fps MJPG video with sharp high-contrast camera cuts on exact frame indices."""
    video_path = tmp_path / "multishot_25fps.avi"
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")  # type: ignore[attr-defined]
    writer = cv2.VideoWriter(str(video_path), fourcc, float(fps), (320, 180))
    assert writer.isOpened()
    try:
        for shot_idx, (n_frames, bgr) in enumerate(shot_frame_ranges):
            frame = np.zeros((180, 320, 3), dtype=np.uint8)
            frame[:, :] = bgr
            # Add distinct spatial structure per shot so scene-change score is cleanly > 0.5
            if shot_idx % 2 == 0:
                cv2.rectangle(frame, (10, 10), (150, 170), (240, 240, 240), -1)
            else:
                cv2.circle(frame, (240, 90), 70, (20, 20, 20), -1)
            for _ in range(n_frames):
                writer.write(frame)
    finally:
        writer.release()
    return video_path


def test_detect_exact_shot_cuts_ms_zero_frame_offset(tmp_path: Path) -> None:
    """Native-FPS shot detection hits non-200ms cuts (880 ms, 2160 ms) with 0-frame error."""
    # Shots: 22 f (0..880 ms), 32 f (880..2160 ms), 26 f (2160..3200 ms).
    # Neither 880 ms nor 2160 ms is a multiple of 200 ms (5 fps proxy drifts 80-160 ms).
    video_path = _build_multishot_25fps_video(
        tmp_path,
        shot_frame_ranges=[
            (22, (20, 30, 220)),
            (32, (230, 220, 20)),
            (26, (20, 210, 40)),
        ],
    )
    cuts = detect_exact_shot_cuts_ms(video_path, clip_in_ms=0, clip_out_ms=3_200)
    assert cuts == (880, 2_160)

    # Strict fail-stop on missing video
    with pytest.raises(FileNotFoundError, match="Video file not found"):
        detect_exact_shot_cuts_ms(tmp_path / "missing.avi")


def test_detect_exact_assembled_cuts_ms_zero_frame_offset(tmp_path: Path) -> None:
    """Assembled CFR cut detection hits exact [v_cfr] splice & internal cut frames."""
    video_path = _build_multishot_25fps_video(
        tmp_path,
        shot_frame_ranges=[
            (25, (20, 30, 220)),  # 0..1000 ms
            (25, (230, 220, 20)),  # 1000..2000 ms
            (25, (20, 210, 40)),  # 2000..3000 ms
        ],
    )
    # Span 0: [2004..2608] (inside Shot 2, ~600 ms -> 15 frames = 600 ms)
    # Span 1: [404..1604] (starts in Shot 0, cuts to Shot 1 at 1000 ms -> 600 + 560 = 1160 ms)
    cuts = detect_exact_assembled_cuts_ms(
        video_path,
        assembly_spans_ms=((2_004, 2_608), (404, 1_604)),
        fps=25.0,
        include_audio=False,
    )
    assert len(cuts) == 2
    assert cuts[0] % 40 == 0
    assert cuts[1] % 40 == 0
    assert 560 <= cuts[0] <= 640
    assert 1_120 <= cuts[1] <= 1_240


def test_snap_locked_crops_to_cuts_eliminates_drift() -> None:
    """Snapping aligns drifted 5fps/raw boundaries onto exact native/CFR cuts cleanly."""
    drifted = (
        LockedShotCrop(0, 2_044, 480, 300, 200, 1),
        LockedShotCrop(2_044, 10_044, 1_400, 320, 220, 2),
        LockedShotCrop(10_044, 15_744, 520, 310, 210, 3),
        LockedShotCrop(15_744, 32_011, 1_380, 300, 190, 4),
        LockedShotCrop(32_011, 43_357, 600, 330, 240, 5),
    )
    # Include one distant cut (25_000 ms) that exceeds max_snap_ms and must be ignored.
    exact_cfr = (2_040, 9_920, 15_760, 25_000, 31_920)
    snapped = snap_locked_crops_to_cuts(drifted, exact_cfr, max_snap_ms=250)

    assert [(c.start_ms, c.end_ms) for c in snapped] == [
        (0, 2_040),
        (2_040, 9_920),
        (9_920, 15_760),
        (15_760, 31_920),
        (31_920, 43_357),
    ]
    assert [c.focus_x_px for c in snapped] == [480, 1_400, 520, 1_380, 600]
    assert [c.active_track_id for c in snapped] == [1, 2, 3, 4, 5]


def test_snap_locked_crops_coalesces_identical_spans_before_snapping() -> None:
    """Identical adjacent spans must not steal an exact CFR cut from a real crop switch."""
    # Mirrors real r02-s86-87 failure: (1849, 9668, 928) + (9668, 9854, 928) -> (9854, 11600, 484).
    # Without coalescing, no-op boundary 9668 stole CFR cut 9840, leaving 928->484 1 frame late!
    crops = (
        LockedShotCrop(0, 1_849, 440, 300, 200, 1),
        LockedShotCrop(1_849, 9_668, 928, 320, 220, 2),
        LockedShotCrop(9_668, 9_854, 928, 320, 220, 2),
        LockedShotCrop(9_854, 11_600, 484, 310, 210, 3),
    )
    snapped = snap_locked_crops_to_cuts(crops, (1_840, 9_840), max_snap_ms=250)
    assert [(c.start_ms, c.end_ms, c.focus_x_px) for c in snapped] == [
        (0, 1_840, 440),
        (1_840, 9_840, 928),
        (9_840, 11_600, 484),
    ]
