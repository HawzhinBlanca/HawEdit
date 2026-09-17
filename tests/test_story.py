"""Tests for grounded story relations connecting narrative meaning to visual events (VE-05)."""

from __future__ import annotations

import pytest

from hawedit.clip import (
    MIN_MEANING_FIDELITY,
    Clip,
    EditorialBelowThreshold,
)
from hawedit.edit_plan import (
    CURRENT_PLAN_VERSION,
    EditorialBrief,
    EffectiveConfiguration,
    SourceTimeMapping,
    VisualEditPlan,
)
from hawedit.judge import JudgeVerdict, tournament_rank_verdicts
from hawedit.sentences import Sentence
from hawedit.story import (
    EditorialProposal,
    StoryCandidateResult,
    StoryGroundingError,
    StoryMap,
    StoryRelation,
    StoryRelationKind,
    build_story_map,
    order_moments_by_story_map,
    produce_story_relations,
    rank_editorial_proposals,
    validate_editorial_proposal,
)
from hawedit.transcripts import Word


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


def test_visual_candidate_keeps_required_context_and_landing_beat() -> None:
    """VE-06: Candidate expansion preserves necessary setup and landing beat or rejects."""
    qa_rel = StoryRelation(
        relation_id="rel_qa",
        kind=StoryRelationKind.QUESTION_ANSWER,
        canonical_sentence_ids=("s_02",),
        visual_event_ids=("v_02",),
        in_ms=3500,
        out_ms=8000,
        confidence=0.9,
        required_context_sentence_ids=("s_01",),
        summary="Host asks question and guest delivers payoff answer",
    )
    payoff_rel = StoryRelation(
        relation_id="rel_payoff",
        kind=StoryRelationKind.SETUP_PAYOFF,
        canonical_sentence_ids=("s_04",),
        visual_event_ids=("v_04",),
        in_ms=14500,
        out_ms=19000,
        confidence=0.88,
        required_context_sentence_ids=("s_03",),
        summary="Contextual setup and decisive concluding claim",
    )
    far_rel = StoryRelation(
        relation_id="rel_far",
        kind=StoryRelationKind.CLAIM_QUALIFICATION,
        canonical_sentence_ids=("s_late",),
        visual_event_ids=("v_late",),
        in_ms=100000,
        out_ms=105000,
        confidence=0.85,
        required_context_sentence_ids=("s_early",),
        summary="Early assumption qualified with later evidence",
    )

    story_map = build_story_map(
        media_id="interview_clip",
        relations=[qa_rel, payoff_rel, far_rel],
        known_sentence_ids=[
            "s_01",
            "s_02",
            "s_03",
            "s_04",
            "s_solo",
            "s_early",
            "s_late",
        ],
        known_visual_event_ids=["v_02", "v_04", "v_late"],
    )

    sentence_spans = {
        "s_01": (1000, 3000),
        "s_02": (3500, 8000),
        "s_03": (10000, 14000),
        "s_04": (14500, 19000),
        "s_solo": (25000, 32000),
        "s_early": (35000, 40000),
        "s_late": (100000, 105000),
    }
    ordered_ids = ["s_01", "s_02", "s_03", "s_04", "s_solo", "s_early", "s_late"]

    # 1. Candidate proposes only the answer [3500..8000], omitting setup question:
    #    System SHALL expand to include setup question s_01 [1000..8000].
    res_setup = story_map.resolve_candidate(
        candidate_id="cand_omit_setup",
        in_ms=3500,
        out_ms=8000,
        sentence_spans=sentence_spans,
        ordered_sentence_ids=ordered_ids,
        max_duration_ms=60000,
    )
    assert res_setup.eligible is True
    assert res_setup.was_expanded is True
    assert res_setup.in_ms == 1000
    assert res_setup.out_ms == 8000
    assert "s_01" in res_setup.covered_sentence_ids
    assert "s_02" in res_setup.covered_sentence_ids
    assert res_setup.active_relation_ids == ("rel_qa",)

    # 2. Candidate proposes only setup [10000..15000], cutting off landing beat mid-idea:
    #    System SHALL expand forward to cover complete landing beat [10000..19000].
    res_landing = story_map.resolve_candidate(
        candidate_id="cand_cut_payoff",
        in_ms=10000,
        out_ms=15000,
        sentence_spans=sentence_spans,
        ordered_sentence_ids=ordered_ids,
        max_duration_ms=60000,
    )
    assert res_landing.eligible is True
    assert res_landing.was_expanded is True
    assert res_landing.in_ms == 10000
    assert res_landing.out_ms == 19000
    assert "s_03" in res_landing.covered_sentence_ids
    assert "s_04" in res_landing.covered_sentence_ids
    assert res_landing.active_relation_ids == ("rel_payoff",)

    # 3. Candidate captures both setup and landing beat:
    #    Preserved as-is without spurious expansion.
    res_complete = story_map.resolve_candidate(
        candidate_id="cand_complete",
        in_ms=10000,
        out_ms=19000,
        sentence_spans=sentence_spans,
        ordered_sentence_ids=ordered_ids,
        max_duration_ms=60000,
    )
    assert res_complete.eligible is True
    assert res_complete.was_expanded is False
    assert res_complete.in_ms == 10000
    assert res_complete.out_ms == 19000

    # 4. Standalone complete statement:
    #    Preserved cleanly without unnecessary bloating.
    res_solo = story_map.resolve_candidate(
        candidate_id="cand_solo",
        in_ms=25000,
        out_ms=32000,
        sentence_spans=sentence_spans,
        ordered_sentence_ids=ordered_ids,
        max_duration_ms=60000,
    )
    assert res_solo.eligible is True
    assert res_solo.was_expanded is False
    assert res_solo.in_ms == 25000
    assert res_solo.out_ms == 32000
    assert res_solo.active_relation_ids == ()

    # 5. Candidate requires context that exceeds maximum duration constraint:
    #    Expansion from 35000 to 105000 would be 70s (> 60s max).
    #    System SHALL reject before ranking (eligible=False, explicit rejection reason).
    res_exceed = story_map.resolve_candidate(
        candidate_id="cand_too_far",
        in_ms=100000,
        out_ms=105000,
        sentence_spans=sentence_spans,
        max_duration_ms=60000,
    )
    assert res_exceed.eligible is False
    assert res_exceed.rejection_reason is not None
    assert "exceeds maximum allowed 60000ms" in res_exceed.rejection_reason

    # 6. Candidate breaking contiguous flow (missing intermediate sentence in narrative order):
    res_gap = story_map.resolve_candidate(
        candidate_id="cand_gap",
        in_ms=1000,
        out_ms=8000,
        sentence_spans={
            "s_01": (1000, 3000),
            "s_gap": (20000, 25000),
            "s_02": (3500, 8000),
        },
        ordered_sentence_ids=["s_01", "s_gap", "s_02"],
        max_duration_ms=60000,
    )
    assert res_gap.eligible is False
    assert res_gap.rejection_reason is not None
    assert "breaks contiguous narrative flow" in res_gap.rejection_reason

    # 7. Batch filtering: only complete and validly expanded candidates advance to ranking
    proposals = [
        ("cand_omit_setup", 3500, 8000),
        ("cand_too_far", 100000, 105000),
        ("cand_solo", 25000, 32000),
    ]
    ranked_eligible = story_map.filter_and_expand_candidates(
        proposals,
        sentence_spans=sentence_spans,
        ordered_sentence_ids=ordered_ids,
        max_duration_ms=60000,
    )
    assert len(ranked_eligible) == 2
    assert ranked_eligible[0].candidate_id == "cand_omit_setup"
    assert ranked_eligible[0].in_ms == 1000
    assert ranked_eligible[1].candidate_id == "cand_solo"

    # 8. StoryCandidateResult serialization round-trip
    res_dict = res_setup.to_dict()
    restored_res = StoryCandidateResult.from_dict(res_dict)
    assert restored_res == res_setup


