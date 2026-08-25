"""Subject-aware horizontal tracking for vertical reframing."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any, Final, Protocol

from hawedit.diarization import Segment, assert_exclusive

__all__ = [
    "DEFAULT_MOVE_MS",
    "DEFAULT_SETTLE_MS",
    "FocusPoint",
    "OpenCvFaceTracker",
    "SpeakerAssociationError",
    "SpeakerFocusPoint",
    "SpeakerSubjectTracker",
    "SubjectTracker",
    "choose_face",
    "stabilize",
    "validate_speaker_focus_points",
]

# How long a committed camera move takes. Under ~250 ms it reads as a cut with a smear; over
# ~600 ms the audience notices the camera rather than the speaker.
DEFAULT_MOVE_MS: Final = 400

# How long the subject must stay outside the dead zone before the camera follows. Without
# this, a single mis-detected frame moves the camera and moves it back.
DEFAULT_SETTLE_MS: Final = 600


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
    """Track the dominant continuous face at a bounded sampling rate.

    **Frontal detection alone is not enough for an interview.** Two people at a table face
    each other, not the lens, and `haarcascade_frontalface_default` finds neither. Measured on
    the real 38-minute source: across the opening eight seconds of a wide two-shot, the frontal
    cascade returned zero faces on every sample, and so did `frontalface_alt2`. The profile
    cascade — run over the frame and again over its mirror, because it only detects one facing
    — found the guest at x=152..154 on all eight and the host at x=491. So the tracker reported
    nothing for that span and the crop held a position measured from a later shot, which put a
    rug on screen for the first eight seconds of the clip.
    """

    def __init__(self, sample_fps: float = 2.0) -> None:
        if sample_fps <= 0 or not math.isfinite(sample_fps):
            raise ValueError("face-tracking fps must be finite and positive")
        self.sample_fps = sample_fps

    def track(self, source: Path, in_ms: int, out_ms: int) -> tuple[FocusPoint, ...]:
        if out_ms <= in_ms:
            raise ValueError(f"reframe span has no duration: {in_ms}..{out_ms}ms")
        try:
            import cv2 as imported_cv2
        except ImportError as exc:
            raise RuntimeError("face tracking needs the media extra (OpenCV)") from exc
        cv2: Any = imported_cv2

        cascades = Path(cv2.data.haarcascades)
        detectors = {}
        for name in ("haarcascade_frontalface_default.xml", "haarcascade_profileface.xml"):
            classifier = cv2.CascadeClassifier(str(cascades / name))
            if classifier.empty():
                raise RuntimeError(f"OpenCV could not load its face detector at {cascades / name}")
            detectors[name] = classifier
        frontal = detectors["haarcascade_frontalface_default.xml"]
        profile = detectors["haarcascade_profileface.xml"]

        capture = cv2.VideoCapture(str(source))
        if not capture.isOpened():
            raise RuntimeError(f"OpenCV could not open {source} for subject tracking")
        step_ms = 1000 / self.sample_fps
        points: list[FocusPoint] = []
        previous: int | None = None

        def boxes(classifier: Any, image: Any) -> list[tuple[int, int, int, int]]:
            return [
                (int(x), int(y), int(w), int(h))
                for x, y, w, h in classifier.detectMultiScale(
                    image, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40)
                )
            ]

        try:
            at = float(in_ms)
            while at < out_ms:
                capture.set(cv2.CAP_PROP_POS_MSEC, at)
                ok, frame = capture.read()
                if not ok:
                    break
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                width = gray.shape[1]
                faces = boxes(frontal, gray) + boxes(profile, gray)
                # The profile cascade is trained on one facing only. The other is the same
                # detector over the mirrored frame, with each box reflected back.
                faces += [
                    (width - (x + w), y, w, h) for x, y, w, h in boxes(profile, cv2.flip(gray, 1))
                ]
                chosen = choose_face(tuple(faces), previous)
                if chosen is not None:
                    center = chosen[0] + chosen[2] // 2
                    # The detected centre, not a running mean of it. `stabilize` decides what
                    # the camera does; this reports only what was seen.
                    points.append(FocusPoint(round(at), center))
                    previous = center
                at += step_ms
        finally:
            capture.release()
        return tuple(points)


def stabilize(
    points: Sequence[FocusPoint],
    *,
    dead_zone_px: int,
    move_ms: int = DEFAULT_MOVE_MS,
    settle_ms: int = DEFAULT_SETTLE_MS,
) -> tuple[FocusPoint, ...]:
    """Turn a per-sample face track into a camera path that holds still and then moves.

    A tracker reports where the face is; it does not report where the camera should be, and
    treating one as the other is what produced the artifact this function exists to stop.
    `OpenCvFaceTracker` samples twice a second, so its raw output moved the crop up to twice
    a second, every second, for the whole clip — a continuous horizontal shimmer that reads
    as a broken encode rather than as camera work. Averaging alone does not fix it: a mean
    over a sliding window still changes every sample, just by less.

    So the camera holds a position and only commits to a new one when the subject has been
    outside `dead_zone_px` of it for a sustained `settle_ms` — a real move by the speaker,
    not a detector flicker or a turn of the head. The new position is the *median* of that
    window, which a single wild detection cannot drag.

    The result is a keyframe list, not a sample list: a pair of equal values spans a hold and
    a pair of differing values spans a move, which is exactly what `render.crop_filter`
    interpolates between. Empty in, empty out — a clip with no track is a static centre crop,
    and this must never invent one.

    Raises:
        ValueError: a non-positive dead zone or duration, or timestamps that do not increase.
    """
    if dead_zone_px <= 0:
        raise ValueError("dead zone must be positive")
    if move_ms <= 0:
        raise ValueError("camera move duration must be positive")
    if settle_ms <= 0:
        raise ValueError("settle duration must be positive")
    if not points:
        return ()
    for earlier, later in pairwise(points):
        if later.at_ms <= earlier.at_ms:
            raise ValueError("focus point timestamps must be strictly increasing")

    held = points[0].center_x
    keyframes: list[FocusPoint] = [FocusPoint(points[0].at_ms, held)]
    pending: list[FocusPoint] = []
    for point in points[1:]:
        if abs(point.center_x - held) <= dead_zone_px:
            # Back inside the dead zone: whatever was building was a wobble, not a move.
            pending.clear()
            continue
        pending.append(point)
        if point.at_ms - pending[0].at_ms < settle_ms:
            continue
        centers = sorted(candidate.center_x for candidate in pending)
        target = centers[len(centers) // 2]
        start = pending[0].at_ms
        # The hold runs to the instant the move begins, then the move eases to the new
        # position. Equal-valued neighbours are what make the interpolation flat.
        if start > keyframes[-1].at_ms:
            keyframes.append(FocusPoint(start, held))
        keyframes.append(FocusPoint(max(start + move_ms, keyframes[-1].at_ms + 1), target))
        held = target
        pending.clear()

    last = points[-1].at_ms
    if last > keyframes[-1].at_ms:
        keyframes.append(FocusPoint(last, held))
    return tuple(keyframes)
