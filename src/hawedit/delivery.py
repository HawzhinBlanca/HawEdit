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

An EDL also counts **frames**, not milliseconds, so it cannot be written without the rate —
and 29.97 is where that stops being a rounding question and becomes a refusal.

The SRT shares §4.3.5's line breaking with the ASS for the same reason it shares the clip
offset: "Insert line breaks yourself from the word alignment … automatic wrapping on RTL text
produces bad break points regardless." A player wraps whatever it is handed, so a cue emitted
as one long line hands that decision to a wrapper that has no word alignment (D-114).
"""

from __future__ import annotations

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

    Raises:
        DeliveryError: `milliseconds` is negative. SRT timestamps are unsigned, and Python's
            `divmod` carries the sign into the *minutes* rather than the hours: measured,
            `-1` formatted as `-1:59:59,999` and `-500` as `-1:59:59,500` — a plausible-looking
            timestamp reading nearly two hours before zero. `build_srt` cannot reach it, but
            this is exported, and `parse_srt_times` then dropped such a cue silently. D-138.
    """
    if milliseconds < 0:
        raise DeliveryError(
            f"an SRT timestamp cannot be negative, got {milliseconds} ms. The format is "
            f"unsigned; formatting this would emit something like -1:59:59,999, which reads as "
            f"a time before the file starts and no player will place."
        )
    seconds, milliseconds = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def parse_srt_times(srt_text: str) -> tuple[tuple[int, int], ...]:
    """Every cue's `(start_ms, end_ms)`, read back out of the file.

    A cue whose timing line does not parse is **refused**, not skipped. It used to be skipped:
    the regex simply found nothing, so a one-cue file with a malformed timestamp read back as
    **zero** cues and callers saw a shorter list rather than an error. `test_pipeline` checks the
    delivered SRT through this reader and asserts only that *some* cue parsed and that the ones
    that did lie inside the clip — a dropped cue passes both. D-138.

    Only the timing line of each cue block is examined, so `-->` inside caption text is not
    mistaken for one; the SRT grammar puts the timing on the block's second line.

    Raises:
        DeliveryError: a cue block's timing line is not `HH:MM:SS,mmm --> HH:MM:SS,mmm`.
    """
    times: list[tuple[int, int]] = []
    for block in srt_text.strip().split("\n\n"):
        lines = block.strip().splitlines()
        if len(lines) < 2:
            continue  # not a cue block: a trailing fragment or a stray blank region
        timing = lines[1]
        match = _SRT_TIME.fullmatch(timing.strip())
        if match is None:
            raise DeliveryError(
                f"cue {lines[0].strip()!r} has an unreadable timing line: {timing.strip()!r}. "
                f"Skipping it would report fewer cues than the file contains, which is how a "
                f"malformed timestamp ships unnoticed."
            )
        h1, m1, s1, ms1, h2, m2, s2, ms2 = match.groups()
        times.append(
            (
                ((int(h1) * 60 + int(m1)) * 60 + int(s1)) * 1000 + int(ms1),
                ((int(h2) * 60 + int(m2)) * 60 + int(s2)) * 1000 + int(ms2),
            )
        )
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


def ms_to_timecode(milliseconds: int, fps: float) -> str:
    """`HH:MM:SS:FF` — SMPTE non-drop timecode at `fps`.

    Raises:
        DeliveryError: `milliseconds` is negative, `fps` is not positive, or `fps` is not a
            whole number of frames per second. Negative for the same reason as
            `ms_to_srt_time`: measured, `-500` at 25 fps formatted as `-1:59:59:13`, and an
            EDL carrying that conforms nothing while looking well-formed. D-138.
    """
    if milliseconds < 0:
        raise DeliveryError(
            f"a SMPTE timecode cannot be negative, got {milliseconds} ms. The format is "
            f"unsigned; formatting this would emit something like -1:59:59:13, which an EDL "
            f"parser reads as a valid field and conforms from nowhere."
        )
    if fps <= 0:
        raise DeliveryError(f"frame rate must be positive, got {fps}")
    if abs(fps - round(fps)) > 1e-9:
        # 29.97 and 59.94 need SMPTE drop-frame timecode, where two frame numbers are skipped
        # each minute except every tenth. Emitting non-drop instead produces an EDL that looks
        # correct and drifts against the footage — the editor finds out at the end of a long
        # conform. Refusing names the number; guessing would not.
        drift_s_per_hour = 3600 * abs(round(fps) - fps) / fps
        raise DeliveryError(
            f"{fps} fps needs SMPTE drop-frame timecode, which this does not write. Non-drop "
            f"timecode at this rate drifts about {drift_s_per_hour:.1f} s per hour against the "
            f"footage, and the EDL looks correct the whole time."
        )
    rate = round(fps)
    total_frames = round(milliseconds * rate / 1000)
    return _frames_to_timecode(total_frames, rate)


def _frames_to_timecode(total_frames: int, rate: int) -> str:
    frames = total_frames % rate
    seconds = total_frames // rate
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"


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
            or `fps` cannot be written as non-drop timecode.
    """
    if clip_in_ms < 0:
        raise DeliveryError(f"clip in-point is negative: {clip_in_ms} ms")
    if clip_out_ms <= clip_in_ms:
        raise DeliveryError(
            f"clip spans {clip_in_ms}..{clip_out_ms} ms, which has no length; there is nothing "
            f"to conform."
        )
    # `ms_to_timecode` validates the rate, and it must run before the frame arithmetic below
    # uses it — a non-integer rate makes `round(fps)` a silent substitution.
    ms_to_timecode(0, fps)  # validate the rate before using its rounded integer form
    rate = round(fps)
    source_in_frame = round(clip_in_ms * rate / 1000)
    source_out_frame = round(clip_out_ms * rate / 1000)
    duration_frames = source_out_frame - source_in_frame
    duration_ms = clip_out_ms - clip_in_ms
    if duration_frames < 1:
        raise DeliveryError(
            f"a {duration_ms} ms clip is less than one frame at {fps} fps: the EDL event would "
            f"be well-formed and cut nothing."
        )
    source_in = _frames_to_timecode(source_in_frame, rate)
    source_out = _frames_to_timecode(source_out_frame, rate)
    record_in = _frames_to_timecode(0, rate)
    record_out = _frames_to_timecode(duration_frames, rate)

    # An EDL is a line-oriented format; a newline inside the title truncates the file's meaning
    # at that point for most parsers.
    one_line_title = " ".join(title.split())
    lines = [
        f"TITLE: {one_line_title}",
        "FCM: NON-DROP FRAME",
        "",
    ]
    for number, channel in ((1, "V"), (2, "A")):
        lines.append(
            f"{number:03d}  {_REEL}       {channel}     C        "
            f"{source_in} {source_out} {record_in} {record_out}"
        )
    return "\n".join(lines) + "\n"
