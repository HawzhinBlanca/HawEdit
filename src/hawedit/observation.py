"""Episode-level visual observation inventory (VE-02 / V02).

Inventories what HawEdit actually observed across all source intervals of an episode.
Distinguishes between unknown, scanned, sampled, and model-inspected evidence,
and ensures static verbal moments (e.g. static interview shots with speech) are
never discarded or suppressed for low visual novelty (D-271).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from itertools import pairwise
from typing import Any, Final

from hawedit.transcripts import validate_media_id

__all__ = [
    "ObservationBudget",
    "ObservationError",
    "ObservationInterval",
    "ObservationInventory",
    "ObservationLevel",
    "TargetedEventCandidate",
    "TargetedObservationPlan",
    "VisualEventKind",
    "apply_targeted_observation",
    "build_observation_inventory",
    "plan_targeted_observation",
]

_SHA256_HEX_CHARS: Final = frozenset("0123456789abcdef")


class ObservationError(RuntimeError):
    """Raised when observation evidence is invalid or invariants are violated."""


class ObservationLevel(str, Enum):
    """Degree of visual inspection for a source interval."""

    UNKNOWN = "unknown"
    SCANNED = "scanned"
    SAMPLED = "sampled"
    MODEL_INSPECTED = "model_inspected"


@dataclass(frozen=True, slots=True)
class ObservationInterval:
    """One discrete source interval and its observation coverage."""

    in_ms: int
    out_ms: int
    level: ObservationLevel
    has_speech: bool = False
    motion_score: float | None = None
    source_frame_indices: tuple[int, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        if type(self.in_ms) is not int or type(self.out_ms) is not int:
            raise TypeError("interval timestamps must be exact integers")
        if self.in_ms < 0:
            raise ValueError(f"interval in_ms must be >= 0, got {self.in_ms}")
        if self.out_ms <= self.in_ms:
            raise ValueError(f"interval out_ms ({self.out_ms}) must be > in_ms ({self.in_ms})")
        if not isinstance(self.level, ObservationLevel):
            raise TypeError(f"level must be an ObservationLevel, got {type(self.level)}")
        if self.motion_score is not None:
            if not isinstance(self.motion_score, int | float):
                raise TypeError("motion_score must be a float or None")
            if not 0.0 <= float(self.motion_score) <= 1.0:
                raise ValueError(f"motion_score must be in 0.0..1.0, got {self.motion_score}")

    @property
    def duration_ms(self) -> int:
        return self.out_ms - self.in_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "in_ms": self.in_ms,
            "out_ms": self.out_ms,
            "duration_ms": self.duration_ms,
            "level": self.level.value,
            "has_speech": self.has_speech,
            "motion_score": (
                round(float(self.motion_score), 4) if self.motion_score is not None else None
            ),
            "source_frame_indices": list(self.source_frame_indices),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ObservationInterval:
        return cls(
            in_ms=int(data["in_ms"]),
            out_ms=int(data["out_ms"]),
            level=ObservationLevel(str(data["level"])),
            has_speech=bool(data.get("has_speech", False)),
            motion_score=(
                float(data["motion_score"]) if data.get("motion_score") is not None else None
            ),
            source_frame_indices=tuple(int(x) for x in data.get("source_frame_indices", ())),
            notes=str(data.get("notes", "")),
        )


@dataclass(frozen=True, slots=True)
class ObservationInventory:
    """Complete, verified inventory of visual observation coverage for an episode."""

    media_id: str
    source_sha256: str
    duration_ms: int
    intervals: tuple[ObservationInterval, ...]

    def __post_init__(self) -> None:
        validate_media_id(self.media_id)
        if (
            not isinstance(self.source_sha256, str)
            or len(self.source_sha256) != 64
            or any(c not in _SHA256_HEX_CHARS for c in self.source_sha256)
        ):
            raise ValueError(
                "source_sha256 must be exactly 64 lowercase hexadecimal characters, got "
                f"{self.source_sha256!r}"
            )
        if type(self.duration_ms) is not int or self.duration_ms <= 0:
            raise ValueError(f"duration_ms must be a positive integer, got {self.duration_ms}")
        if not self.intervals:
            raise ObservationError(f"observation inventory for {self.media_id!r} has no intervals")

        # Invariant: intervals must partition [0, duration_ms) exactly without gaps or overlaps
        if self.intervals[0].in_ms != 0:
            raise ObservationError(
                f"observation inventory starts at {self.intervals[0].in_ms} ms, must start at 0 ms"
            )
        for prev, nxt in pairwise(self.intervals):
            if nxt.in_ms > prev.out_ms:
                raise ObservationError(
                    f"unrepresented gap of {nxt.in_ms - prev.out_ms} ms between "
                    f"{prev.in_ms}..{prev.out_ms} and {nxt.in_ms}..{nxt.out_ms}"
                )
            if nxt.in_ms < prev.out_ms:
                raise ObservationError(
                    f"overlapping intervals: {prev.in_ms}..{prev.out_ms} and "
                    f"{nxt.in_ms}..{nxt.out_ms}"
                )
        if self.intervals[-1].out_ms != self.duration_ms:
            raise ObservationError(
                f"observation inventory ends at {self.intervals[-1].out_ms} ms, "
                f"must end at {self.duration_ms} ms"
            )

    def unseen_intervals(self) -> tuple[tuple[int, int], ...]:
        """Contiguous source intervals where no visual evidence was gathered."""
        unseen: list[tuple[int, int]] = []
        for interval in self.intervals:
            if interval.level == ObservationLevel.UNKNOWN:
                if unseen and unseen[-1][1] == interval.in_ms:
                    unseen[-1] = (unseen[-1][0], interval.out_ms)
                else:
                    unseen.append((interval.in_ms, interval.out_ms))
        return tuple(unseen)

    def static_speech_intervals(
        self,
        min_duration_ms: int = 2000,
        max_motion: float = 0.05,
    ) -> tuple[ObservationInterval, ...]:
        """Speaking intervals with minimal visual motion (e.g. talking head, static interview)."""
        return tuple(
            interval
            for interval in self.intervals
            if interval.has_speech
            and interval.duration_ms >= min_duration_ms
            and interval.motion_score is not None
            and interval.motion_score <= max_motion
        )

    def assert_static_speech_preserved(
        self,
        candidate_spans: Sequence[tuple[int, int]],
        min_duration_ms: int = 2000,
        max_motion: float = 0.05,
    ) -> None:
        """Enforces that static speech moments are not silently suppressed in discovery."""
        static_intervals = self.static_speech_intervals(
            min_duration_ms=min_duration_ms, max_motion=max_motion
        )
        if not static_intervals:
            return
        for s in static_intervals:
            # Check if this static speech moment overlaps at least one candidate span
            covered = any(
                max(s.in_ms, c_in) < min(s.out_ms, c_out) for c_in, c_out in candidate_spans
            )
            if not covered:
                # If candidate discovery produced candidates but none covers substantive
                # static speech, raise to prevent silent suppression
                raise ObservationError(
                    f"static speech interval {s.in_ms}..{s.out_ms} ms ({s.duration_ms} ms) "
                    "was dropped from candidate discovery despite active speech"
                )

    def coverage_summary(self) -> dict[str, Any]:
        """Aggregate breakdown of observation coverage across the media duration."""
        totals: dict[str, int] = {lvl.value: 0 for lvl in ObservationLevel}
        speech_ms = 0
        static_speech_ms = 0

        for interval in self.intervals:
            totals[interval.level.value] += interval.duration_ms
            if interval.has_speech:
                speech_ms += interval.duration_ms
                if interval.motion_score is not None and interval.motion_score <= 0.05:
                    static_speech_ms += interval.duration_ms

        return {
            "media_id": self.media_id,
            "duration_ms": self.duration_ms,
            "speech_ms": speech_ms,
            "static_speech_ms": static_speech_ms,
            "by_level_ms": totals,
            "by_level_share": {k: round(v / self.duration_ms, 4) for k, v in totals.items()},
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "media_id": self.media_id,
            "source_sha256": self.source_sha256,
            "duration_ms": self.duration_ms,
            "coverage_summary": self.coverage_summary(),
            "intervals": [i.to_dict() for i in self.intervals],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ObservationInventory:
        return cls(
            media_id=str(data["media_id"]),
            source_sha256=str(data["source_sha256"]),
            duration_ms=int(data["duration_ms"]),
            intervals=tuple(ObservationInterval.from_dict(i) for i in data["intervals"]),
        )

    @classmethod
    def from_json(cls, text: str) -> ObservationInventory:
        return cls.from_dict(json.loads(text))


def build_observation_inventory(
    media_id: str,
    source_sha256: str,
    duration_ms: int,
    *,
    shot_cuts_ms: Sequence[int] = (),
    scanned_range_ms: tuple[int, int] | None = None,
    speech_intervals: Sequence[tuple[int, int]] = (),
    sampled_frame_times_ms: Sequence[int] = (),
    model_inspected_intervals: Sequence[tuple[int, int]] = (),
    motion_scores_by_shot: Sequence[float] | None = None,
) -> ObservationInventory:
    """Constructs an exact observation inventory partitioning [0, duration_ms).

    Args:
        media_id: Validated media identifier.
        source_sha256: 64-character SHA-256 of source file.
        duration_ms: Total media duration in milliseconds.
        shot_cuts_ms: Internal scene cuts (excluding 0 and duration_ms).
        scanned_range_ms: Range of media scanned by proxy/shot detector
            (defaults to [0, duration_ms]).
        speech_intervals: Active VAD speech intervals (start_ms, end_ms).
        sampled_frame_times_ms: Timestamps where discrete frames were extracted/sampled.
        model_inspected_intervals: Intervals that underwent deep model inspection
            (e.g. Qwen, VideoChat3, Gemini).
        motion_scores_by_shot: Optional motion score per shot.
    """
    if duration_ms <= 0:
        raise ValueError(f"duration_ms must be positive, got {duration_ms}")

    # Default scanned range to the whole duration if not specified
    scan_start, scan_end = scanned_range_ms if scanned_range_ms is not None else (0, duration_ms)
    scan_start = max(0, scan_start)
    scan_end = min(duration_ms, scan_end)

    # Gather all boundary points
    boundaries = {0, duration_ms, scan_start, scan_end}
    for cut in shot_cuts_ms:
        if 0 < cut < duration_ms:
            boundaries.add(cut)
    for s_in, s_out in speech_intervals:
        boundaries.add(max(0, min(duration_ms, s_in)))
        boundaries.add(max(0, min(duration_ms, s_out)))
    for m_in, m_out in model_inspected_intervals:
        boundaries.add(max(0, min(duration_ms, m_in)))
        boundaries.add(max(0, min(duration_ms, m_out)))

    # Frame sampling boundaries (each sampled frame marks a discrete inspected window)
    sorted_frames = sorted(f for f in sampled_frame_times_ms if 0 <= f < duration_ms)

    sorted_boundaries = sorted(boundaries)
    raw_intervals: list[ObservationInterval] = []

    # Map shots to motion scores
    all_cuts = [0, *sorted(c for c in shot_cuts_ms if 0 < c < duration_ms), duration_ms]
    shot_spans = list(pairwise(all_cuts))
    shot_motion: dict[int, float | None] = {}
    if motion_scores_by_shot is not None:
        for idx, score in enumerate(motion_scores_by_shot):
            if idx < len(shot_spans):
                shot_motion[idx] = float(score)

    for b_in, b_out in pairwise(sorted_boundaries):
        if b_out <= b_in:
            continue

        # Check speech presence
        has_speech = any(max(b_in, s_in) < min(b_out, s_out) for s_in, s_out in speech_intervals)

        # Check motion score for this interval
        motion_score: float | None = None
        for shot_idx, (s_in, s_out) in enumerate(shot_spans):
            if max(b_in, s_in) < min(b_out, s_out):
                motion_score = shot_motion.get(shot_idx)
                break

        # Frames within this slice
        frames_in_slice = tuple(f for f in sorted_frames if b_in <= f < b_out)

        # Determine observation level
        is_model_inspected = any(
            max(b_in, m_in) < min(b_out, m_out) for m_in, m_out in model_inspected_intervals
        )
        if is_model_inspected:
            level = ObservationLevel.MODEL_INSPECTED
            notes = "deep multimodal model inspection"
        elif len(frames_in_slice) > 0:
            level = ObservationLevel.SAMPLED
            notes = f"discrete frame sampling ({len(frames_in_slice)} frames)"
        elif scan_start <= b_in and b_out <= scan_end:
            level = ObservationLevel.SCANNED
            notes = "coarse proxy/shot boundary scan"
        else:
            level = ObservationLevel.UNKNOWN
            notes = "unobserved source interval"

        raw_intervals.append(
            ObservationInterval(
                in_ms=b_in,
                out_ms=b_out,
                level=level,
                has_speech=has_speech,
                motion_score=motion_score,
                source_frame_indices=frames_in_slice,
                notes=notes,
            )
        )

    # Compact adjacent intervals with identical properties
    merged: list[ObservationInterval] = []
    for item in raw_intervals:
        if (
            merged
            and merged[-1].out_ms == item.in_ms
            and merged[-1].level == item.level
            and merged[-1].has_speech == item.has_speech
            and merged[-1].motion_score == item.motion_score
            and merged[-1].notes == item.notes
        ):
            merged[-1] = ObservationInterval(
                in_ms=merged[-1].in_ms,
                out_ms=item.out_ms,
                level=item.level,
                has_speech=item.has_speech,
                motion_score=item.motion_score,
                source_frame_indices=merged[-1].source_frame_indices + item.source_frame_indices,
                notes=item.notes,
            )
        else:
            merged.append(item)

    return ObservationInventory(
        media_id=media_id,
        source_sha256=source_sha256,
        duration_ms=duration_ms,
        intervals=tuple(merged),
    )


class VisualEventKind(str, Enum):
    """Types of visual events that can trigger targeted closer observation."""

    SHOT_CUT = "shot_cut"
    SPEAKER_TRANSITION = "speaker_transition"
    BRIEF_REACTION = "brief_reaction"
    OBJECT_DEMONSTRATION = "object_demonstration"
    SCREEN_CHANGE = "screen_change"
    UNCERTAIN_COMPOSITION = "uncertain_composition"


@dataclass(frozen=True, slots=True)
class ObservationBudget:
    """Strict resource envelope for additional targeted visual observation."""

    max_additional_frames: int = 10
    max_frames_per_event: int = 4
    min_frame_interval_ms: int = 100

    def __post_init__(self) -> None:
        if type(self.max_additional_frames) is not int or self.max_additional_frames <= 0:
            raise ValueError(
                "max_additional_frames must be a positive integer, got "
                f"{self.max_additional_frames}"
            )
        if type(self.max_frames_per_event) is not int or self.max_frames_per_event <= 0:
            raise ValueError(
                f"max_frames_per_event must be a positive integer, got {self.max_frames_per_event}"
            )
        if self.max_frames_per_event > self.max_additional_frames:
            raise ValueError(
                f"max_frames_per_event ({self.max_frames_per_event}) cannot exceed "
                f"max_additional_frames ({self.max_additional_frames})"
            )
        if type(self.min_frame_interval_ms) is not int or self.min_frame_interval_ms <= 0:
            raise ValueError(
                "min_frame_interval_ms must be a positive integer, got "
                f"{self.min_frame_interval_ms}"
            )


@dataclass(frozen=True, slots=True)
class TargetedEventCandidate:
    """Candidate visual event that may require denser targeted observation."""

    event_id: str
    kind: VisualEventKind
    in_ms: int
    out_ms: int
    priority: float = 0.5
    description: str = ""

    def __post_init__(self) -> None:
        if not self.event_id or not isinstance(self.event_id, str):
            raise ValueError("event_id must be a non-empty string")
        if not isinstance(self.kind, VisualEventKind):
            raise TypeError(f"kind must be a VisualEventKind, got {type(self.kind)}")
        if type(self.in_ms) is not int or type(self.out_ms) is not int:
            raise TypeError("event timestamps must be exact integers")
        if self.in_ms < 0:
            raise ValueError(f"event in_ms must be >= 0, got {self.in_ms}")
        if self.out_ms <= self.in_ms:
            raise ValueError(f"event out_ms ({self.out_ms}) must be > in_ms ({self.in_ms})")
        if not 0.0 <= float(self.priority) <= 1.0:
            raise ValueError(f"priority must be in 0.0..1.0, got {self.priority}")

    @property
    def duration_ms(self) -> int:
        return self.out_ms - self.in_ms


@dataclass(frozen=True, slots=True)
class TargetedObservationPlan:
    """Bounded plan for denser observation of uncertain visual events."""

    targeted_frames: tuple[int, ...]
    scheduled_events: tuple[TargetedEventCandidate, ...]
    unobserved_events: tuple[tuple[TargetedEventCandidate, str], ...]
    total_budget_frames: int
    allocated_frames: int

    def __post_init__(self) -> None:
        if self.allocated_frames > self.total_budget_frames:
            raise ObservationError(
                f"allocated_frames ({self.allocated_frames}) exceeds "
                f"total_budget_frames ({self.total_budget_frames})"
            )
        if len(self.targeted_frames) != self.allocated_frames:
            raise ObservationError(
                f"targeted_frames count ({len(self.targeted_frames)}) does not match "
                f"allocated_frames ({self.allocated_frames})"
            )

    def is_covered(self, event: TargetedEventCandidate) -> bool:
        """Returns True if at least one targeted frame falls within the event span."""
        return any(event.in_ms <= f <= event.out_ms for f in self.targeted_frames)


def plan_targeted_observation(
    inventory: ObservationInventory,
    events: Sequence[TargetedEventCandidate],
    budget: ObservationBudget,
) -> TargetedObservationPlan:
    """Plans denser frame extraction around brief or uncertain visual events.

    Events that fall between coarse samples are allocated extra frames within the
    configured budget. If the budget is exhausted, remaining events are explicitly
    marked unobserved with reason 'budget_exhausted' rather than quietly dropped
    or exceeding the budget.
    """
    existing_sampled_frames: set[int] = set()
    for interval in inventory.intervals:
        existing_sampled_frames.update(interval.source_frame_indices)

    sorted_events = sorted(events, key=lambda e: (-e.priority, e.in_ms, e.out_ms))

    targeted_frames_list: list[int] = []
    scheduled_events_list: list[TargetedEventCandidate] = []
    unobserved_events_list: list[tuple[TargetedEventCandidate, str]] = []

    remaining_budget = budget.max_additional_frames

    for event in sorted_events:
        already_covered = any(event.in_ms <= f <= event.out_ms for f in existing_sampled_frames)
        if already_covered:
            scheduled_events_list.append(event)
            continue

        if remaining_budget <= 0:
            unobserved_events_list.append((event, "budget_exhausted"))
            continue

        duration_ms = event.duration_ms
        desired_frames = min(
            budget.max_frames_per_event,
            max(1, duration_ms // budget.min_frame_interval_ms),
            remaining_budget,
        )

        if desired_frames <= 0:
            unobserved_events_list.append((event, "budget_exhausted"))
            continue

        if desired_frames == 1:
            frame_times = [event.in_ms + duration_ms // 2]
        else:
            step = duration_ms / (desired_frames + 1)
            frame_times = [round(event.in_ms + (i + 1) * step) for i in range(desired_frames)]

        targeted_frames_list.extend(frame_times)
        remaining_budget -= len(frame_times)
        scheduled_events_list.append(event)

    sorted_targeted_frames = tuple(sorted(targeted_frames_list))

    return TargetedObservationPlan(
        targeted_frames=sorted_targeted_frames,
        scheduled_events=tuple(scheduled_events_list),
        unobserved_events=tuple(unobserved_events_list),
        total_budget_frames=budget.max_additional_frames,
        allocated_frames=len(sorted_targeted_frames),
    )


def apply_targeted_observation(
    inventory: ObservationInventory,
    plan: TargetedObservationPlan,
) -> ObservationInventory:
    """Applies a targeted observation plan to an inventory, promoting observed spans to SAMPLED."""
    if not plan.targeted_frames:
        return inventory

    all_sampled: set[int] = set()
    for interval in inventory.intervals:
        all_sampled.update(interval.source_frame_indices)
    all_sampled.update(plan.targeted_frames)

    speech_intervals = [(i.in_ms, i.out_ms) for i in inventory.intervals if i.has_speech]
    model_intervals = [
        (i.in_ms, i.out_ms)
        for i in inventory.intervals
        if i.level == ObservationLevel.MODEL_INSPECTED
    ]

    return build_observation_inventory(
        media_id=inventory.media_id,
        source_sha256=inventory.source_sha256,
        duration_ms=inventory.duration_ms,
        speech_intervals=speech_intervals,
        sampled_frame_times_ms=sorted(all_sampled),
        model_inspected_intervals=model_intervals,
    )
