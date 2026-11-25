"""Subject-aware horizontal tracking for vertical reframing."""

from __future__ import annotations

import math
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any, Final, Protocol

from hawedit.diarization import Segment, assert_exclusive

__all__ = [
    "DEFAULT_MIN_CONFIDENCE",
    "DEFAULT_MIN_DWELL_MS",
    "DEFAULT_MOVE_MS",
    "DEFAULT_SETTLE_MS",
    "MIN_FACE_AREA",
    "VALID_SPEAKER_STATES",
    "FocusPoint",
    "MotionSpeakerTracker",
    "OpenCvFaceTracker",
    "SpeakerAssociationError",
    "SpeakerFocusPoint",
    "SpeakerSubjectTracker",
    "SubjectTracker",
    "choose_face",
    "compute_two_person_split_crops",
    "detect_motion_focus_points",
    "detect_rapid_speaker_exchange",
    "layout_policy",
    "median_face_box",
    "per_shot_face_boxes",
    "probe_first_frame_face",
    "stabilize",
    "validate_speaker_focus_points",
]

# Minimum duration of a diarized speaker turn required to justify a camera transition.
DEFAULT_MIN_DWELL_MS: Final = 600
DEFAULT_MIN_CONFIDENCE: Final = 0.6

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

# D-357: Downscale frames wider than 960 px before running Haar cascades (~4x faster on 1440p/4K)
# while mapping boxes back to full source coordinates within <= 2 px.
_HAAR_MAX_DETECT_WIDTH: Final = 960
_INTRA_SHOT_MIN_DURATION_MS: Final = 5_000
_ROLLING_MOTION_WINDOW_MS: Final = 1_500
_SPEAKER_SWITCH_DWELL_MS: Final = 2_000
_SPEAKER_SWITCH_RATIO: Final = 1.6
_SPEAKER_SWITCH_MIN_ENERGY: Final = 2.0


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


VALID_SPEAKER_STATES: Final = ("speaker", "listener", "off_screen", "unknown")


@dataclass(frozen=True, slots=True)
class SpeakerFocusPoint:
    """One face centre explicitly attributed to a diarized speaker at a media-clock instant."""

    at_ms: int
    center_x: int
    speaker: str
    state: str = "speaker"
    is_speaking: bool = True
    confidence: float = 1.0

    def __post_init__(self) -> None:
        _exact_non_negative_int(self.at_ms, "speaker focus timestamp")
        _exact_non_negative_int(self.center_x, "speaker focus horizontal centre")
        _safe_speaker_label(self.speaker)
        if self.state not in VALID_SPEAKER_STATES:
            raise ValueError(
                f"invalid speaker state {self.state!r}; expected one of {VALID_SPEAKER_STATES}"
            )
        if type(self.is_speaking) is not bool:
            raise TypeError(
                f"is_speaking must be an exact boolean, got {type(self.is_speaking).__name__}"
            )
        if type(self.confidence) not in (int, float) or not math.isfinite(self.confidence):
            raise TypeError("confidence must be a finite float")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError(f"confidence must be in 0.0..1.0, got {self.confidence}")


