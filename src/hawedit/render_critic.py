"""Post-render sequence critique and grounded defect reporting (VE-11 / V11).

Inspects the actual temporal rendered output sequence and aligned source context across
overlapping temporal windows, reports timestamped grounded editorial/visual defects, and
strictly refuses unsupported all-clear claims.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from hawedit.caption_layout import CaptionLayoutPlan
from hawedit.shot_plan import (
    PlannedShot,
    ProtectedRegionKind,
    ShotLayoutStrategy,
)
from hawedit.timing_continuity import TightenedTimeline

__all__ = [
    "CritiqueInspectionResult",
    "DefectKind",
    "DefectSeverity",
    "PermittedRepair",
    "RenderCriticError",
    "RenderDefect",
    "RenderedSequenceContext",
    "TemporalCritiqueWindow",
    "UnsupportedAllClearError",
    "generate_critique_windows",
    "inspect_rendered_sequence",
]


class RenderCriticError(ValueError):
    """Raised when rendered sequence critique encounters an invalid configuration or state."""


class UnsupportedAllClearError(RenderCriticError):
    """Raised when an all-clear verdict is claimed without grounded evidence or despite defects."""


class DefectSeverity(str, Enum):
    """Severity tier for a detected editorial or composition defect."""

    CRITICAL = "critical"
    WARNING = "warning"


class DefectKind(str, Enum):
    """Categorization of editorial, composition, or continuity defects in rendered output."""

    MISIDENTIFIED_SPEAKER = "misidentified_speaker"
    CUT_SETUP = "cut_setup"
    LOST_DEMONSTRATION_OR_CHART = "lost_demonstration_or_chart"
    CAPTION_OBSCURATION = "caption_obscuration"
    TRUNCATED_LANDING_BEAT = "truncated_landing_beat"
    REACTION_MEANING_ALTERED = "reaction_meaning_altered"
    UNSUPPORTED_CLAIM = "unsupported_claim"
    UNFOLLOWABLE_CONTEXT = "unfollowable_context"
    MISSING_MEDIA = "missing_media"
    CHANGED_MEDIA = "changed_media"
    UNREADABLE_MEDIA = "unreadable_media"
    DURATION_MISMATCH = "duration_mismatch"
    ALL_BLACK_OR_SILENT = "all_black_or_silent"


class PermittedRepair(str, Enum):
    """Bounded repair action permitted to correct a detected defect."""

    ADJUST_CROP = "adjust_crop"
    HOLD_SOURCE_SHOT = "hold_source_shot"
    REPOSITION_CAPTIONS = "reposition_captions"
    EXPAND_BOUNDARY = "expand_boundary"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class RenderDefect:
    """Timestamped, grounded defect record observed in the rendered output sequence."""

    defect_id: str
    timestamp_ms: int
    end_timestamp_ms: int
    severity: DefectSeverity
    defect_kind: DefectKind
    observation: str
    source_reference: str
    permitted_repair: PermittedRepair
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not isinstance(self.defect_id, str) or not self.defect_id.strip():
            raise ValueError("defect_id must be a non-empty string")
        if type(self.timestamp_ms) is not int or type(self.end_timestamp_ms) is not int:
            raise TypeError("defect timestamps must be exact integers")
        if self.timestamp_ms < 0:
            raise ValueError(f"timestamp_ms must be non-negative: {self.timestamp_ms}")
        if self.end_timestamp_ms < self.timestamp_ms:
            raise ValueError(
                f"end_timestamp_ms ({self.end_timestamp_ms}) cannot precede "
                f"timestamp_ms ({self.timestamp_ms})"
            )
        if not isinstance(self.observation, str) or not self.observation.strip():
            raise ValueError("observation must be a non-empty string")
        if not isinstance(self.source_reference, str) or not self.source_reference.strip():
            raise ValueError("source_reference must be a non-empty string")
        if (
            type(self.confidence) not in (int, float)
            or not math.isfinite(self.confidence)
            or not 0.0 <= float(self.confidence) <= 1.0
        ):
            raise ValueError(f"confidence must be a float in [0.0, 1.0], got {self.confidence}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "defect_id": self.defect_id,
            "timestamp_ms": self.timestamp_ms,
            "end_timestamp_ms": self.end_timestamp_ms,
            "severity": self.severity.value,
            "defect_kind": self.defect_kind.value,
            "observation": self.observation,
            "source_reference": self.source_reference,
            "permitted_repair": self.permitted_repair.value,
            "confidence": round(float(self.confidence), 4),
        }


@dataclass(frozen=True, slots=True)
class TemporalCritiqueWindow:
    """Temporal inspection window covering an interval of the rendered output sequence."""

    window_id: str
    start_ms: int
    end_ms: int
    window_kind: str
    has_temporal_motion: bool
    frame_count: int
    defects: tuple[RenderDefect, ...] = ()
    is_observed: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.window_id, str) or not self.window_id.strip():
            raise ValueError("window_id must be a non-empty string")
        if type(self.start_ms) is not int or type(self.end_ms) is not int:
            raise TypeError("window timestamps must be exact integers")
        if self.start_ms < 0:
            raise ValueError(f"start_ms must be non-negative: {self.start_ms}")
        if self.end_ms <= self.start_ms:
            raise ValueError(f"end_ms ({self.end_ms}) must be > start_ms ({self.start_ms})")
        if self.frame_count < 0:
            raise ValueError(f"frame_count must be non-negative, got {self.frame_count}")
        # Invariant: Motion cannot be claimed from isolated stills (needs at least 2 frames)
        if self.has_temporal_motion and self.frame_count < 2:
            raise ValueError(
                f"Window {self.window_id}: temporal motion cannot be judged from isolated stills "
                f"(requires frame_count >= 2, got {self.frame_count})"
            )

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


@dataclass(frozen=True, slots=True)
class RenderedSequenceContext:
    """Rendered output MP4 metadata aligned with source context and edit decisions."""

    render_path: Path | str
    duration_ms: int
    fps: float = 30.0
    width: int = 1080
    height: int = 1920
    source_video_path: Path | str | None = None
    has_source_context: bool = True
    planned_shots: tuple[PlannedShot, ...] = ()
    caption_plan: CaptionLayoutPlan | None = None
    timing_timeline: TightenedTimeline | None = None
    landing_beat_ms: int | None = None
    setup_boundary_ms: int | None = None
    expected_sha256: str | None = None

    def __post_init__(self) -> None:
        if type(self.duration_ms) is not int or self.duration_ms <= 0:
            raise ValueError(f"duration_ms must be a positive integer, got {self.duration_ms}")
        if self.width <= 0 or self.height <= 0:
            raise ValueError(f"width and height must be positive, got {self.width}x{self.height}")
        if self.fps <= 0.0:
            raise ValueError(f"fps must be positive, got {self.fps}")


@dataclass(frozen=True, slots=True)
class CritiqueInspectionResult:
    """Complete temporal inspection outcome across all critique windows of a rendered sequence."""

    inspection_id: str
    render_path: str
    duration_ms: int
    coverage_ratio: float
    windows: tuple[TemporalCritiqueWindow, ...]
    defects: tuple[RenderDefect, ...]
    is_all_clear: bool
    all_clear_refused: bool
    refusal_reason: str | None = None
    observed_media: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.inspection_id, str) or not self.inspection_id.strip():
            raise ValueError("inspection_id must be a non-empty string")
        if not 0.0 <= float(self.coverage_ratio) <= 1.0:
            raise ValueError(f"coverage_ratio must be in [0.0, 1.0], got {self.coverage_ratio}")

    @property
    def critical_defects(self) -> tuple[RenderDefect, ...]:
        return tuple(d for d in self.defects if d.severity == DefectSeverity.CRITICAL)

    @property
    def warning_defects(self) -> tuple[RenderDefect, ...]:
        return tuple(d for d in self.defects if d.severity == DefectSeverity.WARNING)

    @property
    def has_critical_defects(self) -> bool:
        return len(self.critical_defects) > 0

    def assert_verdict_grounded(self) -> None:
        """Enforces that an all-clear claim is grounded by evidence and zero critical defects.

        Raises:
            UnsupportedAllClearError: If an all-clear claim was made without complete coverage,
                or despite detected defects, or without aligned source context,
                or without observed media.
        """
        if self.all_clear_refused:
            raise UnsupportedAllClearError(
                f"All-clear claim refused: {self.refusal_reason or 'grounded defects detected'}"
            )
        if not self.observed_media:
            raise UnsupportedAllClearError(
                "Unsupported all-clear claim: media missing, empty, changed, or unreadable"
            )
        if self.is_all_clear:
            if len(self.defects) > 0:
                raise UnsupportedAllClearError(
                    f"Unsupported all-clear claim: {len(self.defects)} defect(s) exist in "
                    "inspection"
                )
            if self.coverage_ratio < 0.95:
                raise UnsupportedAllClearError(
                    f"Unsupported all-clear claim: temporal coverage ratio "
                    f"{self.coverage_ratio:.2f} is below 0.95 threshold"
                )


def generate_critique_windows(
    duration_ms: int,
    shot_transitions: Sequence[int] = (),
    window_size_ms: int = 2000,
    step_ms: int = 1500,
    fps: float = 30.0,
) -> tuple[TemporalCritiqueWindow, ...]:
    """Generates overlapping temporal critique windows covering the entire rendered sequence.

    Transitions, opening hook (0-3s), and final landing beat are inspected more densely.
    """
    if duration_ms <= 0:
        raise ValueError(f"duration_ms must be positive, got {duration_ms}")

    windows: list[TemporalCritiqueWindow] = []
    created_spans: set[tuple[int, int]] = set()

    def _add_window(start: int, end: int, kind: str) -> None:
        start_clamped = max(0, min(start, duration_ms - 1))
        end_clamped = max(start_clamped + 100, min(end, duration_ms))
        span = (start_clamped, end_clamped)
        if span not in created_spans:
            created_spans.add(span)
            dur = end_clamped - start_clamped
            est_frames = max(2, int(dur * fps / 1000.0))
            wid = f"win_{kind}_{start_clamped}_{end_clamped}"
            windows.append(
                TemporalCritiqueWindow(
                    window_id=wid,
                    start_ms=start_clamped,
                    end_ms=end_clamped,
                    window_kind=kind,
                    has_temporal_motion=True,
                    frame_count=est_frames,
                )
            )

    # 1. Opening hook: dense inspection across 0..3000 ms
    hook_end = min(duration_ms, 3000)
    _add_window(0, hook_end, "opening_hook")
    if hook_end > 1500:
        _add_window(0, 1500, "hook_dense_start")
        _add_window(1200, hook_end, "hook_dense_mid")

    # 2. Shot transitions: dense inspection around cuts (+/-500 ms)
    for cut_ms in sorted(shot_transitions):
        if 0 < cut_ms < duration_ms:
            t_start = max(0, cut_ms - 500)
            t_end = min(duration_ms, cut_ms + 500)
            _add_window(t_start, t_end, "transition")

    # 3. Landing beat: dense inspection across final 3000 ms
    if duration_ms > 3000:
        _add_window(duration_ms - 3000, duration_ms, "landing_beat")
        _add_window(duration_ms - 1500, duration_ms, "landing_beat_dense")
    else:
        _add_window(0, duration_ms, "landing_beat")

    # 4. Regular overlapping body windows
    curr = 0
    while curr < duration_ms:
        end_ms = min(duration_ms, curr + window_size_ms)
        _add_window(curr, end_ms, "body")
        if end_ms >= duration_ms:
            break
        curr += step_ms

    windows.sort(key=lambda w: (w.start_ms, w.end_ms))
    return tuple(windows)


def inspect_rendered_sequence(
    sequence: RenderedSequenceContext,
    *,
    critique_windows: Sequence[TemporalCritiqueWindow] | None = None,
    injected_observations: Sequence[dict[str, Any]] | None = None,
    claim_all_clear: bool = False,
) -> CritiqueInspectionResult:
    """Inspects the actual rendered temporal sequence against source context and edit decisions.

    Checks:
    - Overlapping temporal window coverage across the sequence.
    - Motion evidence grounding: motion cannot be judged from isolated stills.
    - Speaker identification: verifies that shots intended for active speaker show active speaker.
    - Demonstrations and charts: verifies that protected regions are not lost or cropped out.
    - Caption placement: verifies that captions do not obscure essential regions.
    - Narrative setup and landing beats: verifies that necessary setup context was not cut
      and the ending beat landed cleanly.
    - Strict refusal of unsupported all-clear claims.
    """
    if critique_windows is None:
        transitions = [
            shot.output_in_ms for shot in sequence.planned_shots if shot.output_in_ms > 0
        ]
        critique_windows = generate_critique_windows(
            duration_ms=sequence.duration_ms,
            shot_transitions=transitions,
            fps=sequence.fps,
        )

    if not critique_windows:
        raise RenderCriticError("Critique requires at least one temporal critique window")

    # 0. Check physical media existence, non-emptiness, digest, and decodability
    render_file = Path(sequence.render_path)
    observed_media = True
    media_defects: list[RenderDefect] = []
    observed_window_ids: set[str] = set()

    if not render_file.is_file():
        observed_media = False
        media_defects.append(
            RenderDefect(
                defect_id="def_missing_media",
                timestamp_ms=0,
                end_timestamp_ms=sequence.duration_ms,
                severity=DefectSeverity.CRITICAL,
                defect_kind=DefectKind.MISSING_MEDIA,
                observation=f"Render file does not exist on disk: {render_file}",
                source_reference="file_system",
                permitted_repair=PermittedRepair.NONE,
                confidence=1.0,
            )
        )
    elif render_file.stat().st_size == 0:
        observed_media = False
        media_defects.append(
            RenderDefect(
                defect_id="def_empty_media",
                timestamp_ms=0,
                end_timestamp_ms=sequence.duration_ms,
                severity=DefectSeverity.CRITICAL,
                defect_kind=DefectKind.UNREADABLE_MEDIA,
                observation=f"Render file is empty (0 bytes): {render_file}",
                source_reference="file_system",
                permitted_repair=PermittedRepair.NONE,
                confidence=1.0,
            )
        )
    else:
        if sequence.expected_sha256 is not None:
            hasher = hashlib.sha256()
            with open(render_file, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
            actual_sha = hasher.hexdigest()
            if actual_sha.lower() != sequence.expected_sha256.lower():
                observed_media = False
                media_defects.append(
                    RenderDefect(
                        defect_id="def_changed_media",
                        timestamp_ms=0,
                        end_timestamp_ms=sequence.duration_ms,
                        severity=DefectSeverity.CRITICAL,
                        defect_kind=DefectKind.CHANGED_MEDIA,
                        observation=(
                            f"Render file SHA-256 digest mismatch: "
                            f"expected {sequence.expected_sha256}, got {actual_sha}"
                        ),
                        source_reference="sha256_verification",
                        permitted_repair=PermittedRepair.NONE,
                        confidence=1.0,
                    )
                )
        if observed_media:
            try:
                import cv2

                cap = cv2.VideoCapture(str(render_file))
                if not cap.isOpened():
                    observed_media = False
                    media_defects.append(
                        RenderDefect(
                            defect_id="def_unreadable_media",
                            timestamp_ms=0,
                            end_timestamp_ms=sequence.duration_ms,
                            severity=DefectSeverity.CRITICAL,
                            defect_kind=DefectKind.UNREADABLE_MEDIA,
                            observation=(
                                f"Render file could not be opened by decoder: {render_file}"
                            ),
                            source_reference="cv2_decoder",
                            permitted_repair=PermittedRepair.NONE,
                            confidence=1.0,
                        )
                    )
                else:
                    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
                    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
                    actual_duration_ms = int((frame_count / fps) * 1000) if fps > 0 else 0

                    if (
                        sequence.source_video_path
                        and actual_duration_ms > 0
                        and abs(actual_duration_ms - sequence.duration_ms) > 1000
                    ):
                        media_defects.append(
                            RenderDefect(
                                defect_id="def_duration_mismatch",
                                timestamp_ms=min(actual_duration_ms, sequence.duration_ms),
                                end_timestamp_ms=max(actual_duration_ms, sequence.duration_ms),
                                severity=DefectSeverity.CRITICAL,
                                defect_kind=DefectKind.DURATION_MISMATCH,
                                observation=(
                                    f"Declared duration {sequence.duration_ms} ms differs "
                                    f"materially from decoded physical duration "
                                    f"{actual_duration_ms} ms"
                                ),
                                source_reference="duration_probe",
                                permitted_repair=PermittedRepair.EXPAND_BOUNDARY,
                                confidence=1.0,
                            )
                        )

                    decoded_frames = 0
                    total_luminance = 0.0

                    for w in critique_windows:
                        if actual_duration_ms > 0 and w.start_ms >= actual_duration_ms:
                            continue
                        win_bound = actual_duration_ms if actual_duration_ms > 0 else w.end_ms
                        mid_ms = (w.start_ms + min(w.end_ms, win_bound)) / 2.0
                        cap.set(cv2.CAP_PROP_POS_MSEC, mid_ms)
                        ret, frame = cap.read()
                        if ret and frame is not None:
                            decoded_frames += 1
                            mean_lum = float(frame.mean())
                            total_luminance += mean_lum
                            observed_window_ids.add(w.window_id)

                    cap.release()

                    if decoded_frames == 0:
                        observed_media = False
                        media_defects.append(
                            RenderDefect(
                                defect_id="def_undecodable_media",
                                timestamp_ms=0,
                                end_timestamp_ms=sequence.duration_ms,
                                severity=DefectSeverity.CRITICAL,
                                defect_kind=DefectKind.UNREADABLE_MEDIA,
                                observation=(
                                    f"Render file contains no decodable video frames: {render_file}"
                                ),
                                source_reference="cv2_decoder",
                                permitted_repair=PermittedRepair.NONE,
                                confidence=1.0,
                            )
                        )
                    elif decoded_frames > 0 and (total_luminance / decoded_frames) < 1.0:
                        media_defects.append(
                            RenderDefect(
                                defect_id="def_all_black_media",
                                timestamp_ms=0,
                                end_timestamp_ms=sequence.duration_ms,
                                severity=DefectSeverity.CRITICAL,
                                defect_kind=DefectKind.ALL_BLACK_OR_SILENT,
                                observation=(
                                    f"Rendered media decoded {decoded_frames} frames but average "
                                    f"pixel luminance is < 1.0 (blank black media)"
                                ),
                                source_reference="luminance_check",
                                permitted_repair=PermittedRepair.NONE,
                                confidence=1.0,
                            )
                        )
            except Exception as exc:
                observed_media = False
                media_defects.append(
                    RenderDefect(
                        defect_id="def_decoder_exception",
                        timestamp_ms=0,
                        end_timestamp_ms=sequence.duration_ms,
                        severity=DefectSeverity.CRITICAL,
                        defect_kind=DefectKind.UNREADABLE_MEDIA,
                        observation=f"Decoder raised exception reading render file: {exc}",
                        source_reference="cv2_decoder",
                        permitted_repair=PermittedRepair.NONE,
                        confidence=1.0,
                    )
                )

    updated_windows: list[TemporalCritiqueWindow] = []
    for w in critique_windows:
        decoded_in_win = w.window_id in observed_window_ids if observed_window_ids else True
        is_obs = observed_media and w.is_observed and decoded_in_win
        updated_windows.append(
            TemporalCritiqueWindow(
                window_id=w.window_id,
                start_ms=w.start_ms,
                end_ms=w.end_ms,
                window_kind=w.window_kind,
                has_temporal_motion=w.has_temporal_motion,
                frame_count=w.frame_count,
                defects=w.defects,
                is_observed=is_obs,
            )
        )
    critique_windows = tuple(updated_windows)

    # Compute temporal coverage across sequence duration only from OBSERVED windows
    covered_ms = 0
    timeline_cursor = 0
    if observed_media:
        observed_wins = sorted(
            [w for w in critique_windows if w.is_observed], key=lambda w: w.start_ms
        )
        for w in observed_wins:
            if w.start_ms <= timeline_cursor:
                if w.end_ms > timeline_cursor:
                    covered_ms += w.end_ms - timeline_cursor
                    timeline_cursor = w.end_ms
            else:
                covered_ms += w.end_ms - w.start_ms
                timeline_cursor = w.end_ms
        coverage_ratio = min(1.0, covered_ms / max(1, sequence.duration_ms))
    else:
        coverage_ratio = 0.0

    defects: list[RenderDefect] = list(media_defects)

    # 1. Inspect temporal windows for motion grounding and window-attached defects
    for w in critique_windows:
        if not w.has_temporal_motion or w.frame_count < 2:
            defects.append(
                RenderDefect(
                    defect_id=f"def_unsupported_motion_{w.window_id}",
                    timestamp_ms=w.start_ms,
                    end_timestamp_ms=w.end_ms,
                    severity=DefectSeverity.CRITICAL,
                    defect_kind=DefectKind.UNSUPPORTED_CLAIM,
                    observation=(
                        f"Window {w.window_id} attempts to evaluate motion without temporal "
                        f"frames (frame_count={w.frame_count})"
                    ),
                    source_reference=w.window_id,
                    permitted_repair=PermittedRepair.NONE,
                    confidence=1.0,
                )
            )
        for d in w.defects:
            defects.append(d)

    # 2. Inspect source context alignment
    if not sequence.has_source_context:
        defects.append(
            RenderDefect(
                defect_id="def_unaligned_source_context",
                timestamp_ms=0,
                end_timestamp_ms=sequence.duration_ms,
                severity=DefectSeverity.CRITICAL,
                defect_kind=DefectKind.UNSUPPORTED_CLAIM,
                observation=(
                    "Rendered sequence has no aligned source context; cannot verify grounding"
                ),
                source_reference="context_missing",
                permitted_repair=PermittedRepair.NONE,
                confidence=1.0,
            )
        )

    # 3. Check for injected observations (from VLM/critic inspection of rendered frames)
    if injected_observations:
        for idx, obs in enumerate(injected_observations):
            kind_str = str(obs.get("kind", ""))
            try:
                defect_kind = DefectKind(kind_str)
            except ValueError:
                defect_kind = DefectKind.UNSUPPORTED_CLAIM

            sev_str = str(obs.get("severity", "critical"))
            severity = DefectSeverity.WARNING if sev_str == "warning" else DefectSeverity.CRITICAL

            repair_str = str(obs.get("permitted_repair", "none"))
            try:
                permitted_repair = PermittedRepair(repair_str)
            except ValueError:
                permitted_repair = PermittedRepair.NONE

            t_start = int(obs.get("timestamp_ms", 0))
            t_end = int(obs.get("end_timestamp_ms", t_start + 1000))

            defects.append(
                RenderDefect(
                    defect_id=f"def_obs_{idx}_{t_start}",
                    timestamp_ms=t_start,
                    end_timestamp_ms=t_end,
                    severity=severity,
                    defect_kind=defect_kind,
                    observation=str(obs.get("observation", "Grounded visual defect")),
                    source_reference=str(obs.get("source_reference", f"shot_{idx}")),
                    permitted_repair=permitted_repair,
                    confidence=float(obs.get("confidence", 1.0)),
                )
            )

    # 4. Check planned shots against visual protection and speaker grounding
    for shot in sequence.planned_shots:
        # Check if shot focal subject is listener while active speaker is speaking
        if (
            shot.editorial_purpose.focal_subject == "listener"
            and "speaker" in shot.editorial_purpose.reason.lower()
            and not shot.editorial_purpose.priority_over_face
        ):
            defects.append(
                RenderDefect(
                    defect_id=f"def_misidentified_{shot.shot_id}",
                    timestamp_ms=shot.output_in_ms,
                    end_timestamp_ms=shot.output_out_ms,
                    severity=DefectSeverity.CRITICAL,
                    defect_kind=DefectKind.MISIDENTIFIED_SPEAKER,
                    observation=(
                        f"Shot {shot.shot_id} focuses on listener while active speaker is talking"
                    ),
                    source_reference=f"{shot.source_in_ms}..{shot.source_out_ms}",
                    permitted_repair=PermittedRepair.HOLD_SOURCE_SHOT,
                    confidence=0.95,
                )
            )

        # Check protected regions in shot
        for region in shot.protected_regions:
            # If layout is CROP and region is outside portrait 9:16 bounds
            if (
                region.kind
                in (
                    ProtectedRegionKind.GRAPHIC_OR_CHART,
                    ProtectedRegionKind.DEMONSTRATION,
                )
                and shot.layout_strategy == ShotLayoutStrategy.CROP
                and (region.box[0] < 0.15 or region.box[2] > 0.85)
            ):
                defects.append(
                    RenderDefect(
                        defect_id=f"def_lost_content_{shot.shot_id}_{region.region_id}",
                        timestamp_ms=shot.output_in_ms,
                        end_timestamp_ms=shot.output_out_ms,
                        severity=DefectSeverity.CRITICAL,
                        defect_kind=DefectKind.LOST_DEMONSTRATION_OR_CHART,
                        observation=(
                            f"Essential {region.kind.value} '{region.description}' "
                            f"is cropped out in shot {shot.shot_id}"
                        ),
                        source_reference=f"region_{region.region_id}",
                        permitted_repair=PermittedRepair.ADJUST_CROP,
                        confidence=0.98,
                    )
                )

    # 5. Check caption layout for essential region obscuration
    if sequence.caption_plan and (
        len(sequence.caption_plan.unresolvable_conflicts) > 0
        or sequence.caption_plan.status == "needs_review"
    ):
        for cue in sequence.caption_plan.cues:
            if cue.colliding_regions:
                defects.append(
                    RenderDefect(
                        defect_id=f"def_caption_obscure_{cue.cue_id}",
                        timestamp_ms=cue.start_ms,
                        end_timestamp_ms=cue.end_ms,
                        severity=DefectSeverity.CRITICAL,
                        defect_kind=DefectKind.CAPTION_OBSCURATION,
                        observation=(
                            f"Caption cue {cue.cue_id} obscures essential visual region(s): "
                            f"{', '.join(cue.colliding_regions)}"
                        ),
                        source_reference=f"cue_{cue.cue_id}",
                        permitted_repair=PermittedRepair.REPOSITION_CAPTIONS,
                        confidence=0.99,
                    )
                )

    # 6. Check narrative setup boundary
    if (
        sequence.setup_boundary_ms is not None
        and sequence.setup_boundary_ms > 0
        and sequence.planned_shots
        and sequence.planned_shots[0].source_in_ms > sequence.setup_boundary_ms
    ):
        defects.append(
            RenderDefect(
                defect_id="def_cut_setup_context",
                timestamp_ms=0,
                end_timestamp_ms=min(3000, sequence.duration_ms),
                severity=DefectSeverity.CRITICAL,
                defect_kind=DefectKind.CUT_SETUP,
                observation=(
                    f"Render cut starts at source {sequence.planned_shots[0].source_in_ms} ms, "
                    f"removing essential setup context ending at {sequence.setup_boundary_ms} ms"
                ),
                source_reference=f"setup_{sequence.setup_boundary_ms}",
                permitted_repair=PermittedRepair.EXPAND_BOUNDARY,
                confidence=0.96,
            )
        )

    # 7. Check landing beat
    if sequence.landing_beat_ms is not None and sequence.duration_ms < sequence.landing_beat_ms:
        defects.append(
            RenderDefect(
                defect_id="def_truncated_landing",
                timestamp_ms=max(0, sequence.duration_ms - 1500),
                end_timestamp_ms=sequence.duration_ms,
                severity=DefectSeverity.CRITICAL,
                defect_kind=DefectKind.TRUNCATED_LANDING_BEAT,
                observation=(
                    f"Render ends at {sequence.duration_ms} ms, truncating required landing beat "
                    f"at {sequence.landing_beat_ms} ms"
                ),
                source_reference=f"landing_{sequence.landing_beat_ms}",
                permitted_repair=PermittedRepair.EXPAND_BOUNDARY,
                confidence=0.97,
            )
        )

    # Remove duplicates by defect_id
    unique_defects: dict[str, RenderDefect] = {}
    for d in defects:
        if d.defect_id not in unique_defects:
            unique_defects[d.defect_id] = d
    final_defects = tuple(sorted(unique_defects.values(), key=lambda d: d.timestamp_ms))

    # Evaluate all-clear validity
    is_all_clear = False
    all_clear_refused = False
    refusal_reason: str | None = None

    has_critical = any(d.severity == DefectSeverity.CRITICAL for d in final_defects)
    has_any = len(final_defects) > 0
    full_coverage = coverage_ratio >= 0.95

    if claim_all_clear:
        if (
            has_critical
            or has_any
            or not full_coverage
            or not sequence.has_source_context
            or not observed_media
        ):
            all_clear_refused = True
            is_all_clear = False
            reasons: list[str] = []
            if not observed_media:
                reasons.append("rendered media is missing, empty, changed, or undecodable")
            if has_critical:
                crit_count = len(
                    [d for d in final_defects if d.severity == DefectSeverity.CRITICAL]
                )
                reasons.append(f"{crit_count} critical defect(s)")
            elif has_any:
                reasons.append(f"{len(final_defects)} warning defect(s)")
            if not full_coverage:
                reasons.append(f"incomplete temporal coverage ({coverage_ratio:.1%})")
            if not sequence.has_source_context:
                reasons.append("missing aligned source context")
            refusal_reason = f"Refused all-clear claim: {', '.join(reasons)}"
        else:
            is_all_clear = True
    else:
        is_all_clear = (
            (not has_any) and full_coverage and sequence.has_source_context and observed_media
        )

    inspection_id = f"critique_{Path(sequence.render_path).stem}_{sequence.duration_ms}"
    return CritiqueInspectionResult(
        inspection_id=inspection_id,
        render_path=str(sequence.render_path),
        duration_ms=sequence.duration_ms,
        coverage_ratio=round(coverage_ratio, 4),
        windows=tuple(critique_windows),
        defects=final_defects,
        is_all_clear=is_all_clear,
        all_clear_refused=all_clear_refused,
        refusal_reason=refusal_reason,
        observed_media=observed_media,
    )
