"""Tests for brand kit configuration and overlay generators (Task T2.13)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hawedit.brand import (
    DEFAULT_LOGO_MARGIN,
    DEFAULT_LOGO_OPACITY,
    DEFAULT_LOGO_WIDTH,
    BrandKit,
    BrandKitError,
    EndCardConfig,
    ProgressBarConfig,
    SpeakerBio,
    logo_overlay_coordinates,
    progress_bar_filter,
)


def test_speaker_bio_validation_and_serialization() -> None:
    bio = SpeakerBio(name_ckb="د. ئاراس عومەر", title_ckb="پزیشکی پسپۆڕ")
    assert bio.name_ckb == "د. ئاراس عومەر"
    assert bio.title_ckb == "پزیشکی پسپۆڕ"

    d = bio.to_dict()
    assert d == {"name_ckb": "د. ئاراس عومەر", "title_ckb": "پزیشکی پسپۆڕ"}
    restored = SpeakerBio.from_dict(d)
    assert restored == bio

    with pytest.raises(ValueError, match="name_ckb must not be empty"):
        SpeakerBio(name_ckb="")
    with pytest.raises(ValueError, match="name_ckb must not be empty"):
        SpeakerBio(name_ckb="   ")


def test_progress_bar_config_validation() -> None:
    cfg = ProgressBarConfig(enabled=True, color="#00FF00", height_px=8, position="top")
    assert cfg.enabled is True
    assert cfg.color == "#00FF00"
    assert cfg.height_px == 8
    assert cfg.position == "top"

    d = cfg.to_dict()
    assert ProgressBarConfig.from_dict(d) == cfg

    with pytest.raises(ValueError, match="height_px must be positive"):
        ProgressBarConfig(height_px=0)
    with pytest.raises(ValueError, match="position must be 'bottom' or 'top'"):
        ProgressBarConfig(position="middle")
    with pytest.raises(ValueError, match="color must not be empty"):
        ProgressBarConfig(color="")


def test_end_card_config_validation() -> None:
    end_card = EndCardConfig(
        enabled=True,
        duration_s=2.5,
        title_ckb="سەبسکرایب بکەن",
        handle="@hawedit",
    )
    assert end_card.duration_s == 2.5
    d = end_card.to_dict()
    assert EndCardConfig.from_dict(d) == end_card

    with pytest.raises(ValueError, match="duration_s must be positive"):
        EndCardConfig(duration_s=0.0)


def test_brand_kit_validation_and_missing_file_fail_stop(tmp_path: Path) -> None:
    kit = BrandKit()
    assert kit.logo_width == DEFAULT_LOGO_WIDTH
    assert kit.logo_opacity == DEFAULT_LOGO_OPACITY
    assert kit.logo_margin == DEFAULT_LOGO_MARGIN
    kit.assert_valid()

    missing_logo = tmp_path / "non_existent_logo.png"
    kit_missing = BrandKit(logo_path=missing_logo)
    with pytest.raises(BrandKitError, match="brand logo file not found"):
        kit_missing.assert_valid()

    real_logo = tmp_path / "logo.png"
    real_logo.write_bytes(b"PNGFAKE")
    kit_real = BrandKit(logo_path=real_logo)
    kit_real.assert_valid()

    with pytest.raises(ValueError, match="logo_opacity must be in"):
        BrandKit(logo_opacity=0.0)
    with pytest.raises(ValueError, match="logo_opacity must be in"):
        BrandKit(logo_opacity=1.5)
    with pytest.raises(ValueError, match="logo_width must be positive"):
        BrandKit(logo_width=0)
    with pytest.raises(ValueError, match="invalid logo_position"):
        BrandKit(logo_position="center")


def test_brand_kit_json_roundtrip(tmp_path: Path) -> None:
    logo_file = tmp_path / "assets" / "watermark.png"
    logo_file.parent.mkdir(parents=True)
    logo_file.write_bytes(b"FAKE_PNG_HEADER")

    kit = BrandKit(
        speaker_metadata={
            "SPEAKER_00": SpeakerBio(name_ckb="د. ئاراس عومەر", title_ckb="میوان"),
            "SPEAKER_01": SpeakerBio(name_ckb="هاوژین عەزیز", title_ckb="پێشکەشکار"),
        },
        logo_path=logo_file,
        logo_position="top_left",
        progress_bar=ProgressBarConfig(enabled=True, color="#FFCC00"),
        end_card=EndCardConfig(enabled=True, title_ckb="کۆتایی"),
    )

    json_path = tmp_path / "brand_kit.json"
    json_path.write_text(json.dumps(kit.to_dict(), ensure_ascii=False), encoding="utf-8")

    loaded = BrandKit.from_json(json_path)
    assert loaded.logo_path == logo_file
    assert loaded.logo_position == "top_left"
    assert loaded.speaker_metadata["SPEAKER_00"].name_ckb == "د. ئاراس عومەر"
    assert loaded.speaker_metadata["SPEAKER_01"].title_ckb == "پێشکەشکار"
    assert loaded.progress_bar.enabled is True
    assert loaded.progress_bar.color == "#FFCC00"
    assert loaded.end_card.enabled is True
    assert loaded.end_card.title_ckb == "کۆتایی"


def test_logo_overlay_coordinates() -> None:
    x_tr, y_tr = logo_overlay_coordinates("top_right", margin=30)
    assert x_tr == "main_w-overlay_w-30"
    assert y_tr == "30"

    x_tl, y_tl = logo_overlay_coordinates("top_left", margin=40)
    assert x_tl == "40"
    assert y_tl == "40"

    x_br, y_br = logo_overlay_coordinates("bottom_right", margin=50)
    assert x_br == "main_w-overlay_w-50"
    assert y_br == "main_h-overlay_h-50"

    x_bl, y_bl = logo_overlay_coordinates("bottom_left", margin=20)
    assert x_bl == "20"
    assert y_bl == "main_h-overlay_h-20"

    with pytest.raises(ValueError, match="unsupported position"):
        logo_overlay_coordinates("somewhere_else")


def test_progress_bar_filter() -> None:
    filt_bottom = progress_bar_filter(30.0, color="#E50914", height_px=6, position="bottom")
    assert "drawbox=x=0:y=1914:" in filt_bottom
    assert "w='iw*min(t/30.000,1.0)'" in filt_bottom
    assert "h=6" in filt_bottom
    assert "color=#E50914" in filt_bottom

    filt_top = progress_bar_filter(15.5, color="white@0.8", height_px=4, position="top")
    assert "drawbox=x=0:y=0:" in filt_top
    assert "w='iw*min(t/15.500,1.0)'" in filt_top
    assert "h=4" in filt_top
    assert "color=white@0.8" in filt_top

    with pytest.raises(ValueError, match="duration_s must be positive"):
        progress_bar_filter(0.0)
    with pytest.raises(ValueError, match="height_px must be positive"):
        progress_bar_filter(10.0, height_px=0)
