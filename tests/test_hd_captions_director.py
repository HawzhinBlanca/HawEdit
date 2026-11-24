"""Tests for Lane 3 (`hd-captions`, D-362): face-aware hook card, orphan merge, acoustic pop,
and deterministic Sorani digit normalization.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from hawedit.caption_polish import normalize_sorani_digits, polish_clip_sentences
from hawedit.captions import (
    DEFAULT_CAPTION_FONT,
    POPUP_MAX_CHARS,
    POPUP_MAX_WIDTH_PX,
    VIRAL_FONT_SIZE,
    VIRAL_THEME,
    CaptionStyle,
    build_ass,
    find_ffmpeg,
    render_caption_png,
    verify_caption_integrity,
)
from hawedit.sentences import Sentence, assert_deliverable_order
from hawedit.transcripts import Word

FONTS_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
_EXCITED_POP_SNIPPET = r"\1c&H002EFFB8&"


def _w(text: str, start_ms: int, end_ms: int, conf: float = 0.95) -> Word:
    return Word(w=text, start_ms=start_ms, end_ms=end_ms, conf=conf)


def _dialogue_lines(ass_text: str) -> list[str]:
    return [line for line in ass_text.splitlines() if line.startswith("Dialogue:")]


def test_build_ass_face_aware_hook_card_orphan_merge_and_excited_pop(tmp_path: Path) -> None:
    """AC-6, AC-7, AC-8 / T6 (D-362): face-aware hook card, zero-orphan merge, excited pop."""
    long_title = "ئایا ژیری دەستکرد جێگەی مرۆڤ دەگرێتەوە لە داهاتوودا؟"
    # 4-word sentence where word 4 (`لێی`, 3 chars <= 4) trails word 3 by 100 ms (<= 250 ms)
    # plus a second 4-word sentence with a 320 ms pause before short word `لە` and a 3rd with
    # a long trailing word `کوردستان` (> 4 chars).
    s_orphan = Sentence(
        words=(
            _w("ئەمە", 0, 350),
            _w("بابەتێکی", 380, 750),
            _w("زۆر", 780, 1000),
            _w("لێی", 1100, 1350),
        ),
        complete=True,
    )
    s_pause_gap = Sentence(
        words=(
            _w("ئەوان", 2000, 2300),
            _w("ئەمڕۆ", 2350, 2650),
            _w("هاتن", 2700, 2900),
            _w("بۆ.", 3220, 3450),  # gap 320 ms > 250 ms -> must NOT merge
        ),
        complete=True,
    )
    s_long_tail = Sentence(
        words=(
            _w("ئێمە", 4000, 4300),
            _w("باسی", 4350, 4650),
            _w("شاری", 4700, 4950),
            _w("کوردستان.", 5050, 5500),  # 9 chars > 4 -> must NOT merge
        ),
        complete=True,
    )

    # 1. Golden / legacy parity: face_intervals=None, defaults produce exact legacy Hook line
    # with max_chars_per_line=20 wrapping (>= 3 lines) and no \pos override.
    legacy_ass = build_ass(
        (s_orphan,),
        font_name=DEFAULT_CAPTION_FONT,
        font_size=VIRAL_FONT_SIZE,
        style=CaptionStyle.LINE,
        theme=VIRAL_THEME,
        title_ckb=long_title,
        max_chars_per_line=POPUP_MAX_CHARS,
        max_words_per_event=3,
    )
    legacy_explicit_defaults = build_ass(
        (s_orphan,),
        font_name=DEFAULT_CAPTION_FONT,
        font_size=VIRAL_FONT_SIZE,
        style=CaptionStyle.LINE,
        theme=VIRAL_THEME,
        title_ckb=long_title,
        max_chars_per_line=POPUP_MAX_CHARS,
        max_words_per_event=3,
        face_intervals=None,
        merge_short_orphans=False,
        excited_intervals_ms=(),
    )
    assert legacy_ass == legacy_explicit_defaults
    legacy_hook = next(line for line in _dialogue_lines(legacy_ass) if ",Hook," in line)
    assert r"\pos(" not in legacy_hook
    assert legacy_hook.count(r"\N") >= 2  # cramped 3-4 line block at 20 chars

    # 2a. Face-aware hook card: frame-0 face top < 420 px -> sleek <=2-line card relocated to
    # clean lower-mid safe band `\an2\pos(540,1260)`.
    relocated_ass = build_ass(
        (s_orphan,),
        font_name=DEFAULT_CAPTION_FONT,
        font_size=VIRAL_FONT_SIZE,
        style=CaptionStyle.LINE,
        theme=VIRAL_THEME,
        title_ckb=long_title,
        max_chars_per_line=POPUP_MAX_CHARS,
        max_words_per_event=3,
        face_intervals=((0, 2000, 260, 760),),
    )
    relocated_hook = next(line for line in _dialogue_lines(relocated_ass) if ",Hook," in line)
    assert r"{\an2\pos(540,1260)\fad(0,250)}" in relocated_hook
    assert ",1,7,4,8," in next(
        line for line in relocated_ass.splitlines() if line.startswith("Style: Hook,")
    )
    assert relocated_hook.count(r"\N") <= 1  # sleek 2-line wide card (>= 30 chars/line)
    verify_caption_integrity(relocated_ass, fonts_dir=FONTS_DIR)

    # 2b. Face-aware hook card: frame-0 face top >= 420 px -> clean top headroom `\an8\pos(540,95)`.
    headroom_ass = build_ass(
        (s_orphan,),
        font_name=DEFAULT_CAPTION_FONT,
        font_size=VIRAL_FONT_SIZE,
        style=CaptionStyle.LINE,
        theme=VIRAL_THEME,
        title_ckb=long_title,
        max_chars_per_line=POPUP_MAX_CHARS,
        max_words_per_event=3,
        face_intervals=((0, 2000, 480, 960),),
    )
    headroom_hook = next(line for line in _dialogue_lines(headroom_ass) if ",Hook," in line)
    assert r"{\an8\pos(540,95)\fad(0,250)}" in headroom_hook
    assert headroom_hook.count(r"\N") <= 1
    verify_caption_integrity(headroom_ass, fonts_dir=FONTS_DIR)

    # 2c. Face appearing AFTER frame-0 window (start_ms > 500) keeps top headroom.
    late_face_ass = build_ass(
        (s_orphan,),
        font_name=DEFAULT_CAPTION_FONT,
        font_size=VIRAL_FONT_SIZE,
        style=CaptionStyle.LINE,
        theme=VIRAL_THEME,
        title_ckb=long_title,
        max_chars_per_line=POPUP_MAX_CHARS,
        max_words_per_event=3,
        face_intervals=((800, 2500, 200, 700),),
    )
    late_hook = next(line for line in _dialogue_lines(late_face_ass) if ",Hook," in line)
    assert r"{\an8\pos(540,95)\fad(0,250)}" in late_hook

    # 2d. Non-zero clip_in_ms with source-time frame-0 overlapping face also relocates cleanly.
    shifted_sentence = Sentence(
        words=(_w("سڵاو", 10_000, 10_500), _w("کوردستان.", 10_550, 11_200)),
        complete=True,
    )
    shifted_ass = build_ass(
        (shifted_sentence,),
        font_name=DEFAULT_CAPTION_FONT,
        font_size=VIRAL_FONT_SIZE,
        style=CaptionStyle.LINE,
        theme=VIRAL_THEME,
        title_ckb=long_title,
        clip_in_ms=10_000,
        clip_duration_ms=2_000,
        max_chars_per_line=POPUP_MAX_CHARS,
        face_intervals=((10_200, 12_000, 250, 720),),
    )
    shifted_hook = next(line for line in _dialogue_lines(shifted_ass) if ",Hook," in line)
    assert r"{\an2\pos(540,1260)\fad(0,250)}" in shifted_hook

    # 2e. Real libass pixel placement check when ffmpeg is present: relocated hook card ink
    # lands in lower-mid band (y > 900) and top headroom ink lands in top band (y < 400).
    ffmpeg = find_ffmpeg()
    if ffmpeg is not None:
        reloc_ass_path = tmp_path / "hook_relocated.ass"
        reloc_ass_path.write_text(relocated_ass, encoding="utf-8")
        reloc_png = render_caption_png(
            ffmpeg,
            reloc_ass_path,
            FONTS_DIR,
            tmp_path / "hook_relocated.png",
            timestamp_s=0.0,
        )
        reloc_img = cv2.imread(str(reloc_png), cv2.IMREAD_GRAYSCALE)
        assert reloc_img is not None
        # Mask out bottom caption area (y >= 1350) and verify hook card sits cleanly below y=800
        upper_mid_ys = np.where(reloc_img[:1350, :] > 20)[0]
        assert upper_mid_ys.size > 0
        assert int(upper_mid_ys.min()) >= 800, (
            f"hook card leaked into forehead: {upper_mid_ys.min()}"
        )

    # 3. Zero-orphan chunk merge (`merge_short_orphans=True` vs `False`):
    without_merge = build_ass(
        (s_orphan, s_pause_gap, s_long_tail),
        font_name=DEFAULT_CAPTION_FONT,
        font_size=VIRAL_FONT_SIZE,
        style=CaptionStyle.LINE,
        theme=VIRAL_THEME,
        max_chars_per_line=POPUP_MAX_CHARS,
        max_words_per_event=3,
        merge_short_orphans=False,
    )
    with_merge = build_ass(
        (s_orphan, s_pause_gap, s_long_tail),
        font_name=DEFAULT_CAPTION_FONT,
        font_size=VIRAL_FONT_SIZE,
        style=CaptionStyle.LINE,
        theme=VIRAL_THEME,
        max_chars_per_line=POPUP_MAX_CHARS,
        max_words_per_event=3,
        merge_short_orphans=True,
    )
    no_merge_events = _dialogue_lines(without_merge)
    merged_events = _dialogue_lines(with_merge)
    # Without merge: 2 + 2 + 2 = 6 events (s_orphan produces 1-word `لێی` event).
    assert len(no_merge_events) == 6
    assert "لێی" in no_merge_events[1] and "ئەمە" not in no_merge_events[1]
    # With merge: s_orphan merges `لێی` into chunk 0 -> 1 + 2 + 2 = 5 events.
    assert len(merged_events) == 5
    assert "ئەمە بابەتێکی زۆر لێی" in merged_events[0]
    # s_pause_gap (gap 320 ms > 250 ms) and s_long_tail (9 chars > 4) remain split.
    assert "بۆ." in merged_events[2] and "ئەوان" not in merged_events[2]
    assert "کوردستان." in merged_events[4] and "ئێمە" not in merged_events[4]
    verify_caption_integrity(
        with_merge,
        expected_text=" ".join(w.w for s in (s_orphan, s_pause_gap, s_long_tail) for w in s.words),
        fonts_dir=FONTS_DIR,
    )

    # 3b. When max_popup_width_px is tight, merge must NOT overflow width budget.
    if ffmpeg is not None:
        tight_merge = build_ass(
            (s_orphan,),
            font_name=DEFAULT_CAPTION_FONT,
            font_size=VIRAL_FONT_SIZE,
            style=CaptionStyle.LINE,
            theme=VIRAL_THEME,
            max_chars_per_line=POPUP_MAX_CHARS,
            max_words_per_event=3,
            max_popup_width_px=200,  # far too narrow for 4 words at 128 pt
            fonts_dir=FONTS_DIR,
            merge_short_orphans=True,
        )
        assert len(_dialogue_lines(tight_merge)) > 1

        generous_merge = build_ass(
            (s_orphan,),
            font_name=DEFAULT_CAPTION_FONT,
            font_size=VIRAL_FONT_SIZE,
            style=CaptionStyle.LINE,
            theme=VIRAL_THEME,
            max_chars_per_line=POPUP_MAX_CHARS,
            max_words_per_event=3,
            max_popup_width_px=POPUP_MAX_WIDTH_PX + 300,
            fonts_dir=FONTS_DIR,
            merge_short_orphans=True,
        )
        assert len(_dialogue_lines(generous_merge)) == 1
        assert "ئەمە بابەتێکی زۆر لێی" in _dialogue_lines(generous_merge)[0]

    # 4. Acoustic-energy karaoke micro-pop (`excited_intervals_ms`):
    if ffmpeg is not None:
        s_karaoke = Sentence(
            words=(
                _w("ئەمە", 0, 400),  # mid = 200 ms (calm)
                _w("زۆر", 1000, 1500),  # mid = 1250 ms (excited!)
                _w("گرنگە.", 2500, 3000),  # mid = 2750 ms (calm)
            ),
            complete=True,
        )
        calm_ass = build_ass(
            (s_karaoke,),
            font_name=DEFAULT_CAPTION_FONT,
            font_size=VIRAL_FONT_SIZE,
            style=CaptionStyle.WORD_HIGHLIGHT,
            theme=VIRAL_THEME,
            fonts_dir=FONTS_DIR,
            excited_intervals_ms=(),
        )
        assert _EXCITED_POP_SNIPPET not in calm_ass

        excited_ass = build_ass(
            (s_karaoke,),
            font_name=DEFAULT_CAPTION_FONT,
            font_size=VIRAL_FONT_SIZE,
            style=CaptionStyle.WORD_HIGHLIGHT,
            theme=VIRAL_THEME,
            fonts_dir=FONTS_DIR,
            excited_intervals_ms=((900, 1700),),
        )
        hl_lines = [line for line in _dialogue_lines(excited_ass) if ",KurdishHighlight," in line]
        base_lines = [line for line in _dialogue_lines(excited_ass) if ",Kurdish," in line]
        assert len(hl_lines) == 3
        assert all(_EXCITED_POP_SNIPPET not in line for line in base_lines)
        # Only word index 1 (`زۆر`, mid=1250 ms inside [900, 1700]) carries the micro-pop tag.
        assert _EXCITED_POP_SNIPPET not in hl_lines[0]
        assert _EXCITED_POP_SNIPPET in hl_lines[1]
        assert _EXCITED_POP_SNIPPET not in hl_lines[2]
        verify_caption_integrity(
            excited_ass,
            expected_text="ئەمە زۆر گرنگە.",
            fonts_dir=FONTS_DIR,
        )


def test_normalize_sorani_digits_preserves_timestamps_and_rtl_order() -> None:
    """AC-7 / T7 (D-362): deterministic Sorani digit normalization with exact timestamps."""
    # 1. Full 0-10 coverage for both Western and Arabic-Indic numerals + punctuation preservation.
    western_sentence = Sentence(
        words=(
            _w("0", 0, 100, conf=0.91),
            _w("1،", 120, 220, conf=0.92),
            _w("2", 240, 340, conf=0.93),
            _w("«3»", 360, 460, conf=0.94),
            _w("4.", 480, 580, conf=0.95),
            _w("(5)", 600, 700, conf=0.96),
            _w("6؟", 720, 820, conf=0.97),
            _w("7!", 840, 940, conf=0.98),
            _w("8:", 960, 1060, conf=0.99),
            _w("9؛", 1080, 1180, conf=0.90),
            _w("10.", 1200, 1320, conf=0.95),
        ),
        complete=True,
    )
    arabic_indic_sentence = Sentence(
        words=(
            _w("٠", 2000, 2100, conf=0.81),
            _w("١", 2120, 2220, conf=0.82),
            _w("٢", 2240, 2340, conf=0.83),
            _w("٣", 2360, 2460, conf=0.84),
            _w("٤", 2480, 2580, conf=0.85),
            _w("٥", 2600, 2700, conf=0.86),
            _w("٦", 2720, 2820, conf=0.87),
            _w("٧", 2840, 2940, conf=0.88),
            _w("٨", 2960, 3060, conf=0.89),
            _w("٩", 3080, 3180, conf=0.90),
            _w("١٠،", 3200, 3320, conf=0.91),
        ),
        complete=False,
    )
    # 2. Real forensic case (`3 گۆشە 4`) + non-isolated / >10 tokens that must remain untouched.
    mixed_sentence = Sentence(
        words=(
            _w("3", 4000, 4250, conf=0.92),
            _w("گۆشە", 4280, 4600, conf=0.97),
            _w("4", 4640, 4900, conf=0.94),
            _w("ساڵی", 4950, 5200, conf=0.96),
            _w("2026", 5240, 5600, conf=0.95),
            _w("11", 5650, 5900, conf=0.93),
            _w("3.5", 5950, 6200, conf=0.91),
            _w("3%", 6250, 6500, conf=0.90),
            _w("GPT-4.", 6550, 6900, conf=0.98),
        ),
        complete=True,
    )

    originals = (western_sentence, arabic_indic_sentence, mixed_sentence)
    snapshot = [[(w.w, w.start_ms, w.end_ms, w.conf) for w in s.words] for s in originals]

    normalized = normalize_sorani_digits(originals)

    assert len(normalized) == 3
    assert [w.w for w in normalized[0].words] == [
        "سفر",
        "یەک،",
        "دوو",
        "«سێ»",
        "چوار.",
        "(پێنج)",
        "شەش؟",
        "حەوت!",
        "هەشت:",
        "نۆ؛",
        "دە.",
    ]
    assert [w.w for w in normalized[1].words] == [
        "سفر",
        "یەک",
        "دوو",
        "سێ",
        "چوار",
        "پێنج",
        "شەش",
        "حەوت",
        "هەشت",
        "نۆ",
        "دە،",
    ]
    assert [w.w for w in normalized[2].words] == [
        "سێ",
        "گۆشە",
        "چوار",
        "ساڵی",
        "2026",
        "11",
        "3.5",
        "3%",
        "GPT-4.",
    ]

    # Exact 1-to-1 word count, timestamps, confidence, and Sentence.complete preserved.
    for orig_s, norm_s in zip(originals, normalized, strict=True):
        assert norm_s.complete is orig_s.complete
        assert len(norm_s.words) == len(orig_s.words)
        for orig_w, norm_w in zip(orig_s.words, norm_s.words, strict=True):
            assert norm_w.start_ms == orig_w.start_ms
            assert norm_w.end_ms == orig_w.end_ms
            assert norm_w.conf == orig_w.conf
    assert_deliverable_order(normalized)

    # Zero mutation of original sentences (`raw.json` invariant #1).
    assert [[(w.w, w.start_ms, w.end_ms, w.conf) for w in s.words] for s in originals] == snapshot

    # 3. Integration inside polish_clip_sentences() right after deduplicate_micro_stutters():
    # rapid CTC stutter on `3` `3` collapses first -> then normalizes to a single `سێ`!
    stutter_digit_sentence = Sentence(
        words=(
            _w("3", 100, 170, conf=0.75),
            _w("3", 180, 250, conf=0.88),
            _w("گۆشە", 300, 650, conf=0.96),
            _w("٤.", 700, 1050, conf=0.95),
        ),
        complete=True,
    )
    polished = polish_clip_sentences((stutter_digit_sentence,), client=None)
    assert polished.applied is True
    assert polished.stutters_removed == 1
    assert [w.w for w in polished.sentences[0].words] == ["سێ", "گۆشە", "چوار."]
    assert polished.sentences[0].words[0].start_ms == 100
    assert polished.sentences[0].words[0].end_ms == 250
    assert polished.sentences[0].words[0].conf == 0.88
    assert polished.sentences[0].words[2].start_ms == 700
    assert polished.sentences[0].words[2].end_ms == 1050

    # Resulting ASS preserves RTL reading order and passes full caption integrity checks.
    ass_text = build_ass(
        polished.sentences,
        font_name=DEFAULT_CAPTION_FONT,
        font_size=VIRAL_FONT_SIZE,
        style=CaptionStyle.LINE,
        theme=VIRAL_THEME,
        fonts_dir=FONTS_DIR,
    )
    verify_caption_integrity(ass_text, expected_text="سێ گۆشە چوار.", fonts_dir=FONTS_DIR)
