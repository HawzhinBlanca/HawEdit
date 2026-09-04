"""Automatic cover frame selection and title variants generation (pro-grade T4.10).

Chooses an optimal cover frame (thumbnail) for vertical social media reels (Instagram, TikTok,
YouTube Shorts) by evaluating face height share, image sharpness (Laplacian variance), and an
open-eyes heuristic, avoiding mid-blink or motion-blurred frames.

Generates Kurdish Sorani title variants to support social media A/B testing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

__all__ = [
    "CoverCandidate",
    "CoverSelectionError",
    "CoverSelectionResult",
    "generate_title_variants",
    "score_cover_frame",
    "select_cover_frame",
]


class CoverSelectionError(RuntimeError):
    """Raised when an optimal cover frame cannot be selected or extracted."""


@dataclass(frozen=True, slots=True)
class CoverCandidate:
    """Evaluation metrics for a candidate video frame."""

    time_ms: int
    face_share: float
    sharpness: float
    eyes_count: int
    score: float


@dataclass(frozen=True, slots=True)
class CoverSelectionResult:
    """The chosen cover frame and selection audit metadata."""

    chosen_time_ms: int
    score: float
    face_share: float
    sharpness: float
    eyes_count: int
    candidates_evaluated: int
    cover_path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "chosen_time_ms": self.chosen_time_ms,
            "score": self.score,
            "face_share": self.face_share,
            "sharpness": self.sharpness,
            "eyes_count": self.eyes_count,
            "candidates_evaluated": self.candidates_evaluated,
            "cover_path": str(self.cover_path),
        }


def _load_cascades() -> tuple[cv2.CascadeClassifier, cv2.CascadeClassifier]:
    """Load OpenCV frontal face and eye Haar cascade classifiers."""
    data_attr = getattr(cv2, "data", None)
    cascades_dir = Path(data_attr.haarcascades) if data_attr is not None else Path()
    frontal_path = cascades_dir / "haarcascade_frontalface_default.xml"
    eye_path = cascades_dir / "haarcascade_eye.xml"

    if not frontal_path.is_file():
        raise CoverSelectionError(f"Frontal face cascade not found at {frontal_path}")
    if not eye_path.is_file():
        raise CoverSelectionError(f"Eye cascade not found at {eye_path}")

    frontal = cv2.CascadeClassifier(str(frontal_path))
    eye = cv2.CascadeClassifier(str(eye_path))
    if frontal.empty():
        raise CoverSelectionError(f"Failed to load face cascade from {frontal_path}")
    if eye.empty():
        raise CoverSelectionError(f"Failed to load eye cascade from {eye_path}")

    return frontal, eye


def score_cover_frame(
    frame: np.ndarray[Any, Any],
    time_ms: int,
    frontal_cascade: cv2.CascadeClassifier,
    eye_cascade: cv2.CascadeClassifier,
) -> CoverCandidate | None:
    """Score a single video frame for thumbnail suitability.

    Heuristic evaluates:
    1. Face share: ratio of face box height to frame height (larger closeup is better).
    2. Sharpness: variance of Laplacian operator on face region (higher is crisper).
    3. Eyes: presence of detected eyes in upper 55% of face (penalises blinking/closed eyes).
    """
    height, width = frame.shape[:2]
    if height == 0 or width == 0:
        return None

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = frontal_cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=4, minSize=(60, 60)
    )
    if len(faces) == 0:
        return None

    # Select largest face in frame
    x, y, w, h = max(faces, key=lambda b: int(b[2]) * int(b[3]))
    face_share = float(h) / float(height)

    face_roi = gray[y : y + h, x : x + w]
    if face_roi.size == 0:
        return None

    sharpness = float(cv2.Laplacian(face_roi, cv2.CV_64F).var())

    # Detect eyes in upper 55% of the face region
    eye_roi_height = max(1, int(h * 0.55))
    eye_roi = face_roi[0:eye_roi_height, :]
    eyes = eye_cascade.detectMultiScale(eye_roi, scaleFactor=1.1, minNeighbors=3, minSize=(15, 15))
    eyes_count = min(2, len(eyes))

    # Weightings:
    # 2 eyes open: full multiplier (1.0)
    # 1 eye open (profile or wink): moderate multiplier (0.6)
    # 0 eyes (mid-blink): severe penalty (0.1)
    if eyes_count >= 2:
        eye_multiplier = 1.0
    elif eyes_count == 1:
        eye_multiplier = 0.6
    else:
        eye_multiplier = 0.1

    composite = (face_share * 100.0) * math.log1p(max(1.0, sharpness)) * eye_multiplier

    return CoverCandidate(
        time_ms=time_ms,
        face_share=round(face_share, 4),
        sharpness=round(sharpness, 2),
        eyes_count=eyes_count,
        score=round(composite, 4),
    )


def select_cover_frame(
    video_path: Path,
    output_png_path: Path,
    *,
    in_ms: int = 0,
    out_ms: int | None = None,
    sample_interval_ms: int = 400,
) -> CoverSelectionResult:
    """Sample video frames across [in_ms, out_ms] and save the highest-scoring cover thumbnail.

    Args:
        video_path: Path to the input video file (e.g. rendered reel MP4).
        output_png_path: Target path for the extracted cover thumbnail PNG.
        in_ms: Start time in milliseconds (default 0).
        out_ms: End time in milliseconds (default: video duration).
        sample_interval_ms: Interval between candidate sample frames in milliseconds.

    Returns:
        CoverSelectionResult with audit scores and output path.
    """
    if not video_path.is_file():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    if sample_interval_ms <= 0:
        raise ValueError(f"sample_interval_ms must be positive, got {sample_interval_ms}")

    frontal_cascade, eye_cascade = _load_cascades()

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise CoverSelectionError(f"Could not open video {video_path}")

    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        video_duration_ms = int((total_frames / fps) * 1000.0) if fps > 0 else 0

        effective_out_ms = out_ms if out_ms is not None else video_duration_ms
        if effective_out_ms <= in_ms:
            effective_out_ms = max(in_ms + 1000, video_duration_ms)

        candidates: list[CoverCandidate] = []
        frames_by_time: dict[int, np.ndarray[Any, Any]] = {}
        samples_evaluated = 0

        current_ms = in_ms
        while current_ms <= effective_out_ms:
            cap.set(cv2.CAP_PROP_POS_MSEC, float(current_ms))
            ret, frame = cap.read()
            if not ret or frame is None:
                break
            samples_evaluated += 1

            candidate = score_cover_frame(frame, current_ms, frontal_cascade, eye_cascade)
            if candidate is not None:
                candidates.append(candidate)
                frames_by_time[current_ms] = frame

            current_ms += sample_interval_ms

        if not candidates:
            # Fallback if no face was detected: capture midpoint frame
            mid_ms = (in_ms + effective_out_ms) // 2
            cap.set(cv2.CAP_PROP_POS_MSEC, float(mid_ms))
            ret, frame = cap.read()
            if not ret or frame is None:
                # Seek to start
                cap.set(cv2.CAP_PROP_POS_MSEC, float(in_ms))
                ret, frame = cap.read()
                if not ret or frame is None:
                    raise CoverSelectionError(f"Failed to read any video frames from {video_path}")
                mid_ms = in_ms

            chosen_time = mid_ms
            best_candidate = CoverCandidate(
                time_ms=chosen_time,
                face_share=0.0,
                sharpness=0.0,
                eyes_count=0,
                score=0.0,
            )
            winning_frame = frame
        else:
            best_candidate = max(candidates, key=lambda c: c.score)
            chosen_time = best_candidate.time_ms
            winning_frame = frames_by_time[chosen_time]

        output_png_path.parent.mkdir(parents=True, exist_ok=True)
        success = cv2.imwrite(str(output_png_path), winning_frame)
        if not success or not output_png_path.is_file() or output_png_path.stat().st_size == 0:
            raise CoverSelectionError(f"Failed to write cover image to {output_png_path}")

        return CoverSelectionResult(
            chosen_time_ms=best_candidate.time_ms,
            score=best_candidate.score,
            face_share=best_candidate.face_share,
            sharpness=best_candidate.sharpness,
            eyes_count=best_candidate.eyes_count,
            candidates_evaluated=samples_evaluated,
            cover_path=output_png_path,
        )
    finally:
        cap.release()


def generate_title_variants(
    base_title_ckb: str,
    hook_type: str | None = None,
) -> tuple[str, str, str]:
    """Generate three editorial title variants in Sorani Kurdish for social A/B testing.

    Variants:
    1. Primary Hook Title (direct, punchy).
    2. Question / Inquiry Hook ("ئایا ...؟").
    3. Dramatic / Revelation Hook ("نهێنیی ... / گرنگترین دەربڕین لەسەر ...").
    """
    clean_title = base_title_ckb.strip()
    if not clean_title:
        raise ValueError("base_title_ckb cannot be empty")

    # 1. Primary
    v1 = clean_title

    # 2. Question variant
    if clean_title.endswith("؟") or clean_title.endswith("?"):
        v2 = clean_title
    else:
        v2 = f"ئایا {clean_title}؟"

    # 3. Contextual intrigue variant based on hook_type
    if hook_type == "question":
        v3 = f"وەڵامی گرنگ: {clean_title}"
    elif hook_type == "confession":
        v3 = f"دانپێدانانێکی مێژوویی: {clean_title}"
    elif hook_type == "contrast":
        v3 = f"جیاوازییەکی چاوەڕواننەکراو: {clean_title}"
    else:
        v3 = f"باسی گرنگ: {clean_title}"

    return (v1, v2, v3)
