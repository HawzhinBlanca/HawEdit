"""Tests for bounded iterative visual defect repair (VE-12)."""

from __future__ import annotations

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
    RenderDefect,
    RenderedSequenceContext,
    inspect_rendered_sequence,
)
from hawedit.shot_plan import (
    PlannedShot,
    ShotEditorialPurpose,
    ShotLayoutStrategy,
)
from hawedit.transcripts import Word
from hawedit.visual_repair import (
    IllegalTransformationError,
    RepairBudget,
    RepairProposal,
    RepairStatus,
    assert_canonical_speech_preserved,
    bounded_visual_repair,
)


def test_visual_repair_is_bounded_and_cannot_change_meaning_or_approve_itself() -> None:
    """VE-12: Repair allows only approved changes, cannot change meaning, and cannot approve itself.

    WHEN a repair is proposed, THE system SHALL allow only approved transformations,
    invalidate prior review, enforce cumulative iteration/cost limits and stop on
    non-improvement or oscillation.
    """
    duration_ms = 30000
    words = (
        Word("ئابووری", 1000, 2000, 0.99),
        Word("کوردستان", 2000, 3000, 0.98),
        Word("گەشە", 3000, 4000, 0.97),
        Word("دەکات", 4000, 5000, 0.99),
    )

    # 1. Defect A: Misidentified speaker (focuses on listener while active speaker speaks)
    shot_damaged = PlannedShot(
        shot_id="shot_01",
        source_in_ms=5000,
        source_out_ms=25000,
        output_in_ms=0,
        output_out_ms=20000,
        editorial_purpose=ShotEditorialPurpose(
            reason="Active speaker discussing economy",
            focal_subject="listener",  # Defect!
        ),
        layout_strategy=ShotLayoutStrategy.HOLD,
        supporting_evidence_ids=("ev_01",),
    )

    # 2. Defect B: Caption cue colliding with essential visual chart
    cue_colliding = CaptionLayoutCue(
        cue_id="cue_01",
        start_ms=1000,
        end_ms=4000,
        words=words[:3],
        text="ئابووری کوردستان گەشە",
        placement=CaptionPlacement.BOTTOM,
        box=(0.05, 0.72, 0.95, 0.92),
        colliding_regions=("reg_chart_market",),
    )
    caption_plan_colliding = CaptionLayoutPlan(
        cues=(cue_colliding,),
        total_cues=1,
        repositioned_to_top_count=0,
        unresolvable_conflicts=("reg_chart_market",),
        canonical_text="ئابووری کوردستان گەشە",
        status="needs_review",
    )

    sequence_damaged = RenderedSequenceContext(
        render_path="work/renders/candidate_01.mp4",
        duration_ms=duration_ms,
        planned_shots=(shot_damaged,),
        caption_plan=caption_plan_colliding,
        landing_beat_ms=28000,
    )

    initial_critique = inspect_rendered_sequence(sequence_damaged)
    assert len(initial_critique.critical_defects) == 2

    # 3. Successful bounded repair within default 2 iterations
    proposal = bounded_visual_repair(
        sequence=sequence_damaged,
        critique=initial_critique,
        budget=RepairBudget(max_iterations=2),
        canonical_words=words[:3],
    )

    assert proposal.status == RepairStatus.REPAIRED
    assert len(proposal.history) == 2
    assert len(proposal.remaining_defects) == 0

    # Invariant: Prior review is invalidated and repair CANNOT self-approve
    assert proposal.prior_review_invalidated is True
    assert proposal.is_approved is False

    # 4. Invariant: Repair cannot approve itself
    with pytest.raises(IllegalTransformationError, match="cannot self-approve"):
        RepairProposal(
            proposal_id="prop_invalid_self_approval",
            candidate_id="cand_01",
            repaired_sequence=proposal.repaired_sequence,
            status=RepairStatus.REPAIRED,
            prior_review_invalidated=True,
            is_approved=True,  # Prohibited!
            history=proposal.history,
            remaining_defects=(),
        )

    # 5. Invariant: Repair must invalidate prior review
    with pytest.raises(IllegalTransformationError, match="must invalidate earlier"):
        RepairProposal(
            proposal_id="prop_invalid_prior_review",
            candidate_id="cand_01",
            repaired_sequence=proposal.repaired_sequence,
            status=RepairStatus.REPAIRED,
            prior_review_invalidated=False,  # Prohibited!
            is_approved=False,
            history=proposal.history,
            remaining_defects=(),
        )

    # 6. Invariant #1: Repair cannot alter canonical Kurdish speech text
    with pytest.raises(IllegalTransformationError, match="Canonical word altered"):
        bounded_visual_repair(
            sequence=sequence_damaged,
            critique=initial_critique,
            canonical_words=words[:3],
            attempt_illegal_text_alteration=True,
        )

    # 7. Stop rule: Budget exhaustion when defects exceed allowed iterations
    tight_budget_prop = bounded_visual_repair(
        sequence=sequence_damaged,
        critique=initial_critique,
        budget=RepairBudget(max_iterations=1),  # Only 1 iteration for 2 defects
    )
    assert tight_budget_prop.status == RepairStatus.BUDGET_EXHAUSTED
    assert len(tight_budget_prop.history) == 1
    assert len(tight_budget_prop.remaining_defects) > 0

    # 8. Stop rule: Oscillation detection
    oscillating_prop = bounded_visual_repair(
        sequence=sequence_damaged,
        critique=initial_critique,
        budget=RepairBudget(max_iterations=4),
        force_oscillation=True,
    )
    assert oscillating_prop.status == RepairStatus.OSCILLATION_DETECTED

    # 9. Stop rule: Escalation to human on unfixable defect
    unfixable_defect = RenderDefect(
        defect_id="def_unfixable",
        timestamp_ms=5000,
        end_timestamp_ms=10000,
        severity=DefectSeverity.CRITICAL,
        defect_kind=DefectKind.UNFOLLOWABLE_CONTEXT,
        observation="Missing outside context cannot be repaired automatically",
        source_reference="context",
        permitted_repair=PermittedRepair.NONE,
    )
    unfixable_critique = CritiqueInspectionResult(
        inspection_id="crit_unfixable",
        render_path="work/renders/unfixable.mp4",
        duration_ms=duration_ms,
        coverage_ratio=1.0,
        windows=(),
        defects=(unfixable_defect,),
        is_all_clear=False,
        all_clear_refused=True,
    )
    escalated_prop = bounded_visual_repair(
        sequence=sequence_damaged,
        critique=unfixable_critique,
    )
    assert escalated_prop.status == RepairStatus.ESCALATE_TO_HUMAN


def test_canonical_speech_preserved_validator() -> None:
    """VE-12: assert_canonical_speech_preserved catches word deletion and word mutation."""
    original = (Word("سڵاو", 0, 500, 0.99), Word("هاوڕێ", 500, 1000, 0.99))
    shortened = (Word("سڵاو", 0, 500, 0.99),)
    altered = (Word("سڵاو", 0, 500, 0.99), Word("خەڵک", 500, 1000, 0.99))

    with pytest.raises(IllegalTransformationError, match="Word count mismatch"):
        assert_canonical_speech_preserved(original, shortened)

    with pytest.raises(IllegalTransformationError, match="Canonical word altered"):
        assert_canonical_speech_preserved(original, altered)

    # Identical words pass
    assert_canonical_speech_preserved(original, original)
