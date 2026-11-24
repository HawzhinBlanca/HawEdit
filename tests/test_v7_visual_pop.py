"""Tests for V7 Visual Pop (Items #3 & #4, D-379 & D-380).

Covers:
- D-379: `extract_kurdish_callout_cards()` + face-aware Layer 2 `Callout` cards in `build_ass()`.
- D-380: Zero-ghosting `kinetic_entrance=True` (`\\fad(50,0)` on Layer 0/4 with 0.00 px shift
  relative to `\\clip`, subtle vertical micro-lift only on non-clipped Hook/Callout/SpeakerTag)
  and polished broadcast `SpeakerTag` lower-third styling (`\\fad(180,250)`).
- Real 1080x1920 ffmpeg/libass PNG render proof of Kurdish RTL callout cards + 0.00 px ghosting.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest

from hawedit.brand import SpeakerBio
from hawedit.captions import (
    CALLOUT_CARD_FONT_SIZE,
    CALLOUT_CARD_THEME,
    DEFAULT_CAPTION_FONT,
    KURDISH_NON_TERMINAL_WORDS,
    POPUP_MAX_CHARS,
    VIRAL_FONT_SIZE,
    VIRAL_THEME,
    CaptionStyle,
    build_ass,
    extract_kurdish_callout_cards,
    find_ffmpeg,
    subtitle_filter,
    verify_caption_integrity,
)
from hawedit.sentences import Sentence
from hawedit.transcripts import Word

FONTS_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"


def _w(text: str, start_ms: int, end_ms: int, conf: float = 0.96) -> Word:
    return Word(w=text, start_ms=start_ms, end_ms=end_ms, conf=conf)


def _dialogue_lines(ass_text: str) -> list[str]:
    return [line for line in ass_text.splitlines() if line.startswith("Dialogue:")]


def _render_frame_at(
    ffmpeg: Path,
    ass_path: Path,
    out_png: Path,
    *,
    timestamp_s: float,
    duration_s: float,
    width: int = 1080,
    height: int = 1920,
) -> Path:
    vf = subtitle_filter(ass_path, FONTS_DIR)
    subprocess.run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s={width}x{height}:d={duration_s:.2f}:r=20",
            "-vf",
            vf,
            "-ss",
            f"{timestamp_s:.3f}",
            "-frames:v",
            "1",
            "-y",
            str(out_png),
        ],
        check=True,
        capture_output=True,
        timeout=60.0,
    )
    return out_png


def test_extract_kurdish_callout_cards_filters_stopwords_spacing_and_bounds() -> None:
    """D-379: 1-3 word Kurdish phrases, stopword/particle filters, spacing, and hook/tail guards."""
    clip_in_ms = 10_000
    sentences = (
        # t_rel = 0.5..2.5 s (inside 0-4.5 s hook guard -> MUST be skipped)
        Sentence(
            words=(
                _w("زیرەکی", 10_500, 11_000),
                _w("دەستکرد", 11_050, 11_600),
                _w("گەورەترین", 11_650, 12_200),
                _w("شۆڕشە.", 12_250, 12_500),
            ),
            complete=True,
        ),
        # t_rel = 5.0..7.0 s (peak with stopwords + short <=2-char particles + punchy content)
        Sentence(
            words=(
                _w("بەڵام", 15_000, 15_300),
                _w("لە", 15_320, 15_450),
                _w("کوردستان", 15_500, 16_000),
                _w("داهاتووی", 16_050, 16_500),
                _w("تەکنەلۆژیا", 16_550, 17_000),
            ),
            complete=True,
        ),
        # t_rel = 9.0..10.5 s (too close to t_rel=5.5 s, < 10 s min_spacing -> skipped)
        Sentence(
            words=(
                _w("کێشەی", 19_000, 19_500),
                _w("گەورە", 19_550, 20_000),
                _w("دروستبوو.", 20_050, 20_500),
            ),
            complete=True,
        ),
        # t_rel = 17.0..18.5 s (ONLY stopwords & <=2-char particles -> MUST emit NO card)
        Sentence(
            words=(
                _w("و", 27_000, 27_200),
                _w("لە", 27_250, 27_450),
                _w("بە", 27_500, 27_700),
                _w("کە", 27_750, 28_000),
                _w("بەڵام", 28_050, 28_500),
            ),
            complete=True,
        ),
        # t_rel = 20.0..22.0 s (valid second card, >= 10 s after first)
        Sentence(
            words=(
                _w("بۆ", 30_000, 30_200),
                _w("گرنگترین", 30_250, 30_800),
                _w("بڕیاری", 30_850, 31_300),
                _w("بازاڕ.", 31_350, 31_900),
            ),
            complete=True,
        ),
        # t_rel = 33.0..34.8 s (within final 1.2 s of 35 s clip -> MUST be skipped)
        Sentence(
            words=(
                _w("کۆتایی", 43_000, 43_800),
                _w("بەرنامە.", 43_900, 44_800),
            ),
            complete=True,
        ),
    )
    excited_intervals_ms = (
        (10_500, 12_200),  # early hook zone
        (15_000, 17_000),  # peak 1 (t_rel ~5.5 s)
        (19_000, 20_500),  # too close to peak 1 (< 10 s)
        (27_000, 28_500),  # stopwords only
        (30_000, 31_900),  # peak 2 (t_rel ~20.25 s)
        (43_000, 44_800),  # tail guard (< 1.2 s from 35 s end)
    )

    cards = extract_kurdish_callout_cards(
        sentences,
        excited_intervals_ms,
        clip_in_ms=clip_in_ms,
        clip_duration_ms=35_000,
    )

    assert len(cards) == 2
    # Strictly chronological, clip-relative, >= 4.5 s start, <= clip_dur - 1.2 s end
    for start_rel, end_rel, phrase in cards:
        assert start_rel >= 4_500
        assert end_rel <= 35_000 - 1_200
        assert end_rel - start_rel == 2_200
        words = phrase.split()
        assert 1 <= len(words) <= 3
        for tok in words:
            assert len(tok) > 2
            assert tok not in KURDISH_NON_TERMINAL_WORDS

    # Spacing >= 10_000 ms
    assert cards[1][0] - cards[0][0] >= 10_000
    assert cards[1][0] >= cards[0][1]
    assert "کوردستان" in cards[0][2]
    assert "بەڵام" not in cards[0][2]
    assert "گرنگترین" in cards[1][2]
    assert "بۆ" not in cards[1][2]

    # Empty / too-short edge cases return empty tuple cleanly.
    assert extract_kurdish_callout_cards((), excited_intervals_ms) == ()
    assert extract_kurdish_callout_cards(sentences, ()) == ()
    assert (
        extract_kurdish_callout_cards(
            sentences, excited_intervals_ms, clip_in_ms=clip_in_ms, clip_duration_ms=5_000
        )
        == ()
    )


def test_build_ass_defaults_remain_byte_identical() -> None:
    """Default callout_cards=() and kinetic_entrance=False stay 100% byte-identical."""
    sent = Sentence(
        words=(_w("ئەمە", 0, 400), _w("زۆر", 450, 800), _w("باشە.", 850, 1300)),
        complete=True,
    )
    speakers = {"SPK0": SpeakerBio(name_ckb="د. ئاراس عومەر", title_ckb="پزیشکی پسپۆڕ")}
    turns = ((0, 3_500, "SPK0"),)

    implicit = build_ass(
        (sent,),
        style=CaptionStyle.LINE,
        theme=VIRAL_THEME,
        title_ckb="ئەمە تاقیکردنەوەیە",
        face_intervals=((0, 2_000, 500, 900),),
        speaker_metadata=speakers,
        speaker_turns=turns,
    )
    explicit = build_ass(
        (sent,),
        style=CaptionStyle.LINE,
        theme=VIRAL_THEME,
        title_ckb="ئەمە تاقیکردنەوەیە",
        face_intervals=((0, 2_000, 500, 900),),
        speaker_metadata=speakers,
        speaker_turns=turns,
        callout_cards=(),
        kinetic_entrance=False,
    )

    assert implicit == explicit
    assert "Style: Callout," not in implicit
    assert r"\fad(50,0)" not in implicit
    assert r"{\fad(250,250)}" in implicit


def test_build_ass_callout_cards_face_aware_and_style() -> None:
    """D-379: Callout style row + Layer 2 face-aware placement (y=155 top vs y=1240 chest)."""
    sent = Sentence(
        words=(
            _w("لە", 10_000, 10_300),
            _w("کوردستان", 10_350, 10_900),
            _w("زیرەکی", 15_000, 15_500),
            _w("دەستکرد", 15_550, 16_200),
            _w("گەشە", 26_000, 26_500),
            _w("دەکات.", 26_550, 27_200),
        ),
        complete=True,
    )
    cards = (
        (5_000, 7_200, "زیرەکی دەستکرد"),
        (16_000, 18_200, "گۆڕانکاری گەورە"),
    )
    # Face occupies top band (y_top=220 < 420) ONLY during card 2 (source 25_500..28_500),
    # while card 1 (source 15_000..17_200) has clear top headroom (y_top=480 >= 420).
    face_intervals = (
        (14_500, 18_000, 480, 980),
        (25_500, 28_500, 220, 740),
    )

    ass = build_ass(
        (sent,),
        font_name=DEFAULT_CAPTION_FONT,
        font_size=VIRAL_FONT_SIZE,
        style=CaptionStyle.LINE,
        theme=VIRAL_THEME,
        clip_in_ms=10_000,
        clip_duration_ms=20_000,
        max_chars_per_line=POPUP_MAX_CHARS,
        max_words_per_event=3,
        face_intervals=face_intervals,
        callout_cards=cards,
        kinetic_entrance=False,
    )

    style_line = next(line for line in ass.splitlines() if line.startswith("Style: Callout,"))
    assert f"Style: Callout,{DEFAULT_CAPTION_FONT},{CALLOUT_CARD_FONT_SIZE}," in style_line
    assert CALLOUT_CARD_THEME.primary in style_line
    assert ",1,6,4,8," in style_line

    callout_lines = [line for line in _dialogue_lines(ass) if ",Callout," in line]
    assert len(callout_lines) == 2
    assert callout_lines[0].startswith("Dialogue: 2,0:00:05.00,0:00:07.20,Callout,")
    assert (
        r"{\an8\pos(540,155)\fscx86\fscy86\t(0,140,\fscx100\fscy100)\fad(60,220)}زیرەکی دەستکرد"
        in callout_lines[0]
    )
    assert callout_lines[1].startswith("Dialogue: 2,0:00:16.00,0:00:18.20,Callout,")
    assert (
        r"{\an2\pos(540,1240)\fscx86\fscy86\t(0,140,\fscx100\fscy100)\fad(60,220)}گۆڕانکاری گەورە"
        in callout_lines[1]
    )

    verify_caption_integrity(
        ass,
        expected_text=" ".join(w.w for w in sent.words),
        fonts_dir=FONTS_DIR,
    )


def test_build_ass_kinetic_entrance_zero_ghosting_and_speaker_tag_polish() -> None:
    """D-380: \\fad(50,0) on Layer 0 & 4 (0 px shift), micro-lift only on non-clipped overlays."""
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        pytest.skip("ffmpeg unavailable for WORD_HIGHLIGHT box measurement")

    sent = Sentence(
        words=(
            _w("ئەمە", 0, 450),
            _w("کوردستان", 500, 1_100),
            _w("جوانە.", 1_150, 1_700),
        ),
        complete=True,
    )
    speakers = {"SPK0": SpeakerBio(name_ckb="د. ئاراس عومەر", title_ckb="پسپۆڕی زیرەکی دەستکرد")}
    turns = ((0, 3_500, "SPK0"),)

    ass = build_ass(
        (sent,),
        font_name=DEFAULT_CAPTION_FONT,
        font_size=VIRAL_FONT_SIZE,
        style=CaptionStyle.WORD_HIGHLIGHT,
        theme=VIRAL_THEME,
        clip_in_ms=0,
        clip_duration_ms=8_000,
        title_ckb="داهاتووی زیرەکی دەستکرد لە کوردستان",
        face_intervals=((0, 8_000, 480, 960),),
        speaker_metadata=speakers,
        speaker_turns=turns,
        excited_intervals_ms=((450, 1_150),),
        callout_cards=((4_500, 6_700, "زیرەکی دەستکرد"),),
        fonts_dir=FONTS_DIR,
        kinetic_entrance=True,
    )

    lines = _dialogue_lines(ass)
    base_lines = [ln for ln in lines if ",Kurdish," in ln]
    hl_lines = [ln for ln in lines if ",KurdishHighlight," in ln]
    hook_lines = [ln for ln in lines if ",Hook," in ln]
    callout_lines = [ln for ln in lines if ",Callout," in ln]
    speaker_lines = [ln for ln in lines if ",SpeakerTag," in ln]

    assert len(base_lines) == 1
    assert len(hl_lines) == 3
    assert len(hook_lines) == 1
    assert len(callout_lines) == 1
    assert len(speaker_lines) == 1

    # Layer 0 base popup & Layer 4 word highlight carry \fad(50,0) and ZERO position/move shift!
    assert r"{\fad(50,0)}" in base_lines[0]
    assert r"\move(" not in base_lines[0] and r"\pos(" not in base_lines[0]
    for hl in hl_lines:
        assert r"\fad(50,0)" in hl
        assert r"\clip(" in hl
        assert r"\move(" not in hl and r"\pos(" not in hl

    # Non-clipped overlays carry smooth vertical micro-lift via \move(...)
    assert r"\an8\move(540,107,540,95,0,160)\fad(0,250)" in hook_lines[0]
    assert r"\an8\move(540,169,540,155,0,140)\fscx86\fscy86" in callout_lines[0]
    assert r"\an3\move(1020,1652,1020,1640,0,180)\fad(180,250)" in speaker_lines[0]
    assert r"\c&H00D7FF&" in speaker_lines[0]

    verify_caption_integrity(
        ass,
        expected_text="ئەمە کوردستان جوانە.",
        fonts_dir=FONTS_DIR,
    )


def test_real_1080x1920_ffmpeg_render_callout_and_zero_ghosting_karaoke(tmp_path: Path) -> None:
    """Real 1080x1920 ffmpeg/libass render: crisp RTL callout cards + 0.00 px karaoke ghosting."""
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        pytest.skip("ffmpeg unavailable")

    sentences = (
        Sentence(
            words=(
                _w("سڵاو", 0, 400),
                _w("لە", 450, 700),
                _w("هەموو", 750, 1_100),
                _w("بینەران.", 1_150, 1_600),
            ),
            complete=True,
        ),
        Sentence(
            words=(
                _w("لە", 4_800, 5_000),
                _w("کوردستان", 5_050, 5_600),
                _w("زیرەکی", 5_650, 6_200),
                _w("دەستکرد.", 6_250, 6_900),
            ),
            complete=True,
        ),
    )
    excited = ((5_050, 6_850),)
    cards = extract_kurdish_callout_cards(
        sentences,
        excited,
        clip_in_ms=0,
        clip_duration_ms=9_000,
    )
    assert len(cards) == 1
    card_start_ms, card_end_ms, _phrase = cards[0]
    assert card_start_ms >= 4_500 and card_end_ms <= 7_800

    # 1. Top-safe callout + kinetic WORD_HIGHLIGHT karaoke rendered together at 1080x1920.
    top_ass = build_ass(
        sentences,
        font_name=DEFAULT_CAPTION_FONT,
        font_size=VIRAL_FONT_SIZE,
        style=CaptionStyle.WORD_HIGHLIGHT,
        theme=VIRAL_THEME,
        clip_in_ms=0,
        clip_duration_ms=9_000,
        max_chars_per_line=POPUP_MAX_CHARS,
        max_words_per_event=3,
        face_intervals=((0, 9_000, 480, 960),),
        excited_intervals_ms=excited,
        callout_cards=cards,
        fonts_dir=FONTS_DIR,
        kinetic_entrance=True,
    )
    verify_caption_integrity(
        top_ass,
        expected_text=" ".join(w.w for s in sentences for w in s.words),
        fonts_dir=FONTS_DIR,
    )
    top_ass_path = tmp_path / "v7_callout_top.ass"
    top_ass_path.write_text(top_ass, encoding="utf-8")

    # Render at t = 5.90 s: callout card fully settled (140 ms pop-in done) AND karaoke word active.
    top_png = _render_frame_at(
        ffmpeg,
        top_ass_path,
        tmp_path / "v7_callout_top.png",
        timestamp_s=5.90,
        duration_s=6.50,
    )
    img_bgr = cv2.imread(str(top_png), cv2.IMREAD_COLOR)
    assert img_bgr is not None
    assert img_bgr.shape == (1920, 1080, 3)

    # Top-safe callout band (y in 80..360): crisp Electric-Lime (#B8FF2E -> BGR ~46,255,184) ink!
    top_band = img_bgr[80:360, :, :]
    lime_mask = (top_band[:, :, 1] > 180) & (top_band[:, :, 2] > 110) & (top_band[:, :, 0] < 100)
    assert int(np.count_nonzero(lime_mask)) > 500, "Electric-Lime callout pixels missing on top"

    # Bottom karaoke band (y >= 1300): crisp caption pixels present with zero overlap into callout!
    bottom_gray = cv2.cvtColor(img_bgr[1300:, :, :], cv2.COLOR_BGR2GRAY)
    assert int(np.count_nonzero(bottom_gray > 40)) > 1_000
    # Middle safe band (y in 420..1180) stays completely clear (zero leak into face area).
    mid_gray = cv2.cvtColor(img_bgr[420:1180, :, :], cv2.COLOR_BGR2GRAY)
    assert int(np.count_nonzero(mid_gray > 20)) == 0

    # 2. Chest-safe relocation when face occupies top (f_top=220 < 420): lands y in 1050..1300.
    reloc_ass = build_ass(
        sentences,
        font_name=DEFAULT_CAPTION_FONT,
        font_size=VIRAL_FONT_SIZE,
        style=CaptionStyle.WORD_HIGHLIGHT,
        theme=VIRAL_THEME,
        clip_in_ms=0,
        clip_duration_ms=9_000,
        max_chars_per_line=POPUP_MAX_CHARS,
        max_words_per_event=3,
        face_intervals=((0, 9_000, 220, 740),),
        excited_intervals_ms=excited,
        callout_cards=cards,
        fonts_dir=FONTS_DIR,
        kinetic_entrance=True,
    )
    reloc_ass_path = tmp_path / "v7_callout_chest.ass"
    reloc_ass_path.write_text(reloc_ass, encoding="utf-8")
    reloc_png = _render_frame_at(
        ffmpeg,
        reloc_ass_path,
        tmp_path / "v7_callout_chest.png",
        timestamp_s=5.90,
        duration_s=6.50,
    )
    reloc_bgr = cv2.imread(str(reloc_png), cv2.IMREAD_COLOR)
    assert reloc_bgr is not None
    # Top face zone (y < 740) is 100% clear of callout ink!
    assert int(np.count_nonzero(cv2.cvtColor(reloc_bgr[:740, :, :], cv2.COLOR_BGR2GRAY) > 20)) == 0
    # Chest-safe band (y in 1020..1290) holds the Electric-Lime callout card cleanly above karaoke.
    chest_band = reloc_bgr[1020:1290, :, :]
    chest_lime = (
        (chest_band[:, :, 1] > 180) & (chest_band[:, :, 2] > 110) & (chest_band[:, :, 0] < 100)
    )
    assert int(np.count_nonzero(chest_lime)) > 500

    # 3. 0.00 px ghosting proof:
    # (a) Compare kinetic_entrance=True vs kinetic_entrance=False in karaoke band at t=5.90 s
    #     (after 50 ms fade-in settles, mid-\clip sweep): must be bit-for-bit identical (0.00 px!).
    static_ass = build_ass(
        sentences,
        font_name=DEFAULT_CAPTION_FONT,
        font_size=VIRAL_FONT_SIZE,
        style=CaptionStyle.WORD_HIGHLIGHT,
        theme=VIRAL_THEME,
        clip_in_ms=0,
        clip_duration_ms=9_000,
        max_chars_per_line=POPUP_MAX_CHARS,
        max_words_per_event=3,
        face_intervals=((0, 9_000, 480, 960),),
        excited_intervals_ms=excited,
        callout_cards=cards,
        fonts_dir=FONTS_DIR,
        kinetic_entrance=False,
    )
    static_ass_path = tmp_path / "v7_static_ref.ass"
    static_ass_path.write_text(static_ass, encoding="utf-8")
    static_png = _render_frame_at(
        ffmpeg,
        static_ass_path,
        tmp_path / "v7_static_ref.png",
        timestamp_s=5.90,
        duration_s=6.50,
    )
    static_bgr = cv2.imread(str(static_png), cv2.IMREAD_COLOR)
    assert static_bgr is not None
    assert np.array_equal(img_bgr[1300:, :, :], static_bgr[1300:, :, :]), (
        "kinetic_entrance=True displaced karaoke pixels relative to static \\clip reference"
    )

    # (b) Verify Layer 4 actually painted highlight colour onto the active word (non-trivial check).
    layer0_only_ass = "\n".join(
        line for line in top_ass.splitlines() if not line.startswith("Dialogue: 4,")
    )
    layer0_path = tmp_path / "v7_layer0_only.ass"
    layer0_path.write_text(layer0_only_ass + "\n", encoding="utf-8")
    layer0_png = _render_frame_at(
        ffmpeg,
        layer0_path,
        tmp_path / "v7_layer0_only.png",
        timestamp_s=5.90,
        duration_s=6.50,
    )
    l0_bgr = cv2.imread(str(layer0_png), cv2.IMREAD_COLOR)
    assert l0_bgr is not None
    color_diff = (
        np.abs(img_bgr[1300:, :, :].astype(np.int16) - l0_bgr[1300:, :, :].astype(np.int16)).max(
            axis=2
        )
        > 40
    )
    assert int(np.count_nonzero(color_diff)) > 400

    # (c) Mid-fade check (t=5.67 s, 20 ms into \fad(50,0)): kinetic render stays strictly inside
    #     the static \clip footprint (0.00 px shift!) while actively fading opacity.
    fade_png = _render_frame_at(
        ffmpeg,
        top_ass_path,
        tmp_path / "v7_mid_fade.png",
        timestamp_s=5.67,
        duration_s=6.00,
    )
    static_fade_png = _render_frame_at(
        ffmpeg,
        static_ass_path,
        tmp_path / "v7_static_mid_fade.png",
        timestamp_s=5.67,
        duration_s=6.00,
    )
    fade_bgr = cv2.imread(str(fade_png), cv2.IMREAD_COLOR)
    static_fade_bgr = cv2.imread(str(static_fade_png), cv2.IMREAD_COLOR)
    assert fade_bgr is not None and static_fade_bgr is not None
    fade_ink = np.max(fade_bgr[1300:, :, :], axis=2) > 24
    static_fade_footprint = np.max(static_fade_bgr[1300:, :, :], axis=2) > 0
    assert int(np.count_nonzero(fade_ink & (~static_fade_footprint))) == 0
