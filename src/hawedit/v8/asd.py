"""V8 Module 4 (D-385): Audio-Visual Active Speaker Detection & Rock-Steady Locked Crop Planner.

- Backend A (``light_asd_onnx``): ONNXRuntime Light-ASD (112x112 gray crops + 13-dim 16 kHz MFCCs),
  preferring CUDAExecutionProvider on GPU 1; strict fail-stop (zero silent fallback).
- Backend B (``mouth_av_corr``): Deterministic zero-weight scorer correlating sub-pixel
  translation-compensated lower-third mouth motion with a 300-3400 Hz speech envelope.
- Locked Per-Shot Crop Planner: partitions clips at ``shot_cuts_ms`` and hysteresis-filtered
  speaker switches (``>= min_switch_hold_ms``), emitting ONE rock-steady median crop per hold.
"""

from __future__ import annotations

import importlib
import math
import re
import subprocess
import wave
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any, Final, Literal, Protocol

import cv2
import numpy as np
from numpy.typing import NDArray

from hawedit.captions import find_ffmpeg
from hawedit.reframe import FocusPoint

ActiveSpeakerBackend = Literal["light_asd_onnx", "mouth_av_corr"]

DEFAULT_WINDOW_MS: Final = 600
DEFAULT_MAX_LAG_MS: Final = 80
DEFAULT_SPEAKING_THRESHOLD: Final = 0.20
DEFAULT_MIN_SPEECH_RMS: Final = 0.012
DEFAULT_MIN_SWITCH_HOLD_MS: Final = 2_200

_SR: Final = 16_000
_HOP_MS: Final = 10
_WIN_MS: Final = 25
_MOUTH_PATCH: Final = (48, 32)  # (width, height)
_SHIFT_X: Final = 6
_SHIFT_Y: Final = 5
_TRACK_GAP_RESET_MS: Final = 500
_MOUTH_NOISE_FLOOR: Final = 0.010
_MOUTH_MOTION_FULL: Final = 0.025
_LIGHT_ASD_IMG: Final = 112
_LIGHT_ASD_MFCC: Final = 13
_SHOWINFO_PTS_RE: Final[re.Pattern[str]] = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")

__all__ = [
    "DEFAULT_MAX_LAG_MS",
    "DEFAULT_MIN_SPEECH_RMS",
    "DEFAULT_MIN_SWITCH_HOLD_MS",
    "DEFAULT_SPEAKING_THRESHOLD",
    "DEFAULT_WINDOW_MS",
    "ActiveSpeakerBackend",
    "ActiveSpeakerError",
    "ActiveSpeakerScore",
    "FaceDetectionFrame",
    "LockedCropLike",
    "LockedShotCrop",
    "compute_locked_shot_crops",
    "detect_exact_assembled_cuts_ms",
    "detect_exact_shot_cuts_ms",
    "locked_crops_to_focus_points",
    "locked_crops_to_render_inputs",
    "score_active_speakers",
    "snap_locked_crops_to_cuts",
]


class ActiveSpeakerError(RuntimeError):
    """Strict fail-stop error raised when audio-visual ASD inputs or inference fail."""


def _req_int(value: object, name: str, *, min_val: int = 0) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be an exact int, got {type(value).__name__}")
    if value < min_val:
        raise ValueError(f"{name} must be >= {min_val}, got {value}")
    return value


def _req_float(
    value: object, name: str, *, min_val: float | None = None, gt: bool = False
) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise TypeError(f"{name} must be a finite number, got {value!r}")
    out = float(value)
    if min_val is not None and ((out <= min_val) if gt else (out < min_val)):
        op = ">" if gt else ">="
        raise ValueError(f"{name} must be {op} {min_val}, got {out}")
    return out


@dataclass(frozen=True, slots=True)
class FaceDetectionFrame:
    """Single face detection observation belonging to a tracked face at ``at_ms``."""

    at_ms: int
    track_id: int
    cx: float
    cy: float
    w: float
    h: float
    mouth_activity: float = 0.0

    def __post_init__(self) -> None:
        _req_int(self.at_ms, "at_ms")
        _req_int(self.track_id, "track_id")
        _req_float(self.cx, "cx", min_val=0.0)
        _req_float(self.cy, "cy", min_val=0.0)
        _req_float(self.w, "w", min_val=0.0, gt=True)
        _req_float(self.h, "h", min_val=0.0, gt=True)
        _req_float(self.mouth_activity, "mouth_activity", min_val=0.0)


@dataclass(frozen=True, slots=True)
class ActiveSpeakerScore:
    """Audio-visual active speaker score for one face track at ``at_ms``."""

    at_ms: int
    track_id: int
    score: float
    is_speaking: bool
    backend: ActiveSpeakerBackend

    def __post_init__(self) -> None:
        _req_int(self.at_ms, "at_ms")
        _req_int(self.track_id, "track_id")
        _req_float(self.score, "score")
        if type(self.is_speaking) is not bool:
            raise TypeError(f"is_speaking must be bool, got {type(self.is_speaking).__name__}")
        if self.backend not in ("light_asd_onnx", "mouth_av_corr"):
            raise ValueError(f"unsupported ASD backend: {self.backend!r}")


@dataclass(frozen=True, slots=True)
class LockedShotCrop:
    """Rock-steady locked 9:16 crop target for one contiguous shot/speaker hold."""

    start_ms: int
    end_ms: int
    focus_x_px: int
    face_center_y_px: int
    face_height_px: int
    active_track_id: int | None

    def __post_init__(self) -> None:
        start = _req_int(self.start_ms, "start_ms")
        end = _req_int(self.end_ms, "end_ms")
        if end <= start:
            raise ValueError(f"end_ms ({end}) must be > start_ms ({start})")
        _req_int(self.focus_x_px, "focus_x_px")
        _req_int(self.face_center_y_px, "face_center_y_px")
        face_h = _req_int(self.face_height_px, "face_height_px")
        if self.active_track_id is not None:
            _req_int(self.active_track_id, "active_track_id")
            if face_h == 0:
                raise ValueError("face_height_px must be > 0 when active_track_id is set")


