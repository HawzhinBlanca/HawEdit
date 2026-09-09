"""Tests for post-render sequence critique and grounded defect reporting (VE-11)."""

from __future__ import annotations

from pathlib import Path

import pytest

from hawedit.caption_layout import (
    CaptionLayoutCue,
    CaptionLayoutPlan,
    CaptionPlacement,
)
from hawedit.render_critic import (
    CritiqueInspectionResult,
    DefectKind,
    DefectSeverity,
    PermittedRepair,
    RenderedSequenceContext,
    TemporalCritiqueWindow,
    UnsupportedAllClearError,
    generate_critique_windows,
    inspect_rendered_sequence,
)
from hawedit.shot_plan import (
    PlannedShot,
    ProtectedContentRegion,
    ProtectedRegionKind,
    ShotEditorialPurpose,
    ShotLayoutStrategy,
)
from hawedit.transcripts import Word


def test_render_critic_uses_output_sequence_and_reports_grounded_defects() -> None:
    """VE-11: Critic inspects rendered sequence, reports grounded defects, and refuses all-clear.

    WHEN a private render is ready, THE system SHALL inspect its actual temporal output
    and source context, report timestamped grounded defects and refuse unsupported all-clear claims.
    """
    duration_ms = 35000  # 35 second social reel

    # 1. Verify temporal windows cover entire output with dense inspection at
    # hook, transitions, landing
    shot_transitions = [7000, 15000, 25000]
    critique_windows = generate_critique_windows(
        duration_ms=duration_ms,
        shot_transitions=shot_transitions,
        fps=30.0,
    )
    assert len(critique_windows) > 10

    # Verify dense inspection at opening hook (0..3s)
    hook_windows = [w for w in critique_windows if "hook" in w.window_kind]
    assert len(hook_windows) >= 2

    # Verify dense inspection at shot transitions
    trans_windows = [w for w in critique_windows if w.window_kind == "transition"]
    assert len(trans_windows) == len(shot_transitions)

    # Verify dense inspection at landing beat (last 3s)
    landing_windows = [w for w in critique_windows if "landing" in w.window_kind]
    assert len(landing_windows) >= 1

    # Invariant: Temporal motion cannot be judged from isolated stills
    with pytest.raises(ValueError, match="temporal motion cannot be judged from isolated stills"):
        TemporalCritiqueWindow(
            window_id="win_invalid_still",
            start_ms=1000,
            end_ms=2000,
            window_kind="test",
            has_temporal_motion=True,
            frame_count=1,  # Isolated single still claiming motion
        )

    # 2. Defect Scenario A: Misidentified speaker (shot focuses on listener while speaker talks)
    shot_misidentified = PlannedShot(
        shot_id="shot_01",
        source_in_ms=10000,
        source_out_ms=16000,
        output_in_ms=7000,
        output_out_ms=13000,
        editorial_purpose=ShotEditorialPurpose(
            reason="Active speaker elaborating on Kurdish economy",
            focal_subject="listener",  # Defect: focal subject misidentified as listener!
        ),
        layout_strategy=ShotLayoutStrategy.HOLD,
        supporting_evidence_ids=("ev_speaker_01",),
    )

    # 3. Defect Scenario B: Lost demonstration or chart (essential graphic cropped out)
    chart_region = ProtectedContentRegion(
        region_id="reg_chart_market",
        kind=ProtectedRegionKind.GRAPHIC_OR_CHART,
        box=(0.05, 0.20, 0.45, 0.60),  # Far-left chart box outside 9:16 portrait crop
        importance=1.0,
        description="Market share bar chart",
    )
    shot_lost_chart = PlannedShot(
        shot_id="shot_02",
        source_in_ms=18000,
        source_out_ms=26000,
        output_in_ms=15000,
        output_out_ms=23000,
        editorial_purpose=ShotEditorialPurpose(
            reason="Demonstration of economic statistics",
            focal_subject="chart",
            priority_over_face=True,
        ),
        layout_strategy=ShotLayoutStrategy.CROP,  # Crop strategy loses far-left chart
        supporting_evidence_ids=("ev_chart_01",),
        protected_regions=(chart_region,),
    )

    # 4. Defect Scenario C: Caption obscuration (caption placed over essential visual region)
    words = (Word("ئەمە", 0, 500, 0.99), Word("نەخشەیە", 500, 1000, 0.98))
    cue_colliding = CaptionLayoutCue(
        cue_id="cue_obs_01",
        start_ms=15500,
        end_ms=17000,
        words=words,
        text="ئەمە نەخشەیە",
        placement=CaptionPlacement.BOTTOM,
        box=(0.05, 0.72, 0.95, 0.92),
        colliding_regions=("reg_chart_market",),
    )
    caption_plan_obscured = CaptionLayoutPlan(
        cues=(cue_colliding,),
        total_cues=1,
        repositioned_to_top_count=0,
        unresolvable_conflicts=("reg_chart_market",),
        canonical_text="ئەمە نەخشەیە",
        status="needs_review",
    )

    sequence_damaged = RenderedSequenceContext(
        render_path="work/renders/clip_damaged.mp4",
        duration_ms=duration_ms,
        fps=30.0,
        width=1080,
        height=1920,
        planned_shots=(shot_misidentified, shot_lost_chart),
        caption_plan=caption_plan_obscured,
        setup_boundary_ms=12000,  # Required setup ends at 12000 ms, but shot starts at 10000 source
        landing_beat_ms=37000,  # Required landing beat at 37000 ms, but duration is only 35000 ms!
    )

    # Inspect the damaged rendered sequence
    result: CritiqueInspectionResult = inspect_rendered_sequence(
        sequence=sequence_damaged,
        critique_windows=critique_windows,
        claim_all_clear=True,  # Caller audaciously claims all-clear
    )

    # The critic MUST report grounded defects with timestamps and permitted repairs
    assert len(result.defects) >= 4
    assert result.has_critical_defects

    # Verify Grounded Defect 1: Misidentified speaker
    d_speaker = next(d for d in result.defects if d.defect_kind == DefectKind.MISIDENTIFIED_SPEAKER)
    assert d_speaker.severity == DefectSeverity.CRITICAL
    assert d_speaker.permitted_repair == PermittedRepair.HOLD_SOURCE_SHOT
    assert d_speaker.timestamp_ms == 7000
    assert "listener" in d_speaker.observation

    # Verify Grounded Defect 2: Lost demonstration / chart
    d_chart = next(
        d for d in result.defects if d.defect_kind == DefectKind.LOST_DEMONSTRATION_OR_CHART
    )
    assert d_chart.severity == DefectSeverity.CRITICAL
    assert d_chart.permitted_repair == PermittedRepair.ADJUST_CROP
    assert "reg_chart_market" in d_chart.source_reference

    # Verify Grounded Defect 3: Caption obscuration
    d_caption = next(d for d in result.defects if d.defect_kind == DefectKind.CAPTION_OBSCURATION)
    assert d_caption.severity == DefectSeverity.CRITICAL
    assert d_caption.permitted_repair == PermittedRepair.REPOSITION_CAPTIONS
    assert d_caption.timestamp_ms == 15500

    # Verify Grounded Defect 4: Truncated landing beat
    d_landing = next(
        d for d in result.defects if d.defect_kind == DefectKind.TRUNCATED_LANDING_BEAT
    )
    assert d_landing.severity == DefectSeverity.CRITICAL
    assert d_landing.permitted_repair == PermittedRepair.EXPAND_BOUNDARY

    # Refusal of unsupported all-clear claim
    assert result.all_clear_refused is True
    assert result.is_all_clear is False
    assert result.refusal_reason is not None
    assert "critical defect(s)" in result.refusal_reason

    # Calling assert_verdict_grounded() MUST raise UnsupportedAllClearError
    with pytest.raises(UnsupportedAllClearError, match="All-clear claim refused"):
        result.assert_verdict_grounded()


