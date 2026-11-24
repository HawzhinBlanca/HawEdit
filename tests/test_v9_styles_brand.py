"""Tests for HawEdit V9 Module A — Multi-Client Brand Kits & 5 Curated Style Presets (D-388)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest

from hawedit.captions import (
    assert_ass_fonts_cover_kurdish,
    assert_captions_within_clip,
    find_ffmpeg,
)
from hawedit.transcripts import Word
from hawedit.v8.styles import (
    CLIENT_STYLE_PRESETS,
    DEFAULT_STYLE_PRESET_NAME,
    ClientStylePreset,
    get_client_style_preset,
    list_client_style_presets,
    pick_contrasting_ink,
    resolve_client_style_preset,
    validate_hex_color,
    wcag_contrast_ratio,
)
from hawedit.v8.tiktok_subs import (
    END_CARD_DURATION_MS,
    SPEAKER_BIO_END_MS,
    SPEAKER_BIO_START_MS,
    build_viral_tiktok_ass,
    chunk_viral_kurdish_words,
    render_tiktok_frame_rgba,
    render_tiktok_overlay_video,
    render_tiktok_preview_png,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FONTS_DIR = REPO_ROOT / "assets" / "fonts"
VAZIRMATN_FONT = FONTS_DIR / "Vazirmatn.ttf"


def _color_pixel_count(
    rgba_bytes: bytes,
    *,
    width: int,
    height: int,
    target_hex: str,
    y_min: int,
    y_max: int,
    tol: int = 24,
    min_alpha: int = 200,
) -> int:
    arr = np.frombuffer(rgba_bytes, dtype=np.uint8).reshape((height, width, 4))
    band = arr[y_min:y_max]
    r, g, b = int(target_hex[1:3], 16), int(target_hex[3:5], 16), int(target_hex[5:7], 16)
    mask = (
        (band[:, :, 3] >= min_alpha)
        & (np.abs(band[:, :, 0].astype(np.int16) - r) <= tol)
        & (np.abs(band[:, :, 1].astype(np.int16) - g) <= tol)
        & (np.abs(band[:, :, 2].astype(np.int16) - b) <= tol)
    )
    return int(mask.sum())


# ---------------------------------------------------------------------------
# 1. Style Preset Registry, WCAG Contrast & Strict Hex Validation
# ---------------------------------------------------------------------------


class TestClientStylePresets:
    def test_five_curated_presets_exist_with_exact_spec_values(self) -> None:
        expected_names = (
            "viral_gold",
            "crimson_punch",
            "executive_cyan",
            "luxury_minimal",
            "broadcast_news",
        )
        assert tuple(CLIENT_STYLE_PRESETS.keys()) == expected_names
        assert DEFAULT_STYLE_PRESET_NAME == "viral_gold"

        vg = CLIENT_STYLE_PRESETS["viral_gold"]
        assert vg.active_pill_hex == "#FFD700"
        assert vg.active_text_hex == "#0B0B0F"
        assert vg.power_pill_hex == "#B8FF2E"
        assert vg.power_text_hex == "#0B0B0F"
        assert vg.hook_border_hex == "#FFD700"
        assert vg.progress_bar_hex == "#FFD700"
        assert vg.allow_camera_moves is True
        assert vg.max_camera_scale == pytest.approx(1.14)

        cp = CLIENT_STYLE_PRESETS["crimson_punch"]
        assert cp.active_pill_hex == "#FF2E63"
        assert cp.active_text_hex == "#FFFFFF"
        assert cp.power_pill_hex == "#FFD700"
        assert cp.power_text_hex == "#0B0B0F"
        assert cp.hook_border_hex == "#FF2E63"
        assert cp.progress_bar_hex == "#FF2E63"
        assert cp.allow_camera_moves is True
        assert cp.max_camera_scale == pytest.approx(1.15)

        ec = CLIENT_STYLE_PRESETS["executive_cyan"]
        assert ec.active_pill_hex == "#00D4FF"
        assert ec.active_text_hex == "#07131C"
        assert ec.power_pill_hex == "#FFFFFF"
        assert ec.power_text_hex == "#07131C"
        assert ec.hook_fill_rgba == (11, 18, 32, 230)
        assert ec.interrupt_fill_rgba == (11, 18, 32, 230)
        assert ec.hook_border_hex == "#00D4FF"
        assert ec.progress_bar_hex == "#00D4FF"
        assert ec.allow_camera_moves is True
        assert ec.max_camera_scale == pytest.approx(1.08)

        lm = CLIENT_STYLE_PRESETS["luxury_minimal"]
        assert lm.active_pill_hex == "#161820"
        assert lm.active_pill_alpha == 235
        assert lm.active_text_hex == "#F5C451"
        assert lm.active_pill_border_hex == "#F5C451"
        assert lm.active_pill_border_width_px == pytest.approx(2.0)
        assert lm.power_pill_hex == "#F5C451"
        assert lm.power_text_hex == "#111216"
        assert lm.hook_border_hex == "#F5C451"
        assert lm.progress_bar_hex == "#F5C451"
        assert lm.allow_camera_moves is True
        assert lm.max_camera_scale == pytest.approx(1.08)

        bn = CLIENT_STYLE_PRESETS["broadcast_news"]
        assert bn.active_pill_hex == "#102446"
        assert bn.active_pill_alpha == 240
        assert bn.active_text_hex == "#FFFFFF"
        assert bn.active_pill_border_hex == "#FFD700"
        assert bn.power_pill_hex == "#FFD700"
        assert bn.power_text_hex == "#0B1220"
        assert bn.progress_bar_hex == "#1D4ED8"
        assert bn.allow_camera_moves is False
        assert bn.max_camera_scale == pytest.approx(1.00)

    def test_wcag_contrast_ratios_and_ink_picker(self) -> None:
        assert wcag_contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0)
        assert wcag_contrast_ratio("#FFFFFF", "#FFFFFF") == pytest.approx(1.0)
        assert pick_contrasting_ink("#FFD700") == "#0B0B0F"
        assert pick_contrasting_ink("#102446") == "#FFFFFF"

        # Power pills across all 5 presets exceed AAA (>= 7:1) contrast.
        for name, preset in CLIENT_STYLE_PRESETS.items():
            power_cr = wcag_contrast_ratio(preset.power_text_hex, preset.power_pill_hex)
            assert power_cr >= 7.0, f"{name} power pill contrast {power_cr:.2f} < 7.0"
            active_cr = wcag_contrast_ratio(preset.active_text_hex, preset.active_pill_hex)
            if name == "crimson_punch":
                # 90px bold white on #FF2E63 passes WCAG AA Large Text (>= 3.0:1) + dark drop shadow
                assert active_cr >= 3.5
            else:
                assert active_cr >= 7.0, f"{name} active pill contrast {active_cr:.2f} < 7.0"

    def test_list_client_style_presets_returns_json_ready_swatches(self) -> None:
        listed = list_client_style_presets()
        assert len(listed) == 5
        assert [item["name"] for item in listed] == list(CLIENT_STYLE_PRESETS.keys())
        for item in listed:
            assert item["display_name"]
            assert item["description"]
            assert len(item["swatches"]) == 3
            for hex_swatch in item["swatches"]:
                assert validate_hex_color(hex_swatch) == hex_swatch
            assert isinstance(item["allow_camera_moves"], bool)
            assert isinstance(item["max_camera_scale"], float)
            assert isinstance(item["active_contrast_ratio"], float)

    def test_accent_hex_override_and_strict_fail_stop_validation(self) -> None:
        # Bright-pill preset overrides pill hex & auto-picks highest-contrast ink.
        cyan_gold = get_client_style_preset("viral_gold", accent_hex_override="#00e5ff")
        assert cyan_gold.active_pill_hex == "#00E5FF"
        assert cyan_gold.active_text_hex == "#0B0B0F"
        assert cyan_gold.hook_border_hex == "#00E5FF"
        assert cyan_gold.progress_bar_hex == "#00E5FF"

        navy_gold = get_client_style_preset("viral_gold", accent_hex_override="#1e3a8a")
        assert navy_gold.active_pill_hex == "#1E3A8A"
        assert navy_gold.active_text_hex == "#FFFFFF"

        # Dark-pill preset preserves dark pill bg & updates border/progress/champagne ink.
        rose_lux = get_client_style_preset("luxury_minimal", accent_hex_override="#f472b6")
        assert rose_lux.active_pill_hex == "#161820"
        assert rose_lux.active_pill_border_hex == "#F472B6"
        assert rose_lux.active_text_hex == "#F472B6"
        assert rose_lux.progress_bar_hex == "#F472B6"

        dark_lux = get_client_style_preset("luxury_minimal", accent_hex_override="#1e2230")
        assert dark_lux.active_text_hex == "#FFFFFF"

        emerald_news = get_client_style_preset("broadcast_news", accent_hex_override="#22c55e")
        assert emerald_news.active_pill_hex == "#102446"
        assert emerald_news.active_text_hex == "#FFFFFF"
        assert emerald_news.active_pill_border_hex == "#22C55E"
        assert emerald_news.progress_bar_hex == "#22C55E"

        # Strict fail-stop on invalid hex or unknown preset names.
        for bad_hex in ("", "FFD700", "#FFF", "#12345G", "#1234567", "red", " #FFD700 "):
            with pytest.raises(ValueError, match="#RRGGBB"):
                get_client_style_preset("viral_gold", accent_hex_override=bad_hex)

        with pytest.raises(ValueError, match="unknown style preset"):
            get_client_style_preset("nonexistent_style")

        assert resolve_client_style_preset(None) == CLIENT_STYLE_PRESETS["viral_gold"]
        assert (
            resolve_client_style_preset("broadcast_news") == CLIENT_STYLE_PRESETS["broadcast_news"]
        )
        assert resolve_client_style_preset(rose_lux) is rose_lux
        with pytest.raises(TypeError, match="style_preset"):
            resolve_client_style_preset(123)  # type: ignore[arg-type]

    def test_preset_dataclass_post_init_rejects_invalid_fields(self) -> None:
        base = CLIENT_STYLE_PRESETS["broadcast_news"]
        with pytest.raises(ValueError, match="max_camera_scale must be 1.00"):
            ClientStylePreset(
                **{**{f: getattr(base, f) for f in base.__slots__}, "max_camera_scale": 1.10}
            )


# ---------------------------------------------------------------------------
# 2. Skia + HarfBuzz Rendering Across All 5 Presets, Speaker Bio & End Card
# ---------------------------------------------------------------------------


class TestV9StyledSkiaRendering:
    def test_default_none_is_byte_identical_to_viral_gold(self) -> None:
        chunks = chunk_viral_kurdish_words(
            [Word("لە", 0, 350, 0.99), Word("ڕێستۆرانتەکە", 360, 1200, 0.99)]
        )
        rgba_default = render_tiktok_frame_rgba(
            chunks,
            t_ms=700,
            font_path=VAZIRMATN_FONT,
            hook_title_ckb="چیرۆکی ڕێستۆرانتەکە",
        )
        rgba_gold = render_tiktok_frame_rgba(
            chunks,
            t_ms=700,
            font_path=VAZIRMATN_FONT,
            hook_title_ckb="چیرۆکی ڕێستۆرانتەکە",
            style_preset="viral_gold",
        )
        assert rgba_default == rgba_gold

    @pytest.mark.parametrize(
        "preset_name",
        ("viral_gold", "crimson_punch", "executive_cyan", "luxury_minimal", "broadcast_news"),
    )
    def test_all_five_presets_render_signature_pill_and_power_colors(
        self, preset_name: str, tmp_path: Path
    ) -> None:
        preset = get_client_style_preset(preset_name)
        chunks = chunk_viral_kurdish_words(
            [
                Word("لە", 0, 320, 0.99),
                Word("AIـەکە", 340, 1000, 0.99),
                Word("کوردییەکەیان", 1100, 2000, 0.99),
            ],
            power_word_indices={2},
        )
        # Regular active word renders preset's active pill hex.
        rgba_active = render_tiktok_frame_rgba(
            chunks,
            t_ms=650,
            font_path=VAZIRMATN_FONT,
            hook_title_ckb="چیرۆکی ڕێستۆرانتەکە",
            style_preset=preset_name,
        )
        assert (
            _color_pixel_count(
                rgba_active,
                width=1080,
                height=1920,
                target_hex=preset.active_pill_hex,
                y_min=1220,
                y_max=1540,
            )
            > 8_000
        )

        # Power word beat renders preset's power pill hex.
        rgba_power = render_tiktok_frame_rgba(
            chunks,
            t_ms=1500,
            font_path=VAZIRMATN_FONT,
            style_preset=preset_name,
        )
        assert (
            _color_pixel_count(
                rgba_power,
                width=1080,
                height=1920,
                target_hex=preset.power_pill_hex,
                y_min=1220,
                y_max=1540,
            )
            > 10_000
        )

        out_png = render_tiktok_preview_png(
            chunks,
            t_ms=650,
            output_png=tmp_path / f"{preset_name}.png",
            font_path=VAZIRMATN_FONT,
            style_preset=preset,
        )
        assert out_png.is_file()
        assert out_png.stat().st_size > 12_000

    def test_speaker_bio_window_and_zero_overlap_with_hook_and_pill(self) -> None:
        chunks = chunk_viral_kurdish_words(
            [
                Word("پێش", 1800, 2200, 0.99),
                Word("ئەوەی", 2200, 2600, 0.99),
                Word("بەجێی", 3000, 3500, 0.99),
                Word("ناهێڵم", 3500, 4400, 0.99),
            ]
        )
        bio = ("هاوژین", "پێشکەشکار")

        # Before 2600 ms (hook window): speaker bio band (y=1510..1720) must be 100% transparent.
        f_before = render_tiktok_frame_rgba(
            chunks,
            t_ms=2000,
            font_path=VAZIRMATN_FONT,
            hook_title_ckb="چیرۆکی کوردییەکەیان",
            speaker_bio=bio,
            style_preset="executive_cyan",
        )
        arr_before = np.frombuffer(f_before, dtype=np.uint8).reshape((1920, 1080, 4))
        assert int((arr_before[1515:1720, :, 3] > 0).sum()) == 0

        # Inside 2600..6200 ms: bio rendered cleanly below pill with zero overlap gap!
        f_during = render_tiktok_frame_rgba(
            chunks,
            t_ms=3700,
            font_path=VAZIRMATN_FONT,
            hook_title_ckb="چیرۆکی کوردییەکەیان",
            speaker_bio=bio,
            style_preset="executive_cyan",
        )
        arr_during = np.frombuffer(f_during, dtype=np.uint8).reshape((1920, 1080, 4))
        # Bottom TikTok pill present around y=1300..1460
        assert int((arr_during[1300:1465, :, 3] > 200).sum()) > 15_000
        # Speaker bio present below pill at y=1525..1690
        assert int((arr_during[1525:1690, :, 3] > 200).sum()) > 15_000
        # Clean vertical separation gap between pill bottom and bio top!
        assert int((arr_during[1480:1512, :, 3] > 150).sum()) == 0

        # After 6200 ms: speaker bio band completely transparent again.
        f_after = render_tiktok_frame_rgba(
            chunks,
            t_ms=SPEAKER_BIO_END_MS + 100,
            font_path=VAZIRMATN_FONT,
            speaker_bio=bio,
        )
        arr_after = np.frombuffer(f_after, dtype=np.uint8).reshape((1920, 1080, 4))
        assert int((arr_after[1515:1720, :, 3] > 0).sum()) == 0

        # Name-only bio and invalid bio validation.
        f_name_only = render_tiktok_frame_rgba(
            chunks, t_ms=3700, font_path=VAZIRMATN_FONT, speaker_bio=("هاوژین", None)
        )
        arr_no = np.frombuffer(f_name_only, dtype=np.uint8).reshape((1920, 1080, 4))
        assert int((arr_no[1525:1690, :, 3] > 200).sum()) > 8_000

        with pytest.raises(ValueError, match="speaker_bio name_ckb"):
            render_tiktok_frame_rgba(
                chunks, t_ms=3700, font_path=VAZIRMATN_FONT, speaker_bio=("   ", "پێشکەشکار")
            )

    def test_end_card_renders_in_final_two_seconds_without_pill_collision(self) -> None:
        chunks = chunk_viral_kurdish_words([Word("کوردییەکەیان", 8200, 9600, 0.99)])
        end_card = ("فۆڵۆمان بکەن بۆ ئەڵقەی زیاتر", "پۆدکاستی کوردی • AIـەکە", "@hawedit")

        # Before final 2.0 s (t=7500 < 8000): center card band completely empty.
        f_mid = render_tiktok_frame_rgba(
            chunks,
            t_ms=7500,
            duration_ms=10_000,
            font_path=VAZIRMATN_FONT,
            style_preset="luxury_minimal",
            end_card=end_card,
        )
        arr_mid = np.frombuffer(f_mid, dtype=np.uint8).reshape((1920, 1080, 4))
        assert int((arr_mid[600:1150, :, 3] > 0).sum()) == 0

        # Inside final 2.0 s (t=9000 in 8000..10000): centered frosted card + clear gap above pill.
        f_outro = render_tiktok_frame_rgba(
            chunks,
            t_ms=9000,
            duration_ms=10_000,
            font_path=VAZIRMATN_FONT,
            style_preset="luxury_minimal",
            end_card=end_card,
        )
        arr_outro = np.frombuffer(f_outro, dtype=np.uint8).reshape((1920, 1080, 4))
        assert int((arr_outro[620:1150, :, 3] > 200).sum()) > 80_000
        # Gap between outro card bottom and bottom subtitle pill stays clean.
        assert int((arr_outro[1200:1265, :, 3] > 150).sum()) == 0

        with pytest.raises(ValueError, match="end_card title_ckb"):
            render_tiktok_frame_rgba(
                chunks,
                t_ms=9000,
                duration_ms=10_000,
                font_path=VAZIRMATN_FONT,
                end_card=("  ", None, "@hawedit"),
            )

    def test_streaming_overlay_video_with_preset_bio_and_end_card(self, tmp_path: Path) -> None:
        ffmpeg = find_ffmpeg()
        assert ffmpeg is not None, "pinned FFmpeg is required for overlay video test"
        chunks = chunk_viral_kurdish_words(
            [
                Word("لە", 2800, 3200, 0.99),
                Word("ڕێستۆرانتەکە", 3200, 4200, 0.99),
            ]
        )
        mov_path = render_tiktok_overlay_video(
            chunks,
            duration_ms=8000,
            output_mov_or_mkv=tmp_path / "v9_branded_overlay.mov",
            font_path=VAZIRMATN_FONT,
            style_preset="broadcast_news",
            speaker_bio=("هاوژین", "پێشکەشکار"),
            end_card=("فۆڵۆمان بکەن", "پۆدکاستی کوردی", "@hawedit"),
            fps=10.0,
            ffmpeg=ffmpeg,
        )
        assert mov_path.stat().st_size > 20_000

        def extract_frame(ts: str) -> npt.NDArray[np.uint8]:
            raw = subprocess.check_output(
                [
                    str(ffmpeg),
                    "-v",
                    "error",
                    "-ss",
                    ts,
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
            return np.frombuffer(raw, dtype=np.uint8).reshape((1920, 1080, 4))

        # At t=3.5s: broadcast_news pill + speaker bio visible, end card absent.
        arr_bio = extract_frame("3.50")
        assert int((arr_bio[1525:1690, :, 3] > 200).sum()) > 12_000
        assert int((arr_bio[650:1100, :, 3] > 180).sum()) == 0

        # At t=7.0s (inside final 2.0s of 8.0s clip): end card visible, speaker bio gone.
        arr_end = extract_frame("7.00")
        assert int((arr_end[620:1150, :, 3] > 200).sum()) > 60_000
        assert int((arr_end[1525:1690, :, 3] > 180).sum()) == 0


# ---------------------------------------------------------------------------
# 3. Zero-Dep libass Fallback with Presets, Speaker Bio & End Card
# ---------------------------------------------------------------------------


class TestV9StyledAssFallback:
    def test_ass_default_is_byte_identical_to_viral_gold(self) -> None:
        chunks = chunk_viral_kurdish_words(
            [Word("لە", 0, 400, 0.99), Word("کوردییەکەیان", 420, 1200, 0.99)],
            power_word_indices={1},
        )
        ass_none = build_viral_tiktok_ass(chunks, clip_duration_ms=3000, hook_title_ckb="سەرەتا")
        ass_gold = build_viral_tiktok_ass(
            chunks, clip_duration_ms=3000, hook_title_ckb="سەرەتا", style_preset="viral_gold"
        )
        assert ass_none == ass_gold

    def test_ass_emits_preset_colors_speaker_bio_and_end_card_within_bounds(self) -> None:
        chunks = chunk_viral_kurdish_words(
            [Word("لە", 2800, 3200, 0.99), Word("AIـەکە", 3250, 4200, 0.99)]
        )
        ass_text = build_viral_tiktok_ass(
            chunks,
            clip_in_ms=0,
            clip_duration_ms=9000,
            hook_title_ckb="چیرۆکی ڕێستۆرانتەکە",
            style_preset="crimson_punch",
            speaker_bio=("هاوژین", "پێشکەشکار"),
            end_card=("فۆڵۆمان بکەن", "پۆدکاستی کوردی", "@hawedit"),
        )
        # Crimson #FF2E63 in ASS BGR is &H00632EFF
        assert "&H00632EFF" in ass_text
        assert "Style: SpeakerBio," in ass_text
        assert "Style: EndCard," in ass_text
        assert (
            f"Dialogue: 3,0:00:0{SPEAKER_BIO_START_MS // 1000}.60,"
            f"0:00:0{SPEAKER_BIO_END_MS // 1000}.20,SpeakerBio" in ass_text
        )
        end_start_s = (9000 - END_CARD_DURATION_MS) // 1000
        assert f"Dialogue: 4,0:00:0{end_start_s}.00,0:00:09.00,EndCard" in ass_text
        assert "@hawedit" in ass_text
        assert_captions_within_clip(ass_text, 9000)
        assert_ass_fonts_cover_kurdish(ass_text, FONTS_DIR)
