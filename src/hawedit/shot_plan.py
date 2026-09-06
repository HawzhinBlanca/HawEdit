"""Shot-by-shot visual planning with editorial purpose and protected regions (VE-07 / V07).

Requires every output interval to have an explicit editorial reason, focal subject, allowed
crop/layout strategy, protected visual regions (faces, demonstrations, graphics/charts, captions),
and verifiable supporting source evidence IDs before video encoding starts.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from hawedit.transcripts import validate_media_id

__all__ = [
    "PlannedShot",
    "ProtectedContentRegion",
    "ProtectedRegionKind",
    "ShotEditorialPurpose",
    "ShotLayoutStrategy",
    "ShotPlanError",
    "ShotVisualPlan",
    "build_shot_plan",
]


class ShotPlanError(ValueError):
    """Raised when a planned shot lacks editorial purpose, source evidence, or valid geometry."""


class ShotLayoutStrategy(str, Enum):
    """Allowed framing and layout strategy for an output shot interval."""

    KEEP_SOURCE = "keep_source"
    CROP = "crop"
    HOLD = "hold"
    FOLLOW = "follow"
    TWO_PERSON_LAYOUT = "two_person_layout"
    NEEDS_REVIEW = "needs_review"


class ProtectedRegionKind(str, Enum):
    """Categorization of essential visual content that must not be cropped out or covered."""

    SPEAKER_FACE = "speaker_face"
    LISTENER_FACE = "listener_face"
    DEMONSTRATION = "demonstration"
    GRAPHIC_OR_CHART = "graphic_or_chart"
    LOWER_THIRD_CAPTIONS = "lower_third_captions"
    SOURCE_ON_SCREEN_TEXT = "source_on_screen_text"


@dataclass(frozen=True, slots=True)
class ProtectedContentRegion:
    """Normalized bounding box ([0.0..1.0]) that must be protected in output framing."""

    region_id: str
    kind: ProtectedRegionKind
    box: tuple[float, float, float, float]
    importance: float = 1.0
    description: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.region_id, str) or not self.region_id.strip():
            raise ValueError("region_id must be a non-empty string")
        if not isinstance(self.kind, ProtectedRegionKind):
            raise TypeError(f"kind must be a ProtectedRegionKind, got {type(self.kind).__name__}")
        if len(self.box) != 4:
            raise ValueError("box must have exactly 4 normalized coordinates (x0, y0, x1, y1)")
        x0, y0, x1, y1 = self.box
        for val in (x0, y0, x1, y1):
            if type(val) not in (int, float) or not math.isfinite(val):
                raise TypeError("box coordinates must be finite floats")
            if not 0.0 <= float(val) <= 1.0:
                raise ValueError(f"box coordinate must be in [0.0, 1.0], got {val}")
        if x1 <= x0 or y1 <= y0:
            raise ValueError(f"box must have positive width and height: {self.box}")
        if type(self.importance) not in (int, float) or not math.isfinite(self.importance):
            raise TypeError("importance must be a finite float")
        if not 0.0 <= float(self.importance) <= 1.0:
            raise ValueError(f"importance must be in [0.0, 1.0], got {self.importance}")

    @property
    def width(self) -> float:
        return self.box[2] - self.box[0]

    @property
    def height(self) -> float:
        return self.box[3] - self.box[1]

    def to_dict(self) -> dict[str, Any]:
        return {
            "region_id": self.region_id,
            "kind": self.kind.value,
            "box": [round(float(c), 4) for c in self.box],
            "importance": round(float(self.importance), 4),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProtectedContentRegion:
        raw_box = data["box"]
        return cls(
            region_id=str(data["region_id"]),
            kind=ProtectedRegionKind(str(data["kind"])),
            box=(float(raw_box[0]), float(raw_box[1]), float(raw_box[2]), float(raw_box[3])),
            importance=float(data.get("importance", 1.0)),
            description=str(data.get("description", "")),
        )


@dataclass(frozen=True, slots=True)
class ShotEditorialPurpose:
    """Explicit communicative motivation and focal subject for an output shot."""

    reason: str
    focal_subject: str
    priority_over_face: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ShotPlanError("shot requires an explicit, non-empty editorial reason")
        if not isinstance(self.focal_subject, str) or not self.focal_subject.strip():
            raise ShotPlanError("shot requires an explicit, non-empty focal subject")
        if not isinstance(self.priority_over_face, bool):
            raise TypeError("priority_over_face must be a boolean")

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason": self.reason,
            "focal_subject": self.focal_subject,
            "priority_over_face": self.priority_over_face,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ShotEditorialPurpose:
        return cls(
            reason=str(data["reason"]),
            focal_subject=str(data["focal_subject"]),
            priority_over_face=bool(data.get("priority_over_face", False)),
        )


@dataclass(frozen=True, slots=True)
class PlannedShot:
    """A single planned visual shot with verified editorial intent and constraints."""

    shot_id: str
    source_in_ms: int
    source_out_ms: int
    output_in_ms: int
    output_out_ms: int
    editorial_purpose: ShotEditorialPurpose
    layout_strategy: ShotLayoutStrategy
    supporting_evidence_ids: tuple[str, ...]
    protected_regions: tuple[ProtectedContentRegion, ...] = ()
    caption_safe_box: tuple[float, float, float, float] = (0.05, 0.70, 0.95, 0.92)
    transition_in: str = "cut"

    def __post_init__(self) -> None:
        if not isinstance(self.shot_id, str) or not self.shot_id.strip():
            raise ValueError("shot_id must be a non-empty string")
        if type(self.source_in_ms) is not int or type(self.source_out_ms) is not int:
            raise TypeError("source timestamps must be exact integers")
        if type(self.output_in_ms) is not int or type(self.output_out_ms) is not int:
            raise TypeError("output timestamps must be exact integers")
        if self.source_in_ms < 0 or self.output_in_ms < 0:
            raise ValueError("timestamps must be non-negative")
        if self.source_out_ms <= self.source_in_ms:
            raise ValueError(
                f"source_out_ms ({self.source_out_ms}) must be > source_in_ms ({self.source_in_ms})"
            )
        if self.output_out_ms <= self.output_in_ms:
            raise ValueError(
                f"output_out_ms ({self.output_out_ms}) must be > output_in_ms ({self.output_in_ms})"
            )
        source_dur = self.source_out_ms - self.source_in_ms
        output_dur = self.output_out_ms - self.output_in_ms
        if source_dur != output_dur:
            raise ShotPlanError(
                f"source duration ({source_dur}ms) does not match output duration ({output_dur}ms)"
            )
        if not isinstance(self.editorial_purpose, ShotEditorialPurpose):
            raise TypeError("editorial_purpose must be a ShotEditorialPurpose")
        if not isinstance(self.layout_strategy, ShotLayoutStrategy):
            cls_name = type(self.layout_strategy).__name__
            raise TypeError(f"layout_strategy must be a ShotLayoutStrategy, got {cls_name}")
        if not self.supporting_evidence_ids:
            raise ShotPlanError("planned shot requires at least one supporting source evidence ID")
        for eid in self.supporting_evidence_ids:
            if not isinstance(eid, str) or not eid.strip():
                raise ShotPlanError(f"invalid supporting evidence ID: {eid!r}")
        if not self.transition_in.strip():
            raise ShotPlanError("transition_in cannot be empty")

    @property
    def duration_ms(self) -> int:
        return self.output_out_ms - self.output_in_ms

    def has_protected_kind(self, kind: ProtectedRegionKind) -> bool:
        """Return whether this shot contains any protected region of the given kind."""
        return any(r.kind == kind for r in self.protected_regions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "source_in_ms": self.source_in_ms,
            "source_out_ms": self.source_out_ms,
            "output_in_ms": self.output_in_ms,
            "output_out_ms": self.output_out_ms,
            "duration_ms": self.duration_ms,
            "editorial_purpose": self.editorial_purpose.to_dict(),
            "layout_strategy": self.layout_strategy.value,
            "supporting_evidence_ids": list(self.supporting_evidence_ids),
            "protected_regions": [r.to_dict() for r in self.protected_regions],
            "caption_safe_box": [round(float(c), 4) for c in self.caption_safe_box],
            "transition_in": self.transition_in,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlannedShot:
        cap_box = data.get("caption_safe_box", (0.05, 0.70, 0.95, 0.92))
        return cls(
            shot_id=str(data["shot_id"]),
            source_in_ms=int(data["source_in_ms"]),
            source_out_ms=int(data["source_out_ms"]),
            output_in_ms=int(data["output_in_ms"]),
            output_out_ms=int(data["output_out_ms"]),
            editorial_purpose=ShotEditorialPurpose.from_dict(data["editorial_purpose"]),
            layout_strategy=ShotLayoutStrategy(str(data["layout_strategy"])),
            supporting_evidence_ids=tuple(str(e) for e in data["supporting_evidence_ids"]),
            protected_regions=tuple(
                ProtectedContentRegion.from_dict(r) for r in data.get("protected_regions", ())
            ),
            caption_safe_box=(
                float(cap_box[0]),
                float(cap_box[1]),
                float(cap_box[2]),
                float(cap_box[3]),
            ),
            transition_in=str(data.get("transition_in", "cut")),
        )


@dataclass(frozen=True, slots=True)
class ShotVisualPlan:
    """Full shot sequence visual edit plan governing video composition before encoding."""

    clip_id: str
    media_id: str
    shots: tuple[PlannedShot, ...]

    def __post_init__(self) -> None:
        validate_media_id(self.media_id)
        if not isinstance(self.clip_id, str) or not self.clip_id.strip():
            raise ValueError("clip_id must be a non-empty string")
        if not self.shots:
            raise ShotPlanError("shot visual plan requires at least one shot")

        # Enforce strict contiguous output timeline
        expected_output_ms = 0
        for idx, shot in enumerate(self.shots):
            if shot.output_in_ms != expected_output_ms:
                raise ShotPlanError(
                    f"shot {idx} ({shot.shot_id!r}) output_in_ms ({shot.output_in_ms}) does not "
                    f"match expected contiguous timeline boundary ({expected_output_ms})"
                )
            expected_output_ms = shot.output_out_ms

    @property
    def total_duration_ms(self) -> int:
        return self.shots[-1].output_out_ms if self.shots else 0

    @property
    def shot_count(self) -> int:
        return len(self.shots)

    def shot_at_output_ms(self, output_ms: int) -> PlannedShot | None:
        """Find the planned shot covering the given output timestamp."""
        for shot in self.shots:
            if shot.output_in_ms <= output_ms < shot.output_out_ms:
                return shot
        return None

    def assert_valid(self) -> None:
        """Validate entire shot plan against visual editorial constraints."""
        for shot in self.shots:
            # If shot prioritizes demonstration/chart over face, verify appropriate layout
            if shot.editorial_purpose.priority_over_face:
                has_content = shot.has_protected_kind(
                    ProtectedRegionKind.DEMONSTRATION
                ) or shot.has_protected_kind(ProtectedRegionKind.GRAPHIC_OR_CHART)
                if not has_content:
                    raise ShotPlanError(
                        f"shot {shot.shot_id!r} claims priority_over_face but contains no "
                        f"demonstration or graphic_or_chart protected region"
                    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "clip_id": self.clip_id,
            "media_id": self.media_id,
            "total_duration_ms": self.total_duration_ms,
            "shot_count": self.shot_count,
            "shots": [s.to_dict() for s in self.shots],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ShotVisualPlan:
        return cls(
            clip_id=str(data["clip_id"]),
            media_id=str(data["media_id"]),
            shots=tuple(PlannedShot.from_dict(s) for s in data.get("shots", ())),
        )


def build_shot_plan(
    clip_id: str,
    media_id: str,
    shots: Sequence[PlannedShot],
) -> ShotVisualPlan:
    """Construct and validate a full shot visual edit plan."""
    plan = ShotVisualPlan(clip_id=clip_id, media_id=media_id, shots=tuple(shots))
    plan.assert_valid()
    return plan
