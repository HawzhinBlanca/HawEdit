"""Unit tests for multi-part story condensation and semantic pruning (src/hawedit/condenser.py)."""

from __future__ import annotations

import pytest

from hawedit.condenser import (
    BeatKind,
    CondensedStoryPlan,
    StoryBeat,
    StoryCondensationError,
    StorySummary,
    condense_multiple_arcs,
    condense_story,
    remap_words_to_condensed_timeline,
)
from hawedit.sentences import Sentence
from hawedit.transcripts import Word


def _make_word(text: str, start_ms: int, end_ms: int) -> Word:
    return Word(w=text, start_ms=start_ms, end_ms=end_ms, conf=0.99)


def _make_sentence(words: list[Word], complete: bool = True) -> Sentence:
    return Sentence(words=tuple(words), complete=complete)


def test_story_summary_invariants() -> None:
    """StorySummary validates required fields and score bounds."""
    summary = StorySummary(
        headline_kurdish="هەڕەشەی کوشتن لە بەغدا",
        summary_kurdish=(
            "میوانەکە باس لە نامەی هەڕەشەی کوشتن دەکات "
            "کە پێی گەیشتووە لە بەغدا و ناچار بووە بچێتە هەولێر."
        ),
        virality_score=92.5,
        core_topic="تیرۆر و کۆچکردن",
        key_entities=("بەغدا", "هەولێر", "پۆڵ برێمەر"),
    )
    assert summary.headline_kurdish == "هەڕەشەی کوشتن لە بەغدا"
    assert summary.virality_score == 92.5
    assert len(summary.key_entities) == 3

    # Virality score must be in 0..100
    with pytest.raises(ValueError, match="virality_score"):
        StorySummary(
            headline_kurdish="تست",
            summary_kurdish="تست",
            virality_score=150.0,
            core_topic="تست",
            key_entities=(),
        )


def test_story_beat_invariants() -> None:
    """StoryBeat validates kind, sentence indices, and timestamps."""
    beat = StoryBeat(
        beat_id="beat-1",
        beat_kind=BeatKind.HOOK,
        sentence_indices=(0,),
        in_ms=0,
        out_ms=3500,
        importance_score=0.95,
        summary_kurdish="نامەی هەڕەشەی کوشتن لە بەغدا گەیشت",
    )
    assert beat.beat_kind == BeatKind.HOOK
    assert beat.duration_ms == 3500

    with pytest.raises(ValueError, match="out_ms"):
        StoryBeat(
            beat_id="beat-bad",
            beat_kind=BeatKind.SETUP,
            sentence_indices=(1,),
            in_ms=5000,
            out_ms=4000,
            importance_score=0.8,
            summary_kurdish="هەڵە",
        )


def test_condense_story_preserves_hook_and_climax() -> None:
    """Condenser preserves hook and climax while pruning rambling filler."""
    # 5 sentences simulating a 2-minute conversation:
    # S0: Hook (0s - 10s)
    # S1: Rambling filler (12s - 45s)
    # S2: Conflict setup (47s - 65s)
    # S3: Tangential ramble (67s - 95s)
    # S4: Climax (98s - 120s)

    s0 = _make_sentence(
        [
            _make_word("نامەیەکی", 0, 2000),
            _make_word("هەڕەشەم", 2100, 4500),
            _make_word("پێگەیشت", 4600, 7000),
            _make_word("لەگەڵ", 7100, 8500),
            _make_word("فیشەکێک.", 8600, 10000),
        ]
    )
    s1 = _make_sentence(
        [
            _make_word("یەعنی", 12000, 15000),
            _make_word("دەزانی", 15100, 20000),
            _make_word("چۆنە", 20100, 25000),
            _make_word("جاران", 25100, 35000),
            _make_word("دەڕۆیشتین.", 35100, 45000),
        ]
    )
    s2 = _make_sentence(
        [
            _make_word("پێیان", 47000, 50000),
            _make_word("وتم", 50100, 53000),
            _make_word("بیست", 53100, 56000),
            _make_word("و", 56100, 57000),
            _make_word("چوار", 57100, 60000),
            _make_word("کاتژمێر.", 60100, 65000),
        ]
    )
    s3 = _make_sentence(
        [
            _make_word("ئۆتۆمبێلەکەمان", 67000, 75000),
            _make_word("کۆن", 75100, 85000),
            _make_word("بوو.", 85100, 95000),
        ]
    )
    s4 = _make_sentence(
        [
            _make_word("بەرەو", 98000, 102000),
            _make_word("هەولێر", 102100, 108000),
            _make_word("ڕامانکرد.", 108100, 120000),
        ]
    )

    sentences = (s0, s1, s2, s3, s4)
    # Total source duration: 120s
    # Target: 50s
    plan = condense_story(sentences, target_duration_ms=50_000)

    assert isinstance(plan, CondensedStoryPlan)
    assert 0 in plan.retained_sentence_indices  # Hook S0 must be retained
    assert 4 in plan.retained_sentence_indices  # Climax S4 must be retained
    assert 1 in plan.pruned_sentence_indices  # Filler S1 should be pruned
    assert 3 in plan.pruned_sentence_indices  # Ramble S3 should be pruned

    # Output duration must be strictly <= 60s
    assert plan.condensed_duration_ms <= 60_000
    assert plan.condensed_duration_ms >= 25_000
    assert plan.prune_ratio > 0.40  # Condenses at least 40% of the long speech
    assert plan.summary.headline_kurdish != ""
    assert plan.summary.summary_kurdish != ""