def test_story_map_orders_payoff_after_setup() -> None:
    """Task B4: Story map producer orders assembled moments with payoff succeeding setup.

    Proves:
    1. produce_story_relations extracts grounded relations from Kurdish speech (setup->payoff).
    2. order_moments_by_story_map re-orders moments so setup precedes payoff
       (payoff succeeds setup).
    3. The plan JSON carries relation_ids for the join.
    """
    # Create Kurdish sentences for ep29:
    # Sentence 0 (Setup): "ئەگەر سەرەتا سەیری دۆخەکە بکەین هەموو شتێک ئاڵۆز دیار بوو."
    setup_words = (
        Word(w="ئەگەر", start_ms=1000, end_ms=1400, conf=0.96),
        Word(w="سەرەتا", start_ms=1400, end_ms=1800, conf=0.95),
        Word(w="سەیری", start_ms=1800, end_ms=2200, conf=0.94),
        Word(w="دۆخەکە", start_ms=2200, end_ms=2600, conf=0.95),
        Word(w="بکەین.", start_ms=2600, end_ms=3000, conf=0.96),
    )
    setup_sentence = Sentence(words=setup_words, complete=True)

    # Sentence 1 (Payoff): "لە ئەنجامدا دەرکەوت کە دەستکەوتەکە زۆر گرنگ بوو."
    payoff_words = (
        Word(w="لە", start_ms=15000, end_ms=15300, conf=0.96),
        Word(w="ئەنجامدا", start_ms=15300, end_ms=15800, conf=0.95),
        Word(w="دەرکەوت", start_ms=15800, end_ms=16300, conf=0.95),
        Word(w="کە", start_ms=16300, end_ms=16600, conf=0.94),
        Word(w="دەستکەوتەکە", start_ms=16600, end_ms=17200, conf=0.95),
        Word(w="گرنگ", start_ms=17200, end_ms=17700, conf=0.94),
        Word(w="بوو.", start_ms=17700, end_ms=18200, conf=0.96),
    )
    payoff_sentence = Sentence(words=payoff_words, complete=True)

    sentences = (setup_sentence, payoff_sentence)

    # 1. Producer extracts grounded relation connecting setup to payoff
    relations = produce_story_relations(None, sentences, media_id="ep29")
    assert len(relations) >= 1
    rel = relations[0]
    assert rel.kind == StoryRelationKind.SETUP_PAYOFF
    assert rel.required_context_sentence_ids == ("s_00",)
    assert rel.canonical_sentence_ids == ("s_01",)

    # 2. Moments provided in reverse narrative order: [payoff_moment, setup_moment]
    payoff_moment = [payoff_sentence]
    setup_moment = [setup_sentence]
    reverse_moments = [payoff_moment, setup_moment]

    ordered_moments, relation_ids = order_moments_by_story_map(
        reverse_moments, relations, all_sentences=sentences
    )

    # Ordering from story map ensures payoff succeeds setup: setup_moment is first!
    assert ordered_moments[0] == setup_moment
    assert ordered_moments[1] == payoff_moment
    assert relation_ids == (rel.relation_id,)

    # 3. The VisualEditPlan carries relation_ids in its contract and JSON representation
    brief = EditorialBrief.default_for_content(
        "podcast", duration_ms=20_000, relation_ids=relation_ids
    )
    assert brief.relation_ids == relation_ids

    config = EffectiveConfiguration.resolve("podcast")
    time_map = SourceTimeMapping(
        clip_in_ms=1000,
        clip_out_ms=18200,
        retained_intervals_ms=((1000, 3000), (15000, 18200)),
    )
    plan = VisualEditPlan(
        version=CURRENT_PLAN_VERSION,
        clip_id="ep29_assembled_clip",
        media_id="ep29",
        media_sha256="0" * 64,
        brief=brief,
        config=config,
        time_mapping=time_map,
        sentences=sentences,
        relation_ids=relation_ids,
    )
    plan_dict = plan.to_dict()
    assert plan_dict["relation_ids"] == list(relation_ids)
    assert plan_dict["brief"]["relation_ids"] == list(relation_ids)

    # Plan JSON round-trip preserves relation_ids
    plan_json = plan.to_json()
    restored = VisualEditPlan.from_json(plan_json)
    assert restored.relation_ids == relation_ids
    assert restored.brief.relation_ids == relation_ids


