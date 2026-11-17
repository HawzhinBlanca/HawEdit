"""Actual rendered-width caller regressions; synthetic timing is not media QC."""

from pathlib import Path

import pytest

from hawedit.captions import (
    CaptionStyle,
    CaptionVerificationError,
    build_ass,
    chunk_caption_events,
    compute_rtl_word_positions,
    measure_rendered_caption_width,
    wrap_caption_lines,
)
from hawedit.sentences import Sentence
from hawedit.transcripts import Word


def _sentence() -> Sentence:
    return Sentence(
        (
            Word("\u06a9\u0627\u06a9\u06d5", 0, 400, 1.0),
            Word("\u0628\u06cc\u0644\u0627\u06b5", 400, 800, 1.0),
        ),
        complete=True,
    )


def _limit() -> int:
    widths = [
        measure_rendered_caption_width(_sentence().text, font_size=size) for size in (64, 108)
    ]
    threshold = sum(widths) // 2
    assert widths[0] < threshold < widths[1]
    return threshold


@pytest.mark.parametrize("style", [CaptionStyle.LINE, CaptionStyle.WORD_HIGHLIGHT])
def test_ass_pixel_wrapping_uses_selected_font_size(style: CaptionStyle) -> None:
    for size, breaks in ((64, 0), (108, 1)):
        content = build_ass(
            [_sentence()],
            font_size=size,
            style=style,
            max_line_width_px=_limit(),
            keyword_emphasis=False,
        )
        events = [line for line in content.splitlines() if line.startswith("Dialogue:")]
        assert len(events) == 1
        assert events[0].count("\\N") == breaks


@pytest.mark.parametrize(
    "style",
    [
        CaptionStyle.VIRAL_POPUP,
        CaptionStyle.BROADCAST_STUDIO,
        CaptionStyle.RTL_WORD_HIGHLIGHT,
        CaptionStyle.KINETIC_POP,
    ],
)
def test_ass_popup_width_uses_selected_font_context(style: CaptionStyle) -> None:
    counts = (
        (4, 2) if style in (CaptionStyle.RTL_WORD_HIGHLIGHT, CaptionStyle.KINETIC_POP) else (1, 2)
    )
    for size, count in zip((64, 108), counts, strict=True):
        content = build_ass(
            [_sentence()],
            font_size=size,
            style=style,
            max_popup_width_px=_limit(),
            keyword_emphasis=False,
        )
        events = [line for line in content.splitlines() if line.startswith("Dialogue:")]
        assert len(events) == count


@pytest.mark.parametrize("style", [CaptionStyle.LINE, CaptionStyle.WORD_HIGHLIGHT])
def test_ass_generic_popup_width_uses_selected_font_size(style: CaptionStyle) -> None:
    for size, count in ((64, 1), (108, 2)):
        content = build_ass(
            [_sentence()],
            font_size=size,
            style=style,
            max_words_per_event=3,
            max_popup_width_px=_limit(),
            keyword_emphasis=False,
        )
        assert len([line for line in content.splitlines() if line.startswith("Dialogue:")]) == count


@pytest.mark.parametrize("style", list(CaptionStyle))
def test_ass_pixel_measurement_refuses_unavailable_selected_font(style: CaptionStyle) -> None:
    with pytest.raises(CaptionVerificationError, match="measurement"):
        build_ass(
            [_sentence()],
            font_name="HawEdit Deliberately Absent Font",
            style=style,
            max_line_width_px=_limit(),
            max_popup_width_px=_limit(),
            keyword_emphasis=False,
        )


@pytest.mark.parametrize("style", list(CaptionStyle))
def test_ass_pixel_measurement_refuses_empty_selected_fonts(
    style: CaptionStyle, tmp_path: Path
) -> None:
    fonts = tmp_path / "empty-fonts"
    fonts.mkdir()
    with pytest.raises(CaptionVerificationError, match="measurement"):
        build_ass(
            [_sentence()],
            fonts_dir=fonts,
            style=style,
            max_line_width_px=_limit(),
            max_popup_width_px=_limit(),
            keyword_emphasis=False,
        )


@pytest.mark.parametrize("style", list(CaptionStyle))
def test_ass_pixel_measurement_uses_selected_canvas_height(style: CaptionStyle) -> None:
    with pytest.raises(CaptionVerificationError, match="measurement"):
        build_ass(
            [_sentence()],
            play_res_y=0,
            style=style,
            max_line_width_px=_limit(),
            max_popup_width_px=_limit(),
            keyword_emphasis=False,
        )


def test_direct_pixel_consumers_use_selected_font_size() -> None:
    words = _sentence().words
    for size, count in ((64, 1), (108, 2)):
        assert len(wrap_caption_lines(words, max_width_px=_limit(), font_size=size)) == count
        assert len(chunk_caption_events(words, max_width_px=_limit(), font_size=size)) == count


def test_char_only_consumers_do_not_require_render_resources(tmp_path: Path) -> None:
    absent_fonts = tmp_path / "absent-fonts"
    assert not absent_fonts.exists()
    words = _sentence().words
    assert wrap_caption_lines(words, fonts_dir=absent_fonts) == (words,)
    assert chunk_caption_events(words, fonts_dir=absent_fonts) == (words,)


def test_rtl_positions_measure_selected_canvas_height() -> None:
    with pytest.raises(CaptionVerificationError, match="measurement"):
        compute_rtl_word_positions(_sentence().words, canvas_height=0)
