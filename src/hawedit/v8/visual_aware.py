"""HawEdit V10.2 Component 2: Visual-Aware Saliency, Dual-Speaker Banter & Cut-Cover Choreography.

Upgrades visual awareness beyond static face boxes:
1. Shot-scale & dual-speaker banter profiling (``analyze_shot_visual_profiles``): classifies every
   shot as ``closeup``, ``medium``, ``wide_2shot``, or ``no_face`` and detects dual-speaker banter
   (host & guest both actively speaking within 1.5 s on a wide 2-shot) to emit 50/50 stacked
   vertical split-screen crops.
2. Hand-motion + face/headroom negative-space saliency (``measure_hand_motion_saliency``): checks
   real frame-difference gesture energy in the lower-chest band so Stat Cards and Top-PiP cards
   never collide with eyes, foreheads, gesturing hands, or captions.
3. Automatic cut-cover choreography (``choreograph_cut_covers``): covers mid-sentence semantic
   cuts (>= 250 ms removed on the same camera angle) with anchored B-roll cutaways, dual-speaker
   split-screen, or restrained punch-cuts.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final, Literal

import cv2
import numpy as np

from hawedit.v8.asd import ActiveSpeakerScore, FaceDetectionFrame, LockedCropLike
from hawedit.v8.story_editor import VisualCue

__all__ = [
    "DEFAULT_GPU_VISUAL_PYTHON",
    "DEFAULT_TIMELENS2_DIR",
    "DEFAULT_VIDEOCHAT3_DIR",
    "CutCoverAction",
    "CutCoverKind",
    "SafeOverlayZone",
    "ShotScale",
    "ShotVisualProfile",
    "VisualAwareError",
    "VisualGroundings",
    "analyze_shot_visual_profiles",
    "apply_visual_groundings_to_profiles",
    "choreograph_cut_covers",
    "compute_two_person_split_crops",
    "format_visual_groundings_for_director",
    "measure_hand_motion_saliency",
    "protect_visual_gestures_in_cuts",
    "resolve_local_visual_models",
    "run_local_video_awareness",
]

DEFAULT_VIDEOCHAT3_DIR: Final[Path] = Path(r"D:\HawEdit-media\models\MCG-NJU__VideoChat3-4B")
DEFAULT_TIMELENS2_DIR: Final[Path] = Path(r"D:\HawEdit-media\models\MCG-NJU__TimeLens2-4B")
DEFAULT_GPU_VISUAL_PYTHON: Final[Path] = Path(
    r"D:\HawEdit-media\.gpu-visual-venv\Scripts\python.exe"
)


class VisualAwareError(RuntimeError):
    """Strict fail-stop error raised when requested local visual grounding cannot run."""


@dataclass(frozen=True, slots=True)
class VisualGroundings:
    """Grounded scene, gesture, and reaction evidence from §7 VideoChat3-4B and TimeLens2-4B."""

    sv6d_lines: tuple[str, ...]
    gesture_intervals_ms: tuple[tuple[int, int, str], ...]
    models_used: tuple[str, ...]
    reaction_intervals_ms: tuple[tuple[int, int, str], ...] = ()

    @property
    def all_protected_intervals_ms(self) -> tuple[tuple[int, int, str], ...]:
        return (*self.gesture_intervals_ms, *self.reaction_intervals_ms)

    def to_dict(self) -> dict[str, object]:
        return {
            "sv6d_lines": list(self.sv6d_lines),
            "gesture_intervals_ms": [
                {"start_ms": s, "end_ms": e, "label": lbl}
                for s, e, lbl in self.gesture_intervals_ms
            ],
            "reaction_intervals_ms": [
                {"start_ms": s, "end_ms": e, "label": lbl}
                for s, e, lbl in self.reaction_intervals_ms
            ],
            "models_used": list(self.models_used),
        }


ShotScale = Literal["closeup", "medium", "wide_2shot", "no_face"]
SafeOverlayZone = Literal["top", "chest", "top_pip"]
CutCoverKind = Literal["broll_fullscreen", "broll_pip", "stat_card", "split_screen", "punch_cut"]

_CLOSEUP_FACE_SHARE: Final[float] = 0.22
_MEDIUM_FACE_SHARE: Final[float] = 0.12
_HAND_GESTURE_ENERGY_THRESHOLD: Final[float] = 0.14
_DEFAULT_BANTER_WINDOW_MS: Final[int] = 1_500
_DEFAULT_BANTER_MIN_DUR_MS: Final[int] = 1_500
_SAME_SHOT_CUT_MARGIN_MS: Final[int] = 350


@dataclass(frozen=True, slots=True)
class ShotVisualProfile:
    """Visual scene intelligence for one locked crop shot window."""

    start_ms: int
    end_ms: int
    shot_scale: ShotScale
    track_ids: tuple[int, ...]
    dual_active_banter: bool
    hand_motion_energy: float
    safe_overlay_zone: SafeOverlayZone
    split_crops: tuple[tuple[int, int, int, int], tuple[int, int, int, int]] | None = None

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


@dataclass(frozen=True, slots=True)
class CutCoverAction:
    """Visual cover decision concealing a mid-sentence semantic cut cleanly."""

    at_ms: int
    start_ms: int
    end_ms: int
    kind: CutCoverKind
    reason: str
    cue_index: int | None = None


def compute_two_person_split_crops(
    left_cx: float,
    left_cy: float,
    left_h: float,
    right_cx: float,
    right_cy: float,
    right_h: float,
    source_width: int,
    source_height: int,
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    """Compute exact 9:8 ``(x, y, w, h)`` top/bottom crop boxes for 1080x1920 50/50 split-screen."""
    if source_width <= 0 or source_height <= 0:
        raise ValueError(f"Invalid source dims: {source_width}x{source_height}")

    # Target pane aspect ratio is 1080 / 960 = 9 / 8 = 1.125.
    target_ar = 9.0 / 8.0

    def _one_crop(cx: float, cy: float, fh: float) -> tuple[int, int, int, int]:
        # Frame face height at ~34% of the half-screen pane for flattering studio portraits.
        desired_h = int(round(max(source_height * 0.45, min(source_height, fh / 0.34))))
        desired_w = int(round(desired_h * target_ar))
        if desired_w > source_width:
            desired_w = source_width
            desired_h = int(round(desired_w / target_ar))
        crop_w = max(2, min(source_width, desired_w - (desired_w % 2)))
        crop_h = max(2, min(source_height, desired_h - (desired_h % 2)))
        # Place eyes near upper 38% of each 9:8 pane.
        x = max(0, min(source_width - crop_w, int(round(cx - crop_w * 0.5))))
        y = max(0, min(source_height - crop_h, int(round(cy - crop_h * 0.38))))
        return (x, y, crop_w, crop_h)

    return (
        _one_crop(left_cx, left_cy, max(1.0, left_h)),
        _one_crop(right_cx, right_cy, max(1.0, right_h)),
    )


def measure_hand_motion_saliency(
    proxy_mp4: Path,
    start_ms: int,
    end_ms: int,
    face_cy_norm: float,
    face_h_norm: float,
    *,
    max_samples: int = 8,
) -> float:
    """Measure normalized hand/gesture motion energy in the lower-chest band ``[0.0, 1.0]``."""
    if not proxy_mp4.is_file() or end_ms <= start_ms:
        return 0.0
    cap = cv2.VideoCapture(str(proxy_mp4))
    if not cap.isOpened():
        return 0.0
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        if not math.isfinite(fps) or fps <= 0.0:
            return 0.0
        n_samples = max(2, min(max_samples, (end_ms - start_ms) // 250 + 1))
        step_ms = max(100, (end_ms - start_ms) // n_samples)
        prev_roi: np.ndarray[tuple[int, ...], np.dtype[np.float32]] | None = None
        diffs: list[float] = []
        for idx in range(n_samples):
            t_ms = min(end_ms - 1, start_ms + idx * step_ms)
            frame_idx = max(0, int(round(t_ms * fps / 1000.0)))
            cap.set(cv2.CAP_PROP_POS_FRAMES, float(frame_idx))
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            h, w = frame.shape[:2]
            y0_norm = min(0.75, max(0.35, face_cy_norm + face_h_norm * 0.70))
            y1_norm = min(0.92, max(y0_norm + 0.10, 0.86))
            iy0, iy1 = int(h * y0_norm), max(int(h * y0_norm) + 1, int(h * y1_norm))
            ix0, ix1 = int(w * 0.15), max(int(w * 0.15) + 1, int(w * 0.85))
            gray = cv2.cvtColor(frame[iy0:iy1, ix0:ix1], cv2.COLOR_BGR2GRAY).astype(np.float32)
            gray /= 255.0
            if prev_roi is not None and prev_roi.shape == gray.shape:
                diffs.append(float(np.mean(np.abs(gray - prev_roi))))
            prev_roi = gray
        if not diffs:
            return 0.0
        # Map mean frame delta [0.00..0.12] -> [0.0..1.0].
        return round(min(1.0, max(0.0, float(np.mean(diffs)) / 0.12)), 4)
    finally:
        cap.release()


def _detect_dual_active_banter(
    shot_scores: Sequence[ActiveSpeakerScore],
    *,
    banter_window_ms: int,
) -> tuple[bool, tuple[int, int] | None]:
    """Return True when >= 2 distinct tracks both speak actively within ``banter_window_ms``."""
    speaking_by_track: dict[int, list[int]] = {}
    for sc in shot_scores:
        active = sc.is_speaking or (
            sc.score >= 0.0 if sc.backend == "light_asd_onnx" else sc.score >= 0.20
        )
        if active:
            speaking_by_track.setdefault(sc.track_id, []).append(sc.at_ms)

    if len(speaking_by_track) < 2:
        return False, None

    # Sort tracks by total active frames descending and test top two for overlapping banter.
    ranked = sorted(speaking_by_track.items(), key=lambda kv: -len(kv[1]))
    t_a, times_a = ranked[0]
    t_b, times_b = ranked[1]
    if len(times_a) < 2 or len(times_b) < 2:
        return False, None
    for ta in times_a:
        if any(abs(ta - tb) <= banter_window_ms for tb in times_b):
            return True, (t_a, t_b)
    return False, None


def analyze_shot_visual_profiles(
    detections: Sequence[FaceDetectionFrame],
    scores: Sequence[ActiveSpeakerScore],
    locked_crops: Sequence[LockedCropLike],
    *,
    source_width: int,
    source_height: int,
    proxy_width: int | None = None,
    proxy_height: int | None = None,
    proxy_mp4: Path | None = None,
    banter_window_ms: int = _DEFAULT_BANTER_WINDOW_MS,
    banter_min_duration_ms: int = _DEFAULT_BANTER_MIN_DUR_MS,
) -> tuple[ShotVisualProfile, ...]:
    """Compute shot-scale, banter split-screen, and negative-space overlay profiles per shot."""
    if not locked_crops:
        return ()

    p_w = float(proxy_width if proxy_width and proxy_width > 0 else source_width)
    p_h = float(proxy_height if proxy_height and proxy_height > 0 else source_height)
    sx = source_width / p_w
    sy = source_height / p_h

    profiles: list[ShotVisualProfile] = []
    for crop in locked_crops:
        shot_dets = [d for d in detections if crop.start_ms <= d.at_ms < crop.end_ms]
        shot_scores = [s for s in scores if crop.start_ms <= s.at_ms < crop.end_ms]
        track_counts: dict[int, int] = {}
        for d in shot_dets:
            track_counts[d.track_id] = track_counts.get(d.track_id, 0) + 1
        persistent_tracks = tuple(
            tid for tid, cnt in sorted(track_counts.items()) if cnt >= max(2, len(shot_dets) // 12)
        )
        face_share = crop.face_height_px / float(max(1, source_height))

        if crop.face_height_px <= 0 and not persistent_tracks:
            shot_scale: ShotScale = "no_face"
        elif len(persistent_tracks) >= 2:
            shot_scale = "wide_2shot"
        elif face_share >= _CLOSEUP_FACE_SHARE:
            shot_scale = "closeup"
        elif face_share >= _MEDIUM_FACE_SHARE:
            shot_scale = "medium"
        else:
            shot_scale = "medium"

        dual_banter = False
        split_crops: tuple[tuple[int, int, int, int], tuple[int, int, int, int]] | None = None
        if shot_scale == "wide_2shot" and (crop.end_ms - crop.start_ms) >= banter_min_duration_ms:
            is_banter, pair = _detect_dual_active_banter(
                shot_scores, banter_window_ms=banter_window_ms
            )
            crop_pair = (
                pair
                if (is_banter and pair is not None)
                else (
                    (persistent_tracks[0], persistent_tracks[1])
                    if len(persistent_tracks) >= 2
                    else None
                )
            )
            if crop_pair is not None:
                ta, tb = crop_pair
                dets_a = [d for d in shot_dets if d.track_id == ta]
                dets_b = [d for d in shot_dets if d.track_id == tb]
                if dets_a and dets_b:
                    cx_a = float(np.median([d.cx for d in dets_a])) * sx
                    cy_a = float(np.median([d.cy for d in dets_a])) * sy
                    h_a = float(np.median([d.h for d in dets_a])) * sy
                    cx_b = float(np.median([d.cx for d in dets_b])) * sx
                    cy_b = float(np.median([d.cy for d in dets_b])) * sy
                    h_b = float(np.median([d.h for d in dets_b])) * sy
                    # Order consistently: left speaker on top, right speaker on bottom.
                    if cx_a <= cx_b:
                        left, right = (cx_a, cy_a, h_a), (cx_b, cy_b, h_b)
                    else:
                        left, right = (cx_b, cy_b, h_b), (cx_a, cy_a, h_a)
                    split_crops = compute_two_person_split_crops(
                        left[0],
                        left[1],
                        left[2],
                        right[0],
                        right[1],
                        right[2],
                        source_width,
                        source_height,
                    )
                    if is_banter:
                        dual_banter = True

        face_cy_norm = (
            crop.face_center_y_px / float(max(1, source_height))
            if crop.face_height_px > 0
            else 0.35
        )
        hand_energy = (
            measure_hand_motion_saliency(
                proxy_mp4, crop.start_ms, crop.end_ms, face_cy_norm, face_share
            )
            if proxy_mp4 is not None
            else 0.0
        )

        # Negative-space overlay zone routing: avoid eyes/hair AND active hand gestures.
        if shot_scale == "closeup":
            safe_zone: SafeOverlayZone = (
                "top_pip" if hand_energy >= _HAND_GESTURE_ENERGY_THRESHOLD else "chest"
            )
        else:
            safe_zone = "top"

        profiles.append(
            ShotVisualProfile(
                start_ms=crop.start_ms,
                end_ms=crop.end_ms,
                shot_scale=shot_scale,
                track_ids=persistent_tracks,
                dual_active_banter=dual_banter,
                hand_motion_energy=hand_energy,
                safe_overlay_zone=safe_zone,
                split_crops=split_crops,
            )
        )

    return tuple(profiles)


def choreograph_cut_covers(
    semantic_cut_times_ms: Sequence[tuple[int, int]],
    shot_profiles: Sequence[ShotVisualProfile],
    visual_cues: Sequence[VisualCue],
    word_idx_to_output_ms: Mapping[int, int],
    *,
    duration_ms: int,
    existing_shot_cuts_ms: Sequence[int] = (),
    max_punch_cuts: int = 3,
    min_punch_spacing_ms: int = 4_500,
) -> tuple[CutCoverAction, ...]:
    """Assign visual cover actions over mid-sentence semantic jump-cuts on the same camera angle."""
    if not semantic_cut_times_ms or duration_ms <= 0:
        return ()

    actions: list[CutCoverAction] = []
    used_cues: set[int] = set()
    punch_times: list[int] = []

    for cut_ms, removed_ms in sorted(semantic_cut_times_ms, key=lambda pair: pair[0]):
        if removed_ms < 250 or cut_ms <= 600 or cut_ms >= duration_ms - 800:
            continue
        # If a real camera angle cut already happens within +-350 ms, no jump-cut cover needed.
        if any(abs(cut_ms - sc) <= _SAME_SHOT_CUT_MARGIN_MS for sc in existing_shot_cuts_ms):
            continue

        # 1. Prefer an anchored B-roll visual cue within +-2.5 s to cover the cut cleanly.
        best_cue_idx: int | None = None
        best_dist = 2_501
        for c_idx, cue in enumerate(visual_cues):
            if c_idx in used_cues or cue.layout not in ("broll_fullscreen", "broll_pip"):
                continue
            anchor_ms = word_idx_to_output_ms.get(cue.anchor_word_idx)
            if anchor_ms is None:
                continue
            dist = abs(anchor_ms - cut_ms)
            if dist < best_dist:
                best_dist = dist
                best_cue_idx = c_idx

        if best_cue_idx is not None:
            cue = visual_cues[best_cue_idx]
            cov_start = max(500, cut_ms - 450)
            cov_end = min(duration_ms - 400, cov_start + cue.duration_ms)
            if cov_end > cut_ms + 400:
                used_cues.add(best_cue_idx)
                cover_kind: CutCoverKind = (
                    "broll_fullscreen" if cue.layout == "broll_fullscreen" else "broll_pip"
                )
                actions.append(
                    CutCoverAction(
                        at_ms=cut_ms,
                        start_ms=cov_start,
                        end_ms=cov_end,
                        kind=cover_kind,
                        reason=f"B-roll covers {removed_ms} ms semantic cut ({cue.query_en})",
                        cue_index=best_cue_idx,
                    )
                )
                continue

        # 2. If this shot is a dual-active wide banter shot, prefer split-screen cover.
        prof = next(
            (p for p in shot_profiles if p.start_ms <= cut_ms < p.end_ms),
            None,
        )
        if prof is not None and prof.dual_active_banter:
            actions.append(
                CutCoverAction(
                    at_ms=cut_ms,
                    start_ms=prof.start_ms,
                    end_ms=prof.end_ms,
                    kind="split_screen",
                    reason=f"Dual-speaker banter 50/50 split covers {removed_ms} ms semantic cut",
                )
            )
            continue

        # 3. Restrained punch-cut toggle (respecting camera restraint budget & spacing).
        if len(punch_times) < max_punch_cuts and all(
            abs(cut_ms - pt) >= min_punch_spacing_ms for pt in punch_times
        ):
            p_end = min(duration_ms - 300, cut_ms + 2_600)
            if p_end >= cut_ms + 1_800:
                punch_times.append(cut_ms)
                actions.append(
                    CutCoverAction(
                        at_ms=cut_ms,
                        start_ms=cut_ms,
                        end_ms=p_end,
                        kind="punch_cut",
                        reason=f"Restrained 1.12x punch-cut masks {removed_ms} ms semantic cut",
                    )
                )

    return tuple(actions)


def resolve_local_visual_models(
    *,
    videochat3_dir: Path | None = None,
    timelens2_dir: Path | None = None,
    gpu_python: Path | None = None,
) -> tuple[Path | None, Path | None, Path | None]:
    """Locate pinned §7 VideoChat3-4B / TimeLens2-4B checkpoints and CUDA worker Python."""
    vc_env = os.environ.get("HAWEDIT_VIDEOCHAT3_DIR", "").strip()
    tl_env = os.environ.get("HAWEDIT_TIMELENS2_DIR", "").strip()
    py_env = os.environ.get("HAWEDIT_GPU_PYTHON", "").strip()

    vc_cand = videochat3_dir or (Path(vc_env) if vc_env else DEFAULT_VIDEOCHAT3_DIR)
    tl_cand = timelens2_dir or (Path(tl_env) if tl_env else DEFAULT_TIMELENS2_DIR)
    py_cand = gpu_python or (Path(py_env) if py_env else DEFAULT_GPU_VISUAL_PYTHON)

    vc_ok = vc_cand if (vc_cand.is_dir() and (vc_cand / "config.json").is_file()) else None
    tl_ok = tl_cand if (tl_cand.is_dir() and (tl_cand / "config.json").is_file()) else None
    py_ok = py_cand if py_cand.is_file() else None
    return vc_ok, tl_ok, py_ok


_LOCAL_GPU_GROUNDING_WORKER: Final[str] = r"""
import json, sys
from pathlib import Path
import cv2
import torch
from PIL import Image
from transformers import (
    AutoConfig,
    AutoModelForCausalLM,
    AutoModelForImageTextToText,
    AutoProcessor,
)