def test_remap_words_to_condensed_timeline() -> None:
    """Remapping words across non-contiguous cut spans preserves monotonicity and exact lengths."""
    # Retained spans: [0..10_000ms] and [40_000..60_000ms]
    # In output timeline:
    # Span 1: [0..10_000ms] -> output [0..10_000ms]
    # Span 2: [40_000..60_000ms] -> output [10_000..30_000ms]

    words = [
        _make_word("وشەی١", 1000, 4000),
        _make_word("وشەی٢", 5000, 9000),
        _make_word("وشەی_فڕێدراو", 20000, 25000),  # In excised interval [10s..40s]
        _make_word("وشەی٣", 42000, 48000),
        _make_word("وشەی٤", 50000, 58000),
    ]
    retained_spans = ((0, 10_000), (40_000, 60_000))

    remapped = remap_words_to_condensed_timeline(words, retained_spans)
    assert len(remapped) == 4  # Dropped "وشەی_فڕێدراو"

    # Verify Span 1 words
    assert remapped[0].w == "وشەی١"
    assert remapped[0].start_ms == 1000
    assert remapped[0].end_ms == 4000

    assert remapped[1].w == "وشەی٢"
    assert remapped[1].start_ms == 5000
    assert remapped[1].end_ms == 9000

    # Verify Span 2 words (shifted by -30_000ms)
    assert remapped[2].w == "وشەی٣"
    assert remapped[2].start_ms == 12000  # 42000 - 40000 + 10000
    assert remapped[2].end_ms == 18000  # 48000 - 40000 + 10000

    assert remapped[3].w == "وشەی٤"
    assert remapped[3].start_ms == 20000  # 50000 - 40000 + 10000
    assert remapped[3].end_ms == 28000  # 58000 - 40000 + 10000

    # Monotonicity check
    for i in range(len(remapped) - 1):
        assert remapped[i].start_ms < remapped[i].end_ms
        assert remapped[i].end_ms <= remapped[i + 1].start_ms


def test_condense_story_rejects_empty() -> None:
    """Empty sentence sequence is refused with StoryCondensationError."""
    with pytest.raises(StoryCondensationError, match="at least one sentence"):
        condense_story(())


def test_condense_multiple_arcs_empty() -> None:
    """condense_multiple_arcs returns empty list for empty sentence sequence."""
    assert condense_multiple_arcs(()) == []


def test_condense_multiple_arcs_single_window() -> None:
    """condense_multiple_arcs returns single arc when duration <= max_duration_ms."""
    s0 = _make_sentence([_make_word("وشە", 0, 5000), _make_word("کۆتایی", 6000, 30000)])
    plans = condense_multiple_arcs([s0], max_duration_ms=60000)
    assert len(plans) == 1
    assert plans[0].story_id == "clip-01"
    assert plans[0].condensed_duration_ms <= 60000


def test_condense_multiple_arcs_multi_window() -> None:
    """condense_multiple_arcs splits long dialogue into multiple ranked story clips."""
    # Create 12 sentences spanning 240 seconds (each ~20s)
    sentences: list[Sentence] = []
    for i in range(12):
        st = i * 20000
        mid = st + 8000
        en = st + 19000
        sentences.append(
            _make_sentence(
                [
                    _make_word(f"دەستپێک{i}", st, mid),
                    _make_word(f"کۆتایی{i}", mid + 500, en),
                ]
            )
        )

    plans = condense_multiple_arcs(
        sentences,
        max_clips=3,
        target_duration_ms=45000,
        min_duration_ms=20000,
        max_duration_ms=60000,
    )
    assert len(plans) >= 2
    assert len(plans) <= 3
    assert plans[0].story_id == "clip-01"
    assert plans[1].story_id == "clip-02"
    for plan in plans:
        assert plan.condensed_duration_ms <= 60000
        assert plan.summary.headline_kurdish != ""


