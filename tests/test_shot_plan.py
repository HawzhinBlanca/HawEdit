"""Tests for shot-by-shot visual planning with editorial purpose and protected regions (VE-07)."""

from __future__ import annotations

import pytest

from hawedit.shot_plan import (
    PlannedShot,
    ProtectedContentRegion,
    ProtectedRegionKind,
    ShotEditorialPurpose,
    ShotLayoutStrategy,
    ShotPlanError,
    ShotVisualPlan,
    build_shot_plan,
)


def test_every_planned_shot_has_source_evidence_and_protected_regions() -> None:
    """VE-07: Every planned shot requires editorial purpose, evidence, and protected regions."""
    # 1. Missing supporting source evidence is strictly rejected
    with pytest.raises(ShotPlanError, match="requires at least one supporting source evidence ID"):
        PlannedShot(
            shot_id="shot_01",
            source_in_ms=1000,
            source_out_ms=5000,
            output_in_ms=0,
            output_out_ms=4000,
            editorial_purpose=ShotEditorialPurpose(
                reason="Focus on speaker explaining key statistic",
                focal_subject="speaker_face_01",
            ),
            layout_strategy=ShotLayoutStrategy.CROP,
            supporting_evidence_ids=(),  # FORBIDDEN: no evidence
        )

    # 2. Missing explicit editorial reason is strictly rejected
    with pytest.raises(ShotPlanError, match="requires an explicit, non-empty editorial reason"):
        ShotEditorialPurpose(
            reason="",  # FORBIDDEN: empty reason
            focal_subject="speaker_face_01",
        )

    # 3. Missing focal subject is strictly rejected
    with pytest.raises(ShotPlanError, match="requires an explicit, non-empty focal subject"):
        ShotEditorialPurpose(
            reason="Cadence timer elapsed",
            focal_subject="",  # FORBIDDEN: empty focal subject
        )

    # 4. Duration mismatch between source interval and output interval is refused
    with pytest.raises(ShotPlanError, match="source duration .* does not match output duration"):
        PlannedShot(
            shot_id="shot_mismatch",
            source_in_ms=1000,
            source_out_ms=6000,  # 5000ms
            output_in_ms=0,
            output_out_ms=4000,  # 4000ms
            editorial_purpose=ShotEditorialPurpose(
                reason="Focus on speaker",
                focal_subject="speaker_01",
            ),
            layout_strategy=ShotLayoutStrategy.CROP,
            supporting_evidence_ids=("vis_event_01",),
        )

    # 5. Valid shot with speaker face protected region
    speaker_region = ProtectedContentRegion(
        region_id="prot_speaker_01",
        kind=ProtectedRegionKind.SPEAKER_FACE,
        box=(0.35, 0.15, 0.65, 0.45),
        importance=0.95,
        description="Active speaker eye line and mouth region",
    )
    shot_1 = PlannedShot(
        shot_id="shot_01",
        source_in_ms=2000,
        source_out_ms=6000,
        output_in_ms=0,
        output_out_ms=4000,
        editorial_purpose=ShotEditorialPurpose(
            reason="Focus on guest answering opening question",
            focal_subject="speaker_guest",
            priority_over_face=False,
        ),
        layout_strategy=ShotLayoutStrategy.FOLLOW,
        supporting_evidence_ids=("vis_event_01", "sent_01"),
        protected_regions=(speaker_region,),
    )
    assert shot_1.duration_ms == 4000
    assert shot_1.has_protected_kind(ProtectedRegionKind.SPEAKER_FACE) is True
    assert shot_1.has_protected_kind(ProtectedRegionKind.DEMONSTRATION) is False

    # 6. Priority over face: must include demonstration or chart region
    demo_region = ProtectedContentRegion(
        region_id="prot_demo_01",
        kind=ProtectedRegionKind.DEMONSTRATION,
        box=(0.20, 0.40, 0.80, 0.85),
        importance=1.0,
        description="Hand demonstrating device mechanism",
    )
    shot_2 = PlannedShot(
        shot_id="shot_02",
        source_in_ms=6000,
        source_out_ms=10000,
        output_in_ms=4000,
        output_out_ms=8000,
        editorial_purpose=ShotEditorialPurpose(
            reason="Preserve prototype demonstration during explanation",
            focal_subject="device_demonstration",
            priority_over_face=True,
        ),
        layout_strategy=ShotLayoutStrategy.HOLD,
        supporting_evidence_ids=("vis_event_demo_02", "sent_02"),
        protected_regions=(demo_region,),
    )
    assert shot_2.has_protected_kind(ProtectedRegionKind.DEMONSTRATION) is True

    # 7. Priority over face WITHOUT demonstration/chart region is rejected during assert_valid()
    invalid_priority_shot = PlannedShot(
        shot_id="shot_bad_prio",
        source_in_ms=10000,
        source_out_ms=13000,
        output_in_ms=8000,
        output_out_ms=11000,
        editorial_purpose=ShotEditorialPurpose(
            reason="Claimed demonstration but no demonstration region protected",
            focal_subject="fake_demo",
            priority_over_face=True,
        ),
        layout_strategy=ShotLayoutStrategy.CROP,
        supporting_evidence_ids=("vis_event_03",),
        protected_regions=(speaker_region,),  # only face, no demo or chart!
    )
    with pytest.raises(
        ShotPlanError, match="claims priority_over_face but contains no demonstration"
    ):
        build_shot_plan(
            clip_id="clip_bad",
            media_id="interview_01",
            shots=[shot_1, shot_2, invalid_priority_shot],
        )

    # 8. Output timeline discontinuity (gap between shots) is refused
    shot_with_gap = PlannedShot(
        shot_id="shot_gap",
        source_in_ms=10000,
        source_out_ms=13000,
        output_in_ms=9000,  # GAP: shot_2 ends at 8000, this starts at 9000!
        output_out_ms=12000,
        editorial_purpose=ShotEditorialPurpose(
            reason="Reaction shot",
            focal_subject="host_reaction",
        ),
        layout_strategy=ShotLayoutStrategy.HOLD,
        supporting_evidence_ids=("vis_event_03",),
    )
    with pytest.raises(ShotPlanError, match="does not match expected contiguous timeline boundary"):
        build_shot_plan(
            clip_id="clip_gap",
            media_id="interview_01",
            shots=[shot_1, shot_2, shot_with_gap],
        )

    # 9. Valid full sequence with diverse layout strategies
    listener_shot = PlannedShot(
        shot_id="shot_03",
        source_in_ms=10000,
        source_out_ms=13000,
        output_in_ms=8000,
        output_out_ms=11000,
        editorial_purpose=ShotEditorialPurpose(
            reason="Host reaction and nod confirming point",
            focal_subject="listener_host",
        ),
        layout_strategy=ShotLayoutStrategy.KEEP_SOURCE,
        supporting_evidence_ids=("vis_event_reaction_01",),
        protected_regions=(
            ProtectedContentRegion(
                region_id="prot_listener_01",
                kind=ProtectedRegionKind.LISTENER_FACE,
                box=(0.10, 0.20, 0.40, 0.50),
            ),
        ),
    )
    plan = build_shot_plan(
        clip_id="clip_valid_01",
        media_id="interview_01",
        shots=[shot_1, shot_2, listener_shot],
    )
    assert plan.total_duration_ms == 11000
    assert plan.shot_count == 3
    assert plan.shot_at_output_ms(2000) == shot_1
    assert plan.shot_at_output_ms(6000) == shot_2
    assert plan.shot_at_output_ms(9500) == listener_shot
    assert plan.shot_at_output_ms(15000) is None

    # 10. Dictionary serialization and round-trip fidelity
    plan_dict = plan.to_dict()
    restored = ShotVisualPlan.from_dict(plan_dict)
    assert restored.clip_id == plan.clip_id
    assert restored.media_id == plan.media_id
    assert restored.shot_count == plan.shot_count
    assert restored.shots == plan.shots

    # 11. All ShotLayoutStrategy values are valid enum instances
    for strategy in ShotLayoutStrategy:
        assert isinstance(strategy.value, str)