req = json.loads(sys.stdin.read())
video_path = Path(req["video_mp4"])
duration_s = max(0.5, float(req["duration_ms"]) / 1000.0)
device = req.get("device", "cuda:1")
vc_dir = req.get("videochat3_dir")
tl_dir = req.get("timelens2_dir")
gesture_query = req.get(
    "gesture_query",
    req.get("query", "speaker gesturing expressively with hands or pointing"),
)
reaction_query = req.get(
    "reaction_query",
    "person laughing, smiling broadly, or reacting with surprise",
)

cap = cv2.VideoCapture(str(video_path))
total_f = max(1, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
# Multiple of 4 satisfies both TimeLens2 (patch=2) and VideoChat3 (patch=4) cleanly.
n_frames = max(4, min(16, (int(round(duration_s * 0.8)) // 4) * 4 or 4))
frames = []
for i in range(n_frames):
    idx = min(total_f - 1, int(round(i * (total_f - 1) / max(1, n_frames - 1))))
    cap.set(cv2.CAP_PROP_POS_FRAMES, float(idx))
    ok, bgr = cap.read()
    if ok and bgr is not None:
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        # Align dimensions to multiples of 32 for Qwen3-VL / VideoChat3 patch grids.
        tw = max(128, min(448, (w // 32) * 32))
        th = max(128, min(448, (int(round(h * tw / max(1, w))) // 32) * 32))
        rgb = cv2.resize(rgb, (tw, th), interpolation=cv2.INTER_AREA)
        frames.append(Image.fromarray(rgb))
cap.release()
while len(frames) > 4 and len(frames) % 4 != 0:
    frames.pop()

out = {
    "sv6d_lines": [],
    "gesture_intervals_ms": [],
    "reaction_intervals_ms": [],
    "models_used": [],
}
if len(frames) < 4:
    print(json.dumps(out))
    raise SystemExit(0)

if not torch.cuda.is_available():
    raise RuntimeError("CUDA is unavailable in GPU visual grounding worker")
if device == "cuda:1" and torch.cuda.device_count() < 2:
    device = "cuda:0"

eff_fps = len(frames) / duration_s
vmeta = [{
    "fps": eff_fps,
    "total_num_frames": len(frames),
    "frames_indices": list(range(len(frames))),
}]

if tl_dir:
    proc = AutoProcessor.from_pretrained(tl_dir)
    model = AutoModelForImageTextToText.from_pretrained(
        tl_dir, dtype=torch.bfloat16, device_map={"": device}
    )
    dur_cap = int(round(duration_s * 1000.0))
    for out_key, q_text in (
        ("gesture_intervals_ms", gesture_query),
        ("reaction_intervals_ms", reaction_query),
    ):
        if not q_text:
            continue
        prompt = (
            f'Given the query: "{q_text}", return ALL time spans (in seconds) where the query is '
            "relevant.\nOutput format MUST be a JSON array of [start, end] pairs.\n"
        )
        msgs = [{"role": "user", "content": [
            {"type": "video", "video": frames},
            {"type": "text", "text": prompt},
        ]}]
        batch = proc.apply_chat_template(
            msgs, tokenize=True, add_generation_prompt=True, return_dict=True,
            return_tensors="pt", video_metadata=vmeta,
        )
        placed = {k: (v.to(device) if hasattr(v, "to") else v) for k, v in dict(batch).items()}
        with torch.inference_mode():
            gen = model.generate(**placed, max_new_tokens=160, do_sample=False)
        ans = proc.tokenizer.decode(gen[0][batch["input_ids"].shape[1]:], skip_special_tokens=True)
        start_at = ans.find("[")
        if start_at >= 0:
            try:
                spans, _ = json.JSONDecoder().raw_decode(ans[start_at:])
                if isinstance(spans, list):
                    for pair in spans:
                        if isinstance(pair, list) and len(pair) == 2:
                            s_ms = max(0, int(round(float(pair[0]) * 1000.0)))
                            e_ms = min(dur_cap, int(round(float(pair[1]) * 1000.0)))
                            if e_ms > s_ms + 250:
                                out[out_key].append([s_ms, e_ms, q_text])
            except Exception:
                pass
        del batch, placed, gen
    out["models_used"].append("MCG-NJU/TimeLens2-4B")
    del model, proc
    torch.cuda.empty_cache()

if vc_dir:
    cfg = AutoConfig.from_pretrained(vc_dir, trust_remote_code=True)
    vcfg = getattr(cfg, "vision_config", None)
    if vcfg is not None:
        vcfg.attn_impl = "sdpa"
    proc = AutoProcessor.from_pretrained(vc_dir, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        vc_dir,
        config=cfg,
        trust_remote_code=True,
        dtype=torch.bfloat16,
        device_map={"": device},
    )
    sv6d_prompt = (
        f"This clip is {duration_s:.1f} seconds long. "
        f"Timestamps in it run from 0.0 to {duration_s:.1f}.\n\n"
        "Describe it on exactly six lines, one per dimension, in this order and this format:\n\n"
        "subject | <seconds> | what is on screen and what it does\n"
        "aesthetics | <seconds> | lighting, colour, framing\n"
        "camera | <seconds> | shot size and camera movement\n"
        "editing | <seconds> | cuts, pace, transitions\n"
        "narrative | <seconds> | the beat that happens\n"
        "retention | <seconds> | what would keep a viewer watching\n\n"
        f"<seconds> is the moment in THIS clip your observation is about, a number between 0.0 "
        f"and {duration_s:.1f}. Write the number alone, no unit. Put no other times in the "
        "description text. Output the six lines and nothing else."
    )
    msgs = [{"role": "user", "content": [
        {"type": "video", "video": frames},
        {"type": "text", "text": sv6d_prompt},
    ]}]
    batch = proc.apply_chat_template(
        msgs, tokenize=True, add_generation_prompt=True, return_dict=True,
        return_tensors="pt", video_metadata=vmeta,
    )
    placed = {k: (v.to(device) if hasattr(v, "to") else v) for k, v in dict(batch).items()}
    for pk in ("pixel_values", "pixel_values_videos"):
        if hasattr(placed.get(pk), "to"):
            placed[pk] = placed[pk].to(torch.bfloat16)
    with torch.inference_mode():
        gen = model.generate(
            **placed, max_new_tokens=220, do_sample=False, repetition_penalty=1.15
        )
    ans = proc.tokenizer.decode(gen[0][batch["input_ids"].shape[1]:], skip_special_tokens=True)
    out["sv6d_lines"] = [ln.strip() for ln in ans.splitlines() if "|" in ln][:6]
    out["models_used"].append("MCG-NJU/VideoChat3-4B")
    del model, proc, batch, placed
    torch.cuda.empty_cache()

print(json.dumps(out, ensure_ascii=False))
"""


def run_local_video_awareness(
    video_mp4: Path,
    duration_ms: int,
    *,
    videochat3_dir: Path | None = None,
    timelens2_dir: Path | None = None,
    gpu_python: Path | None = None,
    device: str = "cuda:1",
    query: str = "speaker gesturing expressively with hands or pointing",
    reaction_query: str = "person laughing, smiling broadly, or reacting with surprise",
    strict: bool = False,
    timeout_s: float = 180.0,
) -> VisualGroundings | None:
    """Run pinned §7 VideoChat3-4B & dual-query TimeLens2-4B locally on GPU 1."""
    if not video_mp4.is_file() or duration_ms <= 0:
        if strict:
            raise VisualAwareError(f"Invalid video input for visual grounding: {video_mp4}")
        return None

    vc_ok, tl_ok, py_ok = resolve_local_visual_models(
        videochat3_dir=videochat3_dir, timelens2_dir=timelens2_dir, gpu_python=gpu_python
    )
    if py_ok is None or (vc_ok is None and tl_ok is None):
        if strict:
            raise VisualAwareError(
                "Local §7 visual awareness requested but checkpoints/CUDA worker missing "
                f"(videochat3={vc_ok}, timelens2={tl_ok}, gpu_python={py_ok})"
            )
        return None

    req_payload = json.dumps(
        {
            "video_mp4": str(video_mp4),
            "duration_ms": duration_ms,
            "device": device,
            "videochat3_dir": str(vc_ok) if vc_ok is not None else None,
            "timelens2_dir": str(tl_ok) if tl_ok is not None else None,
            "gesture_query": query,
            "reaction_query": reaction_query,
        },
        ensure_ascii=False,
    )
    try:
        proc = subprocess.run(
            [str(py_ok), "-c", _LOCAL_GPU_GROUNDING_WORKER],
            input=req_payload,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=timeout_s,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        if strict:
            raise VisualAwareError(f"Local VideoChat3/TimeLens2 worker failed: {exc}") from exc
        return None

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()[:400]
        if strict:
            raise VisualAwareError(
                f"Local VideoChat3/TimeLens2 worker exited {proc.returncode}: {detail}"
            )
        return None

    try:
        lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
        parsed = json.loads(lines[-1]) if lines else {}
    except ValueError as exc:
        if strict:
            raise VisualAwareError(
                f"Malformed JSON from VideoChat3/TimeLens2 worker: {exc}"
            ) from exc
        return None

    sv6d = tuple(str(x) for x in parsed.get("sv6d_lines", ()) if isinstance(x, str))
    gestures = tuple(
        (int(item[0]), int(item[1]), str(item[2]))
        for item in parsed.get("gesture_intervals_ms", ())
        if isinstance(item, list) and len(item) == 3 and int(item[1]) > int(item[0])
    )
    reactions = tuple(
        (int(item[0]), int(item[1]), str(item[2]))
        for item in parsed.get("reaction_intervals_ms", ())
        if isinstance(item, list) and len(item) == 3 and int(item[1]) > int(item[0])
    )
    models_used = tuple(str(x) for x in parsed.get("models_used", ()) if isinstance(x, str))
    return VisualGroundings(
        sv6d_lines=sv6d,
        gesture_intervals_ms=gestures,
        models_used=models_used,
        reaction_intervals_ms=reactions,
    )


def apply_visual_groundings_to_profiles(
    profiles: Sequence[ShotVisualProfile],
    groundings: VisualGroundings | None,
) -> tuple[ShotVisualProfile, ...]:
    """Upgrade overlay safety & 2-shot reaction splits using TimeLens2-4B grounded spans."""
    if not profiles or groundings is None or not groundings.all_protected_intervals_ms:
        return tuple(profiles)
    upgraded: list[ShotVisualProfile] = []
    for prof in profiles:
        overlaps_protected = any(
            min(prof.end_ms, ge) - max(prof.start_ms, gs) >= 400
            for gs, ge, _ in groundings.all_protected_intervals_ms
        )
        overlaps_reaction = any(
            min(prof.end_ms, re_) - max(prof.start_ms, rs) >= 400
            for rs, re_, _ in groundings.reaction_intervals_ms
        )
        new_zone = (
            "top_pip"
            if (
                overlaps_protected
                and prof.shot_scale == "closeup"
                and prof.safe_overlay_zone == "chest"
            )
            else prof.safe_overlay_zone
        )
        new_banter = prof.dual_active_banter or (
            overlaps_reaction and prof.shot_scale == "wide_2shot" and prof.split_crops is not None
        )
        if new_zone != prof.safe_overlay_zone or new_banter != prof.dual_active_banter:
            upgraded.append(
                replace(prof, safe_overlay_zone=new_zone, dual_active_banter=new_banter)
            )
        else:
            upgraded.append(prof)
    return tuple(upgraded)


def protect_visual_gestures_in_cuts(
    actions: Sequence[CutCoverAction],
    groundings: VisualGroundings | None,
) -> tuple[CutCoverAction, ...]:
    """Downgrade fullscreen B-roll to top_pip when overlapping TimeLens2 gestures/reactions."""
    if not actions or groundings is None or not groundings.all_protected_intervals_ms:
        return tuple(actions)
    protected: list[CutCoverAction] = []
    for act in actions:
        if act.kind == "broll_fullscreen" and any(
            min(act.end_ms, ge) - max(act.start_ms, gs) >= 500
            for gs, ge, _ in groundings.all_protected_intervals_ms
        ):
            protected.append(
                replace(
                    act,
                    kind="broll_pip",
                    reason=f"{act.reason} [downgraded to top_pip to preserve TimeLens2 reaction]",
                )
            )
        else:
            protected.append(act)
    return tuple(protected)


def format_visual_groundings_for_director(
    groundings: VisualGroundings | None,
    shot_profiles: Sequence[ShotVisualProfile] = (),
) -> tuple[str, ...]:
    """Summarize VideoChat3-4B SV6D, TimeLens2-4B peaks & banter splits for the Director."""
    lines: list[str] = []
    if groundings is not None:
        for sv_line in groundings.sv6d_lines[:6]:
            if sv_line.strip():
                lines.append(f"VideoChat3 SV6D: {sv_line.strip()}")
        for gs, ge, lbl in groundings.gesture_intervals_ms[:4]:
            lines.append(f"TimeLens2 gesture ({gs}..{ge}ms): {lbl}")
        for rs, re_, lbl in groundings.reaction_intervals_ms[:4]:
            lines.append(f"TimeLens2 reaction ({rs}..{re_}ms): {lbl}")
    for prof in shot_profiles:
        if prof.dual_active_banter and prof.split_crops is not None:
            lines.append(
                f"50/50 split-screen active ({prof.start_ms}..{prof.end_ms}ms): "
                "wide 2-shot dual-speaker banter/reaction"
            )
    return tuple(lines)
