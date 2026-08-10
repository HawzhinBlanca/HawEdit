"""M3.6 — §2's delivery set. The two formats that did not exist.

§2's architecture diagram ends with what leaves the system:

    MP4 · SRT/ASS · editing JSON · EDL

MP4 is `render.py`, ASS is `captions.py`, the editing JSON is §5's clip contract. SRT and EDL
were never built, so two of the four things §2 says this system delivers did not exist.

They are opposites, and the opposition is the whole design here:

**An SRT ships beside the MP4**, so its timeline is the *clip's* — t=0 is the first frame of
the delivered file. That is the same trap M3.5 found in the ASS path, where source-absolute
timestamps produced a valid, playable, caption-free clip. The subtitle formats now share one
rule and one offset.

**An EDL describes where the clip came from**, so its source timecodes are the *source's* and
its record timecodes are the finished timeline's. An EDL in clip time is an EDL that conforms
the wrong footage — and it looks perfectly well-formed.

And an EDL counts **frames**, not milliseconds, so it cannot be written without knowing the
rate. NTSC 29.97 is where drop-frame numbering becomes mandatory rather than optional.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Final

import pytest

from hawedit.captions import DEFAULT_MAX_CHARS_PER_LINE, build_ass, find_ffmpeg
from hawedit.delivery import (
    DeliveryError,
    build_edl,
    build_srt,
    ms_to_srt_time,
    ms_to_timecode,
    parse_srt_times,
)
from hawedit.sentences import Sentence
from hawedit.transcripts import Word

needs_ffmpeg = pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg — set HAWEDIT_FFMPEG")


def a_sentence(start_ms: int, end_ms: int, text: str = "ڕۆژنامەوانی کوردی.") -> Sentence:
    words = text.split()
    step = (end_ms - start_ms) // max(len(words), 1)
    return Sentence(
        words=tuple(
            Word(
                w=word,
                start_ms=start_ms + i * step,
                end_ms=(start_ms + (i + 1) * step) if i + 1 < len(words) else end_ms,
                conf=0.9,
            )
            for i, word in enumerate(words)
        ),
        complete=True,
    )


# =========================================================================================
# SRT timestamps — the comma matters
# =========================================================================================


def test_an_srt_timestamp_uses_a_comma_not_a_period() -> None:
    """`00:00:01.500` is WebVTT. Players that want SRT reject or mis-parse it, and the
    failure is a subtitle track that silently does not appear."""
    assert ms_to_srt_time(1_500) == "00:00:01,500"


def test_srt_timestamps_are_zero_padded_to_hours() -> None:
    assert ms_to_srt_time(0) == "00:00:00,000"
    assert ms_to_srt_time(3_661_234) == "01:01:01,234"


def test_srt_keeps_full_millisecond_precision() -> None:
    """Unlike ASS, which stores centiseconds, SRT carries all three digits."""
    assert ms_to_srt_time(1_234) == "00:00:01,234"


def test_a_negative_srt_timestamp_is_refused_rather_than_formatted() -> None:
    """Before the guard, -1 formatted as the plausible-looking `-1:59:59,999`."""
    with pytest.raises(DeliveryError, match="cannot be negative"):
        ms_to_srt_time(-1)
    with pytest.raises(DeliveryError, match="cannot be negative"):
        ms_to_srt_time(-500)
    assert ms_to_srt_time(0) == "00:00:00,000"


@pytest.mark.parametrize("value", [True, 1.5, "5"])
def test_srt_timestamp_requires_an_exact_integer(value: object) -> None:
    with pytest.raises(DeliveryError, match="non-negative integer"):
        ms_to_srt_time(value)  # type: ignore[arg-type]


# =========================================================================================
# build_srt — the clip's timeline, like the ASS beside it
# =========================================================================================


def test_the_srt_is_written_on_the_clips_own_timeline() -> None:
    srt = build_srt((a_sentence(84_600, 86_200),), clip_in_ms=84_600, clip_duration_ms=2_000)
    assert parse_srt_times(srt) == ((0, 1_600),)


def test_indices_are_one_based_and_sequential() -> None:
    srt = build_srt(
        (a_sentence(0, 1_000), a_sentence(1_000, 2_000), a_sentence(2_000, 3_000)),
        clip_in_ms=0,
        clip_duration_ms=3_000,
    )
    assert [line for line in srt.splitlines() if line.strip().isdigit()] == ["1", "2", "3"]


def test_the_kurdish_text_is_the_raw_surface_form() -> None:
    """Invariant #3 in the other direction: a viewer sees what was said, not the index's
    normalized form."""
    srt = build_srt((a_sentence(0, 1_000, "ڕۆژنامەوانی کوردی."),), clip_in_ms=0)
    assert "ڕۆژنامەوانی کوردی." in srt


def test_a_sentence_before_the_clip_is_refused() -> None:
    with pytest.raises(DeliveryError, match="before"):
        build_srt((a_sentence(1_000, 3_000),), clip_in_ms=2_000)


def test_a_sentence_past_the_clip_is_refused_when_the_length_is_known() -> None:
    with pytest.raises(DeliveryError, match="past"):
        build_srt((a_sentence(2_000, 9_000),), clip_in_ms=2_000, clip_duration_ms=1_600)


def test_an_incomplete_sentence_is_refused() -> None:
    """Kurdish invariant #2 reaches the sidecar too: a fragment is rejected, never shipped."""
    fragment = Sentence(words=a_sentence(0, 1_000).words, complete=False)
    with pytest.raises(DeliveryError, match="complete"):
        build_srt((fragment,), clip_in_ms=0)


