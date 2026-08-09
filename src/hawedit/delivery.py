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
NTSC 30000/1001 is emitted as SMPTE drop-frame timecode; other fractional rates are refused
rather than rounded into a slowly drifting conform.

The SRT shares §4.3.5's line breaking with the ASS for the same reason it shares the clip
offset: automatic wrapping on RTL text produces bad break points. A player wraps whatever it
is handed, so a cue emitted as one long line hands that decision to a wrapper that has no word
alignment (D-151).
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from typing import Final

from hawedit.captions import DEFAULT_MAX_CHARS_PER_LINE, wrap_caption_lines
from hawedit.sentences import Sentence

__all__ = [
    "DeliveryError",
    "build_edl",
    "build_srt",
    "ms_to_srt_time",
    "ms_to_timecode",
    "parse_srt_times",
]

_SRT_TIME = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})")


class DeliveryError(ValueError):
    """A sidecar this module would not be able to ship honestly."""


def ms_to_srt_time(milliseconds: int) -> str:
    """`HH:MM:SS,mmm`.

    The separator is a **comma**. A period is WebVTT, and a player expecting SRT either
    rejects the file or mis-parses the cue — either way the subtitles do not appear and
    nothing says so.
    """
    seconds, milliseconds = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def parse_srt_times(srt_text: str) -> tuple[tuple[int, int], ...]:
    """Every cue's `(start_ms, end_ms)`, read back out of the file."""
    return tuple(
        (
            ((int(h1) * 60 + int(m1)) * 60 + int(s1)) * 1000 + int(ms1),
            ((int(h2) * 60 + int(m2)) * 60 + int(s2)) * 1000 + int(ms2),
        )
        for h1, m1, s1, ms1, h2, m2, s2, ms2 in _SRT_TIME.findall(srt_text)
    )


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
    """
    if not sentences:
        raise DeliveryError(
            "no sentences to write: an empty SRT is a valid file that delivers no subtitles"
        )
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


_NTSC_DROP_FPS: Final = 30_000 / 1_001
_DROP_RATE_TOLERANCE: Final = 1e-4


def _timecode_rate(fps: float) -> tuple[int, float, bool]:
    """Return nominal counter rate, physical frame rate, and drop-frame mode."""
    if not math.isfinite(fps) or fps <= 0:
        raise DeliveryError(f"frame rate must be finite and positive, got {fps}")
    nominal = round(fps)
    if abs(fps - nominal) <= 1e-9:
        return nominal, float(nominal), False
    # ffprobe reports the exact 30000/1001 ratio while user-facing metadata often reports
    # 29.97. Both identify the same NTSC rate. The narrow tolerance accepts those two values
    # but not an arbitrary nearby fractional rate.
    if abs(fps - _NTSC_DROP_FPS) <= _DROP_RATE_TOLERANCE:
        return 30, _NTSC_DROP_FPS, True
    raise DeliveryError(
        f"fractional frame rate {fps} is unsupported. HawEdit writes SMPTE drop-frame only "
        "for NTSC 30000/1001 (29.97) fps; rounding this rate would create a drifting EDL."
    )


def ms_to_timecode(milliseconds: int, fps: float) -> str:
    """SMPTE timecode: non-drop ``HH:MM:SS:FF`` or NTSC drop ``HH:MM:SS;FF``.

    Raises:
        DeliveryError: time is negative, or `fps` is invalid or unsupported.
    """
    if milliseconds < 0:
        raise DeliveryError(f"timecode time is negative: {milliseconds} ms")
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
) -> str:
    """A CMX 3600 EDL for one clip.

    Source timecodes are the **source's** timeline — where this clip was cut from. Record
    timecodes start at zero, because the delivered clip is the whole record timeline. Writing
    the source range in clip time yields a file that conforms the top of the episode and looks
    entirely well-formed.

    Two events are emitted, video and audio. A video-only EDL conforms picture and silently
    drops the Kurdish speech the clip exists for.

    Raises:
        DeliveryError: the clip has no length, is shorter than a frame, starts before zero,
            or `fps` cannot be represented honestly.
    """
    if clip_in_ms < 0:
        raise DeliveryError(f"clip in-point is negative: {clip_in_ms} ms")
    if clip_out_ms <= clip_in_ms:
        raise DeliveryError(
            f"clip spans {clip_in_ms}..{clip_out_ms} ms, which has no length; there is nothing "
            f"to conform."
        )
    rate, physical_rate, drop_frame = _timecode_rate(fps)
    source_in_frame = round(clip_in_ms * physical_rate / 1000)
    source_out_frame = round(clip_out_ms * physical_rate / 1000)
    duration_frames = source_out_frame - source_in_frame
    duration_ms = clip_out_ms - clip_in_ms
    if duration_frames < 1:
        raise DeliveryError(
            f"a {duration_ms} ms clip is less than one frame at {fps} fps: the EDL event would "
            f"be well-formed and cut nothing."
        )
    source_in = _frames_to_timecode(source_in_frame, rate, drop_frame=drop_frame)
    source_out = _frames_to_timecode(source_out_frame, rate, drop_frame=drop_frame)
    record_in = _frames_to_timecode(0, rate, drop_frame=drop_frame)
    record_out = _frames_to_timecode(duration_frames, rate, drop_frame=drop_frame)

    # An EDL is a line-oriented format; a newline inside the title truncates the file's meaning
    # at that point for most parsers.
    one_line_title = " ".join(title.split())
    lines = [
        f"TITLE: {one_line_title}",
        f"FCM: {'DROP' if drop_frame else 'NON-DROP'} FRAME",
        "",
    ]
    for number, channel in ((1, "V"), (2, "A")):
        lines.append(
            f"{number:03d}  {_REEL}       {channel}     C        "
            f"{source_in} {source_out} {record_in} {record_out}"
        )
    return "\n".join(lines) + "\n"
