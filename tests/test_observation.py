"""Unit tests for episode visual observation inventory (VE-02 / V02)."""

from __future__ import annotations

import pytest

from hawedit.observation import (
    ObservationBudget,
    ObservationError,
    ObservationInterval,
    ObservationInventory,
    ObservationLevel,
    TargetedEventCandidate,
    VisualEventKind,
    apply_targeted_observation,
    build_observation_inventory,
    plan_targeted_observation,
)

_VALID_SHA = "a" * 64


def test_observation_inventory_exposes_unseen_intervals_and_static_speech() -> None:
    """WHEN an episode is scanned, THE system SHALL inventory observation coverage
    for all source intervals and distinguish sampled/model-inspected/unknown evidence
    without suppressing static verbal moments (VE-02 / V02).
    """
    duration_ms = 60_000
    # Media has cuts at 15s, 35s, 50s.
    # Scanned range only covers 0..50s, so 50s..60s is an unseen tail (UNKNOWN).
    shot_cuts = (15_000, 35_000, 50_000)
    speech_intervals = (
        (2_000, 10_000),  # Active speech with normal motion in shot 0
        (18_000, 32_000),  # Long static talking head in shot 1 (motion = 0.01)
        (37_000, 46_000),  # Active speech in shot 2 (motion = 0.40)
    )
    sampled_frames = (4_000, 8_000)
    model_inspected = ((36_000, 48_000),)
    motion_scores = (0.25, 0.01, 0.40, 0.15)

    inventory = build_observation_inventory(
        media_id="ep01-test",
        source_sha256=_VALID_SHA,
        duration_ms=duration_ms,
        shot_cuts_ms=shot_cuts,
        scanned_range_ms=(0, 50_000),
        speech_intervals=speech_intervals,
        sampled_frame_times_ms=sampled_frames,
        model_inspected_intervals=model_inspected,
        motion_scores_by_shot=motion_scores,
    )

    # 1. Unseen intervals: the uninspected tail (50s..60s) must be truthfully exposed
    unseen = inventory.unseen_intervals()
    assert unseen == ((50_000, 60_000),), f"expected unseen tail, got {unseen}"

    # 2. Static speech: 18s..32s has active speech and motion_score <= 0.05
    static_moments = inventory.static_speech_intervals()
    assert len(static_moments) >= 1
    assert any(
        s.in_ms <= 18_000 and s.out_ms >= 32_000 and s.motion_score == 0.01 for s in static_moments
    )

    # 3. Verbal discovery protection: static speech must not be suppressed
    # If candidate discovery proposed spans including the static speech, passes:
    inventory.assert_static_speech_preserved(candidate_spans=((17_000, 33_000), (36_000, 48_000)))

    # If candidate discovery dropped the static speech moment because of low motion, fails:
    with pytest.raises(ObservationError, match="static speech interval .* was dropped"):
        inventory.assert_static_speech_preserved(
            candidate_spans=((2_000, 10_000), (36_000, 48_000))
        )

    # 4. Coverage summary accounts for all four levels
    summary = inventory.coverage_summary()
    assert summary["duration_ms"] == duration_ms
    assert summary["by_level_ms"]["unknown"] == 10_000
    assert summary["by_level_ms"]["model_inspected"] == 12_000
    assert summary["speech_ms"] > 0
    assert summary["static_speech_ms"] == 14_000  # 32_000 - 18_000 = 14_000 ms