def _load_wav_mono_16k(path: Path) -> NDArray[np.float32]:
    if not path.is_file():
        raise FileNotFoundError(f"Audio WAV file not found: {path}")
    try:
        with wave.open(str(path), "rb") as wf:
            ch, sw, sr, nf = (
                wf.getnchannels(),
                wf.getsampwidth(),
                wf.getframerate(),
                wf.getnframes(),
            )
            raw = wf.readframes(nf)
    except (wave.Error, EOFError, OSError) as exc:
        raise ActiveSpeakerError(f"Failed to read WAV file {path}: {exc}") from exc
    if ch <= 0 or sr <= 0 or nf <= 0:
        raise ActiveSpeakerError(f"Invalid WAV stream in {path}: ch={ch}, sr={sr}, frames={nf}")

    if sw == 1:
        s = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sw == 2:
        s = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sw == 3:
        u = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        v = u[:, 0] | (u[:, 1] << 8) | (u[:, 2] << 16)
        s = np.where(v >= 0x800000, v - 0x1000000, v).astype(np.float32) / 8388608.0
    elif sw == 4:
        s = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ActiveSpeakerError(f"Unsupported WAV sample width {sw} bytes")
    if s.size < nf * ch:
        raise ActiveSpeakerError(f"Truncated WAV payload in {path}")
    mono = np.asarray(s[: nf * ch].reshape(nf, ch).mean(axis=1), dtype=np.float32)
    if sr != _SR:
        n_out = max(1, int(round(mono.size * _SR / sr)))
        mono = np.asarray(
            np.interp(
                np.linspace(0.0, 1.0, n_out, endpoint=False),
                np.linspace(0.0, 1.0, mono.size, endpoint=False),
                mono,
            ),
            dtype=np.float32,
        )
    return mono


def _frame_audio(signal: NDArray[np.float32], win: int, hop: int) -> NDArray[np.float32]:
    if signal.size < win:
        padded = np.zeros(win, dtype=np.float32)
        padded[: signal.size] = signal
        return padded.reshape(1, win)
    n = 1 + (signal.size - win) // hop
    idx = np.arange(win, dtype=np.intp)[None, :] + np.arange(n, dtype=np.intp)[:, None] * hop
    return np.asarray(signal[idx], dtype=np.float32)


def _speech_band_envelope(audio_16k: NDArray[np.float32]) -> NDArray[np.float32]:
    win, hop = _SR * _WIN_MS // 1000, _SR * _HOP_MS // 1000
    window = np.hanning(win).astype(np.float32)
    spec = np.fft.rfft(_frame_audio(audio_16k, win, hop) * window[None, :], axis=1)
    freqs = np.fft.rfftfreq(win, d=1.0 / _SR)
    rec = np.fft.irfft(np.where(((freqs >= 300.0) & (freqs <= 3400.0))[None, :], spec, 0.0), win)
    win_rms = max(float(np.sqrt(np.mean(window * window))), 1e-6)
    return np.asarray(np.sqrt(np.mean(rec * rec, axis=1)) / win_rms, dtype=np.float32)


def _compute_mfcc_16k(
    audio_16k: NDArray[np.float32], n_mfcc: int = _LIGHT_ASD_MFCC
) -> NDArray[np.float32]:
    pre = audio_16k.copy()
    if pre.size > 1:
        pre[1:] = audio_16k[1:] - 0.97 * audio_16k[:-1]
    win, hop, n_fft, n_mels = _SR * _WIN_MS // 1000, _SR * _HOP_MS // 1000, 512, 26
    frames = _frame_audio(pre, win, hop) * np.hamming(win).astype(np.float32)[None, :]
    power = (np.abs(np.fft.rfft(frames, n=n_fft, axis=1)) ** 2) / float(n_fft)

    hi_mel = 2595.0 * math.log10(1.0 + (_SR / 2.0) / 700.0)
    hz = 700.0 * (10.0 ** (np.linspace(0.0, hi_mel, n_mels + 2) / 2595.0) - 1.0)
    bins = np.floor((n_fft + 1) * hz / _SR).astype(np.intp)
    fbank = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
    for m in range(1, n_mels + 1):
        lo, c, hi = int(bins[m - 1]), int(bins[m]), int(bins[m + 1])
        if c > lo:
            fbank[m - 1, lo:c] = (np.arange(lo, c) - lo) / float(c - lo)
        if hi > c:
            fbank[m - 1, c:hi] = (hi - np.arange(c, hi)) / float(hi - c)
    log_mel = np.log(np.maximum(power @ fbank.T, 1e-10))
    n_i = np.arange(n_mels, dtype=np.float64)[:, None]
    k_i = np.arange(n_mfcc, dtype=np.float64)[None, :]
    dct = (np.cos(math.pi * (n_i + 0.5) * k_i / n_mels) * math.sqrt(2.0 / n_mels)).astype(
        np.float32
    )
    return np.asarray(log_mel @ dct, dtype=np.float32)


