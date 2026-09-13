"""§2's delivery set — the SRT sidecar and the EDL.

§2's architecture diagram ends with what leaves the system:

    MP4 · SRT/ASS · editing JSON · EDL

MP4 is `render.py`, ASS is `captions.py`, and the editing JSON is §5's clip contract in
`clip.py`. SRT and EDL were never built, so two of the four things §2 says this system delivers
did not exist.

They are written here together because they are **opposites about time**, and getting that
backwards produces a file that is well-formed and wrong:

*An SRT ships beside the MP4.* Its timeline is the clip's — t=0 is the first frame of the
delivered file. This is the trap M3.5 found in the ASS path, where source-absolute timestamps
produced a valid, playable, entirely caption-free clip. Both subtitle formats now take the
same `clip_in_ms` and refuse the same out-of-window sentence.

*An EDL describes where the clip came from.* Its source timecodes are the source's, and only
its record timecodes start at zero. An EDL written in clip time tells an editor to conform
footage from the top of the episode, and nothing about the file looks wrong.

An EDL also counts **frames**, not milliseconds, so it cannot be written without the rate.
NTSC 30000/1001 and 60000/1001 are emitted as SMPTE drop-frame timecode; other fractional rates
are refused rather than rounded into a slowly drifting conform.

The SRT shares §4.3.5's line breaking with the ASS for the same reason it shares the clip
offset: automatic wrapping on RTL text produces bad break points. A player wraps whatever it
is handed, so a cue emitted as one long line hands that decision to a wrapper that has no word
alignment (D-151).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import re
from collections.abc import Sequence
from dataclasses import replace
from enum import Enum
from pathlib import Path
from typing import Any, Final

from hawedit.artifact_bundle import ArtifactBundle, BundleError
from hawedit.boundary import BoundaryInvariantViolated, assert_boundary_invariant
from hawedit.captions import (
    DEFAULT_MAX_CHARS_PER_LINE,
    CaptionVerificationError,
    verify_caption_integrity,
    wrap_caption_lines,
)
from hawedit.clip import Clip, Qc, QcRecord
from hawedit.measure import ClipMeasurement
from hawedit.sentences import Sentence, assert_deliverable_order
from hawedit.timeline import build_episode_otio_timeline, build_otio_timeline, serialize_otio

__all__ = [
    "CandidateState",
    "DeliveryError",
    "DeliveryRefused",
    "build_edl",
    "build_srt",
    "ms_to_srt_time",
    "ms_to_timecode",
    "parse_srt_times",
    "promote_candidate",
    "publish_delivery_bundle",
    "publish_episode_timeline",
    "reconcile_delivery",
]

_SRT_TIME = re.compile(
    r"(\d+):([0-5]\d):([0-5]\d),(\d{3})\s*-->\s*"
    r"(\d+):([0-5]\d):([0-5]\d),(\d{3})"
)


class DeliveryError(ValueError):
    """A sidecar this module would not be able to ship honestly."""


class DeliveryRefused(DeliveryError):
    """Refusal of delivery when independent measurement contradicts contract claims."""

    def __init__(self, reason: str, expected: Any, measured: Any) -> None:
        super().__init__(f"{reason}: expected {expected!r}, measured {measured!r}")
        self.reason = reason
        self.expected = expected
        self.measured = measured


class CandidateState(str, Enum):
    """Lifecycle states of a clip candidate (Phase 1 / ADR D-264)."""

    DRAFT = "draft"
    RENDERED_FOR_REVIEW = "rendered_for_review"
    REJECTED = "rejected"
    APPROVED = "approved"
    PUBLISHED = "published"
    FAILED = "failed"


def _nonnegative_milliseconds(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DeliveryError(f"{label} must be a non-negative integer number of milliseconds")
    if value < 0:
        raise DeliveryError(
            f"{label} cannot be negative, got {value} ms. SRT and SMPTE time fields are "
            "unsigned; formatting this value would emit plausible-looking nonsense."
        )
    return value


def ms_to_srt_time(milliseconds: int) -> str:
    """`HH:MM:SS,mmm`.

    The separator is a **comma**. A period is WebVTT, and a player expecting SRT either
    rejects the file or mis-parses the cue — either way the subtitles do not appear and
    nothing says so. Negative, boolean, fractional and string values are refused as domain
    errors instead of leaking Python arithmetic errors or producing a plausible wrong timestamp.
    """
    milliseconds = _nonnegative_milliseconds(milliseconds, "SRT timestamp")
    seconds, milliseconds = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def parse_srt_times(srt_text: str) -> tuple[tuple[int, int], ...]:
    """Every cue's `(start_ms, end_ms)`, refusing malformed or silently dropped cues.

    This reader validates the grammar position rather than searching the whole block for a
    timestamp. Hunting for the first ``-->`` can skip a malformed timing line and reinterpret
    caption text as timing, while a global regex silently returns fewer cues. Both make a broken
    delivery look valid to the pipeline check that reads the SRT back.
    """
    if not isinstance(srt_text, str):
        raise DeliveryError("SRT content must be text")
    body = srt_text.strip()
    if not body:
        return ()
    blocks = re.split(r"\r?\n(?:[ \t]*\r?\n)+", body)
    times: list[tuple[int, int]] = []
    for expected_index, block in enumerate(blocks, start=1):
        lines = block.splitlines()
        if len(lines) < 2:
            preview = block[:120].replace("\r", " ").replace("\n", " ")
            raise DeliveryError(
                f"SRT cue {expected_index} has no timing line: {preview!r}. Skipping it would "
                "report fewer cues than the file contains."
            )
        label = lines[0].strip()
        if label != str(expected_index):
            raise DeliveryError(
                f"SRT cue index is {label[:40]!r}; expected {expected_index}. Cue indices must "
                "be one-based and sequential so omissions are visible."
            )
        timing = lines[1].strip()
        match = _SRT_TIME.fullmatch(timing)
        if match is None:
            raise DeliveryError(
                f"SRT cue {expected_index} has an unreadable timing line: {timing[:120]!r}. "
                "Skipping it would report fewer cues than the file contains."
            )
        h1, m1, s1, ms1, h2, m2, s2, ms2 = match.groups()
        start = ((int(h1) * 60 + int(m1)) * 60 + int(s1)) * 1000 + int(ms1)
        end = ((int(h2) * 60 + int(m2)) * 60 + int(s2)) * 1000 + int(ms2)
        if end <= start:
            raise DeliveryError(
                f"SRT cue {expected_index} ends at {end} ms and does not end after its "
                f"{start} ms start"
            )
        times.append((start, end))
    return tuple(times)


def build_srt(
    sentences: Sequence[Sentence],
    clip_in_ms: int,
    clip_duration_ms: int | None = None,
    max_chars_per_line: int = DEFAULT_MAX_CHARS_PER_LINE,
) -> str:
    """The SRT sidecar for one clip, on the clip's own timeline.

    Text is the **raw** surface forms, as the ASS is: a viewer sees what was said, not the
    index's normalized form (Kurdish invariant #3 runs the other way).

    Lines are broken from the word alignment by the same `wrap_caption_lines` the ASS uses
    (§4.3.5). SRT has no `WrapStyle` to disable, so the only way to keep the break points is to
    emit them; a single-line cue delegates them to the player.

    Raises:
        DeliveryError: no sentences, a sentence that never closed, or one outside the clip.
        UndeliverableOrder: cues that overlap, run backwards, or end before they start —
            checked before any cue is written, because SRT is read in order (D-165).
    """
    clip_in_ms = _nonnegative_milliseconds(clip_in_ms, "SRT clip in-point")
    if clip_duration_ms is not None:
        clip_duration_ms = _nonnegative_milliseconds(clip_duration_ms, "SRT clip duration")
    if not sentences:
        raise DeliveryError(
            "no sentences to write: an empty SRT is a valid file that delivers no subtitles"
        )
    assert_deliverable_order(sentences)
    cues: list[str] = []
    for index, sentence in enumerate(sentences, start=1):
        if not sentence.complete:
            raise DeliveryError(
                f"sentence at {sentence.start_ms} ms is not complete — reject, never ship "
                f"(Kurdish invariant #2). A fragment in the sidecar is a fragment delivered."
            )
        if sentence.start_ms < clip_in_ms:
            raise DeliveryError(
                f"sentence at {sentence.start_ms} ms starts before the clip does "
                f"({clip_in_ms} ms): it is speech this clip does not contain."
            )
        if clip_duration_ms is not None and sentence.end_ms - clip_in_ms > clip_duration_ms:
            raise DeliveryError(
                f"sentence ending at {sentence.end_ms} ms runs past the end of the clip "
                f"({clip_in_ms + clip_duration_ms} ms)."
            )
        start = ms_to_srt_time(sentence.start_ms - clip_in_ms)
        end = ms_to_srt_time(sentence.end_ms - clip_in_ms)
        text = "\n".join(
            " ".join(word.w for word in line)
            for line in wrap_caption_lines(sentence.words, max_chars=max_chars_per_line)
        )
        cues.append(f"{index}\n{start} --> {end}\n{text}\n")
    return "\n".join(cues) + "\n"


_NTSC_DROP_RATES: Final = ((30, 30_000 / 1_001), (60, 60_000 / 1_001))
_DROP_RATE_TOLERANCE: Final = 1e-4


def _timecode_rate(fps: float) -> tuple[int, float, bool]:
    """Return nominal counter rate, physical frame rate, and drop-frame mode."""
    if isinstance(fps, bool) or not isinstance(fps, int | float):
        raise DeliveryError(f"frame rate must be a finite positive number, got {fps!r}")
    try:
        numeric_fps = float(fps)
    except OverflowError as exc:
        raise DeliveryError("frame rate must be finite, got an out-of-range value") from exc
    if not math.isfinite(numeric_fps) or numeric_fps <= 0:
        raise DeliveryError(f"frame rate must be finite and positive, got {fps}")
    nominal = round(numeric_fps)
    if abs(numeric_fps - nominal) <= 1e-9:
        return nominal, float(nominal), False
    # ffprobe reports exact 30000/1001 or 60000/1001 ratios while user-facing metadata commonly
    # reports 29.97 or 59.94. FFmpeg's maintained SMPTE helper defines both: nominal 30 skips two
    # labels and nominal 60 skips four at every non-tenth minute. The narrow tolerance accepts
    # the conventional decimals but not an arbitrary nearby fractional rate.
    for nominal_rate, physical_rate in _NTSC_DROP_RATES:
        if abs(numeric_fps - physical_rate) <= _DROP_RATE_TOLERANCE:
            return nominal_rate, physical_rate, True
    raise DeliveryError(
        f"fractional frame rate {fps} is unsupported. HawEdit writes SMPTE drop-frame only "
        "for NTSC 30000/1001 (29.97) and 60000/1001 (59.94) fps; rounding another rate "
        "would create a drifting EDL."
    )


def ms_to_timecode(milliseconds: int, fps: float) -> str:
    """SMPTE timecode: non-drop ``HH:MM:SS:FF`` or NTSC drop ``HH:MM:SS;FF``.

    Raises:
        DeliveryError: time is negative, or `fps` is invalid or unsupported.
    """
    milliseconds = _nonnegative_milliseconds(milliseconds, "timecode timestamp")
    nominal, physical, drop_frame = _timecode_rate(fps)
    total_frames = round(milliseconds * physical / 1000)
    return _frames_to_timecode(total_frames, nominal, drop_frame=drop_frame)


def _frames_to_timecode(total_frames: int, rate: int, *, drop_frame: bool = False) -> str:
    if drop_frame:
        # SMPTE EG 35: two time-address counts are skipped at every minute except each tenth.
        # This is the same frame-number adjustment used by FFmpeg's maintained timecode helper.
        drop_frames = rate // 30 * 2
        frames_per_10_minutes = rate // 30 * 17_982
        ten_minute_blocks, remainder = divmod(total_frames, frames_per_10_minutes)
        adjusted = total_frames + 9 * drop_frames * ten_minute_blocks
        if remainder >= drop_frames:
            adjusted += drop_frames * ((remainder - drop_frames) // (frames_per_10_minutes // 10))
        total_frames = adjusted
    frames = total_frames % rate
    seconds = total_frames // rate
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    frame_separator = ";" if drop_frame else ":"
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{frame_separator}{frames:02d}"


_REEL: Final = "AX"  # CMX 3600's "auxiliary" reel: the source is named by the file, not a tape.


def build_edl(
    clip_in_ms: int,
    clip_out_ms: int,
    fps: float,
    title: str = "HAWEDIT CLIP",
    *,
    retained_intervals: Sequence[tuple[int, int]] | None = None,
) -> str:
    """A CMX 3600 EDL for one clip.

    Source timecodes are the **source's** timeline — where this clip was cut from. Record
    timecodes start at zero, because the delivered clip is the whole record timeline. Writing
    the source range in clip time yields a file that conforms the top of the episode and looks
    entirely well-formed.

    When `retained_intervals` is provided (e.g. after dead-air silence excision), distinct edit
    events are emitted for each retained interval, ensuring conforming editors receive exact
    cuts rather than a false continuous source span.

    Raises:
        DeliveryError: the clip has no length, is shorter than a frame, starts before zero,
            or `fps` cannot be represented honestly.
    """
    clip_in_ms = _nonnegative_milliseconds(clip_in_ms, "EDL clip in-point")
    clip_out_ms = _nonnegative_milliseconds(clip_out_ms, "EDL clip out-point")
    if clip_out_ms <= clip_in_ms:
        raise DeliveryError(
            f"clip spans {clip_in_ms}..{clip_out_ms} ms, which has no length; there is nothing "
            f"to conform."
        )
    rate, physical_rate, drop_frame = _timecode_rate(fps)

    intervals: Sequence[tuple[int, int]]
    if retained_intervals is not None:
        if not retained_intervals:
            raise DeliveryError("retained_intervals cannot be empty")
        intervals = retained_intervals
    else:
        intervals = ((clip_in_ms, clip_out_ms),)

    one_line_title = " ".join(title.split())
    lines = [
        f"TITLE: {one_line_title}",
        f"FCM: {'DROP' if drop_frame else 'NON-DROP'} FRAME",
        "",
    ]

    event_num = 1
    cumulative_record_frames = 0

    for seg_in_ms, seg_out_ms in intervals:
        seg_in_ms = _nonnegative_milliseconds(seg_in_ms, "EDL segment in-point")
        seg_out_ms = _nonnegative_milliseconds(seg_out_ms, "EDL segment out-point")
        if seg_out_ms <= seg_in_ms:
            raise DeliveryError(
                f"EDL segment spans {seg_in_ms}..{seg_out_ms} ms, which has no length"
            )
        source_in_frame = round(seg_in_ms * physical_rate / 1000)
        source_out_frame = round(seg_out_ms * physical_rate / 1000)
        duration_frames = source_out_frame - source_in_frame
        if duration_frames < 1:
            raise DeliveryError(
                f"a {seg_out_ms - seg_in_ms} ms segment is less than one frame at {fps} fps"
            )

        source_in = _frames_to_timecode(source_in_frame, rate, drop_frame=drop_frame)
        source_out = _frames_to_timecode(source_out_frame, rate, drop_frame=drop_frame)
        record_in = _frames_to_timecode(cumulative_record_frames, rate, drop_frame=drop_frame)
        record_out = _frames_to_timecode(
            cumulative_record_frames + duration_frames, rate, drop_frame=drop_frame
        )

        for channel in ("V", "A"):
            lines.append(
                f"{event_num:03d}  {_REEL}       {channel}     C        "
                f"{source_in} {source_out} {record_in} {record_out}"
            )
            event_num += 1

        cumulative_record_frames += duration_frames

    return "\n".join(lines) + "\n"


def reconcile_delivery(
    clip: Clip,
    measurement: ClipMeasurement,
    *,
    captions_burned_in: bool = True,
    planned_punch_ins: Sequence[tuple[int, float]] = (),
    source_shot_cuts_ms: Sequence[int] = (),
    fps: float = 25.0,
    delivery_lufs: float = -14.0,
    target_true_peak_db: float = -0.7,
    shot_cut_guard_ms: int = 1500,
    lufs_tolerance: float | None = None,
    min_face_share: float | None = None,
    for_review: bool = False,
) -> None:
    """Reconcile contract claims against independently measured ground truth.

    Raises DeliveryRefused(reason, expected, measured) on any mismatch across the 7
    non-negotiable Level C verification clauses.
    """
    frame_ms = int(round(1000.0 / fps)) if fps > 0 else 40
    # Tolerance is 1 frame plus sub-frame millisecond quantization slack (at 25 fps, 60 ms)
    tolerance_ms = frame_ms + int(round(frame_ms / 2))

    # Clause 1: Duration
    span_ms = clip.out_ms - clip.in_ms
    expected_duration_ms = span_ms - (clip.output.silence_removed_ms if clip.output else 0)
    expected_frames = round(expected_duration_ms * fps / 1000.0)
    measured_frames = measurement.video.frames_count or round(
        measurement.video.duration_ms * fps / 1000.0
    )
    if (
        abs(expected_duration_ms - measurement.video.duration_ms) > tolerance_ms
        or abs(expected_frames - measured_frames) > 1
    ):
        raise DeliveryRefused(
            "duration_mismatch",
            expected=expected_duration_ms,
            measured=measurement.video.duration_ms,
        )

    # Clause 2: Resolution & Geometry (1080x1920 vertical)
    if measurement.video.width != 1080 or measurement.video.height != 1920:
        raise DeliveryRefused(
            "geometry_mismatch",
            expected=(1080, 1920),
            measured=(measurement.video.width, measurement.video.height),
        )

    # Clause 3: Audio Dynamics (LUFS and true-peak)
    if lufs_tolerance is not None:
        effective_lufs_tol = lufs_tolerance
    elif measurement.audio.duration_ms >= 10_000:
        effective_lufs_tol = 0.5
    elif measurement.audio.duration_ms >= 3_000:
        effective_lufs_tol = 2.5
    else:
        # ITU-R BS.1770 / EBU R128 requires 3s minimum integration gating window
        effective_lufs_tol = 5.0
    if abs(measurement.audio.integrated_lufs - delivery_lufs) > effective_lufs_tol:
        raise DeliveryRefused(
            "loudness_violation",
            expected=delivery_lufs,
            measured=measurement.audio.integrated_lufs,
        )
    if measurement.audio.true_peak_db > target_true_peak_db:
        raise DeliveryRefused(
            "true_peak_violation",
            expected=f"<= {target_true_peak_db}",
            measured=measurement.audio.true_peak_db,
        )

    # Clause 4: Silence Removal Math
    expected_silence_removed = clip.output.silence_removed_ms if clip.output else 0
    measured_audio_dur = measurement.audio.duration_ms
    measured_removed = span_ms - measured_audio_dur
    if abs(expected_silence_removed - measured_removed) > tolerance_ms:
        raise DeliveryRefused(
            "silence_math_mismatch",
            expected=expected_silence_removed,
            measured=measured_removed,
        )

    # Clause 5: Visual Cuts and Planned Punch-Ins
    measured_cuts = measurement.scenes.get("cuts_ms", [])
    for at_ms, _ in planned_punch_ins:
        matched = any(abs(at_ms - cut_ms) <= tolerance_ms for cut_ms in measured_cuts)
        if not matched:
            raise DeliveryRefused(
                "missing_punch_in_cut",
                expected=at_ms,
                measured=measured_cuts,
            )

    clip_source_cuts = [
        sc - clip.in_ms for sc in source_shot_cuts_ms if clip.in_ms <= sc <= clip.out_ms
    ]
    punch_in_times = [p[0] for p in planned_punch_ins]
    for cut_ms in measured_cuts:
        near_punch = any(abs(cut_ms - pt) <= tolerance_ms for pt in punch_in_times)
        near_source = any(abs(cut_ms - sc) <= shot_cut_guard_ms for sc in clip_source_cuts)
        if not (near_punch or near_source):
            raise DeliveryRefused(
                "unplanned_rogue_cut",
                expected=f"within {shot_cut_guard_ms}ms of source cut or ±1 frame of punch-in",
                measured=cut_ms,
            )

    # Clause 6: Caption Burn-in Ink Energy
    if captions_burned_in:
        if measurement.captions.ink_energy_detected_share < 0.95:
            raise DeliveryRefused(
                "caption_ink_missing",
                expected=">= 0.95 ink energy share",
                measured=measurement.captions.ink_energy_detected_share,
            )
    elif measurement.captions.ink_energy_detected_share > 0.0:
        raise DeliveryRefused(
            "unexpected_caption_ink",
            expected=0.0,
            measured=measurement.captions.ink_energy_detected_share,
        )

    # Clause 7: Face Tracking In-Frame Presence
    required_face_share = (
        min_face_share
        if min_face_share is not None
        else (0.90 if measurement.video.duration_ms >= 3_000 else 0.50)
    )
    if (
        clip.output
        and clip.output.crop_target == "face_tracked"
        and round(measurement.faces.face_detected_share, 2) < round(required_face_share, 2)
    ):
        raise DeliveryRefused(
            "face_tracking_unsubstantiated",
            expected=f">= {required_face_share:.2f} face detected share",
            measured=measurement.faces.face_detected_share,
        )

    # Clause 7a: Speaking-Frame Face Share (Item 7 / B5)
    if (
        not for_review
        and clip.output
        and clip.output.crop_target == "face_tracked"
        and min_face_share != 0.0
        and measurement.faces.speaking_samples_count > 0
        and round(measurement.faces.speaking_face_share, 2) < 0.98
    ):
        raise DeliveryRefused(
            "speaking_face_share_unsubstantiated",
            expected=">= 0.98 speaking face share",
            measured=measurement.faces.speaking_face_share,
        )

    # Clause 7b: First-Frame Subject Face Gate (Task T2.3)
    if (
        clip.output
        and clip.output.crop_target == "face_tracked"
        and min_face_share is not None
        and min_face_share > 0.0
        and measurement.faces.first_frame_face_share is not None
        and measurement.faces.first_frame_face_share < 0.05
    ):
        raise DeliveryRefused(
            "first_frame_lacks_subject",
            expected=">= 0.05 face share in opening frame",
            measured=measurement.faces.first_frame_face_share,
        )

    # Clause 8: Human Review Binding (Task T1.3 / Register Row 4)
    if (
        not for_review
        and clip.qc
        and clip.qc.human_reviewed
        and clip.qc.reviewed_sha256 is not None
        and clip.qc.reviewed_sha256.lower() != measurement.file.sha256.lower()
    ):
        raise DeliveryRefused(
            "qc_sha256_mismatch",
            expected=measurement.file.sha256.lower(),
            measured=clip.qc.reviewed_sha256.lower(),
        )

    # Clause 9: Provenance & Runtime Alignment (Task T1.6 / Proof C)
    if clip.provenance and clip.provenance.ffmpeg:
        contract_ffmpeg_ver = clip.provenance.ffmpeg.get("version")
        measured_ffmpeg_ver = measurement.tool_metadata.get("ffmpeg_version")
        if (
            contract_ffmpeg_ver
            and measured_ffmpeg_ver
            and contract_ffmpeg_ver not in measured_ffmpeg_ver
            and measured_ffmpeg_ver not in contract_ffmpeg_ver
        ):
            raise DeliveryRefused(
                "ffmpeg_version_mismatch",
                expected=contract_ffmpeg_ver,
                measured=measured_ffmpeg_ver,
            )

    # Clause 10: Production Profile Requirements (Task T1.9)
    if (
        not for_review
        and clip.provenance
        and clip.provenance.profile == "production"
        and not (clip.qc and clip.qc.human_reviewed and clip.qc.reviewed_sha256)
    ):
        raise DeliveryRefused(
            "production_profile_unreviewed",
            expected="valid human review record with sha256 binding in production profile",
            measured="unreviewed or missing qc record",
        )

    # Clause 11: Cover Frame Boundary (Task T4.10)
    if clip.output and clip.output.cover_frame_ms is not None:
        clip_duration_ms = clip.out_ms - clip.in_ms
        is_clip_rel = 0 <= clip.output.cover_frame_ms <= clip_duration_ms
        is_source_abs = clip.in_ms <= clip.output.cover_frame_ms <= clip.out_ms
        if not (is_clip_rel or is_source_abs):
            raise DeliveryRefused(
                "cover_frame_out_of_bounds",
                expected=f"within [0, {clip_duration_ms}] ms or [{clip.in_ms}, {clip.out_ms}] ms",
                measured=clip.output.cover_frame_ms,
            )


def publish_delivery_bundle(
    output_dir: Path,
    clip: Clip,
    source_media_path: str | Path,
    fps: float,
    selected_sentences: Sequence[Sentence] = (),
    punch_ins: tuple[int, ...] = (),
    speaker_turns: tuple[tuple[int, int, str], ...] = (),
    cover_image_path: Path | None = None,
) -> dict[str, Path]:
    """Emit the editorial handoff bundle (EDL, SRT, JSON contract, Resolve OTIO, and cover.png)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, Path] = {}

    edl_text = build_edl(
        clip_in_ms=clip.in_ms,
        clip_out_ms=clip.out_ms,
        fps=fps,
        title=f"HawEdit {clip.clip_id}",
    )
    edl_path = output_dir / f"{clip.clip_id}.edl"
    edl_path.write_text(edl_text, encoding="utf-8")
    results["edl"] = edl_path

    if selected_sentences:
        srt_text = build_srt(
            selected_sentences,
            clip_in_ms=clip.in_ms,
            clip_duration_ms=clip.out_ms - clip.in_ms,
        )
        srt_path = output_dir / f"{clip.clip_id}.srt"
        srt_path.write_text(srt_text, encoding="utf-8")
        results["srt"] = srt_path

    json_path = output_dir / f"{clip.clip_id}.json"
    json_path.write_text(json.dumps(clip.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    results["json"] = json_path

    otio_doc = build_otio_timeline(
        clip=clip,
        source_media_path=str(source_media_path),
        fps=fps,
        punch_ins=punch_ins,
        speaker_turns=speaker_turns,
    )
    otio_path = output_dir / f"{clip.clip_id}.otio"
    otio_path.write_text(serialize_otio(otio_doc), encoding="utf-8")
    results["otio"] = otio_path

    if cover_image_path is not None and cover_image_path.is_file():
        cover_path = output_dir / f"{clip.clip_id}.cover.png"
        cover_path.write_bytes(cover_image_path.read_bytes())
        results["cover"] = cover_path

    return results


def publish_episode_timeline(
    output_dir: Path,
    clips: list[Clip],
    source_media_path: str | Path,
    fps: float,
    episode_title: str = "HawEdit Episode",
) -> Path:
    """Publish an episode-level OpenTimelineIO (.otio) timeline assembling all clips."""
    output_dir.mkdir(parents=True, exist_ok=True)
    otio_doc = build_episode_otio_timeline(
        clips=clips,
        source_media_path=str(source_media_path),
        fps=fps,
        episode_title=episode_title,
    )
    otio_path = output_dir / "timeline.otio"
    otio_path.write_text(serialize_otio(otio_doc), encoding="utf-8")
    return otio_path


def promote_candidate(
    work_dir: Path,
    candidate_id: str,
    qc_record: QcRecord,
    *,
    source: Path | None = None,
    ffmpeg: Path | None = None,
    captions_burned_in: bool | None = None,
    planned_punch_ins: Sequence[tuple[int, float]] = (),
    source_shot_cuts_ms: Sequence[int] = (),
    fps: float = 25.0,
    delivery_lufs: float = -14.0,
    target_true_peak_db: float = -0.7,
    shot_cut_guard_ms: int = 1500,
    lufs_tolerance: float | None = None,
    min_face_share: float | None = None,
) -> tuple[Path, ...]:
    """Verify and promote an unchanged review candidate to public delivery (AC-02).

    Validates:
    - qc_record is approved.
    - review candidate directory exists under work_dir / "review" / candidate_id.
    - candidate MP4 exists and SHA-256 matches qc_record.mp4_sha256.
    - candidate sidecars exist (ass, srt, edl, json, measured.json).
    - candidate editing JSON loads, clip_id matches candidate_id, and assert_renderable()
      holds when bound to approved QC.
    - candidate measured.json loads and matches the MP4 SHA-256.
    - if source is provided, verifies source file exists and matches clip.media_sha256.
    - reconciles delivery against measured truth.
    - atomically publishes the exact candidate files into public work_dir / candidate_id
      using ArtifactBundle without re-rendering.

    Returns:
        tuple[Path, ...]: published artifact paths in work_dir / candidate_id.
    """
    if not qc_record.is_approved:
        raise DeliveryRefused(
            "unapproved_qc_record",
            expected="approved verdict (one of pass, approved, accept, passed)",
            measured=qc_record.verdict,
        )

    review_dir = work_dir / "review" / candidate_id
    if not review_dir.is_dir():
        raise DeliveryError(f"review candidate directory not found: {review_dir}")

    candidate_mp4 = review_dir / f"{candidate_id}.mp4"
    candidate_ass = review_dir / f"{candidate_id}.ass"
    candidate_srt = review_dir / f"{candidate_id}.srt"
    candidate_edl = review_dir / f"{candidate_id}.edl"
    candidate_json = review_dir / f"{candidate_id}.json"
    candidate_measured = review_dir / f"{candidate_id}.measured.json"

    for path in (
        candidate_mp4,
        candidate_ass,
        candidate_srt,
        candidate_edl,
        candidate_json,
        candidate_measured,
    ):
        if not path.is_file():
            raise DeliveryError(f"review candidate is missing required artifact: {path.name}")

    mp4_bytes = candidate_mp4.read_bytes()
    candidate_sha = hashlib.sha256(mp4_bytes).hexdigest().lower()
    if candidate_sha != qc_record.mp4_sha256.lower():
        raise DeliveryRefused(
            "qc_sha256_mismatch",
            expected=qc_record.mp4_sha256.lower(),
            measured=candidate_sha,
        )

    try:
        clip_data = json.loads(candidate_json.read_text(encoding="utf-8"))
        clip = Clip.from_dict(clip_data)
    except Exception as exc:
        raise DeliveryError(f"invalid candidate editing JSON: {exc}") from exc

    if clip.clip_id != candidate_id:
        raise DeliveryRefused(
            "candidate_id_mismatch",
            expected=candidate_id,
            measured=clip.clip_id,
        )

    if source is not None:
        if not source.is_file():
            raise DeliveryError(f"source media file not found: {source}")
        if clip.media_sha256 is not None:
            source_sha = hashlib.sha256(source.read_bytes()).hexdigest().lower()
            if source_sha != clip.media_sha256.lower():
                raise DeliveryRefused(
                    "source_identity_mismatch",
                    expected=clip.media_sha256.lower(),
                    measured=source_sha,
                )

    qc = Qc.from_record(qc_record)
    approved_clip = replace(clip, qc=qc)
    try:
        approved_clip.assert_renderable()
    except (BoundaryInvariantViolated, ValueError) as exc:
        raise DeliveryRefused(
            "plan_binding_invariant_violation",
            expected="valid renderable approved clip with boundary invariants",
            measured=str(exc),
        ) from exc

    try:
        measurement = ClipMeasurement.from_json(candidate_measured.read_text(encoding="utf-8"))
    except Exception as exc:
        raise DeliveryError(f"invalid candidate measurement JSON: {exc}") from exc

    if measurement.file.sha256.lower() != candidate_sha:
        raise DeliveryRefused(
            "measurement_sha256_mismatch",
            expected=candidate_sha,
            measured=measurement.file.sha256.lower(),
        )

    try:
        assert_boundary_invariant(approved_clip.boundary)
    except Exception as exc:
        raise DeliveryRefused(
            "plan_binding_invariant_violation",
            expected="valid boundary invariant",
            measured=str(exc),
        ) from exc

    try:
        verify_caption_integrity(
            candidate_ass,
            expected_text=(
                approved_clip.transcript.raw_ckb
                if (approved_clip.transcript and approved_clip.transcript.words)
                else None
            ),
        )
    except CaptionVerificationError as exc:
        raise DeliveryRefused(
            "caption_integrity_failed",
            expected="valid caption integrity (text, glyphs, geometry)",
            measured=str(exc),
        ) from exc

    srt_text = candidate_srt.read_text(encoding="utf-8")
    if not srt_text.strip():
        raise DeliveryRefused(
            "empty_sidecar",
            expected="non-empty srt sidecar",
            measured="empty",
        )
    try:
        parse_srt_times(srt_text)
    except DeliveryError as exc:
        raise DeliveryRefused(
            "corrupt_srt_sidecar",
            expected="valid parseable srt cues",
            measured=str(exc),
        ) from exc

    edl_text = candidate_edl.read_text(encoding="utf-8").strip()
    if not edl_text or not edl_text.startswith("TITLE:"):
        raise DeliveryRefused(
            "invalid_edl_sidecar",
            expected="valid edl starting with TITLE:",
            measured=edl_text[:40] if edl_text else "empty",
        )

    effective_captions_burned = (
        captions_burned_in
        if captions_burned_in is not None
        else bool(approved_clip.output and approved_clip.output.caption_style != "none")
    )

    reconcile_delivery(
        clip=approved_clip,
        measurement=measurement,
        captions_burned_in=effective_captions_burned,
        planned_punch_ins=planned_punch_ins,
        source_shot_cuts_ms=source_shot_cuts_ms,
        fps=fps,
        delivery_lufs=delivery_lufs,
        target_true_peak_db=target_true_peak_db,
        shot_cut_guard_ms=shot_cut_guard_ms,
        lufs_tolerance=lufs_tolerance,
        min_face_share=min_face_share,
        for_review=False,
    )

    bundle = ArtifactBundle.create(work_dir, candidate_id)
    try:
        candidate_edit_plan = review_dir / f"{candidate_id}.edit_plan.json"
        if not candidate_edit_plan.is_file():
            candidate_edit_plan = review_dir / "edit_plan.json"
        if not candidate_edit_plan.is_file() or candidate_edit_plan.stat().st_size == 0:
            raise DeliveryRefused(
                "missing_edit_plan",
                expected="non-empty edit_plan.json in candidate review bundle",
                measured=f"absent or empty at {candidate_edit_plan}",
            )
        bundle.staged_path("edit_plan.json").write_bytes(candidate_edit_plan.read_bytes())
        bundle.staged_path("mp4").write_bytes(mp4_bytes)
        bundle.staged_path("ass").write_bytes(candidate_ass.read_bytes())
        bundle.staged_path("srt").write_bytes(candidate_srt.read_bytes())
        bundle.staged_path("edl").write_bytes(candidate_edl.read_bytes())
        bundle.staged_path("measured.json").write_bytes(candidate_measured.read_bytes())
        bundle.write_text(
            "json",
            json.dumps(approved_clip.to_dict(), ensure_ascii=False, indent=2),
        )
        return bundle.publish()
    except Exception:
        with contextlib.suppress(BundleError):
            bundle.discard()
        raise