def test_render_critic_approves_grounded_clean_render() -> None:
    """VE-11: Critic approves clean rendered sequence with complete coverage and zero defects."""
    fixture_path = "tests/fixtures/kurdish-speech-3cuts.mp4"
    duration_ms = 4120

    shot_clean = PlannedShot(
        shot_id="shot_clean_01",
        source_in_ms=0,
        source_out_ms=4120,
        output_in_ms=0,
        output_out_ms=4120,
        editorial_purpose=ShotEditorialPurpose(
            reason="Clean explanation by active speaker",
            focal_subject="speaker",
        ),
        layout_strategy=ShotLayoutStrategy.HOLD,
        supporting_evidence_ids=("ev_01",),
    )

    cue_clean = CaptionLayoutCue(
        cue_id="cue_clean_01",
        start_ms=500,
        end_ms=3500,
        words=(Word("سڵاو", 500, 1500, 0.99), Word("هاوڕێیان", 1500, 3500, 0.99)),
        text="سڵاو هاوڕێیان",
        placement=CaptionPlacement.BOTTOM,
        box=(0.05, 0.72, 0.95, 0.92),
    )
    caption_plan_clean = CaptionLayoutPlan(
        cues=(cue_clean,),
        total_cues=1,
        repositioned_to_top_count=0,
        unresolvable_conflicts=(),
        canonical_text="سڵاو هاوڕێیان",
        status="approved",
    )

    sequence_clean = RenderedSequenceContext(
        render_path=fixture_path,
        duration_ms=duration_ms,
        fps=25.0,
        width=1280,
        height=720,
        planned_shots=(shot_clean,),
        caption_plan=caption_plan_clean,
        landing_beat_ms=3800,
    )

    result = inspect_rendered_sequence(sequence_clean, claim_all_clear=True)

    assert result.is_all_clear is True
    assert result.all_clear_refused is False
    assert len(result.defects) == 0
    assert result.coverage_ratio >= 0.95
    assert result.observed_media is True
    # Does not raise!
    result.assert_verdict_grounded()


