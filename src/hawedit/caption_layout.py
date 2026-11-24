"""Content-aware caption layout and essential visual region protection (VE-10 / V10).

Repositions and regroups captions to avoid essential visual regions (faces, demonstrations,
charts/graphics, existing source lower thirds) without altering canonical speech text or
silently shrinking font sizes into unreadability.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from hawedit.captions import (
    DEFAULT_MAX_CHARS_PER_LINE,
    DEFAULT_MAX_LINE_WIDTH_PX,
    POPUP_MAX_WORDS,
    chunk_caption_events,
)
from hawedit.shot_plan import ProtectedContentRegion, ProtectedRegionKind
from hawedit.transcripts import Word

__all__ = [
    "BOTTOM_BAND_BOX",
    "MID_UPPER_BAND_BOX",
    "TOP_BAND_BOX",
    "CaptionLayoutCue",
    "CaptionLayoutError",
    "CaptionLayoutPlan",
    "CaptionPlacement",
    "caption_layout_to_avoidance_intervals",
    "detect_protected_visual_regions",
    "plan_caption_layout",
]


class CaptionLayoutError(ValueError):
    """Raised when caption layout fails invariants or causes unresolvable visual collisions."""


class CaptionPlacement(str, Enum):
    """Approved vertical placement band for captions."""

    BOTTOM = "bottom"
    TOP = "top"
    MID_UPPER = "mid_upper"
    NEEDS_REVIEW = "needs_review"


# Default normalized vertical bands in 1080x1920 portrait frame (D-350 lower-middle safe zone)
BOTTOM_BAND_BOX: tuple[float, float, float, float] = (0.05, 0.70, 0.95, 0.80)
TOP_BAND_BOX: tuple[float, float, float, float] = (0.05, 0.08, 0.95, 0.26)
MID_UPPER_BAND_BOX: tuple[float, float, float, float] = (0.05, 0.28, 0.95, 0.44)


@dataclass(frozen=True, slots=True)
class CaptionLayoutCue:
    """A formatted caption cue with assigned placement band and conflict checks."""

    cue_id: str
    start_ms: int
    end_ms: int
    words: tuple[Word, ...]
    text: str
    placement: CaptionPlacement
    box: tuple[float, float, float, float]
    colliding_regions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.cue_id, str) or not self.cue_id.strip():
            raise ValueError("cue_id must be a non-empty string")
        if type(self.start_ms) is not int or type(self.end_ms) is not int:
            raise TypeError("cue timestamps must be exact integers")
        if self.start_ms < 0:
            raise ValueError("cue start_ms must be non-negative")
        if self.end_ms <= self.start_ms:
            raise ValueError(f"end_ms ({self.end_ms}) must be > start_ms ({self.start_ms})")
        if not self.words:
            raise ValueError("cue must contain at least one Word")
        if not isinstance(self.placement, CaptionPlacement):
            raise TypeError("placement must be a CaptionPlacement enum")
        if len(self.box) != 4:
            raise ValueError("box must have exactly 4 normalized coordinates")

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "cue_id": self.cue_id,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "duration_ms": self.duration_ms,
            "text": self.text,
            "placement": self.placement.value,
            "box": [round(float(c), 4) for c in self.box],
            "colliding_regions": list(self.colliding_regions),
        }


@dataclass(frozen=True, slots=True)
class CaptionLayoutPlan:
    """Complete editorial caption layout plan across an entire clip or shot."""

    cues: tuple[CaptionLayoutCue, ...]
    total_cues: int
    repositioned_to_top_count: int
    unresolvable_conflicts: tuple[str, ...]
    canonical_text: str
    status: str  # "approved", "needs_review"
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_cues": self.total_cues,
            "repositioned_to_top_count": self.repositioned_to_top_count,
            "unresolvable_conflicts": list(self.unresolvable_conflicts),
            "canonical_text": self.canonical_text,
            "status": self.status,
            "note": self.note,
            "cues": [c.to_dict() for c in self.cues],
        }


def _boxes_intersect(
    b1: tuple[float, float, float, float],
    b2: tuple[float, float, float, float],
    min_overlap_ratio: float = 0.05,
) -> bool:
    """Check whether two normalized bounding boxes intersect significantly against either box."""
    x0 = max(b1[0], b2[0])
    y0 = max(b1[1], b2[1])
    x1 = min(b1[2], b2[2])
    y1 = min(b1[3], b2[3])
    if x1 <= x0 or y1 <= y0:
        return False
    inter_area = (x1 - x0) * (y1 - y0)
    b1_area = (b1[2] - b1[0]) * (b1[3] - b1[1])
    b2_area = (b2[2] - b2[0]) * (b2[3] - b2[1])
    if b1_area <= 0.0 or b2_area <= 0.0:
        return False
    return max(inter_area / b1_area, inter_area / b2_area) >= min_overlap_ratio


def plan_caption_layout(
    words: Sequence[Word],
    protected_regions: Sequence[ProtectedContentRegion],
    *,
    clip_in_ms: int = 0,
    clip_out_ms: int | None = None,
    max_chars_per_line: int = DEFAULT_MAX_CHARS_PER_LINE,
    max_line_width_px: int = DEFAULT_MAX_LINE_WIDTH_PX,
    max_words_per_event: int | None = None,
    frame_dimensions: tuple[int, int] = (1080, 1920),
) -> CaptionLayoutPlan:
    """Plan readable caption layout avoiding essential visual regions without text drift.

    Args:
        words: Aligned spoken words in canonical surface form.
        protected_regions: Regions (faces, demos, tables, charts, banners) kept unobscured.
        clip_in_ms: Start of clip in media milliseconds.
        clip_out_ms: Optional end of clip in media milliseconds.
        max_chars_per_line: Max characters allowed before breaking or regrouping.
        max_line_width_px: Max physical width in pixels for 1080x1920 frame.
        max_words_per_event: Optional max word cap per cue (defaults to POPUP_MAX_WORDS).
        frame_dimensions: (width, height) of output canvas.

    Returns:
        CaptionLayoutPlan with conflict-free placements or explicit review escalation.

    Raises:
        CaptionLayoutError: If words are empty or invalid.
    """
    if not words:
        raise CaptionLayoutError("Cannot plan caption layout for empty word sequence")

    canonical_text = " ".join(w.w for w in words)

    # 1. Regroup spoken words into readable, bounded chunks
    # Reuse chunk_caption_events from hawedit.captions
    chunk_kwargs: dict[str, Any] = {
        "max_chars": max_chars_per_line,
        "max_width_px": max_line_width_px,
    }
    if max_words_per_event is not None:
        chunk_kwargs["max_words"] = max_words_per_event
    else:
        chunk_kwargs["max_words"] = POPUP_MAX_WORDS
    chunked = chunk_caption_events(words, **chunk_kwargs)

    planned_cues: list[CaptionLayoutCue] = []
    top_count = 0
    unresolvable_conflicts: list[str] = []

    protected_kinds = (
        ProtectedRegionKind.DEMONSTRATION,
        ProtectedRegionKind.GRAPHIC_OR_CHART,
        ProtectedRegionKind.SOURCE_ON_SCREEN_TEXT,
        ProtectedRegionKind.TABLE_OBJECT,
        ProtectedRegionKind.SPEAKER_FACE,
        ProtectedRegionKind.LISTENER_FACE,
    )

    for idx, cue_words in enumerate(chunked):
        cue_id = f"cue_{idx:03d}"
        cue_start = cue_words[0].start_ms
        cue_end = cue_words[-1].end_ms
        cue_text = " ".join(w.w for w in cue_words)

        # Active protected regions overlapping this cue's time window
        active_regions = [
            r
            for r in protected_regions
            if r.kind in protected_kinds
            and (r.start_ms is None or r.start_ms < cue_end)
            and (r.end_ms is None or r.end_ms > cue_start)
        ]

        # Check default BOTTOM band
        bottom_colliding = [
            r.region_id for r in active_regions if _boxes_intersect(BOTTOM_BAND_BOX, r.box)
        ]

        if not bottom_colliding:
            # Safe at bottom
            cue = CaptionLayoutCue(
                cue_id=cue_id,
                start_ms=cue_start,
                end_ms=cue_end,
                words=tuple(cue_words),
                text=cue_text,
                placement=CaptionPlacement.BOTTOM,
                box=BOTTOM_BAND_BOX,
                colliding_regions=(),
            )
            planned_cues.append(cue)
            continue

        # Bottom has collision with protected content: Evaluate TOP band
        top_colliding = [
            r.region_id for r in active_regions if _boxes_intersect(TOP_BAND_BOX, r.box)
        ]

        if not top_colliding:
            # Safe at top
            cue = CaptionLayoutCue(
                cue_id=cue_id,
                start_ms=cue_start,
                end_ms=cue_end,
                words=tuple(cue_words),
                text=cue_text,
                placement=CaptionPlacement.TOP,
                box=TOP_BAND_BOX,
                colliding_regions=(),
            )
            planned_cues.append(cue)
            top_count += 1
            continue

        # Both Bottom and Top collide: Evaluate MID_UPPER
        mid_colliding = [
            r.region_id for r in active_regions if _boxes_intersect(MID_UPPER_BAND_BOX, r.box)
        ]

        if not mid_colliding:
            cue = CaptionLayoutCue(
                cue_id=cue_id,
                start_ms=cue_start,
                end_ms=cue_end,
                words=tuple(cue_words),
                text=cue_text,
                placement=CaptionPlacement.MID_UPPER,
                box=MID_UPPER_BAND_BOX,
                colliding_regions=(),
            )
            planned_cues.append(cue)
            continue

        # All approved placement bands collide with essential content!
        # Do NOT silently cover the demonstration/face; escalate to review!
        colliding_set = sorted(set(bottom_colliding + top_colliding))
        conflict_desc = f"{cue_id} conflicts with regions {colliding_set}"
        unresolvable_conflicts.append(conflict_desc)
        cue = CaptionLayoutCue(
            cue_id=cue_id,
            start_ms=cue_start,
            end_ms=cue_end,
            words=tuple(cue_words),
            text=cue_text,
            placement=CaptionPlacement.NEEDS_REVIEW,
            box=BOTTOM_BAND_BOX,
            colliding_regions=tuple(sorted(set(bottom_colliding + top_colliding))),
        )
        planned_cues.append(cue)

    # Verify Kurdish Invariant #1: Exact surface words preserved without alteration
    reconstructed_text = " ".join(c.text for c in planned_cues)
    if reconstructed_text != canonical_text:
        raise CaptionLayoutError(
            f"Canonical text changed during caption layout! "
            f"Expected {canonical_text!r}, got {reconstructed_text!r}"
        )

    status = "needs_review" if unresolvable_conflicts else "approved"
    note = (
        f"Protected visual regions avoided. {top_count} cues relocated to top."
        if not unresolvable_conflicts
        else f"Warning: {len(unresolvable_conflicts)} cues have unresolvable visual conflicts."
    )

    return CaptionLayoutPlan(
        cues=tuple(planned_cues),
        total_cues=len(planned_cues),
        repositioned_to_top_count=top_count,
        unresolvable_conflicts=tuple(unresolvable_conflicts),
        canonical_text=canonical_text,
        status=status,
        note=note,
    )


def caption_layout_to_avoidance_intervals(
    plan: CaptionLayoutPlan,
    *,
    merge_gap_ms: int = 300,
) -> tuple[tuple[int, int, int, int], ...]:
    """Convert non-bottom cues from `CaptionLayoutPlan` into `build_ass` `face_intervals`."""
    relocated = [
        (cue.start_ms, cue.end_ms)
        for cue in plan.cues
        if cue.placement in (CaptionPlacement.TOP, CaptionPlacement.MID_UPPER)
    ]
    if not relocated:
        return ()
    merged: list[list[int]] = [[relocated[0][0], relocated[0][1]]]
    for s_ms, e_ms in relocated[1:]:
        if s_ms <= merged[-1][1] + merge_gap_ms:
            merged[-1][1] = max(merged[-1][1], e_ms)
        else:
            merged.append([s_ms, e_ms])
    return tuple((s_ms, e_ms, 1300, 1650) for s_ms, e_ms in merged)


def _crop_center_x_at_ms(
    focus_points: Sequence[Any],
    at_ms: int,
    default_cx: int,
) -> int:
    if not focus_points:
        return default_cx
    parsed: list[tuple[int, int]] = []
    for p in focus_points:
        if hasattr(p, "at_ms") and hasattr(p, "center_x"):
            parsed.append((int(p.at_ms), int(p.center_x)))
        elif isinstance(p, tuple) and len(p) >= 2:
            parsed.append((int(p[0]), int(p[1])))
    if not parsed:
        return default_cx
    best = min(parsed, key=lambda pair: abs(pair[0] - at_ms))
    return best[1]


def _coalesce_timed_regions(
    samples: Sequence[tuple[int, int, tuple[float, float, float, float]]],
    *,
    kind: ProtectedRegionKind,
    prefix: str,
    description: str,
    max_gap_ms: int,
) -> list[ProtectedContentRegion]:
    if not samples:
        return []
    merged: list[tuple[int, int, tuple[float, float, float, float]]] = []
    for s_ms, e_ms, box in samples:
        if merged and s_ms <= merged[-1][1] + max_gap_ms:
            prev_s, prev_e, pb = merged[-1]
            union = (
                min(pb[0], box[0]),
                min(pb[1], box[1]),
                max(pb[2], box[2]),
                max(pb[3], box[3]),
            )
            merged[-1] = (prev_s, max(prev_e, e_ms), union)
        else:
            merged.append((s_ms, e_ms, box))
    return [
        ProtectedContentRegion(
            region_id=f"{prefix}_{idx:02d}",
            kind=kind,
            box=box,
            description=description,
            start_ms=s_ms,
            end_ms=e_ms,
        )
        for idx, (s_ms, e_ms, box) in enumerate(merged)
    ]


def detect_protected_visual_regions(
    source_video: Path,
    clip_in_ms: int,
    clip_out_ms: int,
    *,
    source_dimensions: tuple[int, int],
    focus_points: Sequence[Any] = (),
    per_shot_boxes: Sequence[tuple[int, int, int | None, int | None]] = (),
    face_center_y: int | None = None,
    face_height: int | None = None,
    sample_step_ms: int = 1000,
) -> tuple[ProtectedContentRegion, ...]:
    """Detect lower-third teaser pills, wide table objects, and low face boxes in 9:16 crops.

    Calibrated on real Zar Podcast 16:9->9:16 frames:
    - Burned-in teaser banners (e.g. "لەم پۆدکاستەدا:"): saturated dark-blue lower banner strip
      (`B>95`, `B-R>45`, `B-G>30`, `R<75`) occupying >= 8% of lower band while absent in upper half.
    - Studio table/foreground objects: dense horizontal edge geometry in lower 60..90%
      (`Canny >= 0.10`, vertical Sobel gradient `>= 0.22`, horizontal `HoughLinesP` `>= 8`), well
      separated from plain torso/curtain close-ups (`edge <= 0.048`, `hlines <= 2`).
    """
    if not source_video.is_file():
        raise FileNotFoundError(f"Source video not found: {source_video}")
    if clip_out_ms <= clip_in_ms:
        raise ValueError(f"clip_out_ms ({clip_out_ms}) must be > clip_in_ms ({clip_in_ms})")
    src_w, src_h = source_dimensions
    if src_w <= 0 or src_h <= 0:
        raise CaptionLayoutError(f"Invalid source_dimensions: {source_dimensions}")
    if sample_step_ms < 100:
        raise ValueError(f"sample_step_ms ({sample_step_ms}) must be >= 100")

    import cv2
    import numpy as np

    regions: list[ProtectedContentRegion] = []
    if per_shot_boxes:
        for idx, (s_ms, e_ms, fcy, fh) in enumerate(per_shot_boxes):
            if fcy is not None and fh is not None and fh > 0 and e_ms > s_ms:
                y0 = max(0.0, min(0.99, (fcy - fh / 2.0) / src_h))
                y1 = max(y0 + 0.01, min(1.0, (fcy + fh / 2.0) / src_h))
                regions.append(
                    ProtectedContentRegion(
                        region_id=f"face_shot_{idx:02d}",
                        kind=ProtectedRegionKind.SPEAKER_FACE,
                        box=(0.20, y0, 0.80, y1),
                        description="Tracked per-shot speaker face box",
                        start_ms=int(s_ms),
                        end_ms=int(e_ms),
                    )
                )
    elif face_center_y is not None and face_height is not None and face_height > 0:
        y0 = max(0.0, min(0.99, (face_center_y - face_height / 2.0) / src_h))
        y1 = max(y0 + 0.01, min(1.0, (face_center_y + face_height / 2.0) / src_h))
        regions.append(
            ProtectedContentRegion(
                region_id="face_clip_00",
                kind=ProtectedRegionKind.SPEAKER_FACE,
                box=(0.20, y0, 0.80, y1),
                description="Tracked clip speaker face box",
                start_ms=clip_in_ms,
                end_ms=clip_out_ms,
            )
        )

    cap = cv2.VideoCapture(str(source_video))
    if not cap.isOpened():
        raise CaptionLayoutError(f"Cannot open source video for region detection: {source_video}")

    crop_w = min(src_w, max(2, int(round(src_h * 9 / 16)) & ~1))
    teaser_samples: list[tuple[int, int, tuple[float, float, float, float]]] = []
    table_samples: list[tuple[int, int, tuple[float, float, float, float]]] = []
    frames_decoded = 0
    try:
        for t_ms in range(clip_in_ms, clip_out_ms, sample_step_ms):
            cap.set(cv2.CAP_PROP_POS_MSEC, float(t_ms))
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            frames_decoded += 1
            fh, fw = frame.shape[:2]
            cx_scaled = int(
                round(_crop_center_x_at_ms(focus_points, t_ms, src_w // 2) * (fw / src_w))
            )
            local_crop_w = min(fw, max(2, int(round(crop_w * (fw / src_w)))))
            x_off = max(0, min(fw - local_crop_w, cx_scaled - local_crop_w // 2))
            crop = frame[:, x_off : x_off + local_crop_w]
            p9 = cv2.resize(crop, (540, 960), interpolation=cv2.INTER_AREA)
            t_end = min(clip_out_ms, t_ms + sample_step_ms)

            # 1) Lower-third burned-in dark/saturated teaser banner detection
            b_ch = p9[..., 0].astype(np.int16)
            g_ch = p9[..., 1].astype(np.int16)
            r_ch = p9[..., 2].astype(np.int16)
            blue_mask = (b_ch > 95) & ((b_ch - r_ch) > 45) & ((b_ch - g_ch) > 30) & (r_ch < 75)
            low_blue = blue_mask[int(0.65 * 960) : int(0.92 * 960), :]
            up_blue = blue_mask[int(0.10 * 960) : int(0.50 * 960), :]
            if float(low_blue.mean()) >= 0.08 and float(up_blue.mean()) < 0.04:
                by, bx = np.where(low_blue)
                if bx.size > 50:
                    blue_w = float((bx.max() - bx.min()) / 540.0)
                    if blue_w >= 0.35:
                        y0_n = max(0.65, 0.65 + float(by.min()) / 960.0)
                        y1_n = min(0.95, 0.65 + float(by.max() + 1) / 960.0)
                        teaser_samples.append(
                            (t_ms, t_end, (0.05, y0_n, 0.95, max(y0_n + 0.02, y1_n)))
                        )

            # 2) Wide horizontal studio table/props foreground detection
            gray = cv2.cvtColor(p9, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            sobel_h = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
            band_e = edges[int(0.68 * 960) : int(0.88 * 960), int(0.08 * 540) : int(0.92 * 540)] > 0
            band_sh = (
                np.abs(
                    sobel_h[int(0.68 * 960) : int(0.88 * 960), int(0.08 * 540) : int(0.92 * 540)]
                )
                > 35
            )
            lines = cv2.HoughLinesP(
                edges[int(0.60 * 960) : int(0.90 * 960), :],
                1,
                float(np.pi / 180.0),
                threshold=60,
                minLineLength=110,
                maxLineGap=15,
            )
            n_hlines = 0
            if lines is not None:
                for seg in lines[:, 0, :]:
                    if abs(int(seg[2]) - int(seg[0])) > 80 and abs(int(seg[3]) - int(seg[1])) <= 15:
                        n_hlines += 1
            if float(band_e.mean()) >= 0.10 and float(band_sh.mean()) >= 0.22 and n_hlines >= 8:
                table_samples.append((t_ms, t_end, (0.05, 0.60, 0.95, 0.92)))
    finally:
        cap.release()

    if frames_decoded == 0:
        raise CaptionLayoutError(
            f"Decoded zero frames from {source_video} across [{clip_in_ms}, {clip_out_ms}] ms"
        )

    regions.extend(
        _coalesce_timed_regions(
            teaser_samples,
            kind=ProtectedRegionKind.SOURCE_ON_SCREEN_TEXT,
            prefix="teaser_banner",
            description="Burned-in lower-third teaser banner overlay",
            max_gap_ms=sample_step_ms,
        )
    )
    regions.extend(
        _coalesce_timed_regions(
            table_samples,
            kind=ProtectedRegionKind.TABLE_OBJECT,
            prefix="table_object",
            description="Studio table and foreground props intersecting lower band",
            max_gap_ms=sample_step_ms,
        )
    )
    return tuple(regions)
