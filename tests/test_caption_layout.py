"""Tests for content-aware caption layout avoiding essential visual regions (VE-10)."""

from __future__ import annotations

from pathlib import Path

import pytest

from hawedit.caption_layout import (
    CaptionLayoutCue,
    CaptionLayoutError,
    CaptionLayoutPlan,
    CaptionPlacement,
    plan_caption_layout,
)
from hawedit.shot_plan import ProtectedContentRegion, ProtectedRegionKind
from hawedit.transcripts import Word


def test_caption_layout_avoids_essential_visual_regions_without_text_changes() -> None:
    """VE-10: Captions avoid essential visual regions without altering canonical speech.

    WHEN captions overlap essential visual content or overflow readable geometry,
    THE system SHALL reposition/regroup them within approved constraints or request
    review without altering canonical speech.
    """
    # Canonical Sorani speech words
    words = (
        Word("بە", 1000, 1300, 0.98),
        Word("گوێرەی", 1350, 1800, 0.97),
        Word("ئەم", 1850, 2100, 0.99),
        Word("نەخشەیە", 2150, 2700, 0.96),
        Word("داهات", 2750, 3200, 0.95),
        Word("بەرز", 3250, 3600, 0.98),
        Word("بووەتەوە", 3650, 4200, 0.97),
    )
    original_text = " ".join(w.w for w in words)

    # 1. Essential demonstration in lower third: Captions must reposition to TOP
    chart_region = ProtectedContentRegion(
        region_id="prot_chart_financial",
        kind=ProtectedRegionKind.GRAPHIC_OR_CHART,
        box=(0.10, 0.70, 0.90, 0.90),  # In lower-third caption band
        importance=1.0,
        description="Key financial graph shown on screen",
    )

    plan: CaptionLayoutPlan = plan_caption_layout(words, protected_regions=(chart_region,))

    assert plan.status == "approved"
    assert plan.repositioned_to_top_count > 0
    # Every cue must be placed at TOP, avoiding the chart
    for cue in plan.cues:
        assert cue.placement == CaptionPlacement.TOP
        # Top band box (y in [0.08, 0.26]) does not overlap chart box (y in [0.70, 0.90])
        assert cue.box[3] <= chart_region.box[1]  # cue bottom <= chart top

    # Crucial Invariant: Canonical speech is 100% unchanged
    assert plan.canonical_text == original_text
    reconstructed = " ".join(c.text for c in plan.cues)
    assert reconstructed == original_text

    # 2. Existing source lower third / nameplate: Repositions to TOP
    nameplate_region = ProtectedContentRegion(
        region_id="prot_nameplate_01",
        kind=ProtectedRegionKind.SOURCE_ON_SCREEN_TEXT,
        box=(0.05, 0.75, 0.60, 0.88),
        importance=0.9,
        description="Broadcast guest lower-third nameplate",
    )
    plan_nameplate = plan_caption_layout(words, protected_regions=(nameplate_region,))
    assert plan_nameplate.status == "approved"
    assert all(c.placement == CaptionPlacement.TOP for c in plan_nameplate.cues)
    assert plan_nameplate.canonical_text == original_text

    # 3. Clear bottom: Default BOTTOM placement is used when no conflicts exist
    upper_face = ProtectedContentRegion(
        region_id="prot_speaker_face_upper",
        kind=ProtectedRegionKind.SPEAKER_FACE,
        box=(0.35, 0.15, 0.65, 0.40),  # In upper third, clear from bottom
    )
    plan_clear = plan_caption_layout(words, protected_regions=(upper_face,))
    assert plan_clear.status == "approved"
    assert all(c.placement == CaptionPlacement.BOTTOM for c in plan_clear.cues)
    assert plan_clear.repositioned_to_top_count == 0

    # 4. Long rapid sentence: Regroups into readable lines without dropping words
    long_words = (
        Word("ئەم", 1000, 1200, 0.95),
        Word("پڕۆژەیە", 1250, 1600, 0.95),
        Word("یەکێکە", 1650, 2000, 0.95),
        Word("لە", 2050, 2200, 0.95),
        Word("گرنگترین", 2250, 2800, 0.95),
        Word("هەنگاوەکانی", 2850, 3500, 0.95),
        Word("گەشەپێدانی", 3550, 4200, 0.95),
        Word("کەرتی", 4250, 4600, 0.95),
        Word("ئابووری", 4650, 5200, 0.95),
        Word("لە", 5250, 5400, 0.95),
        Word("کوردستاندا", 5450, 6200, 0.95),
    )
    plan_long = plan_caption_layout(long_words, protected_regions=(), max_chars_per_line=20)
    assert plan_long.status == "approved"
    assert plan_long.total_cues > 1  # Regrouped into multiple cues
    # Ensure every single word is preserved in exact order
    assert plan_long.canonical_text == " ".join(w.w for w in long_words)

    # 5. Unresolvable visual conflict: Both TOP and BOTTOM blocked
    top_blocked = ProtectedContentRegion(
        region_id="prot_top_banner",
        kind=ProtectedRegionKind.GRAPHIC_OR_CHART,
        box=(0.05, 0.05, 0.95, 0.30),
    )
    bottom_blocked = ProtectedContentRegion(
        region_id="prot_bottom_demo",
        kind=ProtectedRegionKind.DEMONSTRATION,
        box=(0.05, 0.65, 0.95, 0.95),
    )
    mid_blocked = ProtectedContentRegion(
        region_id="prot_mid_face",
        kind=ProtectedRegionKind.SPEAKER_FACE,
        box=(0.10, 0.25, 0.90, 0.50),
    )
    plan_conflict = plan_caption_layout(
        words,
        protected_regions=(top_blocked, bottom_blocked, mid_blocked),
    )
    # Refuses to silently obscure essential content
    assert plan_conflict.status == "needs_review"
    assert len(plan_conflict.unresolvable_conflicts) > 0