def test_condenser_scoring_is_measured_and_ranked() -> None:
    """Condenser virality scores are empirically derived and clips are rank-ordered."""
    # S0: High-density hook with strong pacing
    s0 = _make_sentence(
        [
            _make_word("نامەیەکی", 0, 1000),
            _make_word("گرنگ", 1100, 2000),
            _make_word("گەیشت", 2100, 3000),
        ]
    )
    # S1: Weak filler
    s1 = _make_sentence(
        [
            _make_word("یەعنی", 4000, 7000),
            _make_word("دەزانی", 7100, 10000),
            _make_word("وەڵا", 10100, 15000),
        ]
    )
    # S2: Climax
    s2 = _make_sentence(
        [
            _make_word("هەموومان", 16000, 18000),
            _make_word("ڕزگارمان", 18100, 21000),
            _make_word("بوو.", 21100, 24000),
        ]
    )

    plan_dynamic = condense_story((s0, s1, s2), max_duration_ms=60000)
    # Score must be non-zero, within 0..100, and not the obsolete static 85.0
    assert 0.0 <= plan_dynamic.summary.virality_score <= 100.0
    assert plan_dynamic.summary.virality_score != 85.0

    # Custom override is preserved if provided
    plan_override = condense_story((s0, s1, s2), max_duration_ms=60000, virality_score=88.8)
    assert plan_override.summary.virality_score == 88.8


def test_condenser_prunes_filler_even_when_under_max_duration() -> None:
    """CD-08: When input is under max_duration_ms, condenser prunes filler clauses."""
    # S0: Hook (0s..10s, 10s duration)
    s0 = _make_sentence(
        [
            _make_word("نامەیەکی", 0, 2000),
            _make_word("هەڕەشەم", 2100, 5000),
            _make_word("پێگەیشت.", 5100, 10000),
        ]
    )
    # S1: Conversational filler (>30% filler tokens) (11s..25s, 14s duration)
    s1 = _make_sentence(
        [
            _make_word("یەعنی", 11000, 13000),
            _make_word("دەزانی", 13100, 16000),
            _make_word("وەڵا", 16100, 19000),
            _make_word("ئاوا", 19100, 22000),
            _make_word("بوو.", 22100, 25000),
        ]
    )
    # S2: Core content (26s..42s, 16s duration)
    s2 = _make_sentence(
        [
            _make_word("پۆڵ", 26000, 29000),
            _make_word("برێمەر", 29100, 33000),
            _make_word("هاتە", 33100, 37000),
            _make_word("کوردستان.", 37100, 42000),
        ]
    )
    # S3: Climax (43s..55s, 12s duration)
    s3 = _make_sentence(
        [
            _make_word("هەولێر", 43000, 46000),
            _make_word("بوو", 46100, 49000),
            _make_word("بە", 49100, 51000),
            _make_word("پەناگەمان.", 51100, 55000),
        ]
    )

    # Total duration = 55s (<= 60s max_duration_ms).
    # S0 + S2 + S3 = 10s + 16s + 12s = 38s (>= 25s min_duration_ms).
    # S1 has high filler ratio, so CD-08 specifies it must be pruned.
    plan = condense_story(
        (s0, s1, s2, s3),
        min_duration_ms=25000,
        max_duration_ms=60000,
    )

    assert 1 in plan.pruned_sentence_indices
    assert 0 in plan.retained_sentence_indices
    assert 2 in plan.retained_sentence_indices
    assert 3 in plan.retained_sentence_indices
    assert plan.condensed_duration_ms < plan.total_source_duration_ms
    assert plan.prune_ratio > 0.15


def test_condenser_evaluates_late_episode_windows_before_selection() -> None:
    """CD-04: Candidate windows across the entire timeline are evaluated before selection."""
    # 20 sentences spanning 400 seconds
    sentences: list[Sentence] = []
    for i in range(20):
        st = i * 20000
        mid = st + 9000
        en = st + 19000
        if i == 18:
            # S18 is high-density climax near the end of the episode
            w_list = [
                _make_word("ڕزگارکردنی", st, st + 2000),
                _make_word("کوردستان", st + 2100, st + 4500),
                _make_word("لە", st + 4600, st + 6000),
                _make_word("تیرۆر", st + 6100, st + 8000),
                _make_word("سەرکەوتنی", st + 8100, st + 11000),
                _make_word("گەورە", st + 11100, st + 14000),
                _make_word("بوو.", st + 14100, en),
            ]
        else:
            # Low density speech
            w_list = [
                _make_word(f"دەستپێک{i}", st, mid),
                _make_word(f"کۆتایی{i}", mid + 500, en),
            ]
        sentences.append(_make_sentence(w_list))

    plans = condense_multiple_arcs(
        sentences,
        max_clips=2,
        min_duration_ms=20000,
        max_duration_ms=60000,
    )

    # The returned clips must not be restricted only to the first 80s of the episode
    assert len(plans) == 2
    # At least one clip must contain sentences from the late episode (>200s)
    late_sentence_included = any(
        any(s_idx >= 10 for s_idx in p.retained_sentence_indices) for p in plans
    )
    assert late_sentence_included is True