def test_candidate_retains_question_and_qualification_or_refuses() -> None:
    """AC-12 / Task T08: Candidate requires earlier question, referent or later qualification.

    WHEN a candidate requires an earlier question, referent or later qualification,
    THE system SHALL include the required canonical contiguous context or reject it
    and record source-linked reasons.
    """
    rel_qa = StoryRelation(
        relation_id="rel_qa_t08",
        kind=StoryRelationKind.QUESTION_ANSWER,
        canonical_sentence_ids=("s_ans",),
        required_context_sentence_ids=("s_q",),
        visual_event_ids=("vis_qa",),
        in_ms=1000,
        out_ms=7500,
        confidence=0.95,
        summary="Host asks question and guest gives answer",
    )
    rel_setup = StoryRelation(
        relation_id="rel_setup_t08",
        kind=StoryRelationKind.SETUP_PAYOFF,
        canonical_sentence_ids=("s_payoff",),
        required_context_sentence_ids=("s_setup",),
        visual_event_ids=("vis_setup",),
        in_ms=10000,
        out_ms=19000,
        confidence=0.92,
        summary="Setup narrative context leading to punchy payoff",
    )
    rel_qual = StoryRelation(
        relation_id="rel_qual_t08",
        kind=StoryRelationKind.CLAIM_QUALIFICATION,
        canonical_sentence_ids=("s_qual",),
        required_context_sentence_ids=("s_claim",),
        visual_event_ids=("vis_qual",),
        in_ms=25000,
        out_ms=34000,
        confidence=0.90,
        summary="Claim followed by critical qualification caveat",
    )
    rel_long = StoryRelation(
        relation_id="rel_long_t08",
        kind=StoryRelationKind.QUESTION_ANSWER,
        canonical_sentence_ids=("s_long_ans",),
        required_context_sentence_ids=("s_long_q",),
        visual_event_ids=("vis_long",),
        in_ms=40000,
        out_ms=115000,
        confidence=0.88,
        summary="Question separated by 75 seconds from answer",
    )

    story_map = build_story_map(
        media_id="ep29_context",
        relations=[rel_qa, rel_setup, rel_qual, rel_long],
        known_sentence_ids=[
            "s_q",
            "s_ans",
            "s_setup",
            "s_payoff",
            "s_claim",
            "s_qual",
            "s_long_q",
            "s_long_ans",
            "s_gap_mid",
        ],
        known_visual_event_ids=["vis_qa", "vis_setup", "vis_qual", "vis_long"],
    )

    sentence_spans = {
        "s_q": (1000, 3000),
        "s_ans": (3500, 7500),
        "s_setup": (10000, 14000),
        "s_payoff": (14500, 19000),
        "s_claim": (25000, 29000),
        "s_qual": (29500, 34000),
        "s_long_q": (40000, 45000),
        "s_long_ans": (110000, 115000),
        "s_gap_mid": (20000, 23000),
    }
    ordered_ids = [
        "s_q",
        "s_ans",
        "s_setup",
        "s_payoff",
        "s_gap_mid",
        "s_claim",
        "s_qual",
        "s_long_q",
        "s_long_ans",
    ]

    # 1. Earlier Question Retention:
    # Proposing candidate covering only answer [3500..7500ms].
    # System expands backwards to include setup question s_q [1000..7500ms].
    res_q = story_map.resolve_candidate(
        candidate_id="cand_ans_only",
        in_ms=3500,
        out_ms=7500,
        sentence_spans=sentence_spans,
        ordered_sentence_ids=ordered_ids,
        max_duration_ms=60000,
    )
    assert res_q.eligible is True
    assert res_q.was_expanded is True
    assert res_q.in_ms == 1000
    assert res_q.out_ms == 7500
    assert "s_q" in res_q.covered_sentence_ids
    assert "s_ans" in res_q.covered_sentence_ids
    assert "rel_qa_t08" in res_q.active_relation_ids

    # 2. Earlier Referent / Setup Retention:
    # Proposing candidate covering only payoff [14500..19000ms].
    # System expands backwards to include setup [10000..19000ms].
    res_setup = story_map.resolve_candidate(
        candidate_id="cand_payoff_only",
        in_ms=14500,
        out_ms=19000,
        sentence_spans=sentence_spans,
        ordered_sentence_ids=ordered_ids,
        max_duration_ms=60000,
    )
    assert res_setup.eligible is True
    assert res_setup.was_expanded is True
    assert res_setup.in_ms == 10000
    assert res_setup.out_ms == 19000
    assert "s_setup" in res_setup.covered_sentence_ids
    assert "s_payoff" in res_setup.covered_sentence_ids

    # 3. Later Qualification Retention:
    # Proposing candidate covering only claim [25000..29000ms].
    # System expands forwards to include qualification [25000..34000ms].
    res_qual = story_map.resolve_candidate(
        candidate_id="cand_claim_only",
        in_ms=25000,
        out_ms=29000,
        sentence_spans=sentence_spans,
        ordered_sentence_ids=ordered_ids,
        max_duration_ms=60000,
    )
    assert res_qual.eligible is True
    assert res_qual.was_expanded is True
    assert res_qual.in_ms == 25000
    assert res_qual.out_ms == 34000
    assert "s_claim" in res_qual.covered_sentence_ids
    assert "s_qual" in res_qual.covered_sentence_ids
    assert "rel_qual_t08" in res_qual.active_relation_ids

    # 4. Refusal when context expansion exceeds max duration budget:
    # Expansion from 40000 to 115000 is 75000ms > 60000ms max.
    # System rejects before ranking and records source-linked reasons.
    res_long = story_map.resolve_candidate(
        candidate_id="cand_long_ans",
        in_ms=110000,
        out_ms=115000,
        sentence_spans=sentence_spans,
        ordered_sentence_ids=ordered_ids,
        max_duration_ms=60000,
    )
    assert res_long.eligible is False
    assert res_long.rejection_reason is not None
    assert "exceeds maximum allowed 60000ms" in res_long.rejection_reason

    # 5. Refusal when narrative context has broken contiguous flow:
    broken_ordered = ["s_q", "s_gap_mid", "s_ans"]
    res_gap = story_map.resolve_candidate(
        candidate_id="cand_gap_broken",
        in_ms=1000,
        out_ms=7500,
        sentence_spans={
            "s_q": (1000, 3000),
            "s_gap_mid": (20000, 23000),
            "s_ans": (3500, 7500),
        },
        ordered_sentence_ids=broken_ordered,
        max_duration_ms=60000,
    )
    assert res_gap.eligible is False
    assert res_gap.rejection_reason is not None
    assert "breaks contiguous narrative flow" in res_gap.rejection_reason

    # 6. Refusal when required context sentence has missing / unmeasured span:
    broken_spans = {"s_ans": (3500, 7500)}  # s_q missing from spans
    res_no_span = story_map.resolve_candidate(
        candidate_id="cand_no_span",
        in_ms=3500,
        out_ms=7500,
        sentence_spans=broken_spans,
    )
    assert res_no_span.eligible is False
    assert res_no_span.rejection_reason is not None
    assert "required context sentence 's_q' has no measured span" in res_no_span.rejection_reason

    # 7. Verification that assert_candidate_preserves_required_context enforces both boundaries:
    story_map.assert_candidate_preserves_required_context(
        candidate_in_ms=1000,
        candidate_out_ms=7500,
        sentence_spans=sentence_spans,
    )
    # Severing question:
    with pytest.raises(StoryGroundingError, match="severs required context sentence 's_q'"):
        story_map.assert_candidate_preserves_required_context(
            candidate_in_ms=3200,
            candidate_out_ms=7500,
            sentence_spans=sentence_spans,
        )
    # Severing qualification:
    with pytest.raises(
        StoryGroundingError, match="severs canonical qualification sentence 's_qual'"
    ):
        story_map.assert_candidate_preserves_required_context(
            candidate_in_ms=25000,
            candidate_out_ms=29000,
            sentence_spans=sentence_spans,
        )


