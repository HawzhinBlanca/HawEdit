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
rate. 29.97 is where that becomes a refusal rather than a rounding.
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
from hawedit.sentences import Sentence, UndeliverableOrder
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
    """`match` names the specific refusal, because a looser one stopped discriminating.

    It was `match="before"`, and D-138's negative-timestamp guard raises the same
    `DeliveryError` with "…reads as a time **before** the file starts" in it — so once that guard
    existed, deleting *this* one still produced a passing test: the sentence's negative offset
    tripped the downstream guard instead. Measured by the audit that added it, where this
    mutation went from RED to SURVIVED. Two guards that raise one type have to be told apart by
    what they say.
    """
    with pytest.raises(DeliveryError, match="starts before the clip does"):
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


def test_a_non_integer_frame_rate_is_refused_with_the_drift_it_would_cause() -> None:
    """29.97 needs SMPTE drop-frame timecode. Writing non-drop instead produces an EDL that
    looks correct and drifts against the footage — about 3.6 s per hour. Refusing names the
    number; guessing would hand an editor a conform that goes wrong slowly."""
    with pytest.raises(DeliveryError, match="drop-frame"):
        ms_to_timecode(1_000, 29.97)


def test_a_non_positive_rate_is_refused() -> None:
    with pytest.raises(DeliveryError, match="frame rate"):
        ms_to_timecode(1_000, 0)


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


# --- D-138: the edges the claims did not cover ---------------------------------------------
#
# Adversarial pass #21 caught all 18 mutations of M3.6's stated claims. These are what the
# claims did not say: two exported formatters that produced plausible-looking nonsense below
# zero, and a reader that answered "fewer cues" instead of "this file is malformed".


def test_a_negative_srt_timestamp_is_refused_rather_than_formatted() -> None:
    """Measured before the guard: `-1` formatted as `-1:59:59,999` and `-500` as
    `-1:59:59,500`. `divmod` carries the sign into the *minutes*, so the result reads as a time
    nearly two hours before the file starts while looking like an ordinary timestamp.
    """
    with pytest.raises(DeliveryError, match="cannot be negative"):
        ms_to_srt_time(-1)
    with pytest.raises(DeliveryError, match="cannot be negative"):
        ms_to_srt_time(-500)
    # The control: zero is a valid SRT timestamp and must still format, so this is not
    # measuring "anything at the bottom of the range is refused".
    assert ms_to_srt_time(0) == "00:00:00,000"


def test_a_negative_smpte_timecode_is_refused_rather_than_formatted() -> None:
    """Same shape one format over: `-500` at 25 fps formatted as `-1:59:59:13`, and an EDL
    carrying that field conforms from nowhere while parsing cleanly."""
    with pytest.raises(DeliveryError, match="cannot be negative"):
        ms_to_timecode(-500, 25)
    with pytest.raises(DeliveryError, match="cannot be negative"):
        ms_to_timecode(-3_600_000, 25)
    assert ms_to_timecode(0, 25) == "00:00:00:00"


def test_a_cue_with_an_unreadable_timing_line_is_refused_not_skipped() -> None:
    """The defect this pass actually found: the reader dropped the cue.

    A one-cue file whose timestamp is malformed read back as **zero** cues, so every caller saw
    a shorter list rather than an error — and `test_pipeline`'s check on the delivered SRT
    asserts only that *some* cue parsed and that the ones that did lie inside the clip, both of
    which a dropped cue satisfies.
    """
    malformed = "1\n-1:59:59,500 --> 00:00:01,000\nهەولێر\n"
    with pytest.raises(DeliveryError, match="unreadable timing line"):
        parse_srt_times(malformed)

    # The control, and the reason this is not simply "reject anything unusual": a well-formed
    # file still parses, and every cue in it comes back.
    good = "1\n00:00:00,000 --> 00:00:01,000\nا\n\n2\n00:00:01,000 --> 00:00:02,000\nب\n"
    assert parse_srt_times(good) == ((0, 1_000), (1_000, 2_000))


def test_an_arrow_inside_caption_text_is_not_mistaken_for_a_timing_line() -> None:
    """The over-strict direction. The SRT grammar puts the timing on the block's second line, so
    only that line is examined — a `-->` in the caption body is text, and refusing it would fire
    on a legitimate file."""
    with_arrow = "1\n00:00:00,000 --> 00:00:01,000\nهەولێر --> سلێمانی\n"
    assert parse_srt_times(with_arrow) == ((0, 1_000),)