def test_render_critic_refuses_when_source_context_missing() -> None:
    """VE-11: Critic refuses all-clear when aligned source context is missing."""
    sequence_no_context = RenderedSequenceContext(
        render_path="tests/fixtures/kurdish-speech-3cuts.mp4",
        duration_ms=4120,
        has_source_context=False,  # Isolated private render without source context
    )

    result = inspect_rendered_sequence(sequence_no_context, claim_all_clear=True)
    assert result.is_all_clear is False
    assert result.all_clear_refused is True
    assert any(d.defect_kind == DefectKind.UNSUPPORTED_CLAIM for d in result.defects)

    with pytest.raises(UnsupportedAllClearError):
        result.assert_verdict_grounded()


def test_render_critic_refuses_nonexistent_video() -> None:
    """CD-02: Missing media path is rejected with DefectKind.MISSING_MEDIA and 0 coverage."""
    sequence_missing = RenderedSequenceContext(
        render_path="work/renders/nonexistent_file_xyz.mp4",
        duration_ms=30000,
    )

    result = inspect_rendered_sequence(sequence_missing, claim_all_clear=True)

    assert result.is_all_clear is False
    assert result.all_clear_refused is True
    assert result.observed_media is False
    assert result.coverage_ratio == 0.0
    assert any(d.defect_kind == DefectKind.MISSING_MEDIA for d in result.defects)
    assert all(not w.is_observed for w in result.windows)

    with pytest.raises(UnsupportedAllClearError, match="rendered media is missing"):
        result.assert_verdict_grounded()


def test_render_critic_refuses_empty_video(tmp_path: Path) -> None:
    """CD-02: 0-byte video is rejected with UNREADABLE_MEDIA and observed_media=False."""
    empty_file = tmp_path / "empty_video.mp4"
    empty_file.touch()

    sequence_empty = RenderedSequenceContext(
        render_path=str(empty_file),
        duration_ms=10000,
    )

    result = inspect_rendered_sequence(sequence_empty, claim_all_clear=True)

    assert result.is_all_clear is False
    assert result.all_clear_refused is True
    assert result.observed_media is False
    assert result.coverage_ratio == 0.0
    assert any(d.defect_kind == DefectKind.UNREADABLE_MEDIA for d in result.defects)

    with pytest.raises(UnsupportedAllClearError):
        result.assert_verdict_grounded()


def test_render_critic_refuses_mismatched_sha256() -> None:
    """CD-02: Changed digest is rejected with DefectKind.CHANGED_MEDIA."""
    sequence_tampered = RenderedSequenceContext(
        render_path="tests/fixtures/kurdish-speech-3cuts.mp4",
        duration_ms=4120,
        expected_sha256="0000000000000000000000000000000000000000000000000000000000000000",
    )

    result = inspect_rendered_sequence(sequence_tampered, claim_all_clear=True)

    assert result.is_all_clear is False
    assert result.all_clear_refused is True
    assert result.observed_media is False
    assert any(d.defect_kind == DefectKind.CHANGED_MEDIA for d in result.defects)


def test_render_critic_excludes_unobserved_windows_from_coverage() -> None:
    """CD-03: Unobserved windows are excluded from coverage_ratio calculation."""
    fixture_path = "tests/fixtures/kurdish-speech-3cuts.mp4"
    duration_ms = 4120

    # Custom critique windows where the second half was NOT observed
    w1 = TemporalCritiqueWindow(
        window_id="win_observed",
        start_ms=0,
        end_ms=2000,
        window_kind="hook",
        has_temporal_motion=True,
        frame_count=50,
        is_observed=True,
    )
    w2 = TemporalCritiqueWindow(
        window_id="win_unobserved",
        start_ms=2000,
        end_ms=4120,
        window_kind="landing",
        has_temporal_motion=True,
        frame_count=50,
        is_observed=False,  # Unobserved window
    )

    sequence = RenderedSequenceContext(
        render_path=fixture_path,
        duration_ms=duration_ms,
        fps=25.0,
    )

    result = inspect_rendered_sequence(
        sequence,
        critique_windows=(w1, w2),
        claim_all_clear=True,
    )

    # Coverage should only be ~2000 / 4120 = ~0.485 (unobserved w2 excluded)
    assert result.coverage_ratio < 0.60
    assert result.all_clear_refused is True
    assert "incomplete temporal coverage" in (result.refusal_reason or "")
