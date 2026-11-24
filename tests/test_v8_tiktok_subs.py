"""Tests for HawEdit V8 Module 3 — Viral TikTok Animated Kurdish Subtitles (D-383)."""

from __future__ import annotations

import importlib
import json
import subprocess
from itertools import pairwise
from pathlib import Path

import numpy as np
import pytest

from hawedit.captions import (
    RTL_MARK,
    assert_ass_fonts_cover_kurdish,
    assert_captions_within_clip,
    ffprobe_for,
    find_ffmpeg,
    parse_dialogue_times,
    subtitle_filter,
)
from hawedit.transcripts import Word
from hawedit.v8.tiktok_subs import (
    KURDISH_PROCLITICS,
    POWER_PILL_HEX,
    STUDIO_GOLD_PILL_HEX,
    VISUAL_INTERRUPT_CHEST_Y_PX,
    VISUAL_INTERRUPT_MIN_START_MS,
    VISUAL_INTERRUPT_TOP_Y_PX,
    TikTokSubtitleError,
    ViralCaptionChunk,
    ViralCaptionWord,
    _split_directional_runs,
    build_viral_tiktok_ass,
    chunk_viral_kurdish_words,
    pill_glide_progress,
    render_tiktok_frame_rgba,
    render_tiktok_overlay_video,
    render_tiktok_preview_png,
    spring_bounce_scale,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FONTS_DIR = REPO_ROOT / "assets" / "fonts"
VAZIRMATN_FONT = FONTS_DIR / "Vazirmatn.ttf"


def _words(tokens: list[str], *, dur_ms: int = 240, gap_ms: int = 30) -> list[Word]:
    out: list[Word] = []
    cursor = 0
    for token in tokens:
        out.append(Word(w=token, start_ms=cursor, end_ms=cursor + dur_ms, conf=0.98))
        cursor += dur_ms + gap_ms
    return out


# ---------------------------------------------------------------------------
# 1. Strict Viral TikTok Word Chunker
# ---------------------------------------------------------------------------


class TestChunkViralKurdishWords:
    def test_empty_returns_empty_tuple(self) -> None:
        assert chunk_viral_kurdish_words([]) == ()

    def test_long_words_and_power_words_always_solo(self) -> None:
        words = _words(
            [
                "پێش",
                "ئەوەی",
                "کوردییەکەیان",  # 12 chars -> solo
                "ڕێستۆرانتەکە",  # 12 chars -> solo
                "بەجێی",
                "ناهێڵم",
            ]
        )
        chunks = chunk_viral_kurdish_words(words, power_word_indices={2})
        assert [c.text for c in chunks] == [
            "پێش ئەوەی",
            "کوردییەکەیان",
            "ڕێستۆرانتەکە",
            "بەجێی ناهێڵم",
        ]
        assert [len(c.words) for c in chunks] == [2, 1, 1, 2]
        assert chunks[1].has_power_word is True
        assert chunks[1].words[0].is_power_word is True
        assert chunks[2].has_power_word is False

    def test_short_power_word_forces_solo_chunk(self) -> None:
        words = _words(["ئەمە", "زۆر", "گرنگە", "بۆ", "تۆ"])
        chunks = chunk_viral_kurdish_words(words, power_word_indices={2})
        assert [c.text for c in chunks] == ["ئەمە زۆر", "گرنگە", "بۆ تۆ"]
        assert chunks[1].has_power_word is True
        assert len(chunks[1].words) == 1

    def test_punctuation_stripped_for_long_word_threshold(self) -> None:
        # "ئەوەی..." has 5 letters stripped (< 8), so it pairs normally with "پێش".
        words = _words(["پێش", "ئەوەی..."])
        chunks = chunk_viral_kurdish_words(words)
        assert [c.text for c in chunks] == ["پێش ئەوەی..."]
        assert len(chunks[0].words) == 2

    def test_default_two_word_rhythm_never_four_words(self) -> None:
        # 20 ultra-short 2-char words must NEVER produce any 4-word chunk.
        words = _words(["من", "تۆ", "با", "وا"] * 5)
        chunks = chunk_viral_kurdish_words(words)
        assert all(1 <= len(c.words) <= 3 for c in chunks)
        for chunk in chunks:
            if len(chunk.words) == 3:
                assert len(chunk.text) <= 14

    def test_three_words_allowed_only_within_14_chars_and_pause_limit(self) -> None:
        # "لە ناو ماڵ" = 10 chars <= 14 -> clean 3-word chunk
        short_3 = _words(["لە", "ناو", "ماڵ"])
        chunks = chunk_viral_kurdish_words(short_3)
        assert [c.text for c in chunks] == ["لە ناو ماڵ"]
        assert len(chunks[0].words) == 3
        assert len(chunks[0].text) <= 14

        # Same 3 words with a >260 ms pause before the 3rd word -> must split!
        paused = [
            Word("لە", 0, 200, 0.99),
            Word("ناو", 220, 420, 0.99),
            Word("ماڵ", 750, 980, 0.99),  # 330 ms pause > 260 ms
        ]
        paused_chunks = chunk_viral_kurdish_words(paused)
        assert [c.text for c in paused_chunks] == ["لە ناو", "ماڵ"]

    def test_three_words_forbidden_when_over_14_chars(self) -> None:
        # "سڵاو لە هەمووان" = 15 chars > 14; middle word "لە" is a Kurdish proclitic,
        # so it must NOT dangle at the end of a 2-word chunk ("سڵاو لە") — it attaches forward!
        words = _words(["سڵاو", "لە", "هەمووان"])
        chunks = chunk_viral_kurdish_words(words)
        assert [c.text for c in chunks] == ["سڵاو", "لە هەمووان"]
        assert all(len(c.words) <= 2 for c in chunks)

    def test_kurdish_proclitic_never_dangles_when_attachable(self) -> None:
        # Middle proclitic "و" inside <=14 chars forms crisp 3-word unit "من و تۆ".
        assert [c.text for c in chunk_viral_kurdish_words(_words(["من", "و", "تۆ"]))] == ["من و تۆ"]
        # Every listed proclitic triggers non-dangling behavior when total > 14 chars.
        for proc in sorted(KURDISH_PROCLITICS):
            words = _words(["دەنگدان", proc, "هەمووان"])
            chunks = chunk_viral_kurdish_words(words)
            assert chunks[0].words[-1].text != proc
            assert chunks[1].words[0].text == proc

    def test_sentence_terminal_punctuation_splits_chunks(self) -> None:
        words = _words(["باشە.", "ئێستا", "بڕۆین"])
        chunks = chunk_viral_kurdish_words(words)
        assert [c.text for c in chunks] == ["باشە.", "ئێستا بڕۆین"]

    def test_invalid_inputs_fail_stop(self) -> None:
        with pytest.raises(ValueError, match="max_short_3_chars"):
            chunk_viral_kurdish_words([], max_short_3_chars=2)
        with pytest.raises(ValueError, match="long_word_chars"):
            chunk_viral_kurdish_words([], long_word_chars=0)
        with pytest.raises(ValueError, match="pause_split_ms"):
            chunk_viral_kurdish_words([], pause_split_ms=-1)
        with pytest.raises(ValueError, match="1..3 words"):
            ViralCaptionChunk(
                words=tuple(ViralCaptionWord(i, "با", i * 100, i * 100 + 80) for i in range(4)),
                start_ms=0,
                end_ms=380,
            )


# ---------------------------------------------------------------------------
# 2. Physics Curves
# ---------------------------------------------------------------------------


class TestPhysicsCurves:
    def test_spring_bounce_curve(self) -> None:
        assert spring_bounce_scale(0.0) == pytest.approx(0.82)
        assert spring_bounce_scale(70.0) == pytest.approx(1.07)
        assert spring_bounce_scale(140.0) == pytest.approx(1.00)
        assert spring_bounce_scale(500.0) == pytest.approx(1.00)
        assert 0.82 < spring_bounce_scale(25.0) < 1.07
        assert 1.00 < spring_bounce_scale(105.0) < 1.07

    def test_pill_glide_curve(self) -> None:
        assert pill_glide_progress(0.0) == pytest.approx(0.0)
        assert pill_glide_progress(30.0) > 0.5  # ease-out accelerates early
        assert pill_glide_progress(60.0) == pytest.approx(1.0)
        assert pill_glide_progress(120.0) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 3. Skia + HarfBuzz Viral RGBA Renderer & Streaming Overlay
# ---------------------------------------------------------------------------


def _color_centroid_x(
    rgba_bytes: bytes,
    *,
    width: int,
    height: int,
    target_hex: str,
    y_min: int,
    y_max: int,
    tol: int = 24,
) -> tuple[int, float]:
    arr = np.frombuffer(rgba_bytes, dtype=np.uint8).reshape((height, width, 4))
    band = arr[y_min:y_max]
    r, g, b = int(target_hex[1:3], 16), int(target_hex[3:5], 16), int(target_hex[5:7], 16)
    mask = (
        (band[:, :, 3] >= 220)
        & (np.abs(band[:, :, 0].astype(np.int16) - r) <= tol)
        & (np.abs(band[:, :, 1].astype(np.int16) - g) <= tol)
        & (np.abs(band[:, :, 2].astype(np.int16) - b) <= tol)
    )
    xs = np.nonzero(mask)[1]
    if xs.size == 0:
        return 0, 0.0
    return int(xs.size), float(xs.mean())


class TestSkiaHarfBuzzRenderer:
    def test_rtl_active_pill_glides_right_to_left_and_power_word_uses_lime(self) -> None:
        words = [
            Word("پێش", 0, 400, 0.99),
            Word("ئەوەی", 400, 900, 0.99),
            Word("کوردییەکەیان", 950, 1600, 0.99),
        ]
        chunks = chunk_viral_kurdish_words(words, power_word_indices={2})

        # Word 0 active (t=200ms) -> gold pill on RIGHT side of center
        f_w0 = render_tiktok_frame_rgba(
            chunks,
            t_ms=200,
            font_path=VAZIRMATN_FONT,
            hook_title_ckb="چیرۆکی ڕێستۆرانتە کوردییەکە",
        )
        assert len(f_w0) == 1080 * 1920 * 4
        # Empty corner pixel must remain 100% transparent
        assert f_w0[0:4] == b"\x00\x00\x00\x00"
        cnt0, x0 = _color_centroid_x(
            f_w0, width=1080, height=1920, target_hex=STUDIO_GOLD_PILL_HEX, y_min=1200, y_max=1560
        )

        # Mid-glide (t=425ms = 25ms into 60ms glide) -> pill strictly between x0 and x1
        f_mid = render_tiktok_frame_rgba(chunks, t_ms=425, font_path=VAZIRMATN_FONT)
        cnt_mid, x_mid = _color_centroid_x(
            f_mid, width=1080, height=1920, target_hex=STUDIO_GOLD_PILL_HEX, y_min=1200, y_max=1560
        )

        # Word 1 active (t=550ms) -> gold pill settled on LEFT side of center
        f_w1 = render_tiktok_frame_rgba(chunks, t_ms=550, font_path=VAZIRMATN_FONT)
        cnt1, x1 = _color_centroid_x(
            f_w1, width=1080, height=1920, target_hex=STUDIO_GOLD_PILL_HEX, y_min=1200, y_max=1560
        )

        assert cnt0 > 5000
        assert cnt_mid > 5000
        assert cnt1 > 5000
        # True RTL order: word 0 is rightmost, glides leftward toward word 1
        assert x0 > x_mid > x1
        assert x0 > 540.0
        assert x1 < 540.0

        # Hook title pixels present in top band at t=200ms, absent at t=2600ms
        arr_hook = np.frombuffer(f_w0, dtype=np.uint8).reshape((1920, 1080, 4))
        assert int((arr_hook[220:460, :, 3] > 100).sum()) > 15_000

        f_after_hook = render_tiktok_frame_rgba(
            chunks,
            t_ms=2600,
            font_path=VAZIRMATN_FONT,
            hook_title_ckb="چیرۆکی ڕێستۆرانتە کوردییەکە",
        )
        arr_after = np.frombuffer(f_after_hook, dtype=np.uint8).reshape((1920, 1080, 4))
        assert int((arr_after[220:460, :, 3] > 0).sum()) == 0

        # Power word beat (t=1200ms) renders vibrant Electric Lime (#B8FF2E) pill
        f_power = render_tiktok_frame_rgba(chunks, t_ms=1200, font_path=VAZIRMATN_FONT)
        cnt_lime, x_lime = _color_centroid_x(
            f_power, width=1080, height=1920, target_hex=POWER_PILL_HEX, y_min=1200, y_max=1560
        )
        assert cnt_lime > 10_000
        assert 480.0 < x_lime < 600.0

    def test_mixed_kurdish_english_loanwords_shape_cleanly(self, tmp_path: Path) -> None:
        words = [
            Word("لە", 0, 220, 0.99),
            Word("ChatGPT", 240, 620, 0.99),
            Word("100%", 660, 950, 0.99),
            Word("کوردی", 970, 1300, 0.99),
        ]
        chunks = chunk_viral_kurdish_words(words)
        out_png = render_tiktok_preview_png(
            chunks,
            t_ms=350,
            output_png=tmp_path / "mixed_rtl_ltr.png",
            font_path=VAZIRMATN_FONT,
        )
        assert out_png.is_file()
        assert out_png.stat().st_size > 10_000

    def test_render_overlay_video_mov_and_mkv_with_alpha(self, tmp_path: Path) -> None:
        ffmpeg = find_ffmpeg()
        assert ffmpeg is not None, "pinned FFmpeg is required for V8 overlay test"
        ffprobe = ffprobe_for(ffmpeg)

        words = [
            Word("بەجێی", 0, 350, 0.99),
            Word("ناهێڵم", 370, 750, 0.99),
            Word("ڕێستۆرانتەکە", 800, 1300, 0.99),
        ]
        chunks = chunk_viral_kurdish_words(words, power_word_indices={2})

        for ext, expected_pix_fmt in ((".mov", "argb"), (".mkv", "rgba")):
            out_path = tmp_path / f"overlay{ext}"
            produced = render_tiktok_overlay_video(
                chunks,
                duration_ms=1400,
                output_mov_or_mkv=out_path,
                font_path=VAZIRMATN_FONT,
                hook_title_ckb="پێش ئەوەی کوردییەکەیان بزانیت",
                fps=25.0,
                ffmpeg=ffmpeg,
            )
            assert produced == out_path
            assert out_path.stat().st_size > 20_000

            probe_raw = subprocess.check_output(
                [
                    str(ffprobe),
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=width,height,pix_fmt,nb_frames",
                    "-of",
                    "json",
                    str(out_path),
                ],
                text=True,
            )
            stream = json.loads(probe_raw)["streams"][0]
            assert stream["width"] == 1080
            assert stream["height"] == 1920
            assert stream["pix_fmt"] == expected_pix_fmt

    def test_strict_fail_stop_on_bad_inputs_and_missing_deps(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        chunks = chunk_viral_kurdish_words([Word("پێش", 0, 300, 0.99)])
        with pytest.raises(ValueError, match=r"\.mov or \.mkv"):
            render_tiktok_overlay_video(
                chunks,
                duration_ms=500,
                output_mov_or_mkv=tmp_path / "bad.mp4",
                font_path=VAZIRMATN_FONT,
            )
        with pytest.raises(TikTokSubtitleError, match="does not exist"):
            render_tiktok_frame_rgba(
                chunks,
                t_ms=100,
                font_path=tmp_path / "missing.ttf",
            )

        real_import_module = importlib.import_module

        def block_skia(name: str, package: str | None = None) -> object:
            if name == "skia":
                raise ImportError("simulated missing skia")
            return real_import_module(name, package)

        monkeypatch.setattr(importlib, "import_module", block_skia)
        with pytest.raises(TikTokSubtitleError, match="skia-python is required"):
            render_tiktok_frame_rgba(chunks, t_ms=100, font_path=VAZIRMATN_FONT)


# ---------------------------------------------------------------------------
# 4. Zero-Dep libass Viral Fallback (0.00 px ghosting)
# ---------------------------------------------------------------------------


class TestBuildViralTikTokAss:
    def test_ass_structure_spring_bounce_zero_ghosting_and_font_coverage(
        self, tmp_path: Path
    ) -> None:
        words = [
            Word("پێش", 1000, 1400, 0.99),
            Word("ئەوەی", 1420, 1850, 0.99),
            Word("کوردییەکەیان", 1900, 2600, 0.99),
            Word("بەجێی", 2650, 3050, 0.99),
            Word("ناهێڵم", 3080, 3550, 0.99),
        ]
        chunks = chunk_viral_kurdish_words(words, power_word_indices={2})
        ass_text = build_viral_tiktok_ass(
            chunks,
            clip_in_ms=1000,
            clip_duration_ms=2800,
            hook_title_ckb="چیرۆکی ڕێستۆرانتە کوردییەکە",
        )

        assert "WrapStyle: 2" in ass_text
        assert "PlayResX: 1080" in ass_text
        assert "PlayResY: 1920" in ass_text
        assert RTL_MARK in ass_text
        # Never uses \clip (eliminating \clip + \fscx glyph ghosting)
        assert r"\clip" not in ass_text
        # Solo 1-word beat carries the exact spring-bounce animation + electric lime power tint
        assert r"\fscx84\fscy84\t(0,65,\fscx108\fscy108)\t(65,130,\fscx100\fscy100)" in ass_text
        assert r"\c&H002EFFB8&" in ass_text
        assert r"\c&H0000D7FF&" in ass_text

        # All Default-layer dialogue slices must be strictly non-overlapping (0.00 px ghosting)
        default_lines = [line for line in ass_text.splitlines() if line.startswith("Dialogue: 0,")]
        assert len(default_lines) == 5  # 2 slices + 1 solo + 2 slices
        default_only_ass = "\n".join(
            line for line in ass_text.splitlines() if not line.startswith("Dialogue: 1,")
        )
        times = parse_dialogue_times(default_only_ass)
        for (_, prev_end), (next_start, _) in pairwise(times):
            assert next_start >= prev_end

        assert_captions_within_clip(ass_text, 2800)
        assert_ass_fonts_cover_kurdish(ass_text, FONTS_DIR)

        # Render one real frame via FFmpeg libass with shaping=complex to prove runtime validity
        ffmpeg = find_ffmpeg()
        assert ffmpeg is not None
        ass_path = tmp_path / "viral.ass"
        ass_path.write_text(ass_text, encoding="utf-8")
        out_png = tmp_path / "viral_ass_frame.png"
        vf = subtitle_filter(ass_path, FONTS_DIR)
        subprocess.run(
            [
                str(ffmpeg),
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=1080x1920:r=25:d=2.8",
                "-vf",
                vf,
                "-ss",
                "1.1",
                "-frames:v",
                "1",
                str(out_png),
            ],
            check=True,
        )
        assert out_png.is_file()
        assert out_png.stat().st_size > 15_000

    def test_ass_validation_rejects_bad_bounds(self) -> None:
        with pytest.raises(ValueError, match="clip_in_ms"):
            build_viral_tiktok_ass([], clip_in_ms=-10)
        with pytest.raises(ValueError, match="clip_duration_ms"):
            build_viral_tiktok_ass([], clip_duration_ms=0)
        with pytest.raises(ValueError, match="font_size"):
            build_viral_tiktok_ass([], font_size=0)


class TestVisualInterruptsAndBidiD387:
    def test_mixed_latin_arabic_bidi_runs_preserve_ltr_ai_and_rtl_suffix(
        self, tmp_path: Path
    ) -> None:
        # AI stays strictly LTR while Kurdish suffix joins in RTL on the left.
        assert _split_directional_runs("AIـەکە", base_rtl=True) == [
            ("AI", False),
            ("ـەکە", True),
        ]
        # Hyphen and space between Latin and Kurdish resolve to base RTL so they stay between runs.
        assert _split_directional_runs("AI-یەکە", base_rtl=True) == [
            ("AI", False),
            ("-یەکە", True),
        ]
        assert _split_directional_runs("AI و مرۆڤ", base_rtl=True) == [
            ("AI", False),
            (" و مرۆڤ", True),
        ]
        assert _split_directional_runs("GPT-5ی", base_rtl=True) == [
            ("GPT-5", False),
            ("ی", True),
        ]
        assert _split_directional_runs("100%", base_rtl=True) == [("100%", False)]

        # Real 1080x1920 PNG proof rendering AIـەکە + top visual interrupt without errors or tofu.
        words = [Word("لە", 3000, 3400, 0.99), Word("AIـەکە", 3400, 4200, 0.99)]
        chunks = chunk_viral_kurdish_words(words)
        out_png = render_tiktok_preview_png(
            chunks,
            t_ms=3600,
            output_png=tmp_path / "bidi_ai_proof_1080x1920.png",
            font_path=VAZIRMATN_FONT,
            visual_interrupts=[(3000, 4800, "AI و مرۆڤ لەسەر کۆمپیوتەر", "top")],
        )
        assert out_png.is_file()
        assert out_png.stat().st_size > 20_000

    def test_visual_interrupts_render_top_and_chest_without_hook_or_pill_collision(
        self, tmp_path: Path
    ) -> None:
        chunks = chunk_viral_kurdish_words(
            [
                Word("لەسەر", 3000, 3600, 0.99),
                Word("کۆمپیوتەر", 3600, 4400, 0.99),
                Word("بەجێی", 5000, 5600, 0.99),
                Word("ناهێڵم", 5600, 6400, 0.99),
            ]
        )
        interrupts = [
            # Starts at 1800 ms, MUST clamp to >= 2600 ms so it never collides with 0..2400 ms hook!
            (1800, 4600, "لەسەر کۆمپیوتەرەکەی خۆت", "top"),
            (5000, 6600, "شتێک کە مرۆڤ نەیدۆزیوەتەوە", "chest"),
        ]

        # At t=2000 ms (during hook window, before 2600 ms): NO lime interrupt border yet.
        f_early = render_tiktok_frame_rgba(
            chunks,
            t_ms=2000,
            font_path=VAZIRMATN_FONT,
            hook_title_ckb="چیرۆکی کوردییەکە",
            visual_interrupts=interrupts,
        )
        lime_early, _ = _color_centroid_x(
            f_early, width=1080, height=1920, target_hex=POWER_PILL_HEX, y_min=80, y_max=340
        )
        assert lime_early == 0

        # At t=3500 ms: top interrupt rendered cleanly centered near y=210 px with lime border.
        f_top = render_tiktok_frame_rgba(
            chunks,
            t_ms=3500,
            font_path=VAZIRMATN_FONT,
            visual_interrupts=interrupts,
        )
        arr_top = np.frombuffer(f_top, dtype=np.uint8).reshape((1920, 1080, 4))
        top_band_alpha = arr_top[
            VISUAL_INTERRUPT_TOP_Y_PX - 110 : VISUAL_INTERRUPT_TOP_Y_PX + 110, :, 3
        ]
        assert int((top_band_alpha > 180).sum()) > 15_000
        lime_top, _ = _color_centroid_x(
            f_top, width=1080, height=1920, target_hex=POWER_PILL_HEX, y_min=80, y_max=340
        )
        assert lime_top > 800

        # At t=5800 ms: chest interrupt near y=1130 px and bottom pill near y=1380 px (clean gap).
        f_chest = render_tiktok_frame_rgba(
            chunks,
            t_ms=5800,
            font_path=VAZIRMATN_FONT,
            visual_interrupts=interrupts,
        )
        arr_chest = np.frombuffer(f_chest, dtype=np.uint8).reshape((1920, 1080, 4))
        chest_alpha = arr_chest[
            VISUAL_INTERRUPT_CHEST_Y_PX - 110 : VISUAL_INTERRUPT_CHEST_Y_PX + 110, :, 3
        ]
        assert int((chest_alpha > 180).sum()) > 15_000
        # Gap between chest badge bottom (~1190) and bottom TikTok pill top (~1295) stays clean.
        gap_band = arr_chest[1220:1270, :, 3]
        assert int((gap_band > 150).sum()) == 0

        # After interrupt end (t=6800 ms): chest band completely transparent again.
        f_after = render_tiktok_frame_rgba(
            chunks,
            t_ms=6800,
            font_path=VAZIRMATN_FONT,
            visual_interrupts=interrupts,
        )
        arr_after = np.frombuffer(f_after, dtype=np.uint8).reshape((1920, 1080, 4))
        assert int((arr_after[1000:1240, :, 3] > 0).sum()) == 0

        # End-to-end streaming .mov encode verifies dirty-band visual interrupt rendering.
        ffmpeg = find_ffmpeg()
        assert ffmpeg is not None
        mov_path = render_tiktok_overlay_video(
            chunks,
            duration_ms=4200,
            output_mov_or_mkv=tmp_path / "interrupt_overlay.mov",
            font_path=VAZIRMATN_FONT,
            visual_interrupts=[(2700, 4000, "لەسەر کۆمپیوتەرەکەی خۆت", "top")],
            fps=25.0,
            ffmpeg=ffmpeg,
        )
        assert mov_path.stat().st_size > 20_000

        # Extract frame at 3.20s from encoded .mov and verify top interrupt pixels are present.
        raw_rgba = subprocess.check_output(
            [
                str(ffmpeg),
                "-v",
                "error",
                "-ss",
                "3.20",
                "-i",
                str(mov_path),
                "-frames:v",
                "1",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgba",
                "pipe:1",
            ]
        )
        arr_mov = np.frombuffer(raw_rgba, dtype=np.uint8).reshape((1920, 1080, 4))
        assert int((arr_mov[110:310, :, 3] > 180).sum()) > 15_000

    def test_ass_renders_visual_interrupts_and_rejects_invalid_specs(self) -> None:
        chunks = chunk_viral_kurdish_words([Word("کوردی", 3000, 3800, 0.99)])
        ass_text = build_viral_tiktok_ass(
            chunks,
            clip_in_ms=0,
            clip_duration_ms=6000,
            hook_title_ckb="سەرەتا",
            visual_interrupts=[
                (2000, 4200, "لەسەر کۆمپیوتەرەکەی خۆت", "top"),
                (4400, 5800, "شتێک کە مرۆڤ نەیدۆزیوەتەوە", "chest"),
            ],
        )
        assert "Style: InterruptTop," in ass_text
        assert "Style: InterruptChest," in ass_text
        # Every V8 ASS style must use Encoding=-1 (D-334) so libass keeps Kurdish RTL word order.
        style_lines = [line for line in ass_text.splitlines() if line.startswith("Style:")]
        assert style_lines and all(line.endswith(",-1") for line in style_lines)
        # Top interrupt clamped to >= 2600 ms (0:00:02.60) so it never overlaps hook card.
        assert (
            f"Dialogue: 2,0:00:0{VISUAL_INTERRUPT_MIN_START_MS // 1000}.60,0:00:04.20,InterruptTop"
            in ass_text
        )
        assert "Dialogue: 2,0:00:04.40,0:00:05.80,InterruptChest" in ass_text
        assert_captions_within_clip(ass_text, 6000)
        assert_ass_fonts_cover_kurdish(ass_text, FONTS_DIR)

        with pytest.raises(ValueError, match="position"):
            build_viral_tiktok_ass(chunks, visual_interrupts=[(3000, 4000, "کوردی", "bottom")])
        with pytest.raises(ValueError, match="time range"):
            build_viral_tiktok_ass(chunks, visual_interrupts=[(4000, 3000, "کوردی", "top")])
        with pytest.raises(ValueError, match="empty"):
            build_viral_tiktok_ass(chunks, visual_interrupts=[(3000, 4000, "   ", "top")])


def test_chunk_viral_kurdish_words_splits_multi_token_repaired_words() -> None:
    """Multi-word ASR repairs (e.g. 'جوابت ئەیاتەوە') never violate the <=3-word / <=14-char law."""
    words = (
        Word("لە", 0, 150, 0.99),
        Word("ناو", 180, 340, 0.99),
        Word("جوابت ئەیاتەوە", 380, 980, 0.98),
        Word("ئێستا", 1020, 1300, 0.99),
    )
    chunks = chunk_viral_kurdish_words(words)
    for chunk in chunks:
        rendered = " ".join(w.text for w in chunk.words)
        toks = rendered.split()
        assert 1 <= len(toks) <= 3, f"Chunk exceeded 3 tokens: {rendered!r}"
        if len(toks) == 3:
            assert len(rendered) <= 14, f"3-word chunk exceeded 14 chars: {rendered!r}"
