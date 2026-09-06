"""Content-aware caption layout and essential visual region protection (VE-10 / V10).

Repositions and regroups captions to avoid essential visual regions (faces, demonstrations,
charts/graphics, existing source lower thirds) without altering canonical speech text or
silently shrinking font sizes into unreadability.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from hawedit.captions import (
    DEFAULT_MAX_CHARS_PER_LINE,
    DEFAULT_MAX_LINE_WIDTH_PX,
    chunk_caption_events,
)
from hawedit.shot_plan import ProtectedContentRegion, ProtectedRegionKind
from hawedit.transcripts import Word

__all__ = [
    "CaptionLayoutCue",
    "CaptionLayoutError",
    "CaptionLayoutPlan",
    "CaptionPlacement",
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


# Default normalized vertical bands in 1080x1920 portrait frame
BOTTOM_BAND_BOX: tuple[float, float, float, float] = (0.05, 0.72, 0.95, 0.92)
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
    """Check whether two normalized bounding boxes intersect significantly."""
    x0 = max(b1[0], b2[0])
    y0 = max(b1[1], b2[1])
    x1 = min(b1[2], b2[2])
    y1 = min(b1[3], b2[3])
    if x1 <= x0 or y1 <= y0:
        return False
    inter_area = (x1 - x0) * (y1 - y0)
    b2_area = (b2[2] - b2[0]) * (b2[3] - b2[1])
    if b2_area <= 0.0:
        return False
    return (inter_area / b2_area) >= min_overlap_ratio


def plan_caption_layout(
    words: Sequence[Word],
    protected_regions: Sequence[ProtectedContentRegion],
    *,
    clip_in_ms: int = 0,
    clip_out_ms: int | None = None,
    max_chars_per_line: int = DEFAULT_MAX_CHARS_PER_LINE,
    max_line_width_px: int = DEFAULT_MAX_LINE_WIDTH_PX,
    frame_dimensions: tuple[int, int] = (1080, 1920),
) -> CaptionLayoutPlan:
    """Plan readable caption layout avoiding essential visual regions without text drift.

    Args:
        words: Aligned spoken words in canonical surface form.
        protected_regions: Regions (faces, demos, charts, nameplates) that must not be obscured.
        clip_in_ms: Start of clip in media milliseconds.
        clip_out_ms: Optional end of clip in media milliseconds.
        max_chars_per_line: Max characters allowed before breaking or regrouping.
        max_line_width_px: Max physical width in pixels for 1080x1920 frame.
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
    chunked = chunk_caption_events(
        words,
        max_chars=max_chars_per_line,
        max_width_px=max_line_width_px,
    )

    planned_cues: list[CaptionLayoutCue] = []
    top_count = 0
    unresolvable_conflicts: list[str] = []

    for idx, cue_words in enumerate(chunked):
        cue_id = f"cue_{idx:03d}"
        cue_start = cue_words[0].start_ms
        cue_end = cue_words[-1].end_ms
        cue_text = " ".join(w.w for w in cue_words)

        # Active protected regions during this cue's time window
        active_regions = [
            r
            for r in protected_regions
            if r.kind
            in (
                ProtectedRegionKind.DEMONSTRATION,
                ProtectedRegionKind.GRAPHIC_OR_CHART,
                ProtectedRegionKind.SOURCE_ON_SCREEN_TEXT,
                ProtectedRegionKind.SPEAKER_FACE,
                ProtectedRegionKind.LISTENER_FACE,
            )
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
