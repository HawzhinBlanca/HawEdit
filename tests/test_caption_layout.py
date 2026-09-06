"""Tests for content-aware caption layout avoiding essential visual regions (VE-10)."""

from __future__ import annotations

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
