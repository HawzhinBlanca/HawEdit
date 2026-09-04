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
    "MIN_FACE_AREA",
    "FocusPoint",
    "MotionSpeakerTracker",
    "OpenCvFaceTracker",
    "SpeakerAssociationError",
    "SpeakerFocusPoint",
    "SpeakerSubjectTracker",
    "SubjectTracker",
    "choose_face",
    "probe_first_frame_face",
    "stabilize",
    "validate_speaker_focus_points",
]

# How long a committed camera move takes. Under ~250 ms it reads as a cut with a smear; over
# ~600 ms the audience notices the camera rather than the speaker.
DEFAULT_MOVE_MS: Final = 400

# How long the subject must stay outside the dead zone before the camera follows. Without
# this, a single mis-detected frame moves the camera and moves it back.
DEFAULT_SETTLE_MS: Final = 600

# Detections below this area in pixels² are dropped before face selection.  Measured:
# the smallest real detection in the D-258 dataset is 40×40 = 1,600 px², returned by
# the Haar cascade at its configured `minSize`.  On a 1920×1080 frame that is 0.08 % of
# the image — background noise, not a face.  2,000 px² (~45×45) rejects sub-cascade-minimum
# artefacts while accepting every real detection across all three measured sources.
MIN_FACE_AREA: Final = 2_000


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
    """Where a face was, at an instant on the media clock.

    `center_y` and `face_height` are OPTIONAL and default to `None`, which means *unmeasured*
    rather than zero — the same distinction D-033 drew for `payoff_at_ms`. Every caller written
    before vertical framing existed keeps constructing two-argument points and keeps getting the
    crop it always got.
    """

    at_ms: int
    center_x: int
    center_y: int | None = None
    face_height: int | None = None

    def __post_init__(self) -> None:
        _exact_non_negative_int(self.at_ms, "focus point timestamp")
        _exact_non_negative_int(self.center_x, "focus point horizontal centre")
        if self.center_y is not None:
            _exact_non_negative_int(self.center_y, "focus point vertical centre")
        if self.face_height is not None:
            _exact_non_negative_int(self.face_height, "focus point face height")
            if self.face_height == 0:
                raise ValueError("a measured face height cannot be zero")


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
    faces: Sequence[tuple[int, int, int, int]],
    previous_x: int | None,
    min_area: int = MIN_FACE_AREA,
) -> tuple[int, int, int, int] | None:
    """Prefer a large face while preserving continuity with the prior subject.

    Detections smaller than ``min_area`` are dropped before selection.  A 40×40
    box on a 1920×1080 frame is 1,600 px² — noise, not a face — and letting it
    win (when nothing else is found) drags the crop to a background artefact.
    """
    faces = tuple(f for f in faces if f[2] * f[3] >= min_area)
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


