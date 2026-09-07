"""Unit tests for multi-part story condensation and semantic pruning (src/hawedit/condenser.py)."""

from __future__ import annotations

import pytest

from hawedit.condenser import (
    BeatKind,
    CondensedStoryPlan,
    StoryBeat,
    StoryCondensationError,
    StorySummary,
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