def test_no_sentences_is_refused_rather_than_an_empty_file() -> None:
    """An empty SRT is a valid file that delivers no subtitles — the silent case again."""
    with pytest.raises(DeliveryError, match="no sentences"):
        build_srt((), clip_in_ms=0)


def test_the_srt_ends_with_a_blank_line() -> None:
    srt = build_srt((a_sentence(0, 1_000),), clip_in_ms=0)
    assert srt.endswith("\n\n")


@pytest.mark.parametrize("value", [True, 1.5, "0"])
def test_srt_clip_bounds_require_exact_integer_milliseconds(value: object) -> None:
    sentence = a_sentence(0, 1_000)
    with pytest.raises(DeliveryError, match="SRT clip in-point.*non-negative integer"):
        build_srt((sentence,), value)  # type: ignore[arg-type]
    with pytest.raises(DeliveryError, match="SRT clip duration.*non-negative integer"):
        build_srt((sentence,), 0, value)  # type: ignore[arg-type]


def test_an_unreadable_cue_timing_is_refused_instead_of_dropped() -> None:
    malformed = "1\n-1:59:59,500 --> 00:00:01,000\nhello\n"
    with pytest.raises(DeliveryError, match="unreadable timing line"):
        parse_srt_times(malformed)


def test_the_reader_uses_the_timing_lines_grammar_position() -> None:
    hunted = "1\nBAD\n00:00:05,000 --> 00:00:06,000\n"
    with pytest.raises(DeliveryError, match="unreadable timing line"):
        parse_srt_times(hunted)


def test_an_arrow_inside_caption_text_is_not_a_second_timing_line() -> None:
    body = "1\n00:00:00,000 --> 00:00:01,000\nHewler --> Slemani\n"
    assert parse_srt_times(body) == ((0, 1_000),)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("1\n00:60:00,000 --> 00:00:01,000\ntext\n", "unreadable timing line"),
        ("1\n00:00:02,000 --> 00:00:01,000\ntext\n", "does not end after"),
        ("1\n00:00:01,000 --> 00:00:01,000\ntext\n", "does not end after"),
        ("2\n00:00:00,000 --> 00:00:01,000\ntext\n", "expected 1"),
        ("1\n", "no timing line"),
    ],
)
def test_srt_reader_refuses_invalid_clock_and_cue_structure(body: str, message: str) -> None:
    with pytest.raises(DeliveryError, match=message):
        parse_srt_times(body)