def test_editorial_proposal_rejects_unverifiable_source_references() -> None:
    """AC-13 / Task T08: Editorial proposal with invalid source references is rejected.

    WHEN an editorial proposal cites missing sentence IDs, invents timing or reverses a
    protected negation/attribution, THE system SHALL reject it before ranking or rendering.
    """
    rel = StoryRelation(
        relation_id="rel_t08_p",
        kind=StoryRelationKind.QUESTION_ANSWER,
        canonical_sentence_ids=("s_02",),
        required_context_sentence_ids=("s_01",),
        visual_event_ids=("vis_01",),
        in_ms=1000,
        out_ms=8000,
        confidence=0.90,
    )
    story_map = build_story_map(
        media_id="ep29",
        relations=[rel],
        known_sentence_ids=["s_01", "s_02", "s_03"],
        known_visual_event_ids=["vis_01"],
    )
    spans = {
        "s_01": (1000, 3500),
        "s_02": (4000, 8000),
        "s_03": (8500, 12000),
    }

    # 1. Proposal citing missing / nonexistent sentence ID is rejected:
    p_missing = EditorialProposal(
        proposal_id="prop_missing_id",
        in_ms=1000,
        out_ms=3500,
        canonical_sentence_ids=("s_01", "fabricated_s_99"),
        hook_score=0.88,
    )
    res_missing = validate_editorial_proposal(p_missing, story_map, spans)
    assert res_missing.valid is False
    assert "cites missing or ungrounded sentence ID 'fabricated_s_99'" in (
        res_missing.rejection_reason or ""
    )

    # 2. Proposal inventing timing outside cited sentence spans is rejected:
    # Sentence s_01 spans 1000..3500 ms, proposal claims [500..9000ms]
    p_invented = EditorialProposal(
        proposal_id="prop_invented_time",
        in_ms=500,
        out_ms=9000,
        canonical_sentence_ids=("s_01",),
        hook_score=0.90,
    )
    res_invented = validate_editorial_proposal(p_invented, story_map, spans)
    assert res_invented.valid is False
    assert "invents timing [500..9000ms] outside cited sentence bounds [1000..3500ms]" in (
        res_invented.rejection_reason or ""
    )

    # 3. Proposal reversing protected negation is rejected before ranking:
    p_neg = EditorialProposal(
        proposal_id="prop_reversed_neg",
        in_ms=1000,
        out_ms=3500,
        canonical_sentence_ids=("s_01",),
        hook_score=0.92,
        reverses_negation=True,
    )
    res_neg = validate_editorial_proposal(p_neg, story_map, spans)
    assert res_neg.valid is False
    assert "reverses protected negation" in (res_neg.rejection_reason or "")

    # 4. Proposal reversing protected attribution is rejected before ranking:
    p_attr = EditorialProposal(
        proposal_id="prop_reversed_attr",
        in_ms=1000,
        out_ms=3500,
        canonical_sentence_ids=("s_01",),
        hook_score=0.89,
        reverses_attribution=True,
    )
    res_attr = validate_editorial_proposal(p_attr, story_map, spans)
    assert res_attr.valid is False
    assert "reverses protected attribution" in (res_attr.rejection_reason or "")

    # 5. Valid proposal grounded in canonical source sentences passes:
    p_valid = EditorialProposal(
        proposal_id="prop_valid",
        in_ms=1000,
        out_ms=8000,
        canonical_sentence_ids=("s_01", "s_02"),
        hook_score=0.85,
        meaning_fidelity=0.95,
        reason_ckb="پەیامێکی سەربەخۆیە.",
    )
    res_valid = validate_editorial_proposal(p_valid, story_map, spans)
    assert res_valid.valid is True
    assert res_valid.rejection_reason is None

    # 6. Serialization round-trip:
    p_dict = p_valid.to_dict()
    restored_p = EditorialProposal.from_dict(p_dict)
    assert restored_p == p_valid
    res_dict = res_valid.to_dict()
    assert res_dict["valid"] is True


