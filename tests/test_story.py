"""Tests for grounded story relations connecting narrative meaning to visual events (VE-05)."""

from __future__ import annotations

import pytest

from hawedit.story import (
    StoryGroundingError,
    StoryMap,
    StoryRelation,
    StoryRelationKind,
    build_story_map,
)


def test_story_relations_require_canonical_and_visual_evidence() -> None:
    """VE-05: Story relations must be grounded in canonical sentence and visual event IDs."""
    # 1. Missing canonical sentence IDs is refused
    with pytest.raises(StoryGroundingError, match="requires at least one canonical sentence ID"):
        StoryRelation(
            relation_id="rel_01",
            kind=StoryRelationKind.QUESTION_ANSWER,
            canonical_sentence_ids=(),
            visual_event_ids=("vis_event_01",),
            in_ms=1000,
            out_ms=5000,
            confidence=0.9,
        )

    # 2. Missing visual event IDs is refused
    with pytest.raises(StoryGroundingError, match="requires at least one visual event ID"):
        StoryRelation(
            relation_id="rel_02",
            kind=StoryRelationKind.SETUP_PAYOFF,
            canonical_sentence_ids=("s_01",),
            visual_event_ids=(),
            in_ms=1000,
            out_ms=5000,
            confidence=0.9,
        )

    # 3. Valid relation with grounded sentence and visual evidence
    valid_rel = StoryRelation(
        relation_id="rel_qa_01",
        kind=StoryRelationKind.QUESTION_ANSWER,
        canonical_sentence_ids=("s_02",),
        visual_event_ids=("vis_event_01",),
        in_ms=2000,
        out_ms=4500,
        confidence=0.85,
        required_context_sentence_ids=("s_01",),
        summary="Guest answers host's question about election results",
        evidence_notes="Direct eye contact and animated gesture on payoff",
    )
    assert valid_rel.duration_ms == 2500
    assert valid_rel.kind == StoryRelationKind.QUESTION_ANSWER

    # 4. Building StoryMap with grounded IDs succeeds
    story_map = build_story_map(
        media_id="ep29_interview",
        relations=[valid_rel],
        known_sentence_ids=["s_01", "s_02", "s_03"],
        known_visual_event_ids=["vis_event_01", "vis_event_02"],
    )
    assert len(story_map.relations) == 1
    assert story_map.required_sentence_ids_for("rel_qa_01") == ("s_01", "s_02")

    # 5. Fabricated / ungrounded sentence ID is refused by StoryMap
    fake_sentence_rel = StoryRelation(
        relation_id="rel_fake_sent",
        kind=StoryRelationKind.CLAIM_QUALIFICATION,
        canonical_sentence_ids=("fabricated_s_99",),
        visual_event_ids=("vis_event_01",),
        in_ms=5000,
        out_ms=8000,
        confidence=0.7,
    )
    with pytest.raises(StoryGroundingError, match="ungrounded canonical sentence ID"):
        build_story_map(
            media_id="ep29_interview",
            relations=[fake_sentence_rel],
            known_sentence_ids=["s_01", "s_02"],
            known_visual_event_ids=["vis_event_01"],
        )

    # 6. Fabricated / ungrounded visual event ID is refused by StoryMap
    fake_visual_rel = StoryRelation(
        relation_id="rel_fake_vis",
        kind=StoryRelationKind.VISIBLE_REACTION,
        canonical_sentence_ids=("s_01",),
        visual_event_ids=("fabricated_vis_99",),
        in_ms=1000,
        out_ms=2000,
        confidence=0.6,
    )
    with pytest.raises(StoryGroundingError, match="ungrounded visual event ID"):
        build_story_map(
            media_id="ep29_interview",
            relations=[fake_visual_rel],
            known_sentence_ids=["s_01"],
            known_visual_event_ids=["vis_event_01"],
        )

    # 7. Candidate preserving required context passes; candidate severing context is rejected
    sentence_spans = {
        "s_01": (500, 1800),  # Question (required context)
        "s_02": (2000, 4500),  # Answer (core payoff)
    }

    # Candidate covering both question and answer: passes
    story_map.assert_candidate_preserves_required_context(
        candidate_in_ms=400,
        candidate_out_ms=4600,
        sentence_spans=sentence_spans,
    )

    # Candidate clipping out the question: rejected
    with pytest.raises(StoryGroundingError, match="severs required context sentence 's_01'"):
        story_map.assert_candidate_preserves_required_context(
            candidate_in_ms=1900,  # starts after s_01 ended!
            candidate_out_ms=4600,
            sentence_spans=sentence_spans,
        )


def test_story_relation_bounds_and_serialization() -> None:
    """StoryRelation and StoryMap validate bounds and round-trip via dictionary serialization."""
    rel = StoryRelation(
        relation_id="rel_setup_01",
        kind=StoryRelationKind.SETUP_PAYOFF,
        canonical_sentence_ids=("sent_02",),
        visual_event_ids=("event_01",),
        in_ms=5000,
        out_ms=9000,
        confidence=0.92,
        required_context_sentence_ids=("sent_01",),
        summary="Setup story about historical milestone and payoff fact",
        evidence_notes="Speaker gestures towards archive document",
    )
    data = rel.to_dict()
    restored = StoryRelation.from_dict(data)
    assert restored == rel

    s_map = StoryMap(
        media_id="episode_media_01",
        relations=(rel,),
        known_sentence_ids=frozenset({"sent_01", "sent_02"}),
        known_visual_event_ids=frozenset({"event_01"}),
    )
    map_data = s_map.to_dict()
    restored_map = StoryMap.from_dict(map_data)
    assert restored_map.media_id == s_map.media_id
    assert len(restored_map.relations) == 1
    assert restored_map.relations[0] == rel

    # Invalid timestamp ordering
    with pytest.raises(ValueError, match="out_ms .* must be > in_ms"):
        StoryRelation(
            relation_id="rel_bad_time",
            kind=StoryRelationKind.CORRECTION,
            canonical_sentence_ids=("sent_01",),
            visual_event_ids=("event_01",),
            in_ms=5000,
            out_ms=4000,
            confidence=0.8,
        )

    # Invalid confidence
    with pytest.raises(ValueError, match="confidence must be in 0.0..1.0"):
        StoryRelation(
            relation_id="rel_bad_conf",
            kind=StoryRelationKind.CORRECTION,
            canonical_sentence_ids=("sent_01",),
            visual_event_ids=("event_01",),
            in_ms=1000,
            out_ms=2000,
            confidence=1.5,
        )