def test_srt_reader_round_trips_every_cue_and_hours_above_two_digits() -> None:
    body = "1\n00:00:00,000 --> 00:00:01,000\na\n\n2\n100:00:00,000 --> 100:00:01,000\nb\n"
    assert parse_srt_times(body) == ((0, 1_000), (360_000_000, 360_001_000))
    assert parse_srt_times("") == ()


def test_srt_reader_accepts_windows_line_endings_and_spaced_blank_lines() -> None:
    body = (
        "1\r\n00:00:00,000 --> 00:00:01,000\r\na\r\n \t\r\n"
        "2\r\n00:00:01,000 --> 00:00:02,000\r\nb\r\n"
    )
    assert parse_srt_times(body) == ((0, 1_000), (1_000, 2_000))


# =========================================================================================
# §4.3.5 line breaking — the SRT is the other subtitle format, and a player wraps whatever
# it is handed
# =========================================================================================

# Real Sorani, long enough that ordinary speech crosses the line width. 74 chars, 12 words.
LONG_SORANI: Final = "ڕۆژنامەوانی کوردی لە هەولێر و سلێمانی و دهۆک بەردەوامە لەسەر کارەکانی خۆی."


def cue_lines(srt: str) -> list[str]:
    """The text lines of the single cue in `srt`."""
    blocks = [block for block in srt.split("\n\n") if block.strip()]
    assert len(blocks) == 1, f"expected one cue, got {len(blocks)}"
    return blocks[0].splitlines()[2:]


def test_a_long_sentence_is_broken_from_the_word_alignment_not_by_the_player() -> None:
    """§4.3.5: insert line breaks yourself — "automatic wrapping on RTL text produces bad
    break points regardless". SRT has no `WrapStyle: 2` to disable, so a one-line cue hands
    the decision to a wrapper with no word alignment."""
    lines = cue_lines(build_srt((a_sentence(0, 4_000, LONG_SORANI),), clip_in_ms=0))
    assert len(lines) > 1, "a 74-char cue on one line is the player's break points, not ours"
    assert max(len(line) for line in lines) <= DEFAULT_MAX_CHARS_PER_LINE


def test_a_sentence_that_fits_is_left_on_one_line() -> None:
    """The control. Breaking every cue satisfies the test above and is equally wrong — it
    puts a break where the speech has none."""
    short = "ڕۆژنامەوانی کوردی."
    assert len(short) <= DEFAULT_MAX_CHARS_PER_LINE
    assert cue_lines(build_srt((a_sentence(0, 1_000, short),), clip_in_ms=0)) == [short]


def test_wrapping_neither_drops_nor_reorders_nor_splits_a_word() -> None:
    """The second control: a wrapper that meets the width by dropping a word, or by cutting
    one in half, passes the width assertion. Arabic script split mid-word also breaks
    shaping, so the reassembled cue must be the sentence exactly."""
    sentence = a_sentence(0, 4_000, LONG_SORANI)
    lines = cue_lines(build_srt((sentence,), clip_in_ms=0))
    assert " ".join(lines) == sentence.text


def test_a_wrapped_cue_does_not_contain_the_blank_line_that_would_end_it() -> None:
    """A blank line terminates a cue in SRT, so wrapping must not emit one.

    Measured, ffmpeg's demuxer does **not** enforce that: separating the wrapped lines by a
    blank line round-trips through ffmpeg byte-identical to the correct file. So this is a
    check about the strict parsers ffmpeg is not, and the round-trip below cannot stand in
    for it — that is why both exist.
    """
    srt = build_srt(
        (a_sentence(0, 4_000, LONG_SORANI), a_sentence(4_000, 8_000, LONG_SORANI)),
        clip_in_ms=0,
    )
    assert len(parse_srt_times(srt)) == 2
    assert [line for line in srt.splitlines() if line.strip().isdigit()] == ["1", "2"]