def test_high_hook_score_cannot_override_meaning_failure() -> None:
    """AC-13 / Task T08: High hook score cannot override meaning fidelity failure.

    Proposals and verdicts failing meaning fidelity (<0.70) are rejected before ranking
    or rendering, ensuring sensationalized fragments cannot out-rank faithful edits.
    """
    rel = StoryRelation(
        relation_id="rel_meaning_test",
        kind=StoryRelationKind.QUESTION_ANSWER,
        canonical_sentence_ids=("s_ans",),
        required_context_sentence_ids=("s_q",),
        visual_event_ids=("vis_meaning",),
        in_ms=1000,
        out_ms=7500,
        confidence=0.95,
    )
    story_map = build_story_map(
        media_id="ep29",
        relations=[rel],
        known_sentence_ids=["s_q", "s_ans"],
        known_visual_event_ids=["vis_meaning"],
    )
    spans = {
        "s_q": (1000, 3000),
        "s_ans": (3500, 7500),
    }

    # 1. Proposal with sensational high hook (0.99) but failed meaning fidelity (0.40):
    p_sensational = EditorialProposal(
        proposal_id="prop_sensational_fail",
        in_ms=1000,
        out_ms=7500,
        canonical_sentence_ids=("s_q", "s_ans"),
        hook_score=0.99,
        meaning_fidelity=0.40,
        reason_ckb="سەرنجڕاکێشە بەڵام ناوەڕۆک شێوێنراوە.",
    )
    res_sensational = validate_editorial_proposal(p_sensational, story_map, spans)
    assert res_sensational.valid is False
    assert "meaning fidelity 0.40 is below required floor 0.70" in (
        res_sensational.rejection_reason or ""
    )

    # 2. Compliant proposal with solid hook (0.78) and high fidelity (0.95):
    p_faithful = EditorialProposal(
        proposal_id="prop_faithful_pass",
        in_ms=1000,
        out_ms=7500,
        canonical_sentence_ids=("s_q", "s_ans"),
        hook_score=0.78,
        meaning_fidelity=0.95,
        reason_ckb="پەیامێکی تەواو و پارێزراوە.",
    )
    res_faithful = validate_editorial_proposal(p_faithful, story_map, spans)
    assert res_faithful.valid is True

    # 3. rank_editorial_proposals disqualifies sensational proposal: faithful proposal wins:
    ranked = rank_editorial_proposals([p_sensational, p_faithful], story_map, spans)
    assert len(ranked) == 1
    assert ranked[0][0].proposal_id == "prop_faithful_pass"

    # 4. In tournament_rank_verdicts, high hook score cannot override meaning failure:
    v_sensational = JudgeVerdict(
        candidate_id="c_sensational",
        hook_score=0.99,
        self_contained=True,
        payoff_at_ms=4000,
        meaning_fidelity=0.35,  # below 0.70 floor!
        misleading_edit_risk=0.04,
        cultural_landing=0.85,
        narrative_role="payoff",
        title_ckb="سەردێڕی دەستکاری کراو",
        description_ckb="وەسف",
        hashtags_ckb=("#کورد",),
        judge="gemini-2.5-pro",
        clip_in_ms=1000,
        clip_out_ms=7500,
    )
    v_faithful = JudgeVerdict(
        candidate_id="c_faithful",
        hook_score=0.78,
        self_contained=True,
        payoff_at_ms=4000,
        meaning_fidelity=0.95,
        misleading_edit_risk=0.03,
        cultural_landing=0.85,
        narrative_role="payoff",
        title_ckb="سەردێڕی ڕاستەقینە",
        description_ckb="وەسف",
        hashtags_ckb=("#کورد",),
        judge="gemini-2.5-pro",
        clip_in_ms=1000,
        clip_out_ms=7500,
    )
    ranked_verdicts = tournament_rank_verdicts([v_sensational, v_faithful], require_eligible=True)
    assert len(ranked_verdicts) == 1
    assert ranked_verdicts[0][0].candidate_id == "c_faithful"

    # 5. Editorial block projected from the sensational verdict fails the render gate floor:
    editorial_sensational = v_sensational.to_editorial()
    assert editorial_sensational.meaning_fidelity == 0.35
    assert editorial_sensational.meaning_fidelity < MIN_MEANING_FIDELITY

    # Verifying that an Editorial below MIN_MEANING_FIDELITY is refused by Clip.assert_renderable:
    from hawedit.boundary import BoundaryInputs, fuse_boundary
    from hawedit.clip import ClipTranscript, DiscoveryPath, Output, Provenance, Qc
    from hawedit.transcripts import AsrProvenance

    boundary = fuse_boundary(
        BoundaryInputs(anchor_in_ms=1000, anchor_out_ms=7500, sentence_complete=True)
    )
    clip_sensational = Clip(
        clip_id="c_sensational",
        media_id="ep29",
        media_sha256="0" * 64,
        in_ms=boundary.final_in_ms,
        out_ms=boundary.final_out_ms,
        discovery_path=DiscoveryPath.VERBAL,
        boundary=boundary,
        transcript=ClipTranscript(
            raw_ckb="دەقی کوردی",
            norm_ckb="دەقی کوردی",
            en_aux=None,
            words=(),
            asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
        ),
        speaker="SPK_01",
        editorial=editorial_sensational,
        output=Output(
            title_ckb="سەردێڕ",
            description_ckb="وەسف",
            crop_target="speaker_face",
            caption_style="word_highlight",
            durations=(30,),
        ),
        qc=Qc(
            auto_pass=True,
            flags=(),
            human_reviewed=True,
            reviewed_by="Hawa",
            reviewed_at="2026-09-02T19:00:00Z",
            reviewed_sha256="0" * 64,
        ),
        provenance=Provenance.current(),
    )
    with pytest.raises(
        EditorialBelowThreshold, match="meaning fidelity 0.35, below the 0.70 floor"
    ):
        clip_sensational.assert_renderable()
