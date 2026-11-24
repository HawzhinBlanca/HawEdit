"""Tests for E1 per-reel contact sheets (`hawedit.contact_sheet`)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest

from hawedit.captions import find_ffmpeg

ROOT = Path(__file__).resolve().parent.parent


def _make_two_color_mp4(path: Path, *, fps: int = 25) -> None:
    """Create a 2.0 s 1080x1920 synthetic MP4: [0..1s) red, [1..2s) blue."""
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None, "pinned ffmpeg binary required for contact-sheet tests"
    # Note FFmpeg color inputs in BGR order: red=(0,0,255), blue=(255,0,0).
    cmd = [
        str(ffmpeg),
        "-y",
        "-nostdin",
        "-f",
        "lavfi",
        "-i",
        f"color=c=red:s=270x480:r={fps}:d=1.0",
        "-f",
        "lavfi",
        "-i",
        f"color=c=blue:s=270x480:r={fps}:d=1.0",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=48000:cl=stereo:d=2.0",
        "-filter_complex",
        "[0:v][1:v]concat=n=2:v=1:a=0[v]",
        "-map",
        "[v]",
        "-map",
        "2:a",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr


def _sample_tile_center_bgr(
    sheet: np.ndarray[Any, np.dtype[Any]], col: int, row: int
) -> tuple[int, int, int]:
    from hawedit.contact_sheet import TILE_BANNER_HEIGHT, TILE_HEIGHT, TILE_WIDTH

    x = col * TILE_WIDTH + TILE_WIDTH // 2
    y = row * (TILE_HEIGHT + TILE_BANNER_HEIGHT) + TILE_BANNER_HEIGHT + TILE_HEIGHT // 2
    b, g, r = (int(v) for v in sheet[y, x])
    return (b, g, r)


def test_contact_sheet_writes_beside_mp4_and_preserves_bundle_suffixes(tmp_path: Path) -> None:
    from hawedit.artifact_bundle import _SUFFIXES
    from hawedit.candidate_review import REVIEW_SUFFIXES
    from hawedit.contact_sheet import CONTACT_SHEET_SUFFIX, render_reel_contact_sheet

    assert ".contact-sheet.jpg" not in _SUFFIXES
    assert "contact-sheet.jpg" not in _SUFFIXES
    assert "contact-sheet.jpg" not in REVIEW_SUFFIXES
    assert CONTACT_SHEET_SUFFIX == ".contact-sheet.jpg"

    mp4_path = tmp_path / "clip_01.mp4"
    _make_two_color_mp4(mp4_path)

    result = render_reel_contact_sheet(mp4_path, cut_timestamps_ms=(1000,))
    expected = tmp_path / "clip_01.contact-sheet.jpg"
    assert result.sheet_path == expected
    assert expected.is_file() and expected.stat().st_size > 0
    assert result.cut_timestamps_ms == (1000,)


def test_contact_sheet_extracts_first_frame_both_sides_of_cuts_and_caption_crop(
    tmp_path: Path,
) -> None:
    from hawedit.contact_sheet import (
        GRID_COLUMNS,
        TILE_BANNER_HEIGHT,
        TILE_HEIGHT,
        TILE_WIDTH,
        render_reel_contact_sheet,
    )

    mp4_path = tmp_path / "clip_cuts.mp4"
    _make_two_color_mp4(mp4_path)

    result = render_reel_contact_sheet(mp4_path, cut_timestamps_ms=(1000,))
    assert result.tile_count == 3  # FIRST + CUT #1 PRE + CUT #1 POST
    assert result.filler_count == 1  # 4 columns - 3 tiles = 1 filler

    img = cv2.imread(str(result.sheet_path))
    assert img is not None
    assert img.shape[1] == GRID_COLUMNS * TILE_WIDTH
    assert img.shape[0] > TILE_HEIGHT + TILE_BANNER_HEIGHT  # Includes enlarged caption crop strip


def test_contact_sheet_zero_cut_reel_still_includes_first_and_caption_crop(
    tmp_path: Path,
) -> None:
    from hawedit.contact_sheet import TILE_BANNER_HEIGHT, TILE_HEIGHT, render_reel_contact_sheet

    mp4_path = tmp_path / "clip_single_shot.mp4"
    _make_two_color_mp4(mp4_path)

    result = render_reel_contact_sheet(mp4_path, cut_timestamps_ms=())
    assert result.tile_count == 1
    assert result.filler_count == 3
    img = cv2.imread(str(result.sheet_path))
    assert img is not None
    assert img.shape[0] > TILE_HEIGHT + TILE_BANNER_HEIGHT


def test_contact_sheet_pre_and_post_cut_frames_capture_distinct_sides_of_cut(
    tmp_path: Path,
) -> None:
    from hawedit.contact_sheet import render_reel_contact_sheet

    mp4_path = tmp_path / "clip_red_to_blue.mp4"
    _make_two_color_mp4(mp4_path, fps=25)

    result = render_reel_contact_sheet(mp4_path, cut_timestamps_ms=(1000,))
    sheet = cv2.imread(str(result.sheet_path))
    assert sheet is not None

    first_bgr = _sample_tile_center_bgr(sheet, col=0, row=0)
    pre_bgr = _sample_tile_center_bgr(sheet, col=1, row=0)
    post_bgr = _sample_tile_center_bgr(sheet, col=2, row=0)

    # Red segment -> R dominates B; Blue segment -> B dominates R.
    assert first_bgr[2] > first_bgr[0] + 100
    assert pre_bgr[2] > pre_bgr[0] + 100
    assert post_bgr[0] > post_bgr[2] + 100


def test_contact_sheet_caption_crop_targets_active_ass_midpoint_and_enlarges(
    tmp_path: Path,
) -> None:
    from hawedit.contact_sheet import TILE_WIDTH, render_reel_contact_sheet

    mp4_path = tmp_path / "clip_captioned.mp4"
    _make_two_color_mp4(mp4_path, fps=25)
    ass_path = tmp_path / "clip_captioned.ass"
    # Cue spans strictly inside blue half [1.20s, 1.80s] -> midpoint 1500 ms.
    ass_path.write_text(
        "[Script Info]\nScriptType: v4.00+\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Vazirmatn,64,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,0,0,0,0,"
        "100,100,0,0,1,3,0,2,20,20,40,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.20,0:00:01.80,Default,,0,0,0,,کوردی\n",
        encoding="utf-8",
    )

    result = render_reel_contact_sheet(mp4_path, ass_path=ass_path, cut_timestamps_ms=())
    assert result.caption_timestamp_ms == 1500
    assert "ass" in result.caption_source
    assert result.sheet_width == 4 * TILE_WIDTH

    sheet = cv2.imread(str(result.sheet_path))
    assert sheet is not None
    # Enlarged caption crop is at the bottom strip and sampled from the blue region (1500 ms).
    bottom_center = sheet[-40, result.sheet_width // 2]
    assert int(bottom_center[0]) > int(bottom_center[2]) + 100


def test_contact_sheet_marks_unused_grid_cells_as_filler(tmp_path: Path) -> None:
    from hawedit.contact_sheet import FILLER_BG_BGR, render_reel_contact_sheet

    mp4_path = tmp_path / "clip_filler.mp4"
    _make_two_color_mp4(mp4_path)

    result = render_reel_contact_sheet(mp4_path, cut_timestamps_ms=(1000,))
    sheet = cv2.imread(str(result.sheet_path))
    assert sheet is not None
    filler_bgr = _sample_tile_center_bgr(sheet, col=3, row=0)
    # Filler cell must stay close to non-black slate FILLER_BG_BGR (not solid black 0,0,0).
    assert np.all(np.abs(np.array(filler_bgr) - np.array(FILLER_BG_BGR)) <= 12)


def test_contact_sheet_fails_stop_on_missing_or_unreadable_video(tmp_path: Path) -> None:
    from hawedit.contact_sheet import render_reel_contact_sheet

    missing = tmp_path / "missing.mp4"
    with pytest.raises((FileNotFoundError, RuntimeError, ValueError)):
        render_reel_contact_sheet(missing)
    assert not missing.with_suffix(".contact-sheet.jpg").exists()

    corrupt = tmp_path / "corrupt.mp4"
    corrupt.write_bytes(b"not-a-valid-mp4-stream")
    with pytest.raises((RuntimeError, ValueError)):
        render_reel_contact_sheet(corrupt)
    assert not corrupt.with_suffix(".contact-sheet.jpg").exists()


def test_pipeline_post_publish_generates_contact_sheet_next_to_reel(tmp_path: Path) -> None:
    import hashlib

    from hawedit.clip import Qc
    from hawedit.judge import KURDISH_EDITORIAL_JUDGE, JudgeVerdict
    from hawedit.pipeline import StageSkipped, run_pipeline
    from hawedit.transcripts import AsrProvenance, RawTranscript, Word

    fixture = ROOT / "tests" / "fixtures" / "kurdish-speech-3cuts.mp4"
    fixture_sha = hashlib.sha256(fixture.read_bytes()).hexdigest()
    words = (
        Word(w="ڕۆژنامەوانی", start_ms=100, end_ms=800, conf=0.95),
        Word(w="کوردی.", start_ms=800, end_ms=1_700, conf=0.94),
        Word(w="لە", start_ms=2_000, end_ms=2_400, conf=0.93),
        Word(w="هەولێر.", start_ms=2_400, end_ms=4_100, conf=0.92),
    )
    transcript = RawTranscript(
        media_id="cs_pipe",
        text_ckb="ڕۆژنامەوانی کوردی. لە هەولێر.",
        words=words,
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
        media_sha256=fixture_sha,
    )
    verdict = JudgeVerdict(
        candidate_id="cs-pipe-0",
        clip_in_ms=100,
        clip_out_ms=1_700,
        hook_score=0.9,
        self_contained=True,
        meaning_fidelity=0.95,
        misleading_edit_risk=0.02,
        cultural_landing=0.9,
        title_ckb="تێست",
        description_ckb="وەسف",
        hashtags_ckb=("#کوردی",),
        payoff_at_ms=900,
        narrative_role="payoff",
        judge=KURDISH_EDITORIAL_JUDGE,
    )

    run = run_pipeline(
        fixture,
        tmp_path / "work",
        media_id="cs_pipe",
        transcript=transcript,
        select_sentences=(0,),
        verdict=verdict,
        qc=Qc(auto_pass=True),
    )
    assert run.render is not None and not isinstance(run.render, StageSkipped)
    rendered_mp4 = Path(run.render.path)
    sheet_path = rendered_mp4.with_suffix(".contact-sheet.jpg")
    assert sheet_path.is_file() and sheet_path.stat().st_size > 0
    sheet_img = cv2.imread(str(sheet_path))
    assert sheet_img is not None and sheet_img.shape[0] > 0


def test_contact_sheet_resolves_cuts_from_edit_plan_json(tmp_path: Path) -> None:
    from hawedit.captions import CaptionStyle
    from hawedit.contact_sheet import render_reel_contact_sheet
    from hawedit.content_type import ContentType
    from hawedit.edit_plan import (
        CURRENT_PLAN_VERSION,
        EditorialBrief,
        EffectiveConfiguration,
        SourceTimeMapping,
        VisualEditPlan,
    )

    mp4_path = tmp_path / "clip_planned.mp4"
    _make_two_color_mp4(mp4_path, fps=25)
    plan = VisualEditPlan(
        version=CURRENT_PLAN_VERSION,
        clip_id="clip_planned",
        media_id="m_planned",
        media_sha256="b" * 64,
        brief=EditorialBrief("Editorial point", ContentType.PODCAST, (1_000, 2_000)),
        config=EffectiveConfiguration.resolve(
            content_type=ContentType.PODCAST, caption_style=CaptionStyle.WORD_HIGHLIGHT
        ),
        time_mapping=SourceTimeMapping(
            clip_in_ms=5_000,
            clip_out_ms=7_500,
            retained_intervals_ms=((5_000, 6_000), (6_500, 7_500)),
        ),
        shot_cuts_ms=(),
    )
    plan_path = tmp_path / "clip_planned.edit_plan.json"
    plan_path.write_text(plan.to_json(), encoding="utf-8")

    result = render_reel_contact_sheet(mp4_path)
    assert result.cut_timestamps_ms == (1000,)
    sheet = cv2.imread(str(result.sheet_path))
    assert sheet is not None
    pre_bgr = _sample_tile_center_bgr(sheet, col=1, row=0)
    post_bgr = _sample_tile_center_bgr(sheet, col=2, row=0)
    assert pre_bgr[2] > pre_bgr[0] + 100
    assert post_bgr[0] > post_bgr[2] + 100


def test_contact_sheet_cli_roundtrip(tmp_path: Path) -> None:
    mp4_path = tmp_path / "cli_reel.mp4"
    _make_two_color_mp4(mp4_path)
    proc = subprocess.run(
        [sys.executable, "-m", "hawedit.contact_sheet", str(mp4_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "cli_reel.contact-sheet.jpg").is_file()


def test_resolve_caption_target_ignores_unused_top_and_hook_styles(tmp_path: Path) -> None:
    """Speech cue alignment wins over unused KurdishTop*/Hook style declarations."""
    from hawedit.contact_sheet import _resolve_caption_target

    ass_path = tmp_path / "reel.ass"
    ass_path.write_text(
        "\n".join(
            [
                "[V4+ Styles]",
                "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
                "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
                "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
                "Style: Kurdish,Vazirmatn,128,&H00FFFFFF,&H00FFFFFF,&H00000000,"
                "&H80000000,1,0,0,0,100,100,0,0,1,6,2,2,80,80,450,-1",
                "Style: KurdishTop,Vazirmatn,128,&H00FFFFFF,&H00FFFFFF,&H00000000,"
                "&H80000000,1,0,0,0,100,100,0,0,1,6,2,8,80,80,240,-1",
                "Style: KurdishTopHighlight,Vazirmatn,128,&H0000E5FF,&H00FFFFFF,&H00000000,"
                "&H80000000,1,0,0,0,100,100,0,0,1,6,2,8,80,80,240,-1",
                "Style: Hook,Vazirmatn,84,&H00FFFFFF,&H00FFFFFF,&H00000000,"
                "&H66000000,1,0,0,0,100,100,0,0,3,18,0,8,60,60,120,-1",
                "[Events]",
                "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
                "Dialogue: 1,0:00:00.00,0:00:05.00,Hook,,0,0,0,,ناونیشان",
                "Dialogue: 0,0:00:01.00,0:00:03.00,Kurdish,,0,0,0,,سڵاو جیهان",
            ]
        ),
        encoding="utf-8",
    )
    mid_ms, source, band = _resolve_caption_target(
        tmp_path / "reel.mp4", ass_path, duration_ms=10_000
    )
    assert source == "ass_midpoint"
    assert mid_ms == 2_000
    assert band == "bottom"
