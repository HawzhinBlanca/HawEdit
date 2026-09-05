"""Regression tests for Broadcast Studio Multi-Cam Framing & Subtitle Direction (ADR D-272).

Combines high-value regression coverage of:
- Locked-off tripod multi-cam framing and instant camera cut transitions
- Clean broadcast line subtitles without inline override tags
- Lower-third speaker introduction badges with dark backing plates
- Outro end cards with call-to-action branding
- BrandKit asset and geometry validation
- Broadcast Studio preset, safe margins (margin_v=440), and tight framing
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hawedit.brand import BrandKit, BrandKitError, EndCardConfig, SpeakerBio
from hawedit.captions import (
    BROADCAST_THEME,
    CaptionStyle,
    CaptionTheme,
    build_ass,
    contrast_ratio,
    parse_ass_colour,
    relative_luminance,
)
from hawedit.pipeline import build_parser
from hawedit.render import crop_filter, vertical_framing
from hawedit.sentences import Sentence
from hawedit.transcripts import Word


@pytest.fixture
def sample_sentence() -> Sentence:
    words = (
        Word(w="پۆڵ", start_ms=1000, end_ms=1400, conf=0.95),
        Word(w="برێمەر", start_ms=1400, end_ms=1900, conf=0.96),
        Word(w="ویستی", start_ms=1900, end_ms=2300, conf=0.92),
        Word(w="پێشمەرگە", start_ms=2300, end_ms=2900, conf=0.98),
        Word(w="هەڵبوەشێنێتەوە", start_ms=2900, end_ms=3600, conf=0.94),
        Word(w="بە تەواوی", start_ms=3900, end_ms=4500, conf=0.91),
        Word(w="بەڵام", start_ms=4500, end_ms=4900, conf=0.93),
        Word(w="قبوڵ", start_ms=4900, end_ms=5300, conf=0.97),
        Word(w="نەکرا", start_ms=5300, end_ms=5800, conf=0.99),
    )
    return Sentence(words=words, complete=True)


def words_helper(*specs: tuple[str, int, int]) -> tuple[Word, ...]:
    return tuple(Word(w=w, start_ms=s, end_ms=e, conf=1.0) for w, s, e in specs)


# --- D-272 Broadcast Multi-Cam & Subtitle Direction Tests ---


def test_locked_tripod_crop_filter_produces_static_coordinates_within_shot() -> None:
    pts = [
        (1000, 1300),
        (3000, 1300),
    ]
    filt = crop_filter(
        source_width=2560,
        source_height=1440,
        focus_points=pts,
        clip_in_ms=1000,
        punch_ins=(),
    )
    # Start and end center_x are identical, so 895 is the constant coordinate
    assert "895" in filt
    assert "scale=1080:1920" in filt


def test_instant_camera_cut_transitions_on_subframe_delta() -> None:
    pts = [
        (1000, 1300),
        (2999, 1300),
        (3000, 1980),
        (5000, 1980),
    ]
    filt = crop_filter(
        source_width=2560,
        source_height=1440,
        focus_points=pts,
        clip_in_ms=1000,
        punch_ins=(),
    )
    # Transition delta is 1ms (0.001s), evaluating to an instant cut
    assert "895" in filt
    assert "1575" in filt
    assert "0.001" in filt


def test_broadcast_line_subtitles_emit_clean_white_text_without_override_tags(
    sample_sentence: Sentence,
) -> None:
    theme = CaptionTheme(
        primary="&H00FFFFFF",
        secondary="&H00FFFFFF",
        bold=True,
        outline=3.0,
        shadow=1.5,
        outline_colour="&H00000000",
        margin_v=280,
    )
    ass = build_ass(
        [sample_sentence],
        font_size=60,
        style=CaptionStyle.LINE,
        clip_in_ms=1000,
        clip_duration_ms=6000,
        theme=theme,
        max_words_per_event=5,
        keyword_emphasis=False,
    )
    dialogue_lines = [line for line in ass.splitlines() if line.startswith("Dialogue: 0,")]
    assert len(dialogue_lines) >= 2
    for line in dialogue_lines:
        text = line.split(",,", 1)[1]
        assert "\\kf" not in text
        assert "\\c&H" not in text
        assert "\\fscx" not in text


def test_broadcast_line_subtitles_chunk_events_to_max_words(
    sample_sentence: Sentence,
) -> None:
    ass = build_ass(
        [sample_sentence],
        font_size=60,
        style=CaptionStyle.LINE,
        clip_in_ms=1000,
        clip_duration_ms=6000,
        max_words_per_event=4,
        keyword_emphasis=False,
    )
    dialogue_lines = [line for line in ass.splitlines() if line.startswith("Dialogue: 0,")]
    assert len(dialogue_lines) == 3
    # First chunk has 4 words
    assert "پۆڵ برێمەر ویستی پێشمەرگە" in dialogue_lines[0]


def test_broadcast_line_subtitles_hold_across_short_gaps(
    sample_sentence: Sentence,
) -> None:
    ass = build_ass(
        [sample_sentence],
        font_size=60,
        style=CaptionStyle.LINE,
        clip_in_ms=1000,
        clip_duration_ms=6000,
        max_words_per_event=5,
        keyword_emphasis=False,
    )
    dialogue_lines = [line for line in ass.splitlines() if line.startswith("Dialogue: 0,")]
    assert len(dialogue_lines) == 3


def test_speaker_tag_emits_layer_2_lower_third_with_dark_plate(
    sample_sentence: Sentence,
) -> None:
    speaker_metadata = {
        "SPK0": SpeakerBio(name_ckb="سامان فارس", title_ckb="پێشکەشکار"),
    }
    speaker_turns = ((1000, 5000, "SPK0"),)

    ass = build_ass(
        [sample_sentence],
        clip_in_ms=1000,
        clip_duration_ms=6000,
        speaker_turns=speaker_turns,
        speaker_metadata=speaker_metadata,
        keyword_emphasis=False,
    )
    tag_lines = [line for line in ass.splitlines() if line.startswith("Dialogue: 2,")]
    assert len(tag_lines) == 1
    assert "SpeakerTag" in tag_lines[0]
    assert "سامان فارس" in tag_lines[0]
    assert "پێشکەشکار" in tag_lines[0]


def test_speaker_tag_includes_fade_transition(sample_sentence: Sentence) -> None:
    speaker_metadata = {
        "SPK0": SpeakerBio(name_ckb="د. شێروان میرزا", title_ckb="شیکەرەوە"),
    }
    speaker_turns = ((1000, 5000, "SPK0"),)

    ass = build_ass(
        [sample_sentence],
        clip_in_ms=1000,
        clip_duration_ms=6000,
        speaker_turns=speaker_turns,
        speaker_metadata=speaker_metadata,
        keyword_emphasis=False,
    )
    assert "{\\fad(250,250)}" in ass


def test_speaker_tag_omits_subsequent_duplicate_within_suppression_window(
    sample_sentence: Sentence,
) -> None:
    speaker_metadata = {
        "SPK0": SpeakerBio(name_ckb="سامان فارس"),
    }
    # Two rapid turns 2 seconds apart for the same speaker
    speaker_turns = (
        (1000, 2500, "SPK0"),
        (2800, 4500, "SPK0"),
    )
    ass = build_ass(
        [sample_sentence],
        clip_in_ms=1000,
        clip_duration_ms=6000,
        speaker_turns=speaker_turns,
        speaker_metadata=speaker_metadata,
        keyword_emphasis=False,
    )
    tag_lines = [line for line in ass.splitlines() if line.startswith("Dialogue: 2,")]
    # Suppressed within 8000ms window
    assert len(tag_lines) == 1


def test_outro_end_card_emits_layer_3_closing_cta(sample_sentence: Sentence) -> None:
    end_card = EndCardConfig(
        enabled=True,
        duration_s=2.0,
        title_ckb="پۆڵ برێمەر",
        subtitle_ckb="سەردانی چەناڵ بکەن",
        handle="@zarpodcast",
    )
    ass = build_ass(
        [sample_sentence],
        clip_in_ms=1000,
        clip_duration_ms=6000,
        end_card=end_card,
        keyword_emphasis=False,
    )
    end_card_lines = [line for line in ass.splitlines() if line.startswith("Dialogue: 3,")]
    assert len(end_card_lines) == 1
    assert "EndCard" in end_card_lines[0]
    assert "@zarpodcast" in end_card_lines[0]
    assert "پۆڵ برێمەر" in end_card_lines[0]


def test_outro_end_card_duration_clamped_to_clip_duration(sample_sentence: Sentence) -> None:
    end_card = EndCardConfig(
        enabled=True,
        duration_s=2.5,
        title_ckb="کۆتایی",
    )
    ass = build_ass(
        [sample_sentence],
        clip_in_ms=1000,
        clip_duration_ms=5000,
        end_card=end_card,
        keyword_emphasis=False,
    )
    # Clip duration is 5.0s, end card is 2.5s -> start should be 0:00:02.50 to 0:00:05.00
    assert "0:00:02.50,0:00:05.00,EndCard" in ass


def test_brand_kit_validates_missing_logo_file(tmp_path: Path) -> None:
    non_existent = tmp_path / "absent_logo.png"
    kit = BrandKit(logo_path=non_existent)
    with pytest.raises(BrandKitError, match="not found"):
        kit.assert_valid()


def test_brand_kit_validates_opacity_range(tmp_path: Path) -> None:
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(ValueError, match="opacity"):
        BrandKit(logo_path=logo, logo_opacity=1.5)


def test_brand_kit_validates_width_bounds(tmp_path: Path) -> None:
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(ValueError, match="width"):
        BrandKit(logo_path=logo, logo_width=-10)


def test_brand_kit_validates_position_enum(tmp_path: Path) -> None:
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(ValueError, match="logo_position"):
        BrandKit(logo_path=logo, logo_position="center_floating")


def test_broadcast_theme_wcag_contrast() -> None:
    theme = CaptionTheme(
        primary="&H00FFFFFF",
        outline_colour="&H00000000",
    )
    text_rgb = parse_ass_colour(theme.primary)
    bg_dark = (20, 20, 20)
    lum_text = relative_luminance(*text_rgb)
    lum_bg = relative_luminance(*bg_dark)
    cr = contrast_ratio(lum_text, lum_bg)
    # Pure white over dark background exceeds AAA contrast (7.0)
    assert cr > 15.0


def test_broadcast_subtitles_respect_vertical_margin_safe_zone() -> None:
    theme = CaptionTheme(margin_v=280)
    style_line = theme.style_row("Kurdish", "Noto Naskh Arabic", 60)
    assert ",280,1" in style_line


def test_locked_focus_points_multi_shot_sequence() -> None:
    pts = [
        (1000, 1300),
        (2000, 1300),
        (2001, 580),
        (4000, 580),
        (4001, 1980),
        (6000, 1980),
    ]
    filt = crop_filter(
        source_width=2560,
        source_height=1440,
        focus_points=pts,
        clip_in_ms=1000,
        lanczos=True,
        unsharp=True,
    )
    assert "895" in filt
    assert "175" in filt
    assert "1575" in filt
    assert "flags=lanczos" in filt
    assert "unsharp=5:5:0.5:5:5:0.0" in filt


# --- feat(broadcast) Preset & Styling Tests ---


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
    sentence = Sentence(words=words_helper(("سڵاو", 100, 500)), complete=True)
    ass_custom = build_ass((sentence,), margin_v=480)
    assert ",480,1" in ass_custom

    ass_default = build_ass((sentence,))
    assert ",140,1" in ass_default


def test_build_ass_broadcast_studio_formatting() -> None:
    """BROADCAST_STUDIO chunks phrases cleanly and highlights Kurdish keywords inline."""
    test_words = words_helper(
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
