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

import pytest

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