def test_the_two_subtitle_formats_break_the_same_sentence_the_same_way() -> None:
    """§4.3.5 is a requirement about the delivered subtitles, and §2 delivers two formats.
    Sharing `wrap_caption_lines` is what keeps them from drifting apart."""
    sentence = a_sentence(0, 4_000, LONG_SORANI)
    srt_lines = cue_lines(build_srt((sentence,), clip_in_ms=0))
    dialogue = [
        line
        for line in build_ass((sentence,), clip_in_ms=0).splitlines()
        if line.startswith("Dialogue:")
    ]
    assert len(dialogue) == 1
    assert dialogue[0].split(",", 9)[9].split("\\N") == srt_lines


@needs_ffmpeg
def test_a_written_srt_reads_back_through_ffmpeg_with_both_cues_intact(tmp_path: Path) -> None:
    """The written artifact, parsed by something that is not us.

    Putting `\\n` inside an SRT cue is the whole change, and `parse_srt_times` is this module's
    own reader — it cannot be the only witness that a real demuxer reads those breaks as
    in-cue line breaks rather than as the end of the cue. ffmpeg reads the file back with both
    cues, three lines each, and every word present.
    """
    written = tmp_path / "clip.srt"
    written.write_text(
        build_srt(
            (a_sentence(0, 4_000, LONG_SORANI), a_sentence(4_000, 8_000, LONG_SORANI)),
            clip_in_ms=0,
        ),
        encoding="utf-8",
    )
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    out = tmp_path / "roundtrip.srt"
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(written), str(out)],
        check=True,
        capture_output=True,
    )
    body = out.read_text(encoding="utf-8")
    assert [line for line in body.splitlines() if line.strip().isdigit()] == ["1", "2"], body
    # The breaks are still breaks after the round trip, and no word was lost on the way.
    blocks = [block.splitlines()[2:] for block in body.split("\n\n") if block.strip()]
    assert [len(block) for block in blocks] == [3, 3], body
    for block in blocks:
        assert " ".join(block) == LONG_SORANI


# =========================================================================================
# Timecode — an EDL counts frames
# =========================================================================================


def test_a_timecode_is_hours_minutes_seconds_frames() -> None:
    assert ms_to_timecode(0, 25) == "00:00:00:00"
    assert ms_to_timecode(1_000, 25) == "00:00:01:00"
    assert ms_to_timecode(1_040, 25) == "00:00:01:01"


def test_a_frame_boundary_rounds_to_the_nearest_frame() -> None:
    """A millisecond that is not on a frame boundary has to land somewhere, and the nearest
    frame is a half-frame error at worst rather than a whole one."""
    assert ms_to_timecode(1_019, 25) == "00:00:01:00"
    assert ms_to_timecode(1_021, 25) == "00:00:01:01"


def test_an_hour_is_an_hour() -> None:
    assert ms_to_timecode(3_600_000, 25) == "01:00:00:00"


def test_ntsc_drop_frame_skips_the_first_two_counts_outside_tenth_minutes() -> None:
    """Apple's canonical transition: 00:00:59;29 advances to 00:01:00;02."""
    ntsc = 30_000 / 1_001
    assert ms_to_timecode(60_027, ntsc) == "00:00:59;29"
    assert ms_to_timecode(60_060, ntsc) == "00:01:00;02"


def test_ntsc_drop_frame_does_not_skip_at_tenth_minutes_and_stays_aligned_at_an_hour() -> None:
    ntsc = 30_000 / 1_001
    assert ms_to_timecode(600_000, ntsc) == "00:10:00;00"
    assert ms_to_timecode(3_600_000, ntsc) == "01:00:00;00"


def test_the_common_29_97_decimal_is_treated_as_30000_over_1001() -> None:
    assert ms_to_timecode(3_600_000, 29.97) == "01:00:00;00"


