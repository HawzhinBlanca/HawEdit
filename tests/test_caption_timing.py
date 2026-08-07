"""M3.5 — captions are timed to the clip, and the render refuses an ASS with nothing in it.

`render.py`'s own docstring names this failure mode:

    A burn-in has many silent failure modes — the wrong filter order, a font directory that
    resolves to nothing, an ASS file libass parses but finds nothing to draw in — and every
    one of them produces a valid, playable, caption-free clip.

The third one was real and shipping. `build_ass` wrote **source-absolute** timestamps, and
`render_clip` burns them into a stream ffmpeg has already cut at `clip.in_ms`, where t=0 is the
start of the clip. Measured on the real fixture — a 1.6 s clip taken from source 2000 ms, whose
sentence is spoken at source 2000–3600 ms:

    ASS Dialogue line: Dialogue: 0,0:00:02.00,0:00:03.60,Kurdish,,0,0,0,,ڕۆژنامەوانی …
    bytes differing between captioned and uncaptioned render: 0
    captions drawn: False

Nothing was drawn. The clip is 1.6 s long and the caption was scheduled to appear at 2.0 s.
Kurdish invariant #4 — the entire §4.3 surface — was absent from every clip that did not start
near zero, and the pixel test that exists to catch exactly this passed throughout, because its
fixture cuts at 300 ms with words at 0–1600 and the overlap is enough to draw something.

So the offset is applied where the file is built, and — because a fix at one call site is not
a fix (D-038) — the file is checked again where it is burned, whoever built it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hawedit.captions import (
    CaptionsOutsideClip,
    assert_captions_within_clip,
    build_ass,
    find_ffmpeg,
    parse_dialogue_times,
    subtitle_filter,
)
from hawedit.render import crop_filter
from hawedit.sentences import Sentence
from hawedit.transcripts import Word

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "kurdish-speech-3cuts.mp4"
FONTS = ROOT / "assets" / "fonts"
SOURCE_WIDTH, SOURCE_HEIGHT = 640, 360

needs_ffmpeg = pytest.mark.skipif(find_ffmpeg() is None, reason="no ffmpeg — set HAWEDIT_FFMPEG")


def a_sentence(start_ms: int, end_ms: int) -> Sentence:
    middle = (start_ms + end_ms) // 2
    return Sentence(
        words=(
            Word(w="ڕۆژنامەوانی", start_ms=start_ms, end_ms=middle, conf=0.95),
            Word(w="کوردی.", start_ms=middle, end_ms=end_ms, conf=0.95),
        ),
        complete=True,
    )


# =========================================================================================
# parse_dialogue_times — reading back what was written
# =========================================================================================


def test_dialogue_times_round_trip_through_the_ass_format() -> None:
    ass = build_ass((a_sentence(2_000, 3_600),), clip_in_ms=2_000)
    assert parse_dialogue_times(ass) == ((0, 1_600),)


def test_centisecond_truncation_is_visible_rather_than_hidden() -> None:
    """ASS carries centiseconds, so 1 234 ms is written 1.23 and reads back 1 230."""
    ass = build_ass((a_sentence(1_234, 5_678),), clip_in_ms=0)
    assert parse_dialogue_times(ass) == ((1_230, 5_670),)


def test_a_file_with_no_dialogue_parses_to_nothing() -> None:
    assert parse_dialogue_times("[Script Info]\nWrapStyle: 2\n") == ()


# =========================================================================================
# build_ass — timed to the clip it belongs to
# =========================================================================================


def test_the_offset_moves_a_caption_to_the_clips_own_timeline() -> None:
    ass = build_ass((a_sentence(84_600, 86_200),), clip_in_ms=84_600)
    assert parse_dialogue_times(ass) == ((0, 1_600),)


def test_without_the_offset_the_caption_lands_where_it_used_to() -> None:
    """The old behaviour, kept reachable so the difference is a test rather than a memory."""
    ass = build_ass((a_sentence(84_600, 86_200),))
    assert parse_dialogue_times(ass) == ((84_600, 86_200),)


def test_a_sentence_starting_before_the_clip_is_refused() -> None:
    with pytest.raises(CaptionsOutsideClip, match="before"):
        build_ass((a_sentence(1_000, 3_000),), clip_in_ms=2_000)


def test_a_sentence_running_past_the_clip_is_refused_when_the_length_is_known() -> None:
    with pytest.raises(CaptionsOutsideClip, match="past"):
        build_ass((a_sentence(2_000, 9_000),), clip_in_ms=2_000, clip_duration_ms=1_600)


def test_a_sentence_inside_the_clip_is_accepted() -> None:
    ass = build_ass((a_sentence(2_000, 3_600),), clip_in_ms=2_000, clip_duration_ms=1_600)
    assert parse_dialogue_times(ass) == ((0, 1_600),)


# =========================================================================================
# assert_captions_within_clip — the net at the burn, whoever built the file
# =========================================================================================


def test_an_ass_whose_captions_all_fall_past_the_clip_is_refused() -> None:
    """The exact file that shipped: source-absolute times against a 1.6 s clip."""
    ass = build_ass((a_sentence(2_000, 3_600),))
    with pytest.raises(CaptionsOutsideClip, match="nothing to draw"):
        assert_captions_within_clip(ass, clip_duration_ms=1_600)


def test_an_ass_with_captions_inside_the_clip_passes() -> None:
    ass = build_ass((a_sentence(2_000, 3_600),), clip_in_ms=2_000)
    assert_captions_within_clip(ass, clip_duration_ms=1_600)


def test_a_caption_partly_overlapping_the_clip_is_enough_to_draw() -> None:
    """Something is on screen, so this is not the silent-failure case."""
    ass = build_ass((a_sentence(1_000, 3_000),))
    assert_captions_within_clip(ass, clip_duration_ms=1_600)


def test_an_ass_with_no_dialogue_at_all_is_refused() -> None:
    with pytest.raises(CaptionsOutsideClip, match="no Dialogue"):
        assert_captions_within_clip("[Script Info]\nWrapStyle: 2\n", clip_duration_ms=1_600)


# =========================================================================================
# The measurement — decoded pixels, on a clip that does not start at zero
# =========================================================================================


@needs_ffmpeg
def test_captions_are_drawn_on_a_clip_that_starts_two_seconds_in(tmp_path: Path) -> None:
    """The test that would have caught it.

    Cut 2.0–3.6 s of the fixture; the sentence is spoken there. With the offset applied the
    captioned render must differ from an uncaptioned one. Before the fix this compared equal
    at **0 bytes** — a valid, playable, entirely caption-free clip.
    """
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    ass = tmp_path / "captions.ass"
    ass.write_text(
        build_ass((a_sentence(2_000, 3_600),), clip_in_ms=2_000, clip_duration_ms=1_600),
        encoding="utf-8",
    )

    def render(video_filter: str, out: Path) -> Path:
        subprocess.run(
            [
                str(ffmpeg),
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                "2.000",
                "-t",
                "1.600",
                "-i",
                str(FIXTURE),
                "-vf",
                video_filter,
                "-c:v",
                "libx264",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-an",
                "-y",
                str(out),
            ],
            check=True,
        )
        return out

    def frame(video: Path, out: Path) -> bytes:
        subprocess.run(
            [
                str(ffmpeg),
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                "0.5",
                "-i",
                str(video),
                "-frames:v",
                "1",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-y",
                str(out),
            ],
            check=True,
        )
        return out.read_bytes()

    crop = crop_filter(SOURCE_WIDTH, SOURCE_HEIGHT)
    captioned = render(f"{crop},{subtitle_filter(ass, FONTS)}", tmp_path / "cap.mp4")
    plain = render(crop, tmp_path / "plain.mp4")
    captioned_bytes = frame(captioned, tmp_path / "a.rgb")
    plain_bytes = frame(plain, tmp_path / "b.rgb")
    differing = sum(1 for a, b in zip(captioned_bytes, plain_bytes, strict=True) if a != b)
    assert differing > 500, (
        f"only {differing} bytes differ between a captioned and an uncaptioned render of a clip "
        f"starting 2 s into the source. Nothing was drawn: the ASS timestamps are not on the "
        f"clip's own timeline (Kurdish invariant #4)."
    )