def test_caption_layout_models_and_errors() -> None:
    """Validate CaptionLayoutCue data model and empty words error handling."""
    with pytest.raises(CaptionLayoutError, match="empty word sequence"):
        plan_caption_layout((), ())

    cue = CaptionLayoutCue(
        cue_id="c1",
        start_ms=1000,
        end_ms=2500,
        words=(Word("سڵاو", 1000, 2500, 0.99),),
        text="سڵاو",
        placement=CaptionPlacement.BOTTOM,
        box=(0.05, 0.72, 0.95, 0.92),
    )
    assert cue.duration_ms == 1500
    cue_dict = cue.to_dict()
    assert cue_dict["placement"] == "bottom"


def test_caption_layout_protects_table_objects_teaser_label_and_time_scoped_faces() -> None:
    """D5 AC3. TABLE_OBJECT, SOURCE_ON_SCREEN_TEXT, and timed SPEAKER_FACE trigger TOP cleanly."""
    from hawedit.caption_layout import (
        BOTTOM_BAND_BOX,
        caption_layout_to_avoidance_intervals,
    )

    assert BOTTOM_BAND_BOX == (0.05, 0.70, 0.95, 0.80)
    # 9 words -> 3 popups across 0..6s
    spoken = (
        Word("یەکەم", 0, 500, 0.98),
        Word("بەش", 500, 1000, 0.98),
        Word("تەواوە.", 1000, 1500, 0.98),
        Word("دووەم", 2000, 2600, 0.98),
        Word("بەش", 2600, 3200, 0.98),
        Word("لێرەیە.", 3200, 3800, 0.98),
        Word("سێیەم", 4200, 4800, 0.98),
        Word("بەش", 4800, 5400, 0.98),
        Word("ئارامە.", 5400, 6000, 0.98),
    )
    table_reg = ProtectedContentRegion(
        region_id="table_mid_shot",
        kind=ProtectedRegionKind.TABLE_OBJECT,
        box=(0.05, 0.60, 0.95, 0.92),
        start_ms=2000,
        end_ms=3900,
    )
    teaser_reg = ProtectedContentRegion(
        region_id="teaser_banner_start",
        kind=ProtectedRegionKind.SOURCE_ON_SCREEN_TEXT,
        box=(0.06, 0.72, 0.94, 0.88),
        start_ms=0,
        end_ms=1600,
    )
    plan = plan_caption_layout(spoken, (teaser_reg, table_reg), max_words_per_event=3)
    assert len(plan.cues) == 3
    assert plan.cues[0].placement == CaptionPlacement.TOP
    assert plan.cues[1].placement == CaptionPlacement.TOP
    assert plan.cues[2].placement == CaptionPlacement.BOTTOM
    assert plan.canonical_text == " ".join(w.w for w in spoken)

    intervals = caption_layout_to_avoidance_intervals(plan)
    assert len(intervals) >= 1
    assert intervals[0][0] == 0 and intervals[-1][1] == 3800