def test_high_frame_rate_ntsc_skips_four_counts_outside_tenth_minutes() -> None:
    ntsc = 60_000 / 1_001
    assert ms_to_timecode(60_043, ntsc) == "00:00:59;59"
    assert ms_to_timecode(60_060, ntsc) == "00:01:00;04"
    assert ms_to_timecode(600_000, ntsc) == "00:10:00;00"
    assert ms_to_timecode(3_600_000, ntsc) == "01:00:00;00"
    assert ms_to_timecode(3_600_000, 59.94) == "01:00:00;00"


def test_every_high_rate_ntsc_frame_in_ten_minutes_has_one_legal_label() -> None:
    ntsc = 60_000 / 1_001
    frame_count = round(600 * ntsc)
    labels = [ms_to_timecode(round(frame * 1000 / ntsc), ntsc) for frame in range(frame_count)]
    assert len(set(labels)) == frame_count
    for label in labels:
        _, minute, second, frame = (int(part) for part in label.replace(";", ":").split(":"))
        if minute % 10:
            assert not (second == 0 and frame < 4), label


def test_every_ntsc_frame_in_the_first_hour_has_one_legal_drop_frame_label() -> None:
    ntsc = 30_000 / 1_001
    frame_count = round(3_600 * ntsc)
    labels = [ms_to_timecode(round(frame * 1000 / ntsc), ntsc) for frame in range(frame_count)]
    assert len(set(labels)) == frame_count
    for label in labels:
        _, minute, second, frame = (int(part) for part in label.replace(";", ":").split(":"))
        if minute % 10:
            assert (second, frame) not in ((0, 0), (0, 1)), label


def test_an_unsupported_fractional_rate_is_refused_instead_of_rounded() -> None:
    with pytest.raises(DeliveryError, match="fractional frame rate.*unsupported"):
        ms_to_timecode(1_000, 24_000 / 1_001)
    with pytest.raises(DeliveryError, match="fractional frame rate.*unsupported"):
        ms_to_timecode(1_000, 120_000 / 1_001)


def test_a_non_positive_rate_is_refused() -> None:
    with pytest.raises(DeliveryError, match="finite and positive"):
        ms_to_timecode(1_000, 0)


@pytest.mark.parametrize("fps", [float("nan"), float("inf")])
def test_a_non_finite_rate_is_refused(fps: float) -> None:
    with pytest.raises(DeliveryError, match="finite and positive"):
        ms_to_timecode(1_000, fps)


def test_a_negative_timecode_time_is_refused() -> None:
    with pytest.raises(DeliveryError, match="negative"):
        ms_to_timecode(-1, 25)


@pytest.mark.parametrize("value", [True, 1.5, "5"])
def test_timecode_timestamp_requires_an_exact_integer(value: object) -> None:
    with pytest.raises(DeliveryError, match="non-negative integer"):
        ms_to_timecode(value, 25)  # type: ignore[arg-type]


@pytest.mark.parametrize("fps", [True, "25"])
def test_timecode_rate_rejects_boolean_and_string_values(fps: object) -> None:
    with pytest.raises(DeliveryError, match="finite positive number"):
        ms_to_timecode(1_000, fps)  # type: ignore[arg-type]


def test_timecode_rate_normalizes_an_integer_too_large_for_a_float() -> None:
    with pytest.raises(DeliveryError, match="out-of-range"):
        ms_to_timecode(1_000, 10**1_000)


# =========================================================================================
# build_edl — CMX 3600, and the timeline it is NOT written on
# =========================================================================================


def test_the_edl_names_the_source_range_and_the_record_range() -> None:
    edl = build_edl(clip_in_ms=84_600, clip_out_ms=86_200, fps=25, title="EP12 CLIP 1")
    event = next(line for line in edl.splitlines() if line.startswith("001"))
    # source in, source out, record in, record out
    assert "00:01:24:15 00:01:26:05 00:00:00:00 00:00:01:15" in event


