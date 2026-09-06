"""Tests for whole-shot composition and jitter-free camera path stabilization (VE-08)."""

from __future__ import annotations

import pytest

from hawedit.reframe import FocusPoint
from hawedit.shot_composition import (
    CropBox,
    CropKeyframe,
    TemporalGroundingError,
    compose_shot,
    measure_crop_jitter,
)
from hawedit.shot_plan import (
    PlannedShot,
    ProtectedContentRegion,
    ProtectedRegionKind,
    ShotEditorialPurpose,
    ShotLayoutStrategy,
)


def test_shot_composition_preserves_required_content_without_crop_jitter() -> None:
    """VE-08: Whole-shot composition preserves required content without crop jitter.

    WHEN crop/layout decisions span a shot, THE system SHALL preserve required visible content
    with an approved stable camera path or choose an explicit source-preserving alternative.
    """
    # 1. Stationary subject with detector noise/wobble: Hysteresis holds camera still without jitter
    speaker_face = ProtectedContentRegion(
        region_id="prot_speaker_face_01",
        kind=ProtectedRegionKind.SPEAKER_FACE,
        box=(0.42, 0.20, 0.58, 0.45),
        importance=1.0,
        description="Active speaker face",
    )
    stationary_shot = PlannedShot(
        shot_id="shot_stationary",
        source_in_ms=2000,
        source_out_ms=8000,
        output_in_ms=0,
        output_out_ms=6000,
        editorial_purpose=ShotEditorialPurpose(
            reason="Guest explains key concept calmly",
            focal_subject="speaker_guest",
        ),
        layout_strategy=ShotLayoutStrategy.CROP,
        supporting_evidence_ids=("vis_ev_01", "trans_01"),
        protected_regions=(speaker_face,),
    )

    # Simulate noisy raw detections oscillating back and forth (+/- 15 pixels on 1920w => +/- 0.008)
    noisy_observations: list[FocusPoint] = [
        FocusPoint(at_ms=2000, center_x=960, center_y=350, face_height=200),
        FocusPoint(at_ms=2500, center_x=975, center_y=352, face_height=200),
        FocusPoint(at_ms=3000, center_x=948, center_y=348, face_height=200),
        FocusPoint(at_ms=3500, center_x=970, center_y=355, face_height=200),
        FocusPoint(at_ms=4000, center_x=955, center_y=350, face_height=200),
        FocusPoint(at_ms=5000, center_x=965, center_y=349, face_height=200),
        FocusPoint(at_ms=6000, center_x=958, center_y=351, face_height=200),
        FocusPoint(at_ms=7000, center_x=962, center_y=350, face_height=200),
        FocusPoint(at_ms=8000, center_x=960, center_y=350, face_height=200),
    ]

    result = compose_shot(
        stationary_shot,
        noisy_observations,
        source_dimensions=(1920, 1080),
        dead_zone_threshold=0.02,  # 2% width ≈ 38px
    )

    assert result.status == "approved"
    assert result.effective_layout == ShotLayoutStrategy.CROP
    assert "prot_speaker_face_01" in result.preserved_regions
    assert len(result.cutoff_regions) == 0

    # Jitter verification: hysteresis completely eliminated detector wobble
    assert result.jitter_metrics.reversals_x == 0
    assert result.jitter_metrics.reversals_y == 0
    assert result.jitter_metrics.jitter_score == 0.0
    assert result.jitter_metrics.is_jitter_free is True

    # Eyeline and headroom verification: face center in upper third, positive headroom
    assert result.eyeline_ratio > 0.15
    assert result.eyeline_ratio < 0.50
    assert result.headroom_ratio > 0.0

    # 2. Sustained subject movement: smooth transition without restless oscillation
    moving_shot = PlannedShot(
        shot_id="shot_moving",
        source_in_ms=1000,
        source_out_ms=7000,
        output_in_ms=0,
        output_out_ms=6000,
        editorial_purpose=ShotEditorialPurpose(
            reason="Host moves from interview desk to presentation screen",
            focal_subject="host_moving",
        ),
        layout_strategy=ShotLayoutStrategy.FOLLOW,
        supporting_evidence_ids=("vis_ev_02",),
        protected_regions=(
            ProtectedContentRegion(
                region_id="host_face",
                kind=ProtectedRegionKind.SPEAKER_FACE,
                box=(0.30, 0.20, 0.45, 0.45),
            ),
        ),
    )
    moving_observations = [
        FocusPoint(at_ms=1000, center_x=700, center_y=350),  # x ≈ 0.36
        FocusPoint(at_ms=1500, center_x=700, center_y=350),
        FocusPoint(at_ms=2500, center_x=1200, center_y=350),  # sustained shift to x ≈ 0.62
        FocusPoint(at_ms=3200, center_x=1200, center_y=350),
        FocusPoint(at_ms=4000, center_x=1200, center_y=350),
        FocusPoint(at_ms=7000, center_x=1200, center_y=350),
    ]
    result_moving = compose_shot(moving_shot, moving_observations)
    assert result_moving.status == "approved"
    assert result_moving.jitter_metrics.reversals_x == 0  # Monotonic pan, no back-and-forth wobble
    assert result_moving.jitter_metrics.is_jitter_free is True

    # 3. Wide demonstration that cannot fit inside a 9:16 crop: System elevates to KEEP_SOURCE
    wide_demo_region = ProtectedContentRegion(
        region_id="wide_circuit_demo",
        kind=ProtectedRegionKind.DEMONSTRATION,
        box=(0.10, 0.35, 0.90, 0.85),  # 80% width: impossible to fit in 31.6% 9:16 crop
        importance=1.0,
        description="Broad mechanical apparatus demonstration",
    )
    demo_shot = PlannedShot(
        shot_id="shot_demo",
        source_in_ms=3000,
        source_out_ms=8000,
        output_in_ms=0,
        output_out_ms=5000,
        editorial_purpose=ShotEditorialPurpose(
            reason="Demonstrating apparatus functioning",
            focal_subject="apparatus",
            priority_over_face=True,
        ),
        layout_strategy=ShotLayoutStrategy.CROP,  # Requested crop, but impossible
        supporting_evidence_ids=("vis_ev_03",),
        protected_regions=(wide_demo_region,),
    )
    result_demo = compose_shot(demo_shot, ())
    assert result_demo.status == "elevated_to_source_preserving"
    assert result_demo.effective_layout == ShotLayoutStrategy.KEEP_SOURCE
    assert "wide_circuit_demo" in result_demo.preserved_regions
    assert len(result_demo.cutoff_regions) == 0

    # 4. Two separated speakers in conversational exchange: Elevates to TWO_PERSON_LAYOUT
    host_face = ProtectedContentRegion(
        region_id="face_host",
        kind=ProtectedRegionKind.SPEAKER_FACE,
        box=(0.10, 0.20, 0.25, 0.45),
    )
    guest_face = ProtectedContentRegion(
        region_id="face_guest",
        kind=ProtectedRegionKind.LISTENER_FACE,
        box=(0.75, 0.20, 0.90, 0.45),
    )
    two_shot = PlannedShot(
        shot_id="shot_banter",
        source_in_ms=4000,
        source_out_ms=9000,
        output_in_ms=0,
        output_out_ms=5000,
        editorial_purpose=ShotEditorialPurpose(
            reason="Rapid banter between host and guest",
            focal_subject="host_and_guest",
        ),
        layout_strategy=ShotLayoutStrategy.CROP,
        supporting_evidence_ids=("vis_ev_04",),
        protected_regions=(host_face, guest_face),
    )
    result_two_shot = compose_shot(two_shot, ())
    assert result_two_shot.status == "elevated_to_source_preserving"
    assert result_two_shot.effective_layout == ShotLayoutStrategy.TWO_PERSON_LAYOUT
    assert "face_host" in result_two_shot.preserved_regions
    assert "face_guest" in result_two_shot.preserved_regions

    # 5. Temporal grounding enforcement: observations outside source interval are strictly refused
    with pytest.raises(TemporalGroundingError, match="temporal fabrication forbidden"):
        compose_shot(
            stationary_shot,  # interval: [2000, 8000]
            [FocusPoint(at_ms=45000, center_x=960, center_y=350)],  # Far outside interval!
        )