def test_captions_avoid_detected_teaser_pill_and_table_regions_in_rendered_frames(
    tmp_path: Path,
) -> None:
    """D5 AC4. End-to-end visual region probe relocates captions out of bottom pill/table bands."""
    import subprocess

    import cv2
    import numpy as np

    from hawedit.caption_layout import (
        caption_layout_to_avoidance_intervals,
        detect_protected_visual_regions,
    )
    from hawedit.captions import (
        POPUP_MAX_CHARS,
        POPUP_MAX_WIDTH_PX,
        VIRAL_FONT_SIZE,
        VIRAL_THEME,
        CaptionStyle,
        build_ass,
        find_ffmpeg,
        subtitle_filter,
    )
    from hawedit.sentences import Sentence

    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        pytest.skip("ffmpeg required")

    # Synthetic 6s 1280x720 video (matches 16:9->9:16 crop geometry):
    # - 0..2s: burned-in dark-blue lower teaser pill at y=72%..84%
    # - 2..4s: studio table horizontal foreground lines across y=65%..88%
    # - 4..6s: clean dark studio frame
    vid = tmp_path / "scenes.mp4"
    vw, vh = 640, 360
    fourcc = cv2.VideoWriter.fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(vid), fourcc, 10.0, (vw, vh))
    assert writer.isOpened()
    for f_idx in range(60):
        frame = np.full((vh, vw, 3), 24, dtype=np.uint8)
        if f_idx < 20:
            # Saturated dark-blue teaser banner in lower band inside center 9:16 crop
            cv2.rectangle(frame, (225, int(0.71 * vh)), (415, int(0.84 * vh)), (185, 30, 15), -1)
        elif f_idx < 40:
            # Dense horizontal table edges and laptop highlights across lower band
            for row_y in range(int(0.62 * vh), int(0.89 * vh), 7):
                val = 220 if (row_y % 14 == 0) else 60
                cv2.line(frame, (220, row_y), (420, row_y), (val, val, val), 2)
        writer.write(frame)
    writer.release()

    regions = detect_protected_visual_regions(
        vid,
        0,
        6000,
        source_dimensions=(vw, vh),
        sample_step_ms=500,
    )
    kinds = {r.kind for r in regions}
    assert ProtectedRegionKind.SOURCE_ON_SCREEN_TEXT in kinds
    assert ProtectedRegionKind.TABLE_OBJECT in kinds

    s1 = Sentence(
        words=(Word("بڕگەی", 200, 900, 0.95), Word("یەکەم.", 900, 1700, 0.95)), complete=True
    )
    s2 = Sentence(
        words=(Word("بڕگەی", 2200, 2900, 0.95), Word("دووەم.", 2900, 3700, 0.95)), complete=True
    )
    s3 = Sentence(
        words=(Word("بڕگەی", 4200, 4900, 0.95), Word("سێیەم.", 4900, 5700, 0.95)), complete=True
    )
    words_all = tuple(w for s in (s1, s2, s3) for w in s.words)

    plan = plan_caption_layout(
        words_all,
        regions,
        max_chars_per_line=POPUP_MAX_CHARS,
        max_line_width_px=POPUP_MAX_WIDTH_PX,
        max_words_per_event=3,
    )
    intervals = caption_layout_to_avoidance_intervals(plan)
    ass = build_ass(
        (s1, s2, s3),
        theme=VIRAL_THEME,
        font_size=VIRAL_FONT_SIZE,
        style=CaptionStyle.WORD_HIGHLIGHT,
        max_chars_per_line=POPUP_MAX_CHARS,
        max_words_per_event=3,
        max_popup_width_px=POPUP_MAX_WIDTH_PX,
        face_intervals=intervals,
        clip_in_ms=0,
        clip_duration_ms=6000,
    )
    ass_p = tmp_path / "avoid.ass"
    ass_p.write_text(ass, encoding="utf-8")

    # Verify rendered pixels: at 1.0s (teaser pill) & 3.0s (table) captions sit at TOP (y < 600);
    # at 5.0s (clean) caption sits in lower-middle safe zone (y > 1200).
    for ts, expect_top in ((1.0, True), (3.0, True), (5.0, False)):
        out_png = tmp_path / f"chk_{ts:.0f}.png"
        vf = (
            f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            f"{subtitle_filter(ass_p, Path('assets/fonts'))}"
        )
        subprocess.run(
            [
                str(ffmpeg),
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(vid),
                "-vf",
                vf,
                "-ss",
                f"{ts:.2f}",
                "-frames:v",
                "1",
                "-y",
                str(out_png),
            ],
            check=True,
            capture_output=True,
            timeout=30.0,
        )
        im = cv2.imread(str(out_png))
        assert im is not None
        ink_mask = (im[:, :, 2] > 180) & (im[:, :, 1] > 150)
        ys, _ = ink_mask.nonzero()
        assert ys.size > 0, f"no caption ink at t={ts}"
        mean_y = float(ys.mean())
        if expect_top:
            assert mean_y < 600, (
                f"at t={ts} caption overlapped lower protected zone: mean_y={mean_y:.1f}"
            )
        else:
            assert mean_y > 1200, (
                f"at t={ts} clear frame stayed at top unnecessarily: mean_y={mean_y:.1f}"
            )
