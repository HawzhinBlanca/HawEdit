"""Genuine renderer-input regressions; estimates cannot masquerade as measurements."""

import shutil
import sys
from pathlib import Path

import pytest

from hawedit import captions
from hawedit.captions import (
    CaptionVerificationError,
    find_ffmpeg,
    measure_rendered_caption_width,
)


def test_caption_width_missing_renderer_refuses_without_poisoning_cache(tmp_path: Path) -> None:
    absent = tmp_path / "absent-renderer.exe"
    assert not absent.exists()
    with pytest.raises(CaptionVerificationError, match="measurement"):
        measure_rendered_caption_width("unavailable-renderer-negative", ffmpeg=absent)


def test_caption_width_failed_renderer_refuses_after_a_valid_cache_entry(tmp_path: Path) -> None:
    binary = find_ffmpeg()
    assert binary is not None, "Actual caption regression requires the configured renderer"
    text = "cached-renderer-negative"
    assert measure_rendered_caption_width(text, ffmpeg=binary) > 0
    absent = tmp_path / "different-absent-renderer.exe"
    assert not absent.exists()
    with pytest.raises(CaptionVerificationError, match="measurement"):
        measure_rendered_caption_width(text, ffmpeg=absent)


def test_caption_width_cache_binds_renderer_fonts_and_canvas(tmp_path: Path) -> None:
    binary = find_ffmpeg()
    assert binary is not None, "Actual caption regression requires the configured renderer"
    text = "font-directory-negative"
    assert measure_rendered_caption_width(text, ffmpeg=binary) > 0
    empty = tmp_path / "empty-fonts"
    empty.mkdir()
    with pytest.raises(CaptionVerificationError, match="measurement"):
        measure_rendered_caption_width(text, ffmpeg=binary, fonts_dir=empty)


def test_caption_width_rejects_invalid_decoded_extent() -> None:
    with pytest.raises(CaptionVerificationError, match="extent"):
        captions._decoded_ink_width(b"\x01", width=2, height=2)


def test_caption_width_changed_font_context_remeasures(tmp_path: Path) -> None:
    binary = find_ffmpeg()
    assert binary is not None, "Actual caption regression requires the configured renderer"
    fonts = Path(__file__).resolve().parents[1] / "assets" / "fonts"
    target = tmp_path / "fonts"
    target.mkdir()
    selected = target / "selected.ttf"
    shutil.copyfile(fonts / "NotoNaskhArabic-Regular.ttf", selected)
    text = "changed-local-font-negative"
    assert measure_rendered_caption_width(text, ffmpeg=binary, fonts_dir=target) > 0
    shutil.copyfile(fonts / "Vazirmatn.ttf", selected)
    with pytest.raises(CaptionVerificationError, match="measurement"):
        measure_rendered_caption_width(text, ffmpeg=binary, fonts_dir=target)


def test_caption_width_genuine_nonrenderer_process_refuses() -> None:
    with pytest.raises(CaptionVerificationError, match="measurement"):
        measure_rendered_caption_width("actual-nonrenderer-negative", ffmpeg=Path(sys.executable))


@pytest.mark.parametrize("dimension", [0, -1, True, 1.5, None, 1 << 30])
def test_caption_width_refuses_invalid_canvas_dimensions(dimension: object) -> None:
    with pytest.raises(CaptionVerificationError, match="measurement"):
        measure_rendered_caption_width("invalid-canvas-negative", canvas_width=dimension)  # type: ignore[arg-type]
