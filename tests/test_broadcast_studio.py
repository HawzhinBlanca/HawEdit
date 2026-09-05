from __future__ import annotations

from hawedit.captions import (
    BROADCAST_THEME,
    CaptionStyle,
    CaptionTheme,
    build_ass,
)
from hawedit.pipeline import build_parser
from hawedit.render import vertical_framing
from hawedit.sentences import Sentence
from hawedit.transcripts import Word


def words(*specs: tuple[str, int, int]) -> tuple[Word, ...]:
    return tuple(Word(w=w, start_ms=s, end_ms=e, conf=1.0) for w, s, e in specs)


def test_caption_style_broadcast_studio_enum() -> None:
    """CaptionStyle exposes BROADCAST_STUDIO member."""
    assert CaptionStyle.BROADCAST_STUDIO.value == "broadcast_studio"
    assert CaptionStyle("broadcast_studio") is CaptionStyle.BROADCAST_STUDIO


def test_broadcast_theme_values() -> None:
    """BROADCAST_THEME uses safe margin (440px), bold font, and high contrast outline."""
    assert isinstance(BROADCAST_THEME, CaptionTheme)
    assert BROADCAST_THEME.margin_v == 440
    assert BROADCAST_THEME.bold is True
    assert BROADCAST_THEME.outline == 4.0
    assert BROADCAST_THEME.shadow == 1.5
    assert BROADCAST_THEME.primary == "&H00FFFFFF"


def test_build_ass_margin_v_override() -> None:
    """build_ass accepts margin_v parameter and overrides the theme vertical margin."""
    sentence = Sentence(words=words(("سڵاو", 100, 500)), complete=True)
    ass_custom = build_ass((sentence,), margin_v=480)
    assert ",480,1" in ass_custom

    ass_default = build_ass((sentence,))
    assert ",140,1" in ass_default


def test_build_ass_broadcast_studio_formatting() -> None:
    """BROADCAST_STUDIO chunks phrases cleanly and highlights Kurdish keywords inline."""
    test_words = words(
        ("پۆڵ", 100, 400),
        ("برێمەر", 400, 800),
        ("هاتە", 800, 1100),
        ("عێراق", 1100, 1500),
    )
    sentence = Sentence(words=test_words, complete=True)

    ass = build_ass(
        (sentence,),
        style=CaptionStyle.BROADCAST_STUDIO,
        keyword_emphasis=True,
    )

    # MarginV matches BROADCAST_THEME (440px safe zone)
    assert ",440,1" in ass
    # Clean dialogue event (no \\kf karaoke sweep tags)
    assert "\\kf" not in ass
    # Entities (برێمەر, عێراق) receive color styling inline
    assert "{\\c&H00FFFF00&}" in ass
    assert "{\\r}" in ass


def test_vertical_framing_target_face_share_parameter() -> None:
    """vertical_framing supports configurable target_face_height_share and max_vertical_zoom."""
    crop_w, crop_h = 810, 1440
    source_h = 1440

    # Small face: height = 144 (10% of 1440)
    # With default target_share (0.15), zoom = 0.15 / 0.10 = 1.5
    w1, h1, _ = vertical_framing(source_h, crop_w, crop_h, face_center_y=720, face_height=144)
    assert h1 < crop_h

    # With tighter target_share (0.20), zoom = min(0.20 / 0.10, 1.8)
    w2, h2, _ = vertical_framing(
        source_h,
        crop_w,
        crop_h,
        face_center_y=720,
        face_height=144,
        target_face_height_share=0.20,
        max_vertical_zoom=1.8,
    )
    assert h2 < h1  # Tighter framing


def test_pipeline_parser_supports_preset_flag() -> None:
    """The pipeline argument parser accepts --preset flag with broadcast, viral, and split."""
    parser = build_parser()
    args = parser.parse_args(["video.mp4", "--preset", "broadcast"])
    assert args.preset == "broadcast"
