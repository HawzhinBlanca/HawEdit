"""Tests for Pro Video Repurposing: Kinetic Pop, Hook Banners, and Music Ducking (ADR D-273).

Validates the 5 key finishing techniques that bridge the quality gap to the industry Top 3:
- Dynamic kinetic word "pop" subtitles (CaptionStyle.KINETIC_POP)
- 0-3.5s sticky top hook headline banner badges (HookBannerConfig)
- Background music loop with automatic sidechain compression ducking
- CLI parser and preset defaults for broadcast and viral workflows
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hawedit.captions import (
    HOOK_BANNER_MARGIN_V,
    CaptionStyle,
    HookBannerConfig,
    build_ass,
)
from hawedit.pipeline import build_parser
from hawedit.render import render_clip
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
    )
    return Sentence(words=words, complete=True)


def test_kinetic_pop_style_emits_dynamic_bounce_tags(sample_sentence: Sentence) -> None:
    ass = build_ass(
        [sample_sentence],
        style=CaptionStyle.KINETIC_POP,
        clip_in_ms=1000,
        clip_duration_ms=3000,
    )

    assert "Style: Kurdish," in ass
    # Kinetic pop applies scale bounce tags (\fscx118\fscy118 -> \fscx100\fscy100)
    assert r"\fscx118\fscy118" in ass
    assert r"\fscx100\fscy100" in ass
    # Inactive words are coloured in white
    assert r"\c&H00FFFFFF&" in ass
    # Kurdish Sorani words are present and intact
    assert "پۆڵ" in ass
    assert "برێمەر" in ass
    assert "پێشمەرگە" in ass


def test_hook_banner_ass_generation_layer_and_timing(sample_sentence: Sentence) -> None:
    hook_cfg = HookBannerConfig(
        text_ckb="نهێنییە گەورەکەی پۆڵ برێمەر",
        duration_s=3.5,
        enabled=True,
    )
    ass = build_ass(
        [sample_sentence],
        style=CaptionStyle.BROADCAST_STUDIO,
        clip_in_ms=1000,
        clip_duration_ms=5000,
        hook_banner=hook_cfg,
    )

    # Hook banner style definition with plate backing (border_style=3)
    assert "Style: HookBanner," in ass
    assert f",8,60,60,{HOOK_BANNER_MARGIN_V},1" in ass  # Alignment 8 (top center)

    # Dialogue event on layer 3 for 0 -> 3.5s with fade-in/fade-out
    assert "Dialogue: 3,0:00:00.00,0:00:03.50,HookBanner" in ass
    assert r"\fad(150,300)" in ass
    assert "نهێنییە گەورەکەی پۆڵ برێمەر" in ass


def test_hook_banner_disabled_does_not_emit_event(sample_sentence: Sentence) -> None:
    hook_cfg = HookBannerConfig(
        text_ckb="نهێنییە گەورەکەی پۆڵ برێمەر",
        enabled=False,
    )
    ass = build_ass(
        [sample_sentence],
        style=CaptionStyle.BROADCAST_STUDIO,
        clip_in_ms=1000,
        clip_duration_ms=3000,
        hook_banner=hook_cfg,
    )

    assert "Dialogue: 3" not in ass
    assert "HookBanner" not in ass


def test_render_clip_builds_sidechain_ducking_filter(
    tmp_path: Path, sample_sentence: Sentence
) -> None:
    clip_mock = MagicMock(_mock_unsafe=True)
    clip_mock.assert_renderable = MagicMock(return_value=None)
    clip_mock.in_ms = 0
    clip_mock.out_ms = 4000
    clip_mock.duration_ms = 4000
    clip_mock.focus_points = ()

    source = tmp_path / "source.mp4"
    source.write_bytes(b"dummy")
    ass = tmp_path / "subs.ass"
    from hawedit.pipeline import FONTS_DIR

    ass.write_text(
        build_ass([sample_sentence], clip_in_ms=0, clip_duration_ms=4000),
        encoding="utf-8",
    )
    out = tmp_path / "out.mp4"
    music = tmp_path / "music.wav"
    music.write_bytes(b"dummy_music")
    prov = tmp_path / "music.wav.provenance.json"
    prov.write_text(
        json.dumps({"origin": "test", "sha256": hashlib.sha256(b"dummy_music").hexdigest()})
    )

    recorded_cmd: list[str] = []

    def mock_run(cmd: list[str], **kwargs: object) -> MagicMock:
        nonlocal recorded_cmd
        recorded_cmd = list(cmd)
        if "-y" in cmd:
            y_idx = cmd.index("-y")
            staging_file = Path(cmd[y_idx + 1])
            staging_file.write_bytes(b"dummy_video_output")
        result = MagicMock()
        result.returncode = 0
        result.stdout = "ffmpeg version 7.0\n--enable-libass --enable-libharfbuzz"
        result.stderr = b""
        return result

    with (
        patch("subprocess.run", side_effect=mock_run),
        patch("hawedit.render.probe_duration_ms", return_value=4000),
        patch("hawedit.render.assert_rtl_stack"),
        patch("hawedit.render.encoder_available", return_value=True),
        patch("hawedit.render.linked_libraries", return_value=["libass", "libharfbuzz"]),
        patch("hawedit.render.frame_duration_ms", return_value=33),
        patch("hawedit.render.assert_encoded_span"),
    ):
        render_clip(
            clip_mock,
            source,
            ass,
            FONTS_DIR,
            out,
            source_width=1920,
            source_height=1080,
            fps=30.0,
            ffmpeg=Path("ffmpeg"),
            music_bed_path=music,
            music_ducking_volume=0.20,
        )

    cmd_str = " ".join(recorded_cmd)
    # Music input file included
    assert str(music) in recorded_cmd
    # Sidechain compression filter generated
    assert "sidechaincompress=" in cmd_str
    # Amix with dialogue generated
    assert "amix=inputs=2" in cmd_str
    # Music loop and ducking volume passed
    assert "volume=0.20" in cmd_str


def test_cli_parser_recognizes_new_pro_arguments() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "test.mp4",
            "--hook-banner",
            "--hook-text",
            "سەردێڕی سەرەکی",
            "--music-bed",
            "music.wav",
            "--music-ducking-volume",
            "0.18",
        ]
    )
    assert args.hook_banner is True
    assert args.hook_text == "سەردێڕی سەرەکی"
    assert args.music_bed == "music.wav"
    assert args.music_ducking_volume == pytest.approx(0.18)


def test_cli_preset_viral_defaults_to_kinetic_pop_and_hook() -> None:
    parser = build_parser()
    args = parser.parse_args(["test.mp4", "--preset", "viral"])
    assert args.preset == "viral"


def test_cli_preset_broadcast_defaults_to_hook_banner() -> None:
    parser = build_parser()
    args = parser.parse_args(["test.mp4", "--preset", "broadcast"])
    assert args.preset == "broadcast"