def test_crop_box_and_jitter_metrics_models() -> None:
    """Validate CropBox geometry, containment, coordinate math, and jitter computation."""
    box = CropBox(0.25, 0.0, 0.75, 1.0)
    assert box.width == 0.50
    assert box.height == 1.0
    assert box.center_x == 0.50
    assert box.center_y == 0.50

    px = box.to_pixels(1920, 1080)
    assert px == (480, 0, 960, 1080)
    assert px[2] % 2 == 0
    assert px[3] % 2 == 0

    # Containment
    inside_box = (0.30, 0.20, 0.70, 0.80)
    outside_box = (0.10, 0.20, 0.60, 0.80)
    assert box.contains(inside_box) is True
    assert box.contains(outside_box) is False
    assert box.intersection_ratio(inside_box) == 1.0
    assert box.intersection_ratio(outside_box) > 0.0
    assert box.intersection_ratio(outside_box) < 1.0

    # Serialization round-trip
    box_dict = box.to_dict()
    restored_box = CropBox.from_dict(box_dict)
    assert restored_box == box

    # Jitter measurement on oscillating keyframes
    wobbly_keyframes = [
        CropKeyframe(0, CropBox(0.30, 0.0, 0.60, 1.0)),
        CropKeyframe(500, CropBox(0.35, 0.0, 0.65, 1.0)),
        CropKeyframe(1000, CropBox(0.28, 0.0, 0.58, 1.0)),
        CropKeyframe(1500, CropBox(0.36, 0.0, 0.66, 1.0)),
        CropKeyframe(2000, CropBox(0.29, 0.0, 0.59, 1.0)),
    ]
    wobbly_metrics = measure_crop_jitter(wobbly_keyframes)
    assert wobbly_metrics.reversals_x >= 3
    assert wobbly_metrics.is_jitter_free is False
    assert wobbly_metrics.jitter_score > 0.05