def test_observation_inventory_rejects_gaps_and_invalid_bounds() -> None:
    """Verifies strict boundary and partition validation."""
    valid_int1 = ObservationInterval(in_ms=0, out_ms=10_000, level=ObservationLevel.SCANNED)
    valid_int2 = ObservationInterval(in_ms=10_000, out_ms=20_000, level=ObservationLevel.SAMPLED)

    # 1. Starting past 0
    late_int = ObservationInterval(in_ms=500, out_ms=20_000, level=ObservationLevel.SCANNED)
    with pytest.raises(ObservationError, match="starts at 500 ms, must start at 0 ms"):
        ObservationInventory(
            media_id="ep01-test",
            source_sha256=_VALID_SHA,
            duration_ms=20_000,
            intervals=(late_int,),
        )

    # 2. Gap between intervals
    gap_int = ObservationInterval(in_ms=12_000, out_ms=20_000, level=ObservationLevel.SAMPLED)
    with pytest.raises(ObservationError, match="unrepresented gap of 2000 ms"):
        ObservationInventory(
            media_id="ep01-test",
            source_sha256=_VALID_SHA,
            duration_ms=20_000,
            intervals=(valid_int1, gap_int),
        )

    # 3. Overlap between intervals
    overlap_int = ObservationInterval(in_ms=8_000, out_ms=20_000, level=ObservationLevel.SAMPLED)
    with pytest.raises(ObservationError, match="overlapping intervals"):
        ObservationInventory(
            media_id="ep01-test",
            source_sha256=_VALID_SHA,
            duration_ms=20_000,
            intervals=(valid_int1, overlap_int),
        )

    # 4. Premature termination
    with pytest.raises(ObservationError, match="ends at 20000 ms, must end at 30000 ms"):
        ObservationInventory(
            media_id="ep01-test",
            source_sha256=_VALID_SHA,
            duration_ms=30_000,
            intervals=(valid_int1, valid_int2),
        )

    # 5. Invalid source_sha256
    with pytest.raises(ValueError, match="source_sha256 must be exactly 64"):
        ObservationInventory(
            media_id="ep01-test",
            source_sha256="invalid",
            duration_ms=20_000,
            intervals=(valid_int1, valid_int2),
        )


def test_observation_inventory_serialization_roundtrip() -> None:
    """Verifies lossless JSON serialization and deserialization."""
    inventory = build_observation_inventory(
        media_id="ep02-roundtrip",
        source_sha256=_VALID_SHA,
        duration_ms=30_000,
        shot_cuts_ms=(10_000, 20_000),
        speech_intervals=((2_000, 8_000),),
        sampled_frame_times_ms=(5_000,),
        model_inspected_intervals=((15_000, 18_000),),
        motion_scores_by_shot=(0.10, 0.02, 0.30),
    )

    json_str = inventory.to_json()
    restored = ObservationInventory.from_json(json_str)

    assert restored.media_id == inventory.media_id
    assert restored.source_sha256 == inventory.source_sha256
    assert restored.duration_ms == inventory.duration_ms
    assert len(restored.intervals) == len(inventory.intervals)
    for orig, rest in zip(inventory.intervals, restored.intervals, strict=True):
        assert orig.in_ms == rest.in_ms
        assert orig.out_ms == rest.out_ms
        assert orig.level == rest.level
        assert orig.has_speech == rest.has_speech
        assert orig.motion_score == rest.motion_score
        assert orig.notes == rest.notes


