"""Whole-shot composition and camera path stabilization (VE-08 / V08).

Preserves required visible content across whole shots with an approved stable camera path,
protects headroom and eyeline, avoids caption safe collisions, eliminates restless crop jitter
via dead-zone hysteresis, and enforces explicit source-preserving alternatives when 9:16 vertical
cropping cannot preserve essential content.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

from hawedit.reframe import FocusPoint
from hawedit.shot_plan import (
    PlannedShot,
    ProtectedRegionKind,
    ShotLayoutStrategy,
)

__all__ = [
    "CropBox",
    "CropJitterMetrics",
    "CropKeyframe",
    "ShotCompositionError",
    "ShotCompositionResult",
    "TemporalGroundingError",
    "compose_shot",
    "measure_crop_jitter",
]


class ShotCompositionError(ValueError):
    """Raised when whole-shot composition violates editorial or geometric constraints."""


class TemporalGroundingError(ValueError):
    """Raised when camera framing uses visual observations outside the source shot interval."""


@dataclass(frozen=True, slots=True)
class CropBox:
    """Normalized [0.0..1.0] rectangular crop window within the source frame."""

    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        for name, val in (("x0", self.x0), ("y0", self.y0), ("x1", self.x1), ("y1", self.y1)):
            if type(val) not in (int, float) or not math.isfinite(val):
                raise TypeError(f"crop coordinate {name} must be a finite float")
            if not 0.0 <= float(val) <= 1.0:
                raise ValueError(f"crop coordinate {name} must be in [0.0, 1.0], got {val}")
        if self.x1 <= self.x0:
            raise ValueError(f"x1 ({self.x1}) must be > x0 ({self.x0})")
        if self.y1 <= self.y0:
            raise ValueError(f"y1 ({self.y1}) must be > y0 ({self.y0})")

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def center_y(self) -> float:
        return (self.y0 + self.y1) / 2.0

    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height

    def contains(self, box: tuple[float, float, float, float], tolerance: float = 0.001) -> bool:
        """Return True if the given box (x0, y0, x1, y1) is fully within this crop window."""
        bx0, by0, bx1, by1 = box
        return (
            bx0 >= (self.x0 - tolerance)
            and by0 >= (self.y0 - tolerance)
            and bx1 <= (self.x1 + tolerance)
            and by1 <= (self.y1 + tolerance)
        )

    def intersection_ratio(self, box: tuple[float, float, float, float]) -> float:
        """Calculate the visible area fraction of the given box inside this crop window."""
        bx0, by0, bx1, by1 = box
        bw = bx1 - bx0
        bh = by1 - by0
        if bw <= 0.0 or bh <= 0.0:
            return 0.0
        ix0 = max(self.x0, bx0)
        iy0 = max(self.y0, by0)
        ix1 = min(self.x1, bx1)
        iy1 = min(self.y1, by1)
        if ix1 <= ix0 or iy1 <= iy0:
            return 0.0
        inter_area = (ix1 - ix0) * (iy1 - iy0)
        box_area = bw * bh
        return min(1.0, inter_area / box_area)

    def to_pixels(self, source_width: int, source_height: int) -> tuple[int, int, int, int]:
        """Convert normalized crop to pixel coordinates (px_x, px_y, px_w, px_h)."""
        px_x = int(round(self.x0 * source_width))
        px_y = int(round(self.y0 * source_height))
        px_w = int(round(self.width * source_width))
        px_h = int(round(self.height * source_height))
        px_w = max(2, px_w // 2 * 2)
        px_h = max(2, px_h // 2 * 2)
        px_x = max(0, min(px_x, source_width - px_w))
        px_y = max(0, min(px_y, source_height - px_h))
        return (px_x, px_y, px_w, px_h)

    def to_dict(self) -> dict[str, float]:
        return {
            "x0": round(float(self.x0), 4),
            "y0": round(float(self.y0), 4),
            "x1": round(float(self.x1), 4),
            "y1": round(float(self.y1), 4),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CropBox:
        return cls(
            x0=float(data["x0"]),
            y0=float(data["y0"]),
            x1=float(data["x1"]),
            y1=float(data["y1"]),
        )


@dataclass(frozen=True, slots=True)
class CropKeyframe:
    """A crop window applied at a specific instant on the media timeline."""

    at_ms: int
    crop_box: CropBox
    is_holding: bool = True

    def __post_init__(self) -> None:
        if type(self.at_ms) is not int or self.at_ms < 0:
            raise TypeError("at_ms must be a non-negative integer")
        if not isinstance(self.crop_box, CropBox):
            raise TypeError("crop_box must be a CropBox instance")
        if not isinstance(self.is_holding, bool):
            raise TypeError("is_holding must be a boolean")

    def to_dict(self) -> dict[str, Any]:
        return {
            "at_ms": self.at_ms,
            "crop_box": self.crop_box.to_dict(),
            "is_holding": self.is_holding,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CropKeyframe:
        return cls(
            at_ms=int(data["at_ms"]),
            crop_box=CropBox.from_dict(data["crop_box"]),
            is_holding=bool(data.get("is_holding", True)),
        )


@dataclass(frozen=True, slots=True)
class CropJitterMetrics:
    """Quantitative measurement of crop motion stability across a shot."""

    reversals_x: int
    reversals_y: int
    mean_abs_step_x: float
    mean_abs_step_y: float
    max_step_x: float
    max_step_y: float
    jitter_score: float
    is_jitter_free: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "reversals_x": self.reversals_x,
            "reversals_y": self.reversals_y,
            "mean_abs_step_x": round(self.mean_abs_step_x, 5),
            "mean_abs_step_y": round(self.mean_abs_step_y, 5),
            "max_step_x": round(self.max_step_x, 5),
            "max_step_y": round(self.max_step_y, 5),
            "jitter_score": round(self.jitter_score, 5),
            "is_jitter_free": self.is_jitter_free,
        }


def measure_crop_jitter(
    keyframes: Sequence[CropKeyframe],
    *,
    max_jitter_threshold: float = 0.05,
) -> CropJitterMetrics:
    """Evaluate camera path for restless crop jitter and direction reversals.

    High-frequency reversals in velocity indicate camera wobble / detector noise.
    A well-stabilized shot consists of stationary holds and monotonic smooth pans.
    """
    if len(keyframes) < 2:
        return CropJitterMetrics(
            reversals_x=0,
            reversals_y=0,
            mean_abs_step_x=0.0,
            mean_abs_step_y=0.0,
            max_step_x=0.0,
            max_step_y=0.0,
            jitter_score=0.0,
            is_jitter_free=True,
        )

    steps_x: list[float] = []
    steps_y: list[float] = []
    for k1, k2 in pairwise(keyframes):
        steps_x.append(k2.crop_box.center_x - k1.crop_box.center_x)
        steps_y.append(k2.crop_box.center_y - k1.crop_box.center_y)

    reversals_x = 0
    for v1, v2 in pairwise(steps_x):
        if (v1 > 1e-4 and v2 < -1e-4) or (v1 < -1e-4 and v2 > 1e-4):
            reversals_x += 1

    reversals_y = 0
    for v1, v2 in pairwise(steps_y):
        if (v1 > 1e-4 and v2 < -1e-4) or (v1 < -1e-4 and v2 > 1e-4):
            reversals_y += 1

    abs_steps_x = [abs(s) for s in steps_x]
    abs_steps_y = [abs(s) for s in steps_y]
    mean_abs_x = sum(abs_steps_x) / len(abs_steps_x) if abs_steps_x else 0.0
    mean_abs_y = sum(abs_steps_y) / len(abs_steps_y) if abs_steps_y else 0.0
    max_x = max(abs_steps_x) if abs_steps_x else 0.0
    max_y = max(abs_steps_y) if abs_steps_y else 0.0

    # Jitter score penalizes frequent reversals and high-frequency steps
    # For holds and smooth pans, reversals are 0 and jitter_score is near 0
    net_disp_x = abs(keyframes[-1].crop_box.center_x - keyframes[0].crop_box.center_x)
    total_path_x = sum(abs_steps_x)
    oscillation_ratio = (total_path_x - net_disp_x) if total_path_x > net_disp_x else 0.0
    jitter_score = float(reversals_x + reversals_y) * 0.02 + oscillation_ratio

    is_jitter_free = (
        (reversals_x == 0) and (reversals_y == 0) and (jitter_score <= max_jitter_threshold)
    )

    return CropJitterMetrics(
        reversals_x=reversals_x,
        reversals_y=reversals_y,
        mean_abs_step_x=mean_abs_x,
        mean_abs_step_y=mean_abs_y,
        max_step_x=max_x,
        max_step_y=max_y,
        jitter_score=jitter_score,
        is_jitter_free=is_jitter_free,
    )


@dataclass(frozen=True, slots=True)
class ShotCompositionResult:
    """Full composition result for a single planned shot."""

    shot_id: str
    effective_layout: ShotLayoutStrategy
    requested_layout: ShotLayoutStrategy
    camera_keyframes: tuple[CropKeyframe, ...]
    jitter_metrics: CropJitterMetrics
    preserved_regions: tuple[str, ...]
    cutoff_regions: tuple[str, ...]
    caption_conflicts: tuple[str, ...]
    headroom_ratio: float
    eyeline_ratio: float
    status: str  # "approved", "elevated_to_source_preserving", "needs_review"
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "effective_layout": self.effective_layout.value,
            "requested_layout": self.requested_layout.value,
            "camera_keyframes": [k.to_dict() for k in self.camera_keyframes],
            "jitter_metrics": self.jitter_metrics.to_dict(),
            "preserved_regions": list(self.preserved_regions),
            "cutoff_regions": list(self.cutoff_regions),
            "caption_conflicts": list(self.caption_conflicts),
            "headroom_ratio": round(self.headroom_ratio, 4),
            "eyeline_ratio": round(self.eyeline_ratio, 4),
            "status": self.status,
            "note": self.note,
        }


def _calculate_916_crop_width(source_width: int, source_height: int) -> float:
    """Calculate normalized width of a full-height 9:16 vertical crop."""
    target_aspect = 9.0 / 16.0
    source_aspect = float(source_width) / float(source_height)
    # If source is 16:9 (1.777), vertical 9:16 crop uses 100% height, width = (9/16)/source_aspect
    return target_aspect / source_aspect


def compose_shot(
    shot: PlannedShot,
    observations: Sequence[tuple[int, float, float, float, float] | FocusPoint],
    *,
    source_dimensions: tuple[int, int] = (1920, 1080),
    dead_zone_threshold: float = 0.02,
    settle_duration_ms: int = 600,
    move_duration_ms: int = 400,
    min_content_visibility: float = 0.95,
) -> ShotCompositionResult:
    """Compose framing and camera path for a shot while preserving required content.

    Args:
        shot: The planned shot with verified editorial purpose and protected regions.
        observations: Timed detections, either FocusPoint or (at_ms, cx, cy, w, h).
        source_dimensions: (width, height) of source media.
        dead_zone_threshold: Normalized movement threshold for stationary camera holding.
        settle_duration_ms: Time subject must stay outside dead zone to trigger camera movement.
        move_duration_ms: Duration of camera transition easing.
        min_content_visibility: Minimum fraction of protected region that must remain visible.

    Returns:
        ShotCompositionResult with stable camera path or an explicit source-preserving alternative.
    """
    src_w, src_h = source_dimensions
    norm_crop_w = _calculate_916_crop_width(src_w, src_h)
    norm_crop_h = 1.0

    # 1. Temporal grounding enforcement: No time fabrication / contemporaneous borrowing
    for obs in observations:
        t_ms = obs.at_ms if isinstance(obs, FocusPoint) else int(obs[0])
        if t_ms < shot.source_in_ms or t_ms > shot.source_out_ms:
            raise TemporalGroundingError(
                f"observation at {t_ms}ms is outside shot source interval "
                f"[{shot.source_in_ms}, {shot.source_out_ms}]: temporal fabrication forbidden"
            )

    # 2. Check if protected regions can physically fit inside a 9:16 vertical crop
    # Find bounding box enclosing all protected regions for this shot
    cutoff_regions: list[str] = []
    preserved_regions: list[str] = []

    if shot.protected_regions:
        min_rx0 = min(r.box[0] for r in shot.protected_regions)
        min_ry0 = min(r.box[1] for r in shot.protected_regions)
        max_rx1 = max(r.box[2] for r in shot.protected_regions)
        max_ry1 = max(r.box[3] for r in shot.protected_regions)
        required_span_w = max_rx1 - min_rx0
        required_span_h = max_ry1 - min_ry0
    else:
        min_rx0, min_ry0, max_rx1, max_ry1 = 0.35, 0.2, 0.65, 0.8
        required_span_w = 0.30
        required_span_h = 0.60

    has_wide_demonstration = any(
        r.kind in (ProtectedRegionKind.DEMONSTRATION, ProtectedRegionKind.GRAPHIC_OR_CHART)
        and r.width > norm_crop_w * 0.90
        for r in shot.protected_regions
    )
    face_kinds = (ProtectedRegionKind.SPEAKER_FACE, ProtectedRegionKind.LISTENER_FACE)
    num_faces = len([r for r in shot.protected_regions if r.kind in face_kinds])
    has_multiple_separated_faces = num_faces >= 2 and required_span_w > norm_crop_w

    needs_source_preserving = (
        required_span_w > norm_crop_w
        or required_span_h > norm_crop_h
        or has_wide_demonstration
        or has_multiple_separated_faces
    )

    if needs_source_preserving:
        # A single 9:16 crop cannot fit the required visible content!
        # Choose an explicit source-preserving alternative rather than silent cutoff.
        if has_multiple_separated_faces:
            effective_layout = ShotLayoutStrategy.TWO_PERSON_LAYOUT
            reason = "Elevated to two-person layout to preserve both conversation participants."
        elif has_wide_demonstration:
            effective_layout = ShotLayoutStrategy.KEEP_SOURCE
            reason = "Elevated to keep_source full frame to preserve wide demonstration/graphic."
        elif shot.layout_strategy in (ShotLayoutStrategy.CROP, ShotLayoutStrategy.FOLLOW):
            effective_layout = ShotLayoutStrategy.KEEP_SOURCE
            reason = "Elevated to keep_source because required content span exceeds 9:16 crop."
        else:
            effective_layout = shot.layout_strategy
            reason = "Preserving existing layout strategy."

        # Keyframe for full source view (x0=0, y0=0, x1=1, y1=1)
        full_box = CropBox(0.0, 0.0, 1.0, 1.0)
        kf_start = CropKeyframe(at_ms=shot.source_in_ms, crop_box=full_box, is_holding=True)
        kf_end = CropKeyframe(at_ms=shot.source_out_ms, crop_box=full_box, is_holding=True)
        keyframes = (kf_start, kf_end)
        metrics = measure_crop_jitter(keyframes)

        for r in shot.protected_regions:
            preserved_regions.append(r.region_id)

        elevated = effective_layout != shot.layout_strategy
        status_str = "elevated_to_source_preserving" if elevated else "approved"

        return ShotCompositionResult(
            shot_id=shot.shot_id,
            effective_layout=effective_layout,
            requested_layout=shot.layout_strategy,
            camera_keyframes=keyframes,
            jitter_metrics=metrics,
            preserved_regions=tuple(preserved_regions),
            cutoff_regions=(),
            caption_conflicts=(),
            headroom_ratio=0.30,
            eyeline_ratio=0.33,
            status=status_str,
            note=reason,
        )

    # 3. Content fits in 9:16 crop: Compute stabilized camera path with dead-zone hysteresis
    # Determine target horizontal centers from observations
    raw_points: list[tuple[int, float, float]] = []
    for obs in observations:
        if isinstance(obs, FocusPoint):
            cx = float(obs.center_x) / float(src_w)
            cy = float(obs.center_y) / float(src_h) if obs.center_y is not None else 0.35
            raw_points.append((obs.at_ms, cx, cy))
        else:
            at_t, bx, by, _bw, _bh = obs
            raw_points.append((at_t, bx, by))

    if not raw_points:
        # Default to center of protected regions or middle of frame
        default_cx = (min_rx0 + max_rx1) / 2.0
        default_cy = (min_ry0 + max_ry1) / 2.0
        raw_points = [
            (shot.source_in_ms, default_cx, default_cy),
            (shot.source_out_ms, default_cx, default_cy),
        ]

    # Sort chronologically
    raw_points.sort(key=lambda p: p[0])

    # Apply dead-zone hysteresis
    held_cx = raw_points[0][1]
    held_cy = raw_points[0][2]
    kf_list: list[CropKeyframe] = []

    def make_crop_box(cx: float, cy: float) -> CropBox:
        half_w = norm_crop_w / 2.0
        x0 = max(0.0, min(cx - half_w, 1.0 - norm_crop_w))
        x1 = x0 + norm_crop_w
        # Vertical placement: place eye line / center at upper third (y ≈ 0.33)
        target_composition_y = 0.33
        desired_y0 = cy - target_composition_y
        y0 = max(0.0, min(desired_y0, 1.0 - norm_crop_h))
        y1 = y0 + norm_crop_h
        return CropBox(x0, y0, x1, y1)

    # Initial keyframe
    first_box = make_crop_box(held_cx, held_cy)
    kf_list.append(CropKeyframe(at_ms=raw_points[0][0], crop_box=first_box, is_holding=True))

    pending_points: list[tuple[int, float, float]] = []

    for pt in raw_points[1:]:
        t, px, py = pt
        if abs(px - held_cx) <= dead_zone_threshold:
            # Within dead zone: it's minor wobble / detector jitter. Clear pending move and hold.
            pending_points.clear()
            continue

        pending_points.append(pt)
        # Check if subject sustained outside dead zone for at least settle_duration_ms
        if t - pending_points[0][0] >= settle_duration_ms:
            # Commit to new position: median of pending window to reject outliers
            target_cx = sorted(p[1] for p in pending_points)[len(pending_points) // 2]
            target_cy = sorted(p[2] for p in pending_points)[len(pending_points) // 2]
            start_move_t = pending_points[0][0]

            # Append hold up to start of move
            if start_move_t > kf_list[-1].at_ms:
                kf_list.append(
                    CropKeyframe(
                        at_ms=start_move_t,
                        crop_box=make_crop_box(held_cx, held_cy),
                        is_holding=True,
                    )
                )

            # Append smooth transition to target
            end_move_t = min(start_move_t + move_duration_ms, shot.source_out_ms)
            target_box = make_crop_box(target_cx, target_cy)
            kf_list.append(
                CropKeyframe(
                    at_ms=end_move_t,
                    crop_box=target_box,
                    is_holding=False,
                )
            )

            held_cx = target_cx
            held_cy = target_cy
            pending_points.clear()

    # Final hold to the end of the shot
    if kf_list[-1].at_ms < shot.source_out_ms:
        final_box = make_crop_box(held_cx, held_cy)
        kf_list.append(
            CropKeyframe(
                at_ms=shot.source_out_ms,
                crop_box=final_box,
                is_holding=True,
            )
        )

    camera_keyframes = tuple(kf_list)
    jitter_metrics = measure_crop_jitter(camera_keyframes)

    # 4. Verify protected regions visibility across all keyframes
    caption_conflicts: list[str] = []
    cap_x0, cap_y0, cap_x1, cap_y1 = shot.caption_safe_box

    for region in shot.protected_regions:
        is_preserved_everywhere = True
        for kf in camera_keyframes:
            if shot.layout_strategy == ShotLayoutStrategy.FOLLOW and region.kind in (
                ProtectedRegionKind.SPEAKER_FACE,
                ProtectedRegionKind.LISTENER_FACE,
            ):
                # In a follow shot, the tracked face moves with the camera path
                face_w = region.width
                face_h = region.height
                current_box = (
                    kf.crop_box.center_x - face_w / 2.0,
                    kf.crop_box.center_y - face_h / 2.0,
                    kf.crop_box.center_x + face_w / 2.0,
                    kf.crop_box.center_y + face_h / 2.0,
                )
            else:
                current_box = region.box

            vis = kf.crop_box.intersection_ratio(current_box)
            if vis < min_content_visibility:
                is_preserved_everywhere = False
                break

            # Check caption collision:
            # Map region box into output crop coordinates
            rx0, ry0, rx1, ry1 = current_box
            out_rx0 = (rx0 - kf.crop_box.x0) / kf.crop_box.width
            out_ry0 = (ry0 - kf.crop_box.y0) / kf.crop_box.height
            out_rx1 = (rx1 - kf.crop_box.x0) / kf.crop_box.width
            out_ry1 = (ry1 - kf.crop_box.y0) / kf.crop_box.height

            # If essential region (face or demo) intersects lower third caption box
            inter_cap_w = max(0.0, min(out_rx1, cap_x1) - max(out_rx0, cap_x0))
            inter_cap_h = max(0.0, min(out_ry1, cap_y1) - max(out_ry0, cap_y0))
            if (
                inter_cap_w > 0.0
                and inter_cap_h > 0.0
                and (inter_cap_w * inter_cap_h) / (region.width * region.height) > 0.20
            ):
                caption_conflicts.append(region.region_id)

        if is_preserved_everywhere:
            preserved_regions.append(region.region_id)
        else:
            cutoff_regions.append(region.region_id)

    # Calculate headroom and eyeline ratio for the initial frame
    first_crop = camera_keyframes[0].crop_box
    # Headroom = distance from top of face to crop top / face height
    face_kinds = (ProtectedRegionKind.SPEAKER_FACE, ProtectedRegionKind.LISTENER_FACE)
    face_regions = [r for r in shot.protected_regions if r.kind in face_kinds]
    if face_regions:
        primary_face = face_regions[0]
        face_top = primary_face.box[1]
        headroom = (face_top - first_crop.y0) / max(0.05, primary_face.height)
        eyeline = (primary_face.box[1] + primary_face.box[3]) / 2.0 - first_crop.y0
    else:
        headroom = 0.25
        eyeline = 0.33

    status = "approved"
    note = "Composed stable 9:16 camera path with verified content protection."
    if cutoff_regions:
        status = "needs_review"
        note = f"Warning: crop cuts off protected regions: {cutoff_regions}"
    elif not jitter_metrics.is_jitter_free:
        status = "needs_review"
        score = jitter_metrics.jitter_score
        note = f"Warning: camera path exhibits crop jitter (score={score:.4f})"

    return ShotCompositionResult(
        shot_id=shot.shot_id,
        effective_layout=shot.layout_strategy,
        requested_layout=shot.layout_strategy,
        camera_keyframes=camera_keyframes,
        jitter_metrics=jitter_metrics,
        preserved_regions=tuple(preserved_regions),
        cutoff_regions=tuple(cutoff_regions),
        caption_conflicts=tuple(set(caption_conflicts)),
        headroom_ratio=headroom,
        eyeline_ratio=eyeline,
        status=status,
        note=note,
    )