def test_the_source_timecode_is_the_sources_timeline_not_the_clips() -> None:
    """An EDL in clip time conforms the wrong footage, and is perfectly well-formed."""
    edl = build_edl(clip_in_ms=84_600, clip_out_ms=86_200, fps=25)
    assert "00:01:24:15" in edl, "the source in-point must be where the clip came FROM"
    assert not edl.count("00:00:00:00 00:00:00:00"), "source and record ranges collapsed"


def test_the_record_timeline_starts_at_zero() -> None:
    edl = build_edl(clip_in_ms=84_600, clip_out_ms=86_200, fps=25)
    assert "00:00:00:00" in edl


def test_source_and_record_ranges_use_the_same_quantized_frame_duration() -> None:
    edl = build_edl(clip_in_ms=20, clip_out_ms=60, fps=25)
    event = next(line for line in edl.splitlines() if line.startswith("001"))
    fields = event.split()[-4:]
    assert fields == ["00:00:00:00", "00:00:00:02", "00:00:00:00", "00:00:00:02"]


def test_the_edl_declares_non_drop_frame() -> None:
    assert "FCM: NON-DROP FRAME" in build_edl(clip_in_ms=0, clip_out_ms=1_000, fps=25)


def test_an_ntsc_edl_declares_and_uses_drop_frame_timecode() -> None:
    edl = build_edl(clip_in_ms=60_060, clip_out_ms=120_120, fps=30_000 / 1_001)
    event = next(line for line in edl.splitlines() if line.startswith("001"))
    assert "FCM: DROP FRAME" in edl
    assert event.split()[-4:] == [
        "00:01:00;02",
        "00:02:00;04",
        "00:00:00;00",
        "00:01:00;02",
    ]


def test_a_high_frame_rate_ntsc_edl_uses_four_count_drop_frame_timecode() -> None:
    edl = build_edl(clip_in_ms=60_060, clip_out_ms=120_120, fps=60_000 / 1_001)
    event = next(line for line in edl.splitlines() if line.startswith("001"))
    assert "FCM: DROP FRAME" in edl
    assert event.split()[-4:] == [
        "00:01:00;04",
        "00:02:00;08",
        "00:00:00;00",
        "00:01:00;04",
    ]


def test_the_title_appears_and_is_sanitised_to_one_line() -> None:
    edl = build_edl(clip_in_ms=0, clip_out_ms=1_000, fps=25, title="EP12\nCLIP 1")
    assert "TITLE: EP12 CLIP 1" in edl


def test_both_a_video_and_an_audio_event_are_emitted() -> None:
    """A video-only EDL conforms picture and silently drops the Kurdish it exists for."""
    edl = build_edl(clip_in_ms=0, clip_out_ms=1_000, fps=25)
    assert "  V  " in edl or " V " in edl
    assert " A " in edl


def test_a_zero_length_clip_is_refused() -> None:
    with pytest.raises(DeliveryError, match="no length"):
        build_edl(clip_in_ms=1_000, clip_out_ms=1_000, fps=25)


def test_a_clip_shorter_than_one_frame_is_refused() -> None:
    """At 25 fps a 20 ms clip rounds to zero frames: a well-formed EDL event that cuts
    nothing."""
    with pytest.raises(DeliveryError, match="one frame"):
        build_edl(clip_in_ms=0, clip_out_ms=20, fps=25)


def test_a_negative_in_point_is_refused() -> None:
    with pytest.raises(DeliveryError, match="negative"):
        build_edl(clip_in_ms=-1, clip_out_ms=1_000, fps=25)


@pytest.mark.parametrize("value", [True, 1.5, "0"])
def test_edl_clip_bounds_require_exact_integer_milliseconds(value: object) -> None:
    with pytest.raises(DeliveryError, match="EDL clip in-point.*non-negative integer"):
        build_edl(clip_in_ms=value, clip_out_ms=1_000, fps=25)  # type: ignore[arg-type]
    with pytest.raises(DeliveryError, match="EDL clip out-point.*non-negative integer"):
        build_edl(clip_in_ms=0, clip_out_ms=value, fps=25)  # type: ignore[arg-type]