def test_targeted_visual_observation_respects_budget_and_recovers_brief_event() -> None:
    """WHEN an important event is uncertain or falls between coarse samples,
    THE system SHALL request bounded targeted observation or declare insufficient
    evidence, while preserving configured model/frame/pixel budgets (VE-03 / V03).
    """
    duration_ms = 30_000
    # Coarse uniform sampling every 5s: 0s, 5s, 10s, 15s, 20s, 25s
    coarse_frames = (0, 5_000, 10_000, 15_000, 20_000, 25_000)
    inventory = build_observation_inventory(
        media_id="ep03-budget-test",
        source_sha256=_VALID_SHA,
        duration_ms=duration_ms,
        sampled_frame_times_ms=coarse_frames,
    )

    # Candidate events falling between the 5s coarse samples:
    # 1. Brief object demonstration: 2_100..2_600 ms (duration 500 ms, priority 0.95)
    # 2. Key emotional reaction: 7_200..7_600 ms (duration 400 ms, priority 0.85)
    # 3. Quick screen title change: 12_100..12_400 ms (duration 300 ms, priority 0.75)
    # 4. Low priority gesture: 17_100..17_300 ms (duration 200 ms, priority 0.40)
    ev1 = TargetedEventCandidate(
        event_id="demo-1",
        kind=VisualEventKind.OBJECT_DEMONSTRATION,
        in_ms=2_100,
        out_ms=2_600,
        priority=0.95,
        description="presenter reveals a book cover",
    )
    ev2 = TargetedEventCandidate(
        event_id="react-2",
        kind=VisualEventKind.BRIEF_REACTION,
        in_ms=7_200,
        out_ms=7_600,
        priority=0.85,
        description="guest raises eyebrows in surprise",
    )
    ev3 = TargetedEventCandidate(
        event_id="screen-3",
        kind=VisualEventKind.SCREEN_CHANGE,
        in_ms=12_100,
        out_ms=12_400,
        priority=0.75,
        description="brief graphic title card",
    )
    ev4 = TargetedEventCandidate(
        event_id="gesture-4",
        kind=VisualEventKind.UNCERTAIN_COMPOSITION,
        in_ms=17_100,
        out_ms=17_300,
        priority=0.40,
        description="hand gesture",
    )

    # Budget: strictly allows at most 4 additional frames, max 2 per event
    budget = ObservationBudget(
        max_additional_frames=4,
        max_frames_per_event=2,
        min_frame_interval_ms=150,
    )

    plan = plan_targeted_observation(inventory, [ev1, ev2, ev3, ev4], budget)

    # Assert budget was strictly respected
    assert plan.allocated_frames <= budget.max_additional_frames
    assert plan.allocated_frames == 4
    assert len(plan.targeted_frames) == 4

    # High priority events (ev1 and ev2) were scheduled and allocated frames
    assert ev1 in plan.scheduled_events
    assert ev2 in plan.scheduled_events
    assert plan.is_covered(ev1)
    assert plan.is_covered(ev2)
    for frame_time in plan.targeted_frames[:2]:
        assert ev1.in_ms <= frame_time <= ev1.out_ms

    # Budget was exhausted: ev3 and ev4 must be explicitly declared as unobserved
    unobserved_ids = [ev.event_id for ev, _ in plan.unobserved_events]
    assert "screen-3" in unobserved_ids
    assert "gesture-4" in unobserved_ids
    for _, reason in plan.unobserved_events:
        assert reason == "budget_exhausted"

    # Apply the targeted observation plan: returns an updated inventory
    updated_inventory = apply_targeted_observation(inventory, plan)

    # In the updated inventory, the brief event (ev1) is now covered by discrete sampled frames
    brief_intervals = [
        i
        for i in updated_inventory.intervals
        if max(i.in_ms, ev1.in_ms) < min(i.out_ms, ev1.out_ms)
    ]
    assert any(i.level == ObservationLevel.SAMPLED for i in brief_intervals)
    assert any(
        any(ev1.in_ms <= f <= ev1.out_ms for f in i.source_frame_indices) for i in brief_intervals
    )


def test_targeted_observation_budget_validation() -> None:
    """Verifies strict input validation for observation budgets and candidates."""
    with pytest.raises(ValueError, match="max_additional_frames must be a positive integer"):
        ObservationBudget(max_additional_frames=0)

    with pytest.raises(
        ValueError, match=r"max_frames_per_event .* cannot exceed max_additional_frames"
    ):
        ObservationBudget(max_additional_frames=3, max_frames_per_event=5)

    with pytest.raises(ValueError, match="min_frame_interval_ms must be a positive integer"):
        ObservationBudget(min_frame_interval_ms=-10)

    with pytest.raises(ValueError, match="priority must be in 0.0..1.0"):
        TargetedEventCandidate(
            event_id="bad-pri",
            kind=VisualEventKind.SHOT_CUT,
            in_ms=100,
            out_ms=200,
            priority=1.5,
        )