class SubjectTracker(Protocol):
    def track(
        self,
        source: Path,
        in_ms: int,
        out_ms: int,
        shot_cuts_ms: Sequence[int] = (),
    ) -> tuple[FocusPoint, ...]: ...


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
    max_distance: int | None = None,
) -> tuple[int, int, int, int] | None:
    """Prefer a large face while preserving continuity with the prior subject.

    Detections smaller than ``min_area`` are dropped before selection.  A 40×40
    box on a 1920×1080 frame is 1,600 px² — noise, not a face — and letting it
    win (when nothing else is found) drags the crop to a background artefact.

    When ``previous_x`` and ``max_distance`` are provided, candidates further than
    ``max_distance`` from ``previous_x`` are rejected, preventing single-frame
    dropouts on wide two-shots from immediately flipping to a distant listener.
    """
    faces = tuple(f for f in faces if f[2] * f[3] >= min_area)
    if not faces:
        return None
    if previous_x is None:
        return max(faces, key=lambda face: (face[2] * face[3], -face[0]))
    if max_distance is not None:
        faces = tuple(f for f in faces if abs(f[0] + f[2] // 2 - previous_x) <= max_distance)
        if not faces:
            return None
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


def _torso_hsv_hist(cv2: Any, frame: Any, box: tuple[int, int, int, int]) -> Any:
    """Compute a normalized 18x8 H-S histogram of the upper torso below a face box."""
    height, width = frame.shape[:2]
    x, y, bw, bh = box
    cx = x + bw // 2
    tx0 = max(0, cx - int(bw * 0.7))
    tx1 = min(width, cx + int(bw * 0.7))
    ty0 = min(height - 1, y + int(bh * 1.15))
    ty1 = min(height, y + int(bh * 2.4))
    if tx1 - tx0 < 8 or ty1 - ty0 < 8:
        return None
    roi = cv2.cvtColor(frame[ty0:ty1, tx0:tx1], cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([roi], [0, 1], None, [18, 8], [0, 180, 0, 256])
    cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
    return hist


def _lower_face_motion(
    cv2: Any, prev_gray: Any, gray: Any, box: tuple[int, int, int, int]
) -> float:
    """Mean pixel difference in the lower half (mouth/jaw) of a face box."""
    import numpy as np

    height, width = gray.shape[:2]
    x, y, bw, bh = box
    my0 = max(0, y + int(bh * 0.50))
    my1 = min(height, y + int(bh * 1.05))
    mx0 = max(0, x)
    mx1 = min(width, x + bw)
    if mx1 - mx0 < 8 or my1 - my0 < 8:
        return 0.0
    diff = cv2.absdiff(prev_gray[my0:my1, mx0:mx1], gray[my0:my1, mx0:mx1])
    return float(np.mean(diff))


def _filter_person_clusters(clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep persistent face clusters at a comparable scale to the shot's primary subject."""
    import numpy as np

    persistent = [c for c in clusters if len(c["centers"]) >= 2]
    if len(persistent) < 2:
        return persistent
    med_widths = [float(np.median(c["widths"])) for c in persistent]
    max_w = max(med_widths)
    return [c for c, w in zip(persistent, med_widths, strict=True) if w >= 0.45 * max_w]


def _select_active_cluster_center(
    cv2: Any,
    clusters: list[dict[str, Any]],
    adjacent_hist: Any,
) -> int | None:
    """Choose the active speaking person cluster in a multi-person shot."""
    import numpy as np

    persistent = _filter_person_clusters(clusters)
    if len(persistent) < 2:
        return None

    motions = [float(np.mean(c["motions"])) if c["motions"] else 0.0 for c in persistent]
    max_motion = max(motions)

    if adjacent_hist is not None:
        best_score = -1.0
        best_center: int | None = None
        adj_f32 = adjacent_hist.astype(np.float32)
        for cluster, motion in zip(persistent, motions, strict=True):
            norm_m = motion / max_motion if max_motion > 1.0 else 0.0
            h_corr = 0.0
            if cluster["hists"]:
                c_hist = np.mean(cluster["hists"], axis=0).astype(np.float32)
                h_corr = max(0.0, float(cv2.compareHist(c_hist, adj_f32, cv2.HISTCMP_CORREL)))
            score = 0.55 * norm_m + 0.45 * h_corr
            if score > best_score:
                best_score = score
                best_center = int(round(float(np.median(cluster["centers"]))))
        return best_center

    ranked = sorted(
        zip(motions, persistent, strict=True),
        key=lambda item: item[0],
        reverse=True,
    )
    if ranked[0][0] >= 2.0 and (ranked[1][0] <= 0.0 or ranked[0][0] >= 1.25 * ranked[1][0]):
        return int(round(float(np.median(ranked[0][1]["centers"]))))
    return None


def _detect_haar_faces(
    cv2: Any,
    frontal: Any,
    profile: Any,
    gray: Any,
) -> list[tuple[int, int, int, int]]:
    """Run frontal + profile + mirrored-profile Haar cascades, downscaling width > 960 px."""
    height, width = gray.shape[:2]

    def _run_boxes(classifier: Any, image: Any, min_side: int) -> list[tuple[int, int, int, int]]:
        return [
            (int(x), int(y), int(w), int(h))
            for x, y, w, h in classifier.detectMultiScale(
                image, scaleFactor=1.1, minNeighbors=5, minSize=(min_side, min_side)
            )
        ]

    if width > _HAAR_MAX_DETECT_WIDTH:
        scale = _HAAR_MAX_DETECT_WIDTH / float(width)
        det_w = _HAAR_MAX_DETECT_WIDTH
        det_h = max(1, int(round(height * scale)))
        det_gray = cv2.resize(gray, (det_w, det_h), interpolation=cv2.INTER_AREA)
        min_side = max(24, int(round(40 * scale)))
        raw_faces = _run_boxes(frontal, det_gray, min_side) + _run_boxes(
            profile, det_gray, min_side
        )
        flipped_profile = _run_boxes(profile, cv2.flip(det_gray, 1), min_side)
        raw_faces += [(det_w - (x + w), y, w, h) for x, y, w, h in flipped_profile]
        mapped: list[tuple[int, int, int, int]] = []
        for x, y, w, h in raw_faces:
            rx = max(0, min(width - 1, round(x / scale)))
            ry = max(0, min(height - 1, round(y / scale)))
            rw = max(1, min(width - rx, round(w / scale)))
            rh = max(1, min(height - ry, round(h / scale)))
            mapped.append((rx, ry, rw, rh))
        return mapped

    faces = _run_boxes(frontal, gray, 40) + _run_boxes(profile, gray, 40)
    flipped = _run_boxes(profile, cv2.flip(gray, 1), 40)
    faces += [(width - (x + w), y, w, h) for x, y, w, h in flipped]
    return faces


def _intra_shot_speaker_switch(
    cv2: Any,
    frames_in_shot: list[dict[str, Any]],
    clusters: list[dict[str, Any]],
    adjacent_hist: Any,
    step_ms: float,
) -> tuple[list[int], frozenset[int]] | None:
    """Compute per-frame active cluster centres and switch indices on >= 5 s wide shots (D-357).

    Returns ``(per_frame_center_x, switch_frame_indices)`` when a multi-person shot lasts at
    least ``_INTRA_SHOT_MIN_DURATION_MS`` and an opening speaker cluster can be identified;
    returns ``None`` otherwise so callers stay on the single-cluster shot path.
    """
    import numpy as np

    persistent = _filter_person_clusters(clusters)
    if len(persistent) < 2 or not frames_in_shot:
        return None

    step_ms_int = max(1, round(step_ms))
    shot_start = int(frames_in_shot[0]["at"])
    shot_end = int(frames_in_shot[-1]["at"])
    shot_duration_ms = (shot_end - shot_start) + step_ms_int
    if shot_duration_ms < _INTRA_SHOT_MIN_DURATION_MS:
        return None

    half_win = _ROLLING_MOTION_WINDOW_MS // 2
    cluster_anchors = [int(round(float(np.median(c["centers"])))) for c in persistent]
    cluster_samples: list[list[tuple[int, float]]] = [c["motion_samples"] for c in persistent]

    rolling_motions: list[list[float]] = []
    for obs in frames_in_shot:
        t = int(obs["at"])
        lo = t - half_win
        hi = t + half_win
        frame_m: list[float] = []
        for samples in cluster_samples:
            vals = [m for st, m in samples if lo <= st <= hi]
            frame_m.append(float(np.mean(vals)) if vals else 0.0)
        rolling_motions.append(frame_m)

    # Pick opening active cluster: prefer a clear motion winner in the opening 2.5 s (or
    # earliest active frame), falling back to `_select_active_cluster_center` with `adjacent_hist`.
    opening_idx: int | None = None
    opening_motions: list[float] = []
    for samples in cluster_samples:
        vals = [m for st, m in samples if shot_start <= st <= shot_start + 2_500]
        opening_motions.append(float(np.mean(vals)) if vals else 0.0)
    ranked_open = sorted(
        enumerate(opening_motions),
        key=lambda item: item[1],
        reverse=True,
    )
    if ranked_open[0][1] >= _SPEAKER_SWITCH_MIN_ENERGY and (
        ranked_open[1][1] <= 0.0 or ranked_open[0][1] >= 1.25 * ranked_open[1][1]
    ):
        opening_idx = ranked_open[0][0]
    else:
        for frame_m in rolling_motions:
            ranked_f = sorted(enumerate(frame_m), key=lambda item: item[1], reverse=True)
            if ranked_f[0][1] >= _SPEAKER_SWITCH_MIN_ENERGY and (
                ranked_f[1][1] <= 0.0 or ranked_f[0][1] >= 1.25 * ranked_f[1][1]
            ):
                opening_idx = ranked_f[0][0]
                break
    if opening_idx is None:
        fallback_cx = _select_active_cluster_center(cv2, clusters, adjacent_hist)
        if fallback_cx is None:
            return None
        opening_idx = min(
            range(len(cluster_anchors)),
            key=lambda idx: abs(cluster_anchors[idx] - fallback_cx),
        )

    active_idx = opening_idx
    segments: list[tuple[int, int]] = [(0, active_idx)]
    challenger_idx: int | None = None
    challenger_start_idx = 0
    challenger_start_ms = shot_start

    for f_idx, obs in enumerate(frames_in_shot):
        t = int(obs["at"])
        frame_m = rolling_motions[f_idx]
        cur_m = frame_m[active_idx]
        best_other_idx = max(
            (idx for idx in range(len(persistent)) if idx != active_idx),
            key=lambda idx: frame_m[idx],
        )
        cand_m = frame_m[best_other_idx]
        dominates = cand_m >= _SPEAKER_SWITCH_MIN_ENERGY and (
            cur_m <= 0.0 or cand_m >= _SPEAKER_SWITCH_RATIO * cur_m
        )
        if dominates:
            if challenger_idx != best_other_idx:
                challenger_idx = best_other_idx
                challenger_start_idx = f_idx
                challenger_start_ms = t
            elapsed_ms = (t + step_ms_int) - challenger_start_ms
            if elapsed_ms >= _SPEAKER_SWITCH_DWELL_MS:
                active_idx = challenger_idx
                if challenger_start_idx > segments[-1][0]:
                    segments.append((challenger_start_idx, active_idx))
                else:
                    segments[-1] = (segments[-1][0], active_idx)
                challenger_idx = None
        else:
            challenger_idx = None

    per_frame_cx: list[int] = [0] * len(frames_in_shot)
    switch_indices: set[int] = set()
    for seg_pos, (start_idx, c_idx) in enumerate(segments):
        end_idx = segments[seg_pos + 1][0] if seg_pos + 1 < len(segments) else len(frames_in_shot)
        anchor_cx = cluster_anchors[c_idx]
        for idx in range(start_idx, end_idx):
            per_frame_cx[idx] = anchor_cx
        if seg_pos > 0:
            switch_indices.add(start_idx)

    return per_frame_cx, frozenset(switch_indices)


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

    def __init__(
        self,
        sample_fps: float = 5.0,
        *,
        enable_tracker: bool = True,
        detector_kind: str = "auto",
        yunet_model_path: Path | None = None,
    ) -> None:
        if sample_fps <= 0 or not math.isfinite(sample_fps):
            raise ValueError("face-tracking fps must be finite and positive")
        self.sample_fps = sample_fps
        self.enable_tracker = enable_tracker
        self.detector_kind = detector_kind
        self.yunet_model_path = yunet_model_path
        self.last_intra_shot_switches_ms: tuple[int, ...] = ()

    def track(
        self,
        source: Path,
        in_ms: int,
        out_ms: int,
        shot_cuts_ms: Sequence[int] = (),
    ) -> tuple[FocusPoint, ...]:
        self.last_intra_shot_switches_ms = ()
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

        yunet_detector: Any = None
        if self.detector_kind in ("auto", "yunet"):
            model_file = self.yunet_model_path
            if model_file is None:
                repo_model = (
                    Path(__file__).resolve().parents[2] / "models" / "face_detection_yunet.onnx"
                )
                if repo_model.is_file():
                    model_file = repo_model
            if model_file is not None and model_file.is_file() and hasattr(cv2, "FaceDetectorYN"):
                try:
                    yunet_detector = cv2.FaceDetectorYN.create(
                        str(model_file),
                        "",
                        (320, 320),
                        score_threshold=0.6,
                        nms_threshold=0.3,
                        top_k=10,
                    )
                except Exception:
                    yunet_detector = None

        capture = cv2.VideoCapture(str(source))
        if not capture.isOpened():
            raise RuntimeError(f"OpenCV could not open {source} for subject tracking")
        step_ms = 1000 / self.sample_fps
        cuts = sorted(c for c in shot_cuts_ms if in_ms <= c <= out_ms)

        # Single sequential forward pass: collect per-shot detections, mouth-motion energy,
        # and torso HSV histograms so multi-person wide shots select the active speaker instead
        # of locking onto a slightly larger silent listener.
        shot_frames: list[list[dict[str, Any]]] = [[]]
        shot_bounds: list[int] = [in_ms]
        previous_at: int | None = None
        prev_gray: Any = None
        tracker: Any = None
        legacy_prev: int | None = None

        try:
            at = float(in_ms)
            while at < out_ms:
                at_int = round(at)
                if (
                    cuts
                    and previous_at is not None
                    and any(previous_at < c <= at_int for c in cuts)
                ):
                    cut_ms = max(c for c in cuts if previous_at < c <= at_int)
                    shot_frames.append([])
                    shot_bounds.append(cut_ms)
                    prev_gray = None
                    tracker = None
                    legacy_prev = None
                capture.set(cv2.CAP_PROP_POS_MSEC, at)
                ok, frame = capture.read()
                if not ok:
                    break
                height, width = frame.shape[:2]
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces: list[tuple[int, int, int, int]] = []
                if yunet_detector is not None:
                    try:
                        yunet_detector.setInputSize((width, height))
                        _, y_faces = yunet_detector.detect(frame)
                        if y_faces is not None:
                            for f in y_faces:
                                faces.append((int(f[0]), int(f[1]), int(f[2]), int(f[3])))
                    except Exception:
                        faces = []
                if not faces:
                    faces = _detect_haar_faces(cv2, frontal, profile, gray)
                # Drop background noise/blinds in upper edge (y < 8% frame height)
                faces = [f for f in faces if f[1] >= int(height * 0.08)]

                # Track optional OpenCV tracker fallback on single-speaker frames
                tracked_box: tuple[int, int, int, int] | None = None
                max_dist = int(width * 0.35) if legacy_prev is not None else None
                legacy_chosen = choose_face(tuple(faces), legacy_prev, max_distance=max_dist)
                if legacy_chosen is not None:
                    legacy_prev = legacy_chosen[0] + legacy_chosen[2] // 2
                    if self.enable_tracker:
                        if tracker is None:
                            tracker = _create_tracker(cv2)
                        if tracker is not None:
                            try:
                                tracker.init(frame, legacy_chosen)
                            except Exception:
                                tracker = None
                elif self.enable_tracker and tracker is not None:
                    try:
                        tracked_ok, bbox = tracker.update(frame)
                    except Exception:
                        tracked_ok, bbox = False, None
                        tracker = None
                    if tracked_ok and bbox is not None:
                        bx, by, bw, bh = (int(v) for v in bbox)
                        center = bx + bw // 2
                        if (
                            bw > 0
                            and bh > 0
                            and bx + bw <= width
                            and by + bh <= height
                            and (legacy_prev is None or abs(center - legacy_prev) <= width * 0.25)
                        ):
                            tracked_box = (bx, by, bw, bh)
                            legacy_prev = center
                        else:
                            tracker = None
                    else:
                        tracker = None

                face_motions: list[float | None] = (
                    [_lower_face_motion(cv2, prev_gray, gray, f) for f in faces]
                    if prev_gray is not None
                    else [None for _ in faces]
                )
                face_hists = [_torso_hsv_hist(cv2, frame, f) for f in faces]
                shot_frames[-1].append(
                    {
                        "at": at_int,
                        "width": width,
                        "height": height,
                        "faces": faces,
                        "motions": face_motions,
                        "hists": face_hists,
                        "tracked_box": tracked_box,
                    }
                )
                prev_gray = gray
                previous_at = at_int
                at += step_ms
        finally:
            capture.release()

        import numpy as np

        # Cluster spatially distinct faces within each shot and gather close-up histograms
        shot_clusters: list[list[dict[str, Any]]] = []
        shot_single_hist: dict[int, Any] = {}
        for s_idx, frames_in_shot in enumerate(shot_frames):
            clusters: list[dict[str, Any]] = []
            for obs in frames_in_shot:
                sep = max(60, int(obs["width"] * 0.16))
                # Pick at most one (largest) box per existing/new cluster on this frame
                frame_best: dict[int, tuple[tuple[int, int, int, int], float | None, Any]] = {}
                for box, mot, hist in zip(obs["faces"], obs["motions"], obs["hists"], strict=True):
                    cx = box[0] + box[2] // 2
                    match_idx: int | None = None
                    for c_idx, cl in enumerate(clusters):
                        if abs(cx - cl["anchor"]) <= sep:
                            match_idx = c_idx
                            break
                    if match_idx is None:
                        clusters.append(
                            {
                                "anchor": cx,
                                "centers": [],
                                "widths": [],
                                "motions": [],
                                "motion_samples": [],
                                "hists": [],
                            }
                        )
                        match_idx = len(clusters) - 1
                    area = box[2] * box[3]
                    prev_entry = frame_best.get(match_idx)
                    if prev_entry is None or area > prev_entry[0][2] * prev_entry[0][3]:
                        frame_best[match_idx] = (box, mot, hist)
                for c_idx, (box, mot, hist) in frame_best.items():
                    cx = box[0] + box[2] // 2
                    cl = clusters[c_idx]
                    cl["centers"].append(cx)
                    cl["widths"].append(box[2])
                    cl["anchor"] = int(round(float(np.median(cl["centers"]))))
                    if mot is not None:
                        cl["motions"].append(mot)
                        cl["motion_samples"].append((int(obs["at"]), mot))
                    if hist is not None:
                        cl["hists"].append(hist)
            shot_clusters.append(clusters)
            persistent = _filter_person_clusters(clusters)
            if len(persistent) == 1 and persistent[0]["hists"]:
                shot_single_hist[s_idx] = np.mean(persistent[0]["hists"], axis=0)
            elif not persistent and len(clusters) == 1 and clusters[0]["hists"]:
                shot_single_hist[s_idx] = np.mean(clusters[0]["hists"], axis=0)

        shot_has_face = [
            bool(
                any(f[2] * f[3] >= MIN_FACE_AREA for obs in frames_in_shot for f in obs["faces"])
                or any(obs["tracked_box"] is not None for obs in frames_in_shot)
            )
            for frames_in_shot in shot_frames
        ]
        if not any(shot_has_face):
            return ()

        points: list[FocusPoint] = []
        intra_switches: list[int] = []
        motion_fps = min(max(self.sample_fps, 2.0), 5.0)
        for s_idx, frames_in_shot in enumerate(shot_frames):
            if not frames_in_shot:
                continue
            if not shot_has_face[s_idx]:
                # D-361: Frame zero-face cutaway shots inside multi-shot clips via motion saliency
                # instead of blindly holding the prior shot's speaker position.
                shot_start_ms = shot_bounds[s_idx]
                if s_idx + 1 < len(shot_bounds):
                    last_at = int(frames_in_shot[-1]["at"])
                    next_cut = min(
                        (c for c in cuts if c > last_at),
                        default=shot_bounds[s_idx + 1],
                    )
                    shot_end_ms = min(next_cut, shot_bounds[s_idx + 1])
                else:
                    shot_end_ms = out_ms
                if shot_end_ms > shot_start_ms:
                    motion_pts = detect_motion_focus_points(
                        source,
                        shot_start_ms,
                        shot_end_ms,
                        sample_fps=motion_fps,
                    )
                    if motion_pts:
                        entry_ms = (
                            max(shot_start_ms, points[-1].at_ms + 1) if points else shot_start_ms
                        )
                        if entry_ms < shot_end_ms:
                            if points and entry_ms - 1 > points[-1].at_ms:
                                prev_pt = points[-1]
                                points.append(
                                    FocusPoint(
                                        entry_ms - 1,
                                        prev_pt.center_x,
                                        prev_pt.center_y,
                                        prev_pt.face_height,
                                    )
                                )
                            points.append(FocusPoint(entry_ms, motion_pts[0].center_x))
                            for mp in motion_pts:
                                mp_at = min(mp.at_ms, shot_end_ms - 1)
                                if mp_at > points[-1].at_ms:
                                    points.append(FocusPoint(mp_at, mp.center_x))
                            shot_tail_ms = min(int(frames_in_shot[-1]["at"]), shot_end_ms - 1)
                            if shot_tail_ms > points[-1].at_ms:
                                points.append(FocusPoint(shot_tail_ms, points[-1].center_x))
                continue
            adj_hist: Any = None
            if shot_single_hist:
                nearest_idx = min(shot_single_hist.keys(), key=lambda idx: abs(idx - s_idx))
                if nearest_idx != s_idx:
                    adj_hist = shot_single_hist[nearest_idx]
            switch_plan = _intra_shot_speaker_switch(
                cv2, frames_in_shot, shot_clusters[s_idx], adj_hist, step_ms
            )
            default_active_cx = (
                None
                if switch_plan is not None
                else _select_active_cluster_center(cv2, shot_clusters[s_idx], adj_hist)
            )
            previous: int | None = None
            for f_idx, obs in enumerate(frames_in_shot):
                width = obs["width"]
                sep = max(60, int(width * 0.16))
                active_cx = switch_plan[0][f_idx] if switch_plan is not None else default_active_cx
                is_switch_frame = switch_plan is not None and f_idx in switch_plan[1]
                if is_switch_frame:
                    previous = None
                cand_faces: Sequence[tuple[int, int, int, int]] = obs["faces"]
                if active_cx is not None:
                    cand_faces = [
                        f for f in cand_faces if abs((f[0] + f[2] // 2) - active_cx) <= sep
                    ]
                max_dist = int(width * 0.35) if previous is not None else None
                chosen = choose_face(tuple(cand_faces), previous, max_distance=max_dist)
                if is_switch_frame:
                    assert active_cx is not None
                    new_cx = chosen[0] + chosen[2] // 2 if chosen is not None else active_cx
                    new_cy = chosen[1] + chosen[3] // 2 if chosen is not None else None
                    new_h = chosen[3] if chosen is not None else None
                    if points and obs["at"] - 1 > points[-1].at_ms:
                        prev_pt = points[-1]
                        points.append(
                            FocusPoint(
                                obs["at"] - 1,
                                prev_pt.center_x,
                                prev_pt.center_y,
                                prev_pt.face_height,
                            )
                        )
                    points.append(FocusPoint(obs["at"], new_cx, new_cy, new_h))
                    intra_switches.append(int(obs["at"]))
                    previous = new_cx
                elif chosen is not None:
                    center = chosen[0] + chosen[2] // 2
                    points.append(
                        FocusPoint(obs["at"], center, chosen[1] + chosen[3] // 2, chosen[3])
                    )
                    previous = center
                elif active_cx is None and obs["tracked_box"] is not None:
                    bx, by, bw, bh = obs["tracked_box"]
                    center = bx + bw // 2
                    points.append(FocusPoint(obs["at"], center, by + bh // 2, bh))
                    previous = center
                elif previous is not None:
                    # CD-11: Hold last stable confirmed face position rather than dead zone
                    points.append(FocusPoint(obs["at"], previous))
        self.last_intra_shot_switches_ms = tuple(intra_switches)
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
        detector_kind: str = "auto",
        yunet_model_path: Path | None = None,
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
        self.detector_kind = detector_kind
        self.yunet_model_path = yunet_model_path
        self.confirmed_speaker_centers: dict[str, int] = {}

    def track_speakers(
        self,
        source: Path,
        in_ms: int,
        out_ms: int,
        turns: Sequence[Segment],
        shot_cuts_ms: Sequence[int] = (),
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
            self.confirmed_speaker_centers = {}
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

        yunet_detector: Any = None
        if self.detector_kind in ("auto", "yunet"):
            model_file = self.yunet_model_path
            if model_file is None:
                repo_model = (
                    Path(__file__).resolve().parents[2] / "models" / "face_detection_yunet.onnx"
                )
                if repo_model.is_file():
                    model_file = repo_model
            if model_file is not None and model_file.is_file() and hasattr(cv2, "FaceDetectorYN"):
                try:
                    yunet_detector = cv2.FaceDetectorYN.create(
                        str(model_file),
                        "",
                        (320, 320),
                        score_threshold=0.6,
                        nms_threshold=0.3,
                        top_k=10,
                    )
                except Exception:
                    yunet_detector = None

        capture = cv2.VideoCapture(str(source))
        if not capture.isOpened():
            raise RuntimeError(f"OpenCV could not open {source} for speaker tracking")

        step_ms = 1000.0 / self.sample_fps
        points: list[SpeakerFocusPoint] = []
        speaker_face_centers: dict[str, int] = {}
        last_known_center: int | None = None
        prev_gray: Any = None
        previous_at: int | None = None
        cuts = sorted(c for c in shot_cuts_ms if in_ms <= c <= out_ms)

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

                # Reset scene-local cache across shot cuts: identity across cuts requires
                # fresh evidence rather than remembered coordinates, and prev_gray must be reset
                # so cross-shot pixel differences do not trigger false mouth-motion spikes.
                if (
                    cuts
                    and previous_at is not None
                    and any(previous_at < c <= at_int for c in cuts)
                ):
                    speaker_face_centers.clear()
                    last_known_center = None
                    prev_gray = None

                active = [
                    turn for turn in overlapping_turns if turn.start_ms <= at_int < turn.end_ms
                ]
                if not active:
                    prev_gray = gray
                    at += step_ms
                    continue

                active_speaker = active[0].speaker

                faces: list[tuple[int, int, int, int]] = []
                if yunet_detector is not None:
                    try:
                        yunet_detector.setInputSize((width, height))
                        _, y_faces = yunet_detector.detect(frame)
                        if y_faces is not None:
                            for f in y_faces:
                                faces.append((int(f[0]), int(f[1]), int(f[2]), int(f[3])))
                    except Exception:
                        faces = []
                if not faces:
                    faces = boxes(frontal, gray) + boxes(profile, gray)
                    faces += [
                        (width - (x + w), y, w, h)
                        for x, y, w, h in boxes(profile, cv2.flip(gray, 1))
                    ]
                valid_faces = [
                    f
                    for f in faces
                    if f[2] * f[3] >= self.min_face_area and f[1] >= int(height * 0.08)
                ]

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
                point_state = "speaker"
                point_is_speaking = True
                point_confidence = 1.0

                if len(deduped_faces) == 1:
                    face = deduped_faces[0]
                    fx, fy, fw, fh = face
                    cx = fx + fw // 2
                    selected_center = cx

                    my = max(0, fy + 2 * fh // 3)
                    mh = min(height - my, fh // 3)
                    mx = max(0, fx)
                    mw = min(width - mx, fw)

                    motion_val = 0.0
                    has_motion = False
                    if prev_gray is not None and mh > 0 and mw > 0:
                        curr_mouth = gray[my : my + mh, mx : mx + mw]
                        prev_mouth = prev_gray[my : my + mh, mx : mx + mw]
                        if curr_mouth.shape == prev_mouth.shape:
                            diff = cv2.absdiff(curr_mouth, prev_mouth)
                            motion_val = float(diff.mean())
                            has_motion = True

                    other_speakers = [
                        spk
                        for spk, sc in speaker_face_centers.items()
                        if spk != active_speaker and abs(cx - sc) <= fw
                    ]
                    contradicts_active = (
                        active_speaker in speaker_face_centers
                        and abs(cx - speaker_face_centers[active_speaker]) > fw
                    )
                    if other_speakers:
                        point_state = "listener"
                        point_is_speaking = False
                        point_confidence = 0.8
                    elif contradicts_active:
                        # The visible face is at a spatial location contradictory to active
                        # speaker's confirmed position on this continuous shot: listener reaction.
                        point_state = "listener"
                        point_is_speaking = False
                        point_confidence = 0.7
                    elif has_motion:
                        if motion_val >= self.motion_threshold:
                            point_state = "speaker"
                            point_is_speaking = True
                            speaker_face_centers[active_speaker] = cx
                            last_known_center = cx
                        else:
                            # Mouth is quiet: do NOT equate lone face with active speaker.
                            point_state = "listener"
                            point_is_speaking = False
                            point_confidence = 0.5
                    else:
                        # First frame: no motion measurement yet.
                        if active_speaker in speaker_face_centers:
                            if abs(cx - speaker_face_centers[active_speaker]) <= fw:
                                point_state = "speaker"
                                point_is_speaking = True
                                point_confidence = 0.8
                                last_known_center = cx
                            else:
                                point_state = "unknown"
                                point_is_speaking = False
                                point_confidence = 0.4
                        else:
                            point_state = "unknown"
                            point_is_speaking = False
                            point_confidence = 0.4
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
                    best_cx = best_face[0] + best_face[2] // 2
                    is_other_speaker = any(
                        spk != active_speaker and abs(best_cx - sc) <= best_face[2]
                        for spk, sc in speaker_face_centers.items()
                    )
                    contradicts_active_multi = (
                        active_speaker in speaker_face_centers
                        and abs(best_cx - speaker_face_centers[active_speaker]) > best_face[2]
                    )

                    if (
                        best_motion >= self.motion_threshold
                        and (
                            second_motion == 0.0
                            or best_motion >= second_motion * self.ambiguity_ratio
                        )
                        and not is_other_speaker
                        and not contradicts_active_multi
                    ):
                        selected_center = best_cx
                        speaker_face_centers[active_speaker] = selected_center
                        last_known_center = selected_center
                        point_state = "speaker"
                        point_is_speaking = True
                        point_confidence = 1.0
                    else:
                        # Ambiguous: hold active speaker's confirmed position if available
                        point_is_speaking = False
                        if active_speaker in speaker_face_centers:
                            known = speaker_face_centers[active_speaker]
                            closest_face = min(
                                deduped_faces,
                                key=lambda f: abs((f[0] + f[2] // 2) - known),
                            )
                            selected_center = closest_face[0] + closest_face[2] // 2
                            point_state = "listener" if is_other_speaker else "unknown"
                            point_confidence = 0.6
                        elif last_known_center is not None:
                            target_x = last_known_center
                            closest_face = min(
                                deduped_faces,
                                key=lambda f: abs((f[0] + f[2] // 2) - target_x),
                            )
                            selected_center = closest_face[0] + closest_face[2] // 2
                            point_state = "listener" if is_other_speaker else "unknown"
                            point_confidence = 0.4
                        else:
                            largest_face = max(deduped_faces, key=lambda f: f[2] * f[3])
                            selected_center = largest_face[0] + largest_face[2] // 2
                            point_state = "listener" if is_other_speaker else "unknown"
                            point_confidence = 0.3
                else:
                    point_state = "off_screen"
                    point_is_speaking = False
                    point_confidence = 0.5
                    selected_center = speaker_face_centers.get(active_speaker)

                if selected_center is not None:
                    points.append(
                        SpeakerFocusPoint(
                            at_ms=at_int,
                            center_x=selected_center,
                            speaker=active_speaker,
                            state=point_state,
                            is_speaking=point_is_speaking,
                            confidence=point_confidence,
                        )
                    )
                    previous_at = at_int

                prev_gray = gray
                at += step_ms
        finally:
            capture.release()

        self.confirmed_speaker_centers = dict(speaker_face_centers)
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


def per_shot_face_boxes(
    points: Sequence[FocusPoint],
    shot_cuts_ms: Sequence[int] = (),
    clip_in_ms: int = 0,
    clip_out_ms: int | None = None,
) -> tuple[tuple[int, int, int | None, int | None], ...]:
    """Compute (start_ms, end_ms, center_y, face_height) per camera shot interval.

    When shot_cuts_ms is empty, returns a single interval for the whole clip.
    When camera cuts exist within the clip, each shot gets its own median face box,
    enabling adaptive zoom on wide shots without vertical shimmer within shots. D-281.
    """
    if not points:
        end_ms = clip_out_ms if clip_out_ms is not None else clip_in_ms
        return ((clip_in_ms, end_ms, None, None),)

    end_ms = clip_out_ms if clip_out_ms is not None else max(p.at_ms for p in points)
    global_y, global_h = median_face_box(points)

    cuts_in_range = sorted(c for c in shot_cuts_ms if clip_in_ms < c < end_ms)
    if not cuts_in_range:
        return ((clip_in_ms, end_ms, global_y, global_h),)

    boundaries = [clip_in_ms, *cuts_in_range, end_ms]
    results: list[tuple[int, int, int | None, int | None]] = []
    for s_in, s_out in pairwise(boundaries):
        shot_pts = [p for p in points if s_in <= p.at_ms < s_out]
        if shot_pts:
            s_y, s_h = median_face_box(shot_pts)
            results.append(
                (
                    s_in,
                    s_out,
                    s_y if s_y is not None else global_y,
                    s_h if s_h is not None else global_h,
                )
            )
        else:
            results.append((s_in, s_out, global_y, global_h))
    return tuple(results)


def stabilize(
    points: Sequence[FocusPoint],
    *,
    dead_zone_px: int,
    move_ms: int = DEFAULT_MOVE_MS,
    settle_ms: int = DEFAULT_SETTLE_MS,
    shot_cuts_ms: Sequence[int] = (),
    max_pan_px: int | None = None,
    cut_on_max_pan: bool = False,
    edge_guard_px: int | None = None,
    edge_settle_ms: int = 250,
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

    When `edge_guard_px` is set and the subject drifts at least `edge_guard_px` from the held
    centre (leaning toward the crop boundary, D-361), the shorter `edge_settle_ms` window and
    a faster smooth follow (`min(move_ms, 350)`) engage so the camera follows before the face
    is clipped, while staying 100% tripod-locked inside `dead_zone_px`.

    Across Stage 0 shot cuts, changes are executed as instant cut steps rather than slow
    interpolated pans, preventing jarring camera movement over scene transitions or empty
    furniture across wide two-shots.

    The result is a keyframe list, not a sample list: a pair of equal values spans a hold and
    a pair of differing values spans a move, which is exactly what `render.crop_filter`
    interpolates between. Empty in, empty out — a clip with no track is a static centre crop,
    and this must never invent one.

    Raises:
        ValueError: a non-positive dead zone, edge guard, or duration, or timestamps that do
            not increase.
    """
    if dead_zone_px <= 0:
        raise ValueError("dead zone must be positive")
    if move_ms <= 0:
        raise ValueError("camera move duration must be positive")
    if settle_ms <= 0:
        raise ValueError("settle duration must be positive")
    if edge_guard_px is not None and edge_guard_px <= 0:
        raise ValueError("edge guard must be positive")
    if edge_settle_ms <= 0:
        raise ValueError("edge settle duration must be positive")
    if not points:
        return ()
    for earlier, later in pairwise(points):
        if later.at_ms <= earlier.at_ms:
            raise ValueError("focus point timestamps must be strictly increasing")

    held = points[0].center_x
    keyframes: list[FocusPoint] = [FocusPoint(points[0].at_ms, held)]
    pending: list[FocusPoint] = []
    cuts = sorted(c for c in shot_cuts_ms if points[0].at_ms <= c <= points[-1].at_ms)
    prev_point = points[0]

    for point in points[1:]:
        recent_cuts = [c for c in cuts if keyframes[-1].at_ms < c <= point.at_ms]
        is_explicit_step = (
            1 <= point.at_ms - prev_point.at_ms <= 2
            and abs(prev_point.center_x - held) <= dead_zone_px
        )

        if abs(point.center_x - held) <= dead_zone_px:
            # Back inside the dead zone: whatever was building was a wobble, not a move.
            pending.clear()
            prev_point = point
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
            prev_point = point
            continue

        # Preserve explicit <= 2 ms intra-shot hard-cut steps emitted by active-speaker switching
        if is_explicit_step:
            target = point.center_x
            if prev_point.at_ms > keyframes[-1].at_ms:
                keyframes.append(FocusPoint(prev_point.at_ms, held))
            keyframes.append(FocusPoint(max(point.at_ms, keyframes[-1].at_ms + 1), target))
            held = target
            pending.clear()
            prev_point = point
            continue

        in_edge_danger = edge_guard_px is not None and abs(point.center_x - held) >= edge_guard_px
        effective_settle_ms = min(settle_ms, edge_settle_ms) if in_edge_danger else settle_ms
        if point.at_ms - pending[0].at_ms < effective_settle_ms:
            prev_point = point
            continue
        centers = sorted(candidate.center_x for candidate in pending)
        target = centers[len(centers) // 2]
        start = pending[0].at_ms
        effective_move_ms = min(move_ms, 350) if in_edge_danger else move_ms

        cuts_in_move = [c for c in cuts if start <= c <= start + effective_move_ms]

        # Prevent slow panning across distant empty space on a continuous shot
        if not cuts_in_move and max_pan_px is not None and abs(target - held) > max_pan_px:
            if cut_on_max_pan:
                if start > keyframes[-1].at_ms:
                    keyframes.append(FocusPoint(start, held))
                keyframes.append(FocusPoint(max(start + 1, keyframes[-1].at_ms + 1), target))
                held = target
            pending.clear()
            prev_point = point
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
            keyframes.append(
                FocusPoint(max(start + effective_move_ms, keyframes[-1].at_ms + 1), target)
            )
        held = target
        pending.clear()
        prev_point = point

    last = points[-1].at_ms
    if last > keyframes[-1].at_ms:
        keyframes.append(FocusPoint(last, held))
    return tuple(keyframes)


def detect_motion_focus_points(
    source: Path,
    in_ms: int,
    out_ms: int,
    *,
    sample_fps: float = 2.0,
) -> tuple[FocusPoint, ...]:
    """Track non-face visual action via OpenCV frame-difference motion saliency (D-357).

    Computes the energy-weighted horizontal centroid of inter-frame luma differences across
    ``[in_ms, out_ms)`` and passes the raw centroid track through :func:`stabilize`. Returns
    an empty tuple when the span is visually static so callers never fabricate motion.
    """
    _exact_non_negative_int(in_ms, "motion-tracking in-point")
    _exact_non_negative_int(out_ms, "motion-tracking out-point")
    if out_ms <= in_ms:
        raise ValueError(f"motion-tracking span has no duration: {in_ms}..{out_ms}ms")
    if sample_fps <= 0 or not math.isfinite(sample_fps):
        raise ValueError("motion-tracking fps must be finite and positive")

    try:
        import cv2 as imported_cv2
    except ImportError as exc:
        raise RuntimeError("motion tracking needs the media extra (OpenCV)") from exc
    import numpy as np

    cv2: Any = imported_cv2
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise RuntimeError(f"OpenCV could not open {source} for motion tracking")

    step_ms = 1000.0 / sample_fps
    raw_points: list[FocusPoint] = []
    prev_blur: Any = None
    previous_at: int | None = None
    frame_width = 0
    frame_height = 0

    try:
        at = float(in_ms)
        while at < out_ms:
            at_int = round(at)
            if at_int >= out_ms:
                break
            if previous_at is not None and at_int <= previous_at:
                at_int = previous_at + 1
                if at_int >= out_ms:
                    break
            capture.set(cv2.CAP_PROP_POS_MSEC, at)
            ok, frame = capture.read()
            if not ok or frame is None:
                break
            height, width = frame.shape[:2]
            frame_width, frame_height = width, height
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            det_w = min(width, 480)
            scale = det_w / float(width)
            if det_w < width:
                det_h = max(1, int(round(height * scale)))
                small = cv2.resize(gray, (det_w, det_h), interpolation=cv2.INTER_AREA)
            else:
                small = gray
            blur = cv2.GaussianBlur(small, (5, 5), 0)

            if prev_blur is not None and blur.shape == prev_blur.shape:
                diff = cv2.absdiff(prev_blur, blur)
                active_mask = diff >= 18
                active_count = int(np.count_nonzero(active_mask))
                if active_count > 0:
                    active_ratio = active_count / float(diff.size)
                    mean_active = float(diff[active_mask].mean())
                    if active_ratio >= 0.001 and mean_active >= 20.0:
                        weights = np.where(active_mask, diff.astype(np.float64), 0.0)
                        col_weights = weights.sum(axis=0)
                        total_w = float(col_weights.sum())
                        if total_w > 0.0:
                            xs = np.arange(det_w, dtype=np.float64)
                            cx_small = float(np.dot(col_weights, xs) / total_w)
                            cx = max(0, min(width - 1, round(cx_small / scale)))
                            raw_points.append(FocusPoint(at_int, cx))
                            previous_at = at_int

            prev_blur = blur
            at += step_ms
    finally:
        capture.release()

    if not raw_points:
        return ()
    crop_w = min(frame_width, max(2, int(frame_height * 9 / 16)))
    return stabilize(
        raw_points,
        dead_zone_px=max(1, crop_w // 8),
        move_ms=DEFAULT_MOVE_MS,
        settle_ms=DEFAULT_SETTLE_MS,
    )


def detect_rapid_speaker_exchange(
    turns: Sequence[Segment],
    in_ms: int,
    out_ms: int,
    *,
    max_turn_duration_ms: int = 4000,
    min_turns: int = 3,
) -> bool:
    """Detect whether an interval contains a rapid conversational exchange between >= 2 speakers.

    Task T2.12: When diarization shows rapid conversational banter (turns < 4.0s),
    offering a two-person stacked split-screen avoids dizzying whip-pans or rapid alternating cuts.

    Args:
        turns: Diarization segments (must be exclusive).
        in_ms: Start timestamp in milliseconds.
        out_ms: End timestamp in milliseconds.
        max_turn_duration_ms: Maximum duration of a turn to count as rapid (default 4000ms).
        min_turns: Minimum number of rapid alternating turns within the interval (default 3).

    Returns:
        True if at least min_turns alternating turns by >= 2 distinct speakers occur
        within [in_ms, out_ms] where each turn duration <= max_turn_duration_ms.
    """
    _exact_non_negative_int(in_ms, "rapid-exchange in-point")
    _exact_non_negative_int(out_ms, "rapid-exchange out-point")
    if out_ms <= in_ms:
        raise ValueError(f"span has no duration: {in_ms}..{out_ms}ms")
    if max_turn_duration_ms <= 0:
        raise ValueError("max_turn_duration_ms must be positive")
    if min_turns < 2:
        raise ValueError("min_turns must be at least 2")

    assert_exclusive(turns)

    # Filter turns overlapping the span
    span_turns = [t for t in turns if t.start_ms < out_ms and t.end_ms > in_ms]
    if len(span_turns) < min_turns:
        return False

    speakers = {t.speaker for t in span_turns}
    if len(speakers) < 2:
        return False

    rapid_count = 0
    prev_speaker: str | None = None
    for turn in span_turns:
        effective_start = max(turn.start_ms, in_ms)
        effective_end = min(turn.end_ms, out_ms)
        dur = effective_end - effective_start
        if dur <= max_turn_duration_ms:
            if prev_speaker is not None and turn.speaker != prev_speaker:
                rapid_count += 1
            elif prev_speaker is None:
                rapid_count = 1
            prev_speaker = turn.speaker
        else:
            if rapid_count >= min_turns:
                return True
            rapid_count = 0
            prev_speaker = None

    return rapid_count >= min_turns


def compute_two_person_split_crops(
    source_width: int,
    source_height: int,
    top_center_x: int,
    bottom_center_x: int,
    *,
    target_width: int = 1080,
    target_height: int = 1920,
    pane_aspect_ratio: float = 1080.0 / 960.0,
    top_center_y: int | None = None,
    bottom_center_y: int | None = None,
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    """Compute crop bounding boxes (x, y, w, h) for top and bottom split-screen panes.

    Task T2.12: Each pane in a 1080x1920 canvas has dimensions 1080x960 (aspect ratio 9:8 = 1.125).
    Extracts a 9:8 aspect ratio window from source video centered horizontally on each speaker's
    face and framed naturally.

    Args:
        source_width: Width of the source video frame.
        source_height: Height of the source video frame.
        top_center_x: Horizontal center of top speaker's face in source coordinates.
        bottom_center_x: Horizontal center of bottom speaker's face in source coordinates.
        target_width: Final canvas width (default 1080).
        target_height: Final canvas height (default 1920).
        pane_aspect_ratio: Aspect ratio of each pane (w/h, default 1080/960 = 1.125).
        top_center_y: Optional vertical face center for top speaker.
        bottom_center_y: Optional vertical face center for bottom speaker.

    Returns:
        ((top_x, top_y, top_w, top_h), (bot_x, bot_y, bot_w, bot_h))
    """
    if source_width <= 0 or source_height <= 0:
        raise ValueError(f"source dimensions must be positive: {source_width}x{source_height}")
    if target_width <= 0 or target_height <= 0:
        raise ValueError(f"target dimensions must be positive: {target_width}x{target_height}")
    if pane_aspect_ratio <= 0:
        raise ValueError(f"pane_aspect_ratio must be positive: {pane_aspect_ratio}")

    pane_crop_h = min(source_height, int(round(source_width / pane_aspect_ratio)))
    pane_crop_w = int(round(pane_crop_h * pane_aspect_ratio))
    if pane_crop_w > source_width:
        pane_crop_w = source_width
        pane_crop_h = int(round(pane_crop_w / pane_aspect_ratio))

    def _crop_for_center(cx: int, cy: int | None) -> tuple[int, int, int, int]:
        left = int(round(cx - pane_crop_w / 2.0))
        left = max(0, min(left, source_width - pane_crop_w))
        if cy is None:
            top = 0
        else:
            top = int(round(cy - pane_crop_h * 0.38))
            top = max(0, min(top, source_height - pane_crop_h))
        return (left, top, pane_crop_w, pane_crop_h)

    top_crop = _crop_for_center(top_center_x, top_center_y)
    bot_crop = _crop_for_center(bottom_center_x, bottom_center_y)
    return top_crop, bot_crop


def layout_policy(
    points: Sequence[SpeakerFocusPoint],
    turns: Sequence[Segment],
    in_ms: int,
    out_ms: int,
    *,
    dead_zone_px: int = 100,
    min_dwell_ms: int = DEFAULT_MIN_DWELL_MS,
    move_ms: int = DEFAULT_MOVE_MS,
    settle_ms: int = DEFAULT_SETTLE_MS,
    shot_cuts_ms: Sequence[int] = (),
    max_pan_px: int | None = None,
    cut_on_max_pan: bool = True,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    edge_guard_px: int | None = None,
) -> tuple[FocusPoint, ...]:
    """Derive stable camera keyframes obeying persistence policy on brief variations.

    Task T11 (AC-17 / §3 Stage 6 / VE-08):
    When speaker evidence varies briefly (e.g. short interjections, backchannels, or listener
    reactions < min_dwell_ms) or becomes ambiguous (state != "speaker" or confidence <
    min_confidence), the camera holds the established speaker's position rather than jittering
    or whip-cutting. When a turn change is verified and sustained (duration >= min_dwell_ms with
    verified speaker evidence), the camera transitions cleanly at the sustained turn boundary.

    Scene shot cuts (shot_cuts_ms) reset spatial identity across the cut and step instantaneously.
    """
    _exact_non_negative_int(in_ms, "layout policy in-point")
    _exact_non_negative_int(out_ms, "layout policy out-point")
    if out_ms <= in_ms:
        raise ValueError(f"span has no duration: {in_ms}..{out_ms}ms")
    if dead_zone_px <= 0:
        raise ValueError("dead zone must be positive")
    if min_dwell_ms <= 0:
        raise ValueError("min_dwell_ms must be positive")
    if move_ms <= 0:
        raise ValueError("camera move duration must be positive")
    if settle_ms <= 0:
        raise ValueError("settle duration must be positive")
    if not (0.0 <= min_confidence <= 1.0):
        raise ValueError("min_confidence must be in [0.0, 1.0]")

    assert_exclusive(turns)

    if not points:
        return ()

    for p in points:
        if not isinstance(p, SpeakerFocusPoint):
            raise TypeError("points must contain only SpeakerFocusPoint values")
        if not (in_ms <= p.at_ms < out_ms):
            raise ValueError(f"point at {p.at_ms} ms is outside clip range [{in_ms}, {out_ms})")

    for earlier, later in pairwise(points):
        if later.at_ms <= earlier.at_ms:
            raise ValueError("focus point timestamps must be strictly increasing")

    overlapping_turns = tuple(t for t in turns if t.start_ms < out_ms and t.end_ms > in_ms)
    if not overlapping_turns:
        return ()

    cuts = sorted(c for c in shot_cuts_ms if in_ms <= c <= out_ms)
    # Observed shots need their own speaking evidence; coordinates cannot cross scene cuts.
    observed_shots: dict[int, bool] = {}
    for p in points:
        active = next((t for t in overlapping_turns if t.start_ms <= p.at_ms < t.end_ms), None)
        if active is None:
            continue
        shot = bisect_right(cuts, p.at_ms)
        verified = (
            p.speaker == active.speaker
            and p.state == "speaker"
            and p.is_speaking
            and p.confidence >= min_confidence
        )
        observed_shots[shot] = observed_shots.get(shot, False) or verified
    if not all(observed_shots.values()):
        return ()

    # Identify sustained speaker cut boundaries
    sustained_speaker_cuts: list[int] = []
    prev_turn_speaker: str | None = None
    for turn in overlapping_turns:
        eff_start = max(turn.start_ms, in_ms)
        eff_end = min(turn.end_ms, out_ms)
        dur = eff_end - eff_start
        if (
            eff_start > in_ms
            and prev_turn_speaker is not None
            and turn.speaker != prev_turn_speaker
        ):
            if dur >= min_dwell_ms:
                has_verified = any(
                    p.speaker == turn.speaker
                    and p.state == "speaker"
                    and p.is_speaking
                    and p.confidence >= min_confidence
                    for p in points
                    if eff_start <= p.at_ms < eff_end
                )
                if has_verified:
                    sustained_speaker_cuts.append(eff_start)
                    prev_turn_speaker = turn.speaker
        else:
            if prev_turn_speaker is None or dur >= min_dwell_ms:
                prev_turn_speaker = turn.speaker

    all_cuts = sorted(set(cuts) | set(sustained_speaker_cuts))

    filtered_points: list[FocusPoint] = []
    held_center: int | None = None
    established_speaker: str | None = None
    last_pt_time: int | None = None

    for p in points:
        # Reset spatial continuity across scene cuts
        if cuts and last_pt_time is not None and any(last_pt_time < c <= p.at_ms for c in cuts):
            held_center = None
            established_speaker = None

        active_turns = [t for t in overlapping_turns if t.start_ms <= p.at_ms < t.end_ms]
        if not active_turns:
            continue
        active_turn = active_turns[0]
        eff_start = max(active_turn.start_ms, in_ms)
        eff_end = min(active_turn.end_ms, out_ms)
        dur = eff_end - eff_start
        is_turn_sustained = (dur >= min_dwell_ms) or (
            len({t.speaker for t in overlapping_turns}) == 1
        )

        is_verified_speaker = (
            p.speaker == active_turn.speaker
            and p.state == "speaker"
            and p.is_speaking
            and p.confidence >= min_confidence
        )

        resolved_center: int
        if is_turn_sustained and is_verified_speaker:
            resolved_center = p.center_x
            held_center = p.center_x
            established_speaker = active_turn.speaker
        elif not is_turn_sustained and established_speaker is not None and held_center is not None:
            # Transient turn by other speaker: hold the established speaker's position
            resolved_center = held_center
        elif (
            is_turn_sustained
            and established_speaker == active_turn.speaker
            and held_center is not None
        ):
            # Sustained turn by established speaker, but ambiguous frame: hold established center
            resolved_center = held_center
        elif held_center is not None:
            # Ambiguous frame on transition: hold last confirmed center
            resolved_center = held_center
        else:
            if not is_verified_speaker:
                continue
            resolved_center = p.center_x
            held_center = p.center_x
            established_speaker = active_turn.speaker

        filtered_points.append(FocusPoint(p.at_ms, resolved_center))
        last_pt_time = p.at_ms

    if not filtered_points:
        return ()

    return stabilize(
        filtered_points,
        dead_zone_px=dead_zone_px,
        move_ms=move_ms,
        settle_ms=settle_ms,
        shot_cuts_ms=all_cuts,
        max_pan_px=max_pan_px,
        cut_on_max_pan=cut_on_max_pan,
        edge_guard_px=edge_guard_px,
    )