def _create_tracker(cv2_mod: Any) -> Any:
    for name in ("TrackerCSRT", "TrackerKCF", "TrackerMIL"):
        cls = getattr(cv2_mod, name, None)
        if cls is not None and hasattr(cls, "create"):
            return cls.create()
        factory = getattr(cv2_mod, f"{name}_create", None)
        if callable(factory):
            return factory()
    return None


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

    def __init__(self, sample_fps: float = 5.0, *, enable_tracker: bool = True) -> None:
        if sample_fps <= 0 or not math.isfinite(sample_fps):
            raise ValueError("face-tracking fps must be finite and positive")
        self.sample_fps = sample_fps
        self.enable_tracker = enable_tracker

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
        tracker: Any = None

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
                height = gray.shape[0]
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
                    # the camera does; this reports only what was seen. The vertical half of
                    # the box travels with it: `render.vertical_framing` needs how far down the
                    # frame the face sits and how much of it the face fills, and a tracker that
                    # measured both and reported one is why the crop could only ever be centred.
                    points.append(
                        FocusPoint(round(at), center, chosen[1] + chosen[3] // 2, chosen[3])
                    )
                    previous = center
                    if self.enable_tracker:
                        if tracker is None:
                            tracker = _create_tracker(cv2)
                        if tracker is not None:
                            try:
                                tracker.init(frame, (chosen[0], chosen[1], chosen[2], chosen[3]))
                            except Exception:
                                tracker = None
                elif self.enable_tracker and tracker is not None:
                    tracked_ok = False
                    bbox = None
                    try:
                        tracked_ok, bbox = tracker.update(frame)
                    except Exception:
                        tracker = None
                    if tracked_ok and bbox is not None:
                        bx, by, bw, bh = (int(v) for v in bbox)
                        if bw > 0 and bh > 0 and bx + bw <= width and by + bh <= height:
                            center = bx + bw // 2
                            points.append(FocusPoint(round(at), center, by + bh // 2, bh))
                            previous = center
                        else:
                            tracker = None
                    else:
                        tracker = None
                at += step_ms
        finally:
            capture.release()
        return tuple(points)


class MotionSpeakerTracker:
    """Associate visible faces with exclusive speaker turns via mouth pixel-motion energy.

    Task T2.1 / Candidate (a): computes inter-frame pixel-motion energy in the lower third
    (mouth region) of candidate Haar face boxes at >= 5 fps, correlating motion with the
    active exclusive diarization turn.

    Invariants:
    - Only emits SpeakerFocusPoint during active exclusive diarization turns.
    - Timestamps are strictly monotonically increasing within the clip span.
    - On ambiguity (motion difference below threshold or multiple quiet/moving faces),
      holds the speaker's last confirmed position ("on ambiguity hold, never wander").
    """

    def __init__(
        self,
        sample_fps: float = 5.0,
        *,
        min_face_area: int = MIN_FACE_AREA,
        motion_threshold: float = 1.0,
        ambiguity_ratio: float = 1.25,
    ) -> None:
        if sample_fps <= 0 or not math.isfinite(sample_fps):
            raise ValueError("speaker-tracking fps must be finite and positive")
        if motion_threshold < 0 or not math.isfinite(motion_threshold):
            raise ValueError("motion threshold must be finite and non-negative")
        if ambiguity_ratio < 1.0 or not math.isfinite(ambiguity_ratio):
            raise ValueError("ambiguity ratio must be >= 1.0 and finite")
        self.sample_fps = sample_fps
        self.min_face_area = min_face_area
        self.motion_threshold = motion_threshold
        self.ambiguity_ratio = ambiguity_ratio

    def track_speakers(
        self,
        source: Path,
        in_ms: int,
        out_ms: int,
        turns: Sequence[Segment],
    ) -> tuple[SpeakerFocusPoint, ...]:
        _exact_non_negative_int(in_ms, "speaker-tracking in-point")
        _exact_non_negative_int(out_ms, "speaker-tracking out-point")
        if out_ms <= in_ms:
            raise ValueError(f"speaker-tracking span has no duration: {in_ms}..{out_ms}ms")
        assert_exclusive(turns)
        overlapping_turns = tuple(
            turn for turn in turns if turn.start_ms < out_ms and turn.end_ms > in_ms
        )
        if not overlapping_turns:
            return ()

        try:
            import cv2 as imported_cv2
        except ImportError as exc:
            raise RuntimeError("speaker tracking needs the media extra (OpenCV)") from exc
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
            raise RuntimeError(f"OpenCV could not open {source} for speaker tracking")

        step_ms = 1000.0 / self.sample_fps
        points: list[SpeakerFocusPoint] = []
        speaker_face_centers: dict[str, int] = {}
        last_known_center: int | None = None
        prev_gray: Any = None
        previous_at: int | None = None

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
                height = gray.shape[0]

                at_int = int(round(at))
                if at_int >= out_ms:
                    break
                if previous_at is not None and at_int <= previous_at:
                    at_int = previous_at + 1
                    if at_int >= out_ms:
                        break

                active = [
                    turn for turn in overlapping_turns if turn.start_ms <= at_int < turn.end_ms
                ]
                if not active:
                    prev_gray = gray
                    at += step_ms
                    continue

                active_speaker = active[0].speaker

                faces = boxes(frontal, gray) + boxes(profile, gray)
                faces += [
                    (width - (x + w), y, w, h) for x, y, w, h in boxes(profile, cv2.flip(gray, 1))
                ]
                valid_faces = [f for f in faces if f[2] * f[3] >= self.min_face_area]

                # Deduplicate overlapping face boxes
                deduped_faces: list[tuple[int, int, int, int]] = []
                for f in sorted(valid_faces, key=lambda b: b[2] * b[3], reverse=True):
                    fx, fy, fw, fh = f
                    cx = fx + fw // 2
                    cy = fy + fh // 2
                    if not any(
                        abs(cx - (df[0] + df[2] // 2)) < df[2] // 2
                        and abs(cy - (df[1] + df[3] // 2)) < df[3] // 2
                        for df in deduped_faces
                    ):
                        deduped_faces.append(f)

                selected_center: int | None = None

                if len(deduped_faces) == 1:
                    face = deduped_faces[0]
                    selected_center = face[0] + face[2] // 2
                    speaker_face_centers[active_speaker] = selected_center
                    last_known_center = selected_center
                elif len(deduped_faces) > 1:
                    face_motions: list[tuple[float, tuple[int, int, int, int]]] = []
                    for face in deduped_faces:
                        fx, fy, fw, fh = face
                        my = max(0, fy + 2 * fh // 3)
                        mh = min(height - my, fh // 3)
                        mx = max(0, fx)
                        mw = min(width - mx, fw)

                        motion_val = 0.0
                        if prev_gray is not None and mh > 0 and mw > 0:
                            curr_mouth = gray[my : my + mh, mx : mx + mw]
                            prev_mouth = prev_gray[my : my + mh, mx : mx + mw]
                            if curr_mouth.shape == prev_mouth.shape:
                                diff = cv2.absdiff(curr_mouth, prev_mouth)
                                motion_val = float(diff.mean())
                        face_motions.append((motion_val, face))

                    face_motions.sort(key=lambda item: item[0], reverse=True)
                    best_motion, best_face = face_motions[0]
                    second_motion = face_motions[1][0] if len(face_motions) > 1 else 0.0

                    if best_motion >= self.motion_threshold and (
                        second_motion == 0.0 or best_motion >= second_motion * self.ambiguity_ratio
                    ):
                        selected_center = best_face[0] + best_face[2] // 2
                        speaker_face_centers[active_speaker] = selected_center
                        last_known_center = selected_center
                    else:
                        # Ambiguous: hold active speaker's confirmed position if available
                        if active_speaker in speaker_face_centers:
                            known = speaker_face_centers[active_speaker]
                            closest_face = min(
                                deduped_faces,
                                key=lambda f: abs((f[0] + f[2] // 2) - known),
                            )
                            selected_center = closest_face[0] + closest_face[2] // 2
                            last_known_center = selected_center
                        elif last_known_center is not None:
                            target_x = last_known_center
                            closest_face = min(
                                deduped_faces,
                                key=lambda f: abs((f[0] + f[2] // 2) - target_x),
                            )
                            selected_center = closest_face[0] + closest_face[2] // 2
                        else:
                            largest_face = max(deduped_faces, key=lambda f: f[2] * f[3])
                            selected_center = largest_face[0] + largest_face[2] // 2
                            speaker_face_centers[active_speaker] = selected_center
                            last_known_center = selected_center
                else:
                    if active_speaker in speaker_face_centers:
                        selected_center = speaker_face_centers[active_speaker]
                    elif last_known_center is not None:
                        selected_center = last_known_center

                if selected_center is not None:
                    points.append(
                        SpeakerFocusPoint(
                            at_ms=at_int,
                            center_x=selected_center,
                            speaker=active_speaker,
                        )
                    )
                    previous_at = at_int

                prev_gray = gray
                at += step_ms
        finally:
            capture.release()

        return tuple(points)


def probe_first_frame_face(
    source: Path,
    timestamp_ms: int,
    *,
    min_face_share: float = 0.08,
    expected_center_x: int | None = None,
    max_x_drift: int | None = None,
) -> tuple[bool, FocusPoint | None]:
    """Inspect the frame at `timestamp_ms` to verify the presence of the tracked subject.

    Returns (True, FocusPoint) if a face meeting or exceeding `min_face_share` is found at the
    expected spatial region. Returns (False, None) if no face is found, or if the detected face
    is too small or at a discordant horizontal position indicating a cut to an off-subject angle.
    """
    try:
        import cv2 as imported_cv2
    except ImportError as exc:
        raise RuntimeError("face tracking needs the media extra (OpenCV)") from exc
    cv2: Any = imported_cv2

    cascades = Path(cv2.data.haarcascades)
    frontal = cv2.CascadeClassifier(str(cascades / "haarcascade_frontalface_default.xml"))
    profile = cv2.CascadeClassifier(str(cascades / "haarcascade_profileface.xml"))
    if frontal.empty() or profile.empty():
        raise RuntimeError(f"OpenCV could not load face detector cascades at {cascades}")

    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise RuntimeError(f"OpenCV could not open {source} to probe first frame")
    try:
        capture.set(cv2.CAP_PROP_POS_MSEC, float(timestamp_ms))
        ok, frame = capture.read()
        if not ok or frame is None:
            return False, None
        height, width = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        def boxes(classifier: Any, image: Any) -> list[tuple[int, int, int, int]]:
            return [
                (int(x), int(y), int(w), int(h))
                for x, y, w, h in classifier.detectMultiScale(
                    image, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40)
                )
            ]

        faces = boxes(frontal, gray) + boxes(profile, gray)
        faces += [(width - (x + w), y, w, h) for x, y, w, h in boxes(profile, cv2.flip(gray, 1))]
        if not faces:
            return False, None

        valid_faces = [f for f in faces if (float(f[3]) / float(height)) >= min_face_share]
        if not valid_faces:
            return False, None

        chosen = choose_face(tuple(valid_faces), expected_center_x)
        if chosen is None:
            return False, None

        center_x = chosen[0] + chosen[2] // 2
        center_y = chosen[1] + chosen[3] // 2
        face_h = chosen[3]

        if (
            expected_center_x is not None
            and max_x_drift is not None
            and abs(center_x - expected_center_x) > max_x_drift
        ):
            return False, None

        return True, FocusPoint(timestamp_ms, center_x, center_y, face_h)
    finally:
        capture.release()


def median_face_box(points: Sequence[FocusPoint]) -> tuple[int | None, int | None]:
    """The clip's vertical framing, as `(center_y, face_height)`, or `(None, None)`.

    **One placement for the whole clip, deliberately.** The horizontal crop moves because people
    take turns talking; the vertical one does not, because nobody stands up mid-sentence at a
    podcast table. A per-sample vertical path would reintroduce exactly the shimmer `stabilize`
    exists to remove, in the axis where there is nothing to follow — so the medians are taken
    once, over the whole raw track, and a single wild detection cannot drag either.

    `(None, None)` when no point carried a measurement, which is what every caller written
    before vertical framing produces, and which `render.vertical_framing` treats as "leave the
    crop where it has always been".
    """
    verticals = sorted(p.center_y for p in points if p.center_y is not None)
    heights = sorted(p.face_height for p in points if p.face_height is not None)
    if not verticals or not heights:
        return None, None
    return verticals[len(verticals) // 2], heights[len(heights) // 2]


def stabilize(
    points: Sequence[FocusPoint],
    *,
    dead_zone_px: int,
    move_ms: int = DEFAULT_MOVE_MS,
    settle_ms: int = DEFAULT_SETTLE_MS,
    shot_cuts_ms: Sequence[int] = (),
    max_pan_px: int | None = None,
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

    Across Stage 0 shot cuts, changes are executed as instant cut steps rather than slow
    interpolated pans, preventing jarring camera movement over scene transitions or empty
    furniture across wide two-shots.

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
    cuts = sorted(c for c in shot_cuts_ms if points[0].at_ms <= c <= points[-1].at_ms)

    for point in points[1:]:
        recent_cuts = [c for c in cuts if keyframes[-1].at_ms < c <= point.at_ms]

        if abs(point.center_x - held) <= dead_zone_px:
            # Back inside the dead zone: whatever was building was a wobble, not a move.
            pending.clear()
            continue
        pending.append(point)

        # If a shot cut occurred, step instantaneously at the cut point without slow sliding
        if recent_cuts:
            cut_time = recent_cuts[-1]
            target = point.center_x
            if cut_time > keyframes[-1].at_ms:
                keyframes.append(FocusPoint(cut_time, held))
            keyframes.append(FocusPoint(max(cut_time + 1, keyframes[-1].at_ms + 1), target))
            held = target
            pending.clear()
            continue

        if point.at_ms - pending[0].at_ms < settle_ms:
            continue
        centers = sorted(candidate.center_x for candidate in pending)
        target = centers[len(centers) // 2]
        start = pending[0].at_ms

        cuts_in_move = [c for c in cuts if start <= c <= start + move_ms]

        # Prevent slow panning across distant empty space on a continuous shot
        if not cuts_in_move and max_pan_px is not None and abs(target - held) > max_pan_px:
            pending.clear()
            continue

        if cuts_in_move:
            cut_time = cuts_in_move[0]
            if cut_time > keyframes[-1].at_ms:
                keyframes.append(FocusPoint(cut_time, held))
            keyframes.append(FocusPoint(max(cut_time + 1, keyframes[-1].at_ms + 1), target))
        else:
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