def _decode_gray_frames(
    video_path: Path, timestamps_ms: Sequence[int]
) -> dict[int, NDArray[np.uint8]]:
    if not video_path.is_file():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ActiveSpeakerError(f"OpenCV failed to open video: {video_path}")
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        if not math.isfinite(fps) or fps <= 0.0:
            raise ActiveSpeakerError(f"Invalid video FPS ({fps}) in {video_path}")
        frames: dict[int, NDArray[np.uint8]] = {}
        cur_idx = -1
        last_gray: NDArray[np.uint8] | None = None
        for at_ms in sorted(set(timestamps_ms)):
            target = max(0, int(round(at_ms * fps / 1000.0)))
            if target == cur_idx and last_gray is not None:
                frames[at_ms] = last_gray
                continue
            if target - cur_idx > 120:
                cap.set(cv2.CAP_PROP_POS_FRAMES, float(target))
                cur_idx = target - 1
            while cur_idx < target - 1 and cap.grab():
                cur_idx += 1
            ok, bgr = cap.read()
            if not ok or bgr is None:
                if last_gray is not None and (target - max(cur_idx, 0)) <= 1:
                    frames[at_ms] = last_gray
                    continue
                raise ActiveSpeakerError(
                    f"Video {video_path} ended before {at_ms} ms (fps={fps:.2f})"
                )
            cur_idx += 1
            last_gray = np.asarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), dtype=np.uint8)
            frames[at_ms] = last_gray
        return frames
    finally:
        cap.release()


def _extract_roi(
    gray: NDArray[np.uint8],
    det: FaceDetectionFrame,
    out_size: tuple[int, int] = _MOUTH_PATCH,
    *,
    full_face: bool = False,
) -> NDArray[np.float32]:
    img_h, img_w = gray.shape[:2]
    x0, y0 = det.cx - det.w * 0.5, det.cy - det.h * 0.5
    if full_face:
        rx0, rx1, ry0, ry1 = x0, x0 + det.w, y0, y0 + det.h
    else:
        rx0, rx1 = x0 + det.w * 0.20, x0 + det.w * 0.80
        ry0, ry1 = y0 + det.h * 0.58, y0 + det.h * 0.90
    ix0, iy0 = max(0, min(img_w - 1, math.floor(rx0))), max(0, min(img_h - 1, math.floor(ry0)))
    ix1, iy1 = max(ix0 + 1, min(img_w, math.ceil(rx1))), max(iy0 + 1, min(img_h, math.ceil(ry1)))
    roi = gray[iy0:iy1, ix0:ix1]
    if roi.size == 0:
        return np.zeros((out_size[1], out_size[0]), dtype=np.float32)
    return (
        np.asarray(cv2.resize(roi, out_size, interpolation=cv2.INTER_AREA), dtype=np.float32)
        / 255.0
    )


def _aligned_mouth_motion(prev_blur: NDArray[np.float32], curr_blur: NDArray[np.float32]) -> float:
    """Sub-pixel rigid-translation-compensated RMSE lip/jaw motion (48x32 patches)."""
    pw, ph = _MOUTH_PATCH
    inner = curr_blur[_SHIFT_Y : ph - _SHIFT_Y, _SHIFT_X : pw - _SHIFT_X]
    inner_zm = inner - float(np.mean(inner))
    _, _, min_loc, _ = cv2.minMaxLoc(cv2.matchTemplate(prev_blur, inner, cv2.TM_SQDIFF))
    ih, iw = inner.shape
    cx, cy = float(min_loc[0]) + (iw - 1) * 0.5, float(min_loc[1]) + (ih - 1) * 0.5

    def _rmse_at(dx: float, dy: float) -> float:
        sub = np.asarray(
            cv2.getRectSubPix(prev_blur, (iw, ih), (cx + dx, cy + dy)), dtype=np.float32
        )
        d = (sub - float(np.mean(sub))) - inner_zm
        return float(np.sqrt(np.mean(d * d)))

    best_dx, best_dy, best = 0.0, 0.0, _rmse_at(0.0, 0.0)
    if best < _MOUTH_NOISE_FLOOR * 0.5:
        return best
    for step in (0.5, 0.25):
        cdx, cdy = best_dx, best_dy
        for ox, oy in ((0.0, -step), (0.0, step), (-step, 0.0), (step, 0.0)):
            r = _rmse_at(best_dx + ox, best_dy + oy)
            if r < best:
                best, cdx, cdy = r, best_dx + ox, best_dy + oy
        best_dx, best_dy = cdx, cdy
    return best


def _smooth_1d(values: NDArray[np.float32], radius: int) -> NDArray[np.float32]:
    if radius <= 0 or values.size <= 1:
        return values.copy()
    k = np.ones(2 * radius + 1, dtype=np.float32) / float(2 * radius + 1)
    return np.convolve(np.pad(values, (radius, radius), mode="edge"), k, mode="valid").astype(
        np.float32
    )


def _max_lagged_pearson(
    motion: NDArray[np.float32], audio: NDArray[np.float32], center: int, half_w: int, max_lag: int
) -> float:
    n = min(motion.size, audio.size)
    lo, hi = max(0, center - half_w), min(n, center + half_w + 1)
    if hi - lo < 4:
        return 0.0
    m = motion[lo:hi].astype(np.float64)
    if float(np.linalg.norm(m - float(np.mean(m)))) < 1e-8:
        return 0.0
    best = -1.0
    for lag in range(-max_lag, max_lag + 1):
        a_lo, a_hi = lo + lag, hi + lag
        s0, s1 = max(0, -a_lo), (hi - lo) - max(0, a_hi - n)
        a_lo, a_hi = max(0, a_lo), min(n, a_hi)
        if s1 - s0 < 4:
            continue
        mc = m[s0:s1] - float(np.mean(m[s0:s1]))
        a = audio[a_lo:a_hi].astype(np.float64)
        ac = a - float(np.mean(a))
        denom = float(np.linalg.norm(mc) * np.linalg.norm(ac))
        if denom >= 1e-8:
            best = max(best, float(np.dot(mc, ac)) / denom)
    return best if best > -1.0 else 0.0