def test_the_reader_takes_the_timing_from_the_grammars_position_not_by_hunting() -> None:
    """The control the test above could not be: it does not discriminate.

    Reading the timing as "the first line in the block containing `-->`" behaves *identically* on
    a valid cue, because that line **is** line 1 — measured, that mutation survived. The two
    readings only diverge when line 1 is malformed: hunting then walks past it and parses a
    caption line as the cue's timing, inventing a cue out of text instead of refusing the file.
    """
    hunted = "1\n00:00:00,000 to 00:00:01,000\n00:00:05,000 --> 00:00:06,000\n"
    with pytest.raises(DeliveryError, match="unreadable timing line"):
        parse_srt_times(hunted)


# --- D-165: a sidecar is read in order, and nothing required the cues to be in one ----------


def test_cues_that_go_backwards_are_refused_rather_than_written() -> None:
    """Measured before the guard: `build_srt` shipped `00:00:01,000 --> 00:00:01,400` followed
    by `00:00:00,000 --> 00:00:00,400`.

    `build_srt` refused an incomplete sentence, one starting before the clip and one ending
    after it — every check about a sentence on its own, none about the sequence. SRT is read
    sequentially, so §4.3's own warning applies: the subtitles "do not appear and nothing says
    so".
    """
    forwards = (a_sentence(0, 400), a_sentence(1_000, 1_400))
    backwards = (a_sentence(1_000, 1_400), a_sentence(0, 400))

    # The control: the very same two sentences in order are written without complaint, so this
    # measures the ordering and not something else about the pair.
    assert parse_srt_times(build_srt(forwards, clip_in_ms=0, clip_duration_ms=5_000)) == (
        (0, 400),
        (1_000, 1_400),
    )
    with pytest.raises(UndeliverableOrder, match="starts before the previous one ends"):
        build_srt(backwards, clip_in_ms=0, clip_duration_ms=5_000)


def test_overlapping_cues_are_refused_rather_than_written() -> None:
    """Two captions on screen at once. Measured before the guard: `0 --> 1200` shipped beside
    `800 --> 1400`, overlapping by 400 ms."""
    with pytest.raises(UndeliverableOrder, match="starts before the previous one ends"):
        build_srt(
            (a_sentence(0, 1_200), a_sentence(800, 1_400)), clip_in_ms=0, clip_duration_ms=5_000
        )

    # The control: touching exactly is ordinary consecutive speech and must still be written.
    touching = (a_sentence(0, 1_000), a_sentence(1_000, 1_400))
    assert len(parse_srt_times(build_srt(touching, clip_in_ms=0, clip_duration_ms=5_000))) == 2


def test_a_sentence_whose_words_are_unordered_is_refused() -> None:
    """`Word` refuses `end_ms <= start_ms`, so no single word runs backwards — and says nothing
    about a sentence, whose bounds are `words[0].start_ms` and `words[-1].end_ms`.

    Measured before the guard, this shipped `00:00:00,900 --> 00:00:00,400`: a cue whose end
    precedes its start, built entirely from words that are individually valid.
    """
    unordered = Sentence(
        words=(
            Word(w="باشە", start_ms=900, end_ms=1_400, conf=0.9),
            Word(w="ئەمە", start_ms=0, end_ms=400, conf=0.9),
        ),
        complete=True,
    )
    with pytest.raises(UndeliverableOrder, match="ends before it starts"):
        build_srt((unordered,), clip_in_ms=0, clip_duration_ms=5_000)


def test_the_burned_in_captions_refuse_the_same_sequence_the_sidecar_does() -> None:
    """`pipeline.py` hands the *same* sentences to `build_ass` and `build_srt`, so a guard on
    one and not the other would burn the overlap into the video while the sidecar refused it."""
    overlapping = (a_sentence(0, 1_200), a_sentence(800, 1_400))
    with pytest.raises(UndeliverableOrder, match="starts before the previous one ends"):
        build_ass(overlapping)

    # The control: the ordered pair still renders, so this is the ordering and not build_ass
    # rejecting the fixture for some other reason.
    assert build_ass((a_sentence(0, 1_000), a_sentence(1_000, 1_400))).count("Dialogue:") == 2


def test_every_cue_the_writer_produced_is_read_back(tmp_path: Path) -> None:
    """The round-trip as a count, which nothing asserted: `build_srt` writes one cue per
    sentence, and the reader must return exactly that many.

    A parser that silently drops one satisfies "the SRT has no cues" being false and "the cues
    that parsed lie inside the clip" being true, which is all the pipeline test checked.
    """
    sentences = tuple(
        a_sentence(index * 1_000, index * 1_000 + 900, LONG_SORANI) for index in range(5)
    )
    srt = build_srt(sentences, clip_in_ms=0, clip_duration_ms=5_000)

    assert len(parse_srt_times(srt)) == len(sentences)
    assert srt.count("-->") == len(sentences), "one timing line per cue"
