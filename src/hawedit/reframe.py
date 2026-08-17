"""Subject-aware horizontal tracking for vertical reframing."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from hawedit.diarization import Segment, assert_exclusive

__all__ = [
    "FocusPoint",
    "OpenCvFaceTracker",
    "SpeakerAssociationError",
    "SpeakerFocusPoint",
    "SpeakerSubjectTracker",
    "SubjectTracker",
    "choose_face",
    "validate_speaker_focus_points",
]


class SpeakerAssociationError(RuntimeError):
    """Speaker-labelled visual evidence contradicts the measured diarization or clip."""


def _exact_non_negative_int(value: object, field: str) -> None:
    if type(value) is not int:
        raise TypeError(f"{field} must be an exact integer")
    if value < 0:
        raise ValueError(f"{field} must be non-negative")


def _safe_speaker_label(value: object) -> None:
    if not isinstance(value, str):
        raise TypeError("speaker label must be a string")
    if (
        not value
        or value.strip() != value
        or not value.isprintable()
        or value.splitlines() != [value]
    ):
        raise ValueError("speaker label must be non-empty, trimmed, printable, and one line")


@dataclass(frozen=True, slots=True)
class FocusPoint:
    at_ms: int
    center_x: int

    def __post_init__(self) -> None:
        _exact_non_negative_int(self.at_ms, "focus point timestamp")
        _exact_non_negative_int(self.center_x, "focus point horizontal centre")


@dataclass(frozen=True, slots=True)
class SpeakerFocusPoint:
    """One face centre explicitly attributed to a diarized speaker at a media-clock instant."""

    at_ms: int
    center_x: int
    speaker: str

    def __post_init__(self) -> None:
        _exact_non_negative_int(self.at_ms, "speaker focus timestamp")
        _exact_non_negative_int(self.center_x, "speaker focus horizontal centre")
        _safe_speaker_label(self.speaker)


class SubjectTracker(Protocol):
    def track(self, source: Path, in_ms: int, out_ms: int) -> tuple[FocusPoint, ...]: ...


class SpeakerSubjectTracker(Protocol):
    """Associate visible face centres with exclusive diarization turns.

    This is deliberately distinct from :class:`SubjectTracker`: a class name or a non-empty
    point tuple is not proof that speech evidence participated in the crop.
    """

    def track_speakers(
        self,
        source: Path,
        in_ms: int,
        out_ms: int,
        turns: Sequence[Segment],
    ) -> tuple[SpeakerFocusPoint, ...]: ...


def validate_speaker_focus_points(
    points: Sequence[SpeakerFocusPoint],
    turns: Sequence[Segment],
    in_ms: int,
    out_ms: int,
) -> tuple[FocusPoint, ...]:
    """Bind every claimed face centre to the exclusive speaker active at that instant.

    Empty output is valid and means the associator found no unambiguous subject. Invalid output
    is not ambiguity: it is refused so callers cannot silently fall back and hide a broken or
    untrusted association provider.
    """
    _exact_non_negative_int(in_ms, "speaker-tracking in-point")
    _exact_non_negative_int(out_ms, "speaker-tracking out-point")
    if out_ms <= in_ms:
        raise ValueError(f"speaker-tracking span has no duration: {in_ms}..{out_ms}ms")
    assert_exclusive(turns)

    validated: list[FocusPoint] = []
    previous_at: int | None = None
    for point in points:
        if not isinstance(point, SpeakerFocusPoint):
            raise SpeakerAssociationError(
                "speaker tracker output must contain only SpeakerFocusPoint values"
            )
        if previous_at is not None and point.at_ms <= previous_at:
            raise SpeakerAssociationError("speaker focus timestamps must be strictly increasing")
        if not in_ms <= point.at_ms < out_ms:
            raise SpeakerAssociationError(
                f"speaker focus point at {point.at_ms} ms is outside the final clip "
                f"{in_ms}..{out_ms} ms"
            )
        active = [turn for turn in turns if turn.start_ms <= point.at_ms < turn.end_ms]
        if not active:
            raise SpeakerAssociationError(
                f"speaker focus point at {point.at_ms} ms has no active diarization turn"
            )
        active_speaker = active[0].speaker
        if point.speaker != active_speaker:
            raise SpeakerAssociationError(
                f"speaker focus point at {point.at_ms} ms claims {point.speaker!r}, but the "
                f"active speaker is {active_speaker!r}"
            )
        validated.append(FocusPoint(point.at_ms, point.center_x))
        previous_at = point.at_ms
    return tuple(validated)


def choose_face(
    faces: Sequence[tuple[int, int, int, int]], previous_x: int | None
) -> tuple[int, int, int, int] | None:
    """Prefer a large face while preserving continuity with the prior subject."""
    if not faces:
        return None
    if previous_x is None:
        return max(faces, key=lambda face: (face[2] * face[3], -face[0]))
    return max(
        faces,
        key=lambda face: (
            (face[2] * face[3]) / (1 + abs(face[0] + face[2] // 2 - previous_x)),
            face[2] * face[3],
        ),
    )


class OpenCvFaceTracker:
    """Track the dominant continuous face at a bounded sampling rate."""

    def __init__(self, sample_fps: float = 2.0, smoothing: int = 5) -> None:
        if sample_fps <= 0 or not math.isfinite(sample_fps):
            raise ValueError("face-tracking fps must be finite and positive")
        if smoothing < 1:
            raise ValueError("face-tracking smoothing window must be positive")
        self.sample_fps = sample_fps
        self.smoothing = smoothing

    def track(self, source: Path, in_ms: int, out_ms: int) -> tuple[FocusPoint, ...]:
        if out_ms <= in_ms:
            raise ValueError(f"reframe span has no duration: {in_ms}..{out_ms}ms")
        try:
            import cv2 as imported_cv2
        except ImportError as exc:
            raise RuntimeError("face tracking needs the media extra (OpenCV)") from exc
        cv2: Any = imported_cv2

        cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        detector = cv2.CascadeClassifier(str(cascade_path))
        if detector.empty():
            raise RuntimeError(f"OpenCV could not load its face detector at {cascade_path}")
        capture = cv2.VideoCapture(str(source))
        if not capture.isOpened():
            raise RuntimeError(f"OpenCV could not open {source} for subject tracking")
        step_ms = 1000 / self.sample_fps
        history: list[int] = []
        points: list[FocusPoint] = []
        previous: int | None = None
        try:
            at = float(in_ms)
            while at < out_ms:
                capture.set(cv2.CAP_PROP_POS_MSEC, at)
                ok, frame = capture.read()
                if not ok:
                    break
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                detected = detector.detectMultiScale(
                    gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40)
                )
                faces = tuple(
                    (int(face[0]), int(face[1]), int(face[2]), int(face[3])) for face in detected
                )
                chosen = choose_face(faces, previous)
                if chosen is not None:
                    center = chosen[0] + chosen[2] // 2
                    history.append(center)
                    smoothed = round(
                        sum(history[-self.smoothing :]) / len(history[-self.smoothing :])
                    )
                    points.append(FocusPoint(round(at), smoothed))
                    previous = center
                at += step_ms
        finally:
            capture.release()
        return tuple(points)