def _score_with_mouth_av_corr(
    gray_frames: dict[int, NDArray[np.uint8]],
    audio_16k: NDArray[np.float32],
    detections: Sequence[FaceDetectionFrame],
    *,
    window_ms: int,
    max_lag_ms: int,
    speaking_threshold: float,
    min_speech_rms: float,
) -> tuple[ActiveSpeakerScore, ...]:
    raw_env = _speech_band_envelope(audio_16k)
    smooth_env, local_env = _smooth_1d(raw_env, 6), _smooth_1d(raw_env, 7)
    grid_len = max(raw_env.size, max(d.at_ms for d in detections) // _HOP_MS + 2)
    if smooth_env.size < grid_len:
        pad = grid_len - smooth_env.size
        smooth_env = np.pad(smooth_env, (0, pad))
        local_env = np.pad(local_env, (0, pad))

    by_track: dict[int, list[tuple[int, FaceDetectionFrame]]] = defaultdict(list)
    for idx, det in enumerate(detections):
        by_track[det.track_id].append((idx, det))

    half_win, max_lag = max(2, window_ms // _HOP_MS), max(0, max_lag_ms // _HOP_MS)
    out: list[ActiveSpeakerScore | None] = [None] * len(detections)

    for track_id, items in by_track.items():
        ordered = sorted(items, key=lambda pair: pair[1].at_ms)
        ts = [det.at_ms for _, det in ordered]
        patches = [
            np.asarray(
                cv2.GaussianBlur(_extract_roi(gray_frames[det.at_ms], det), (5, 5), 1.2),
                dtype=np.float32,
            )
            for _, det in ordered
        ]
        motions = np.zeros(len(ordered), dtype=np.float32)
        for i in range(1, len(ordered)):
            if ts[i] - ts[i - 1] <= _TRACK_GAP_RESET_MS:
                motions[i] = _aligned_mouth_motion(patches[i - 1], patches[i])
        if len(ordered) > 1 and ts[1] - ts[0] <= _TRACK_GAP_RESET_MS:
            motions[0] = motions[1]

        m_grid = np.zeros(grid_len, dtype=np.float32)
        seg_start = 0
        for i in range(1, len(ordered) + 1):
            if i < len(ordered) and ts[i] - ts[i - 1] <= _TRACK_GAP_RESET_MS:
                continue
            seg_ts = np.asarray(ts[seg_start:i], dtype=np.float64)
            seg_m = motions[seg_start:i].astype(np.float64)
            g0, g1 = (
                max(0, int(seg_ts[0] // _HOP_MS)),
                min(grid_len - 1, int(seg_ts[-1] // _HOP_MS)),
            )
            if g1 >= g0:
                m_grid[g0 : g1 + 1] = (
                    float(seg_m[0])
                    if seg_ts.size == 1
                    else np.interp(np.arange(g0, g1 + 1) * _HOP_MS, seg_ts, seg_m).astype(
                        np.float32
                    )
                )
            seg_start = i

        smooth_m, local_m = _smooth_1d(m_grid, 6), _smooth_1d(m_grid, 7)
        for orig_idx, det in ordered:
            g = min(grid_len - 1, det.at_ms // _HOP_MS)
            e_loc, m_loc = float(local_env[g]), float(local_m[g])
            s_gate = (
                (1.0 if e_loc > 0.0 else 0.0)
                if min_speech_rms <= 0.0
                else min(1.0, max(0.0, (e_loc - 0.5 * min_speech_rms) / (1.5 * min_speech_rms)))
            )
            m_gate = min(
                1.0,
                max(0.0, (m_loc - _MOUTH_NOISE_FLOOR) / (_MOUTH_MOTION_FULL - _MOUTH_NOISE_FLOOR)),
            )
            act = min(1.0, m_loc / 0.06)
            if s_gate <= 0.0 or m_gate <= 0.0:
                score = 0.0
            else:
                e_win = smooth_env[max(0, g - half_win) : min(grid_len, g + half_win + 1)]
                e_cv = float(np.std(e_win)) / max(float(np.mean(e_win)), 1e-8)
                if e_cv < 0.08:
                    score = s_gate * m_gate * 0.50 * act
                else:
                    corr = max(0.0, _max_lagged_pearson(smooth_m, smooth_env, g, half_win, max_lag))
                    score = s_gate * m_gate * (0.85 * corr + 0.15 * act)
                score = min(1.0, max(0.0, score))
            out[orig_idx] = ActiveSpeakerScore(
                det.at_ms, track_id, float(score), score >= speaking_threshold, "mouth_av_corr"
            )

    return tuple(item for item in out if item is not None)


def _load_onnx_session(model_path: Path, gpu_device_id: int) -> Any:
    if not model_path.is_file():
        raise FileNotFoundError(f"Light-ASD ONNX model not found: {model_path}")
    try:
        ort = importlib.import_module("onnxruntime")
    except ImportError as exc:
        raise ActiveSpeakerError(
            "onnxruntime is required when onnx_model_path is specified"
        ) from exc
    avail = set(ort.get_available_providers())
    providers: list[str | tuple[str, dict[str, int]]] = []
    if "CUDAExecutionProvider" in avail:
        providers.append(("CUDAExecutionProvider", {"device_id": gpu_device_id}))
    if "CPUExecutionProvider" in avail:
        providers.append("CPUExecutionProvider")
    if not providers:
        raise ActiveSpeakerError(f"No usable ONNXRuntime providers available: {sorted(avail)}")
    try:
        return ort.InferenceSession(str(model_path), providers=providers)
    except Exception as exc:
        raise ActiveSpeakerError(
            f"Failed to load Light-ASD ONNX model {model_path}: {exc}"
        ) from exc


def _score_with_light_asd_onnx(
    session: Any,
    gray_frames: dict[int, NDArray[np.uint8]],
    audio_16k: NDArray[np.float32],
    detections: Sequence[FaceDetectionFrame],
    *,
    speaking_threshold: float,
) -> tuple[ActiveSpeakerScore, ...]:
    inputs = list(session.get_inputs())
    if len(inputs) < 2:
        raise ActiveSpeakerError(f"Light-ASD ONNX model needs >= 2 inputs, got {len(inputs)}")
    vis_in = next(
        (
            i
            for i in inputs
            if any(k in str(i.name).lower() for k in ("video", "visual", "face", "img", "mouth"))
            or (len(tuple(i.shape)) >= 3 and tuple(i.shape)[-1] == _LIGHT_ASD_IMG)
        ),
        inputs[0],
    )
    aud_in = next((i for i in inputs if i is not vis_in), inputs[1])
    mfcc = _compute_mfcc_16k(audio_16k, _LIGHT_ASD_MFCC)

    by_track: dict[int, list[tuple[int, FaceDetectionFrame]]] = defaultdict(list)
    for idx, det in enumerate(detections):
        by_track[det.track_id].append((idx, det))
    out: list[ActiveSpeakerScore | None] = [None] * len(detections)

    for track_id, items in by_track.items():
        ordered = sorted(items, key=lambda pair: pair[1].at_ms)
        t_len = len(ordered)
        crops = np.stack(
            [
                _extract_roi(
                    gray_frames[d.at_ms], d, (_LIGHT_ASD_IMG, _LIGHT_ASD_IMG), full_face=True
                )
                for _, d in ordered
            ],
            axis=0,
        )
        vis_arr = (crops * 2.0 - 1.0).astype(np.float32)
        vis_tensor: NDArray[np.float32] = (
            vis_arr.reshape(1, 1, t_len, _LIGHT_ASD_IMG, _LIGHT_ASD_IMG)
            if len(vis_in.shape) == 5
            else vis_arr.reshape(1, t_len, _LIGHT_ASD_IMG, _LIGHT_ASD_IMG)
        )
        aud_arr = np.zeros((4 * t_len, _LIGHT_ASD_MFCC), dtype=np.float32)
        for fi, (_, det) in enumerate(ordered):
            base = det.at_ms // _HOP_MS
            for sub in range(4):
                aud_arr[fi * 4 + sub] = mfcc[min(mfcc.shape[0] - 1, max(0, base + sub - 2))]
        aud_tensor: NDArray[np.float32] = (
            aud_arr.reshape(1, 1, 4 * t_len, _LIGHT_ASD_MFCC)
            if len(aud_in.shape) == 4
            else aud_arr.reshape(1, 4 * t_len, _LIGHT_ASD_MFCC)
        )
        try:
            raw_out = session.run(None, {vis_in.name: vis_tensor, aud_in.name: aud_tensor})
        except Exception as exc:
            raise ActiveSpeakerError(
                f"Light-ASD ONNX inference failed on track {track_id}: {exc}"
            ) from exc
        if not raw_out:
            raise ActiveSpeakerError("Light-ASD ONNX model returned no outputs")
        arr = np.asarray(raw_out[0], dtype=np.float32)
        flat = (
            (arr[..., 1] - arr[..., 0]).reshape(-1)
            if arr.ndim >= 2 and arr.shape[-1] == 2
            else arr.reshape(-1)
        )
        if flat.size < t_len:
            raise ActiveSpeakerError(f"Light-ASD ONNX output length {flat.size} < {t_len}")
        for fi, (orig_idx, det) in enumerate(ordered):
            val = float(flat[fi])
            if not math.isfinite(val):
                raise ActiveSpeakerError(
                    f"Light-ASD ONNX non-finite score {val!r} at {det.at_ms} ms"
                )
            out[orig_idx] = ActiveSpeakerScore(
                det.at_ms, track_id, val, val >= speaking_threshold, "light_asd_onnx"
            )

    return tuple(item for item in out if item is not None)


def score_active_speakers(
    video_path: Path | str,
    audio_wav_path: Path | str,
    detections: Sequence[FaceDetectionFrame],
    *,
    onnx_model_path: Path | str | None = None,
    gpu_device_id: int = 1,
    window_ms: int = DEFAULT_WINDOW_MS,
    max_lag_ms: int = DEFAULT_MAX_LAG_MS,
    speaking_threshold: float | None = None,
    min_speech_rms: float = DEFAULT_MIN_SPEECH_RMS,
) -> tuple[ActiveSpeakerScore, ...]:
    """Score per-face active speaking via ONNX Light-ASD or local mouth-ROI AV correlation."""
    _req_int(gpu_device_id, "gpu_device_id")
    _req_int(window_ms, "window_ms", min_val=1)
    _req_int(max_lag_ms, "max_lag_ms")
    min_rms = _req_float(min_speech_rms, "min_speech_rms", min_val=0.0)

    session = (
        _load_onnx_session(Path(onnx_model_path), gpu_device_id)
        if onnx_model_path is not None
        else None
    )
    audio_16k = _load_wav_mono_16k(Path(audio_wav_path))
    gray_frames = _decode_gray_frames(Path(video_path), [d.at_ms for d in detections])
    if not detections:
        return ()
    if session is not None:
        thresh = 0.0 if speaking_threshold is None else float(speaking_threshold)
        return _score_with_light_asd_onnx(
            session, gray_frames, audio_16k, detections, speaking_threshold=thresh
        )
    thresh = DEFAULT_SPEAKING_THRESHOLD if speaking_threshold is None else float(speaking_threshold)
    return _score_with_mouth_av_corr(
        gray_frames,
        audio_16k,
        detections,
        window_ms=window_ms,
        max_lag_ms=max_lag_ms,
        speaking_threshold=thresh,
        min_speech_rms=min_rms,
    )


def _coalesce_runs(runs: list[tuple[int, int, int]]) -> list[tuple[int, int, int]]:
    merged: list[tuple[int, int, int]] = []
    for s, e, tid in runs:
        if merged and merged[-1][2] == tid:
            merged[-1] = (merged[-1][0], e, tid)
        else:
            merged.append((s, e, tid))
    return merged


def _plan_shot_speaker_runs(
    shot_start: int,
    shot_end: int,
    shot_dets: Sequence[FaceDetectionFrame],
    shot_scores: Sequence[ActiveSpeakerScore],
    min_switch_hold_ms: int,
) -> list[tuple[int, int, int]]:
    det_tracks = {d.track_id for d in shot_dets}
    by_ts: dict[int, list[ActiveSpeakerScore]] = defaultdict(list)
    for sc in shot_scores:
        if sc.track_id in det_tracks:
            by_ts[sc.at_ms].append(sc)

    events = [
        (at_ms, max(sp, key=lambda sc: (sc.score, -sc.track_id)).track_id)
        for at_ms in sorted(by_ts)
        if (sp := [sc for sc in by_ts[at_ms] if sc.is_speaking])
    ]
    if not events:
        if by_ts:
            by_tid: dict[int, list[float]] = defaultdict(list)
            for sc_list in by_ts.values():
                for sc in sc_list:
                    by_tid[sc.track_id].append(sc.score)
            best = max(by_tid, key=lambda t: (sum(by_tid[t]) / len(by_tid[t]), -t))
        else:
            counts: dict[int, int] = defaultdict(int)
            for d in shot_dets:
                counts[d.track_id] += 1
            best = max(counts, key=lambda t: (counts[t], -t))
        return [(shot_start, shot_end, best)]

    runs: list[tuple[int, int, int]] = []
    cur_start, cur_tid = shot_start, events[0][1]
    for at_ms, tid in events[1:]:
        if tid != cur_tid and at_ms > cur_start:
            runs.append((cur_start, at_ms, cur_tid))
            cur_start, cur_tid = at_ms, tid
    runs = _coalesce_runs([*runs, (cur_start, shot_end, cur_tid)])

    while len(runs) > 1:
        short = [i for i, (s, e, _) in enumerate(runs) if (e - s) < min_switch_hold_ms]
        if not short:
            break
        totals: dict[int, int] = defaultdict(int)
        for s, e, tid in runs:
            totals[tid] += e - s
        idx = min(
            short,
            key=lambda i: (
                runs[i][1] - runs[i][0],
                0 if (0 < i < len(runs) - 1 and runs[i - 1][2] == runs[i + 1][2]) else 1,
                totals[runs[i][2]],
                i,
            ),
        )
        s_i, e_i, _ = runs[idx]
        if idx == 0:
            runs[1] = (s_i, runs[1][1], runs[1][2])
            del runs[0]
        elif idx == len(runs) - 1:
            runs[-2] = (runs[-2][0], e_i, runs[-2][2])
            del runs[-1]
        elif runs[idx - 1][2] == runs[idx + 1][2]:
            runs[idx - 1 : idx + 2] = [(runs[idx - 1][0], runs[idx + 1][1], runs[idx - 1][2])]
        elif (runs[idx - 1][1] - runs[idx - 1][0]) >= (runs[idx + 1][1] - runs[idx + 1][0]):
            runs[idx - 1] = (runs[idx - 1][0], e_i, runs[idx - 1][2])
            del runs[idx]
        else:
            runs[idx + 1] = (s_i, runs[idx + 1][1], runs[idx + 1][2])
            del runs[idx]
        runs = _coalesce_runs(runs)
    return runs


def compute_locked_shot_crops(
    detections: Sequence[FaceDetectionFrame],
    scores: Sequence[ActiveSpeakerScore],
    *,
    source_width: int,
    source_height: int,
    shot_cuts_ms: Sequence[int] = (),
    clip_duration_ms: int,
    min_switch_hold_ms: int = DEFAULT_MIN_SWITCH_HOLD_MS,
) -> tuple[LockedShotCrop, ...]:
    """Plan rock-steady locked per-shot crops partitioned at shot cuts and speaker switches."""
    src_w = _req_int(source_width, "source_width", min_val=1)
    src_h = _req_int(source_height, "source_height", min_val=1)
    dur_ms = _req_int(clip_duration_ms, "clip_duration_ms", min_val=1)
    min_hold = _req_int(min_switch_hold_ms, "min_switch_hold_ms")
    cuts = sorted(
        {
            _req_int(c, "shot_cuts_ms element")
            for c in shot_cuts_ms
            if 0 < _req_int(c, "shot_cuts_ms element") < dur_ms
        }
    )

    crops: list[LockedShotCrop] = []
    for shot_start, shot_end in pairwise([0, *cuts, dur_ms]):
        shot_dets = [d for d in detections if shot_start <= d.at_ms < shot_end]
        if not shot_dets:
            crops.append(LockedShotCrop(shot_start, shot_end, src_w // 2, src_h // 2, 0, None))
            continue
        shot_scores = [sc for sc in scores if shot_start <= sc.at_ms < shot_end]
        for seg_s, seg_e, tid in _plan_shot_speaker_runs(
            shot_start, shot_end, shot_dets, shot_scores, min_hold
        ):
            seg_dets = [d for d in shot_dets if d.track_id == tid and seg_s <= d.at_ms < seg_e] or [
                d for d in shot_dets if d.track_id == tid
            ]
            fx = max(0, min(src_w - 1, int(round(float(np.median([d.cx for d in seg_dets]))))))
            fy = max(0, min(src_h - 1, int(round(float(np.median([d.cy for d in seg_dets]))))))
            fh = max(1, min(src_h, int(round(float(np.median([d.h for d in seg_dets]))))))
            crops.append(LockedShotCrop(seg_s, seg_e, fx, fy, fh, tid))
    return tuple(crops)


class LockedCropLike(Protocol):
    """Structural geometry protocol satisfied by ``LockedShotCrop`` and ``LockedCropWindow``."""

    @property
    def start_ms(self) -> int: ...
    @property
    def end_ms(self) -> int: ...
    @property
    def focus_x_px(self) -> int: ...
    @property
    def face_center_y_px(self) -> int: ...
    @property
    def face_height_px(self) -> int: ...
    @property
    def active_track_id(self) -> int | None: ...


def _parse_showinfo_cuts_ms(stderr: str, *, min_shot_gap_ms: int) -> tuple[int, ...]:
    """Parse FFmpeg ``showinfo`` ``pts_time`` stamps using floor-ms (<= true frame PTS)."""
    cuts: list[int] = []
    for match in _SHOWINFO_PTS_RE.finditer(stderr):
        at_ms = int(math.floor(float(match.group(1)) * 1000.0))
        if at_ms > 250 and (not cuts or at_ms - cuts[-1] >= min_shot_gap_ms):
            cuts.append(at_ms)
    return tuple(cuts)


def _resolve_ffmpeg_binary(ffmpeg: Path | None) -> Path:
    binary = ffmpeg or find_ffmpeg()
    if binary is None:
        raise ActiveSpeakerError("No ffmpeg binary available for exact shot-cut detection")
    return binary


def detect_exact_shot_cuts_ms(
    video_path: Path | str,
    *,
    clip_in_ms: int = 0,
    clip_out_ms: int | None = None,
    threshold: float = 0.30,
    min_shot_gap_ms: int = 400,
    ffmpeg: Path | None = None,
) -> tuple[int, ...]:
    """Detect shot cuts at native source FPS on the exact ``render.py`` ``-ss/-t`` PTS timeline.

    Avoids the 40-160 ms quantization drift caused by running scene detection on a 5 fps proxy:
    every timestamp is floored to ``<= true_frame_pts_ms`` so ``crop_filter`` transitions ``x``,
    ``y``, ``w``, and ``h`` on the exact first frame of the new shot (0-frame offset, D-387).
    """
    src = Path(video_path)
    if not src.is_file():
        raise FileNotFoundError(f"Video file not found: {src}")
    in_ms = _req_int(clip_in_ms, "clip_in_ms")
    gap_ms = _req_int(min_shot_gap_ms, "min_shot_gap_ms")
    thr = _req_float(threshold, "threshold", min_val=0.0, gt=True)
    binary = _resolve_ffmpeg_binary(ffmpeg)

    cmd: list[str] = [str(binary), "-hide_banner"]
    timeout_s = 120.0
    if in_ms > 0:
        cmd.extend(["-ss", f"{in_ms / 1000.0:.3f}"])
    if clip_out_ms is not None:
        out_ms = _req_int(clip_out_ms, "clip_out_ms", min_val=in_ms + 1)
        dur_s = (out_ms - in_ms) / 1000.0
        cmd.extend(["-t", f"{dur_s:.3f}"])
        timeout_s = max(60.0, dur_s * 3.0)
    cmd.extend(
        [
            "-i",
            str(src),
            "-vf",
            f"scale=320:-2,select='gt(scene,{thr:.2f})',showinfo",
            "-an",
            "-f",
            "null",
            "-",
        ]
    )
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout_s)
    if proc.returncode != 0:
        raise ActiveSpeakerError(
            f"Native-FPS shot-cut detection failed on {src}: {proc.stderr.strip()[:400]}"
        )
    return _parse_showinfo_cuts_ms(proc.stderr, min_shot_gap_ms=gap_ms)


def detect_exact_assembled_cuts_ms(
    video_path: Path | str,
    assembly_spans_ms: Sequence[tuple[int, int]],
    *,
    fps: float = 25.0,
    threshold: float = 0.25,
    min_shot_gap_ms: int = 400,
    include_audio: bool = True,
    ffmpeg: Path | None = None,
) -> tuple[int, ...]:
    """Detect exact ``[v_cfr]`` shot/splice cuts on an assembled multi-span clip (D-387).

    Replicates ``render.py``'s ``trim=start:end,setpts=PTS-STARTPTS`` + ``concat`` + ``fps``
    framing semantics using ``-copyts`` pre-seeked inputs so every splice and internal shot cut
    lands on the exact ``[v_cfr]`` frame (eliminating CFR span-rounding double-cuts).
    """
    src = Path(video_path)
    if not src.is_file():
        raise FileNotFoundError(f"Video file not found: {src}")
    if not assembly_spans_ms:
        return ()
    fps_val = _req_float(fps, "fps", min_val=0.0, gt=True)
    thr = _req_float(threshold, "threshold", min_val=0.0, gt=True)
    gap_ms = _req_int(min_shot_gap_ms, "min_shot_gap_ms")
    binary = _resolve_ffmpeg_binary(ffmpeg)

    cmd: list[str] = [str(binary), "-hide_banner", "-copyts"]
    parts: list[str] = []
    concat_inputs: list[str] = []
    total_dur_s = 0.0
    for idx, (raw_in, raw_out) in enumerate(assembly_spans_ms):
        s_in = _req_int(raw_in, "assembly_spans_ms start")
        s_out = _req_int(raw_out, "assembly_spans_ms end", min_val=s_in + 1)
        in_s = s_in / 1000.0
        out_s = s_out / 1000.0
        total_dur_s += out_s - in_s
        pre_s = max(0.0, in_s - 2.0)
        cmd.extend(["-ss", f"{pre_s:.3f}", "-to", f"{out_s + 0.5:.3f}", "-i", str(src)])
        parts.append(
            f"[{idx}:v]trim=start={in_s:.3f}:end={out_s:.3f},setpts=PTS-STARTPTS,scale=320:-2[v{idx}]"
        )
        if include_audio:
            parts.append(
                f"[{idx}:a]atrim=start={in_s:.3f}:end={out_s:.3f},asetpts=PTS-STARTPTS[a{idx}]"
            )
            concat_inputs.append(f"[v{idx}][a{idx}]")
        else:
            concat_inputs.append(f"[v{idx}]")

    n = len(assembly_spans_ms)
    if include_audio:
        concat_clause = f"{''.join(concat_inputs)}concat=n={n}:v=1:a=1[vc][ac]"
        map_args = ["-map", "[vo]", "-map", "[ac]"]
    else:
        concat_clause = f"{''.join(concat_inputs)}concat=n={n}:v=1:a=0[vc]"
        map_args = ["-map", "[vo]"]
    fc = (
        f"{';'.join(parts)};{concat_clause};"
        f"[vc]fps={fps_val:g},select='gt(scene,{thr:.2f})',showinfo[vo]"
    )
    cmd.extend(["-filter_complex", fc, *map_args, "-f", "null", "-"])
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        timeout=max(60.0, total_dur_s * 4.0),
    )
    if proc.returncode != 0:
        raise ActiveSpeakerError(
            f"Assembled CFR shot-cut detection failed on {src}: {proc.stderr.strip()[:400]}"
        )
    return _parse_showinfo_cuts_ms(proc.stderr, min_shot_gap_ms=gap_ms)


def snap_locked_crops_to_cuts(
    crops: Sequence[LockedCropLike],
    exact_cuts_ms: Sequence[int],
    *,
    max_snap_ms: int = 250,
) -> tuple[LockedShotCrop, ...]:
    """Coalesce contiguous identical crops, then snap real boundaries onto exact CFR shot cuts."""
    if not crops:
        return ()

    # Coalesce adjacent spans with identical geometry so no-op splice boundaries never steal
    # an exact CFR shot cut from the real crop transition immediately after them.
    merged: list[LockedShotCrop] = []
    for c in crops:
        item = LockedShotCrop(
            start_ms=c.start_ms,
            end_ms=c.end_ms,
            focus_x_px=c.focus_x_px,
            face_center_y_px=c.face_center_y_px,
            face_height_px=c.face_height_px,
            active_track_id=c.active_track_id,
        )
        if (
            merged
            and merged[-1].end_ms == item.start_ms
            and merged[-1].focus_x_px == item.focus_x_px
            and merged[-1].face_center_y_px == item.face_center_y_px
            and merged[-1].face_height_px == item.face_height_px
            and merged[-1].active_track_id == item.active_track_id
        ):
            prev = merged[-1]
            merged[-1] = LockedShotCrop(
                start_ms=prev.start_ms,
                end_ms=item.end_ms,
                focus_x_px=prev.focus_x_px,
                face_center_y_px=prev.face_center_y_px,
                face_height_px=prev.face_height_px,
                active_track_id=prev.active_track_id,
            )
        else:
            merged.append(item)

    if len(merged) == 1 or not exact_cuts_ms:
        return tuple(merged)
    snap_tol = _req_int(max_snap_ms, "max_snap_ms")
    valid_cuts = sorted({_req_int(c, "exact_cuts_ms element") for c in exact_cuts_ms})

    boundaries = [merged[0].start_ms, *(c.end_ms for c in merged)]
    used_cuts: set[int] = set()
    for idx in range(1, len(boundaries) - 1):
        cur = boundaries[idx]
        lo = boundaries[idx - 1] + 1
        hi = boundaries[idx + 1] - 1
        candidates = [
            cut
            for cut in valid_cuts
            if cut not in used_cuts and lo <= cut <= hi and abs(cut - cur) <= snap_tol
        ]
        if candidates:
            best = min(candidates, key=lambda cut: (abs(cut - cur), cut))
            boundaries[idx] = best
            used_cuts.add(best)

    return tuple(
        LockedShotCrop(
            start_ms=boundaries[i],
            end_ms=boundaries[i + 1],
            focus_x_px=crop.focus_x_px,
            face_center_y_px=crop.face_center_y_px,
            face_height_px=crop.face_height_px,
            active_track_id=crop.active_track_id,
        )
        for i, crop in enumerate(merged)
    )


def locked_crops_to_focus_points(
    crops: Sequence[LockedCropLike],
    *,
    clip_in_ms: int = 0,
) -> tuple[FocusPoint, ...]:
    """Convert locked shot crops into zero-skew hold-and-step ``FocusPoint`` pairs.

    Emits ``(cut_ms, prev_x)`` followed by ``(cut_ms + 1, next_x)`` matching ``reframe.stabilize``
    and ``render.py:_interpolated()`` (D-360/D-387), so horizontal ``x`` switches at ``cut_ms - 2``
    ms — the exact same millisecond as ``per_shot_boxes`` ``y``, ``w``, and ``h``.
    """
    base_ms = _req_int(clip_in_ms, "clip_in_ms")
    pts: list[FocusPoint] = []
    for idx, crop in enumerate(crops):
        fh = crop.face_height_px if crop.face_height_px > 0 else None
        cy = crop.face_center_y_px if fh is not None else None
        s_abs = base_ms + crop.start_ms
        e_abs = base_ms + crop.end_ms
        # For shots after the first, step at (cut_ms + 1) so the 1 ms pair is (cut_ms, cut_ms + 1).
        entry_ms = s_abs + 1 if idx > 0 and s_abs + 1 < e_abs else s_abs
        pts.append(FocusPoint(entry_ms, crop.focus_x_px, cy, fh))
        if e_abs > entry_ms:
            pts.append(FocusPoint(e_abs, crop.focus_x_px, cy, fh))
    return tuple(pts)


def locked_crops_to_render_inputs(
    crops: Sequence[LockedCropLike],
    *,
    clip_in_ms: int = 0,
) -> tuple[tuple[tuple[int, int], ...], tuple[tuple[int, int, int | None, int | None], ...]]:
    """Return synchronized ``(focus_points, per_shot_boxes)`` for ``render.render_clip`` (D-387)."""
    base_ms = _req_int(clip_in_ms, "clip_in_ms")
    focus_pts = tuple(
        (pt.at_ms, pt.center_x) for pt in locked_crops_to_focus_points(crops, clip_in_ms=base_ms)
    )
    per_shot_boxes = tuple(
        (
            base_ms + crop.start_ms,
            base_ms + crop.end_ms,
            crop.face_center_y_px if crop.face_height_px > 0 else None,
            crop.face_height_px if crop.face_height_px > 0 else None,
        )
        for crop in crops
    )
    return focus_pts, per_shot_boxes
