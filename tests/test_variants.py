"""Unit and integration tests for Length Variants (Task T2.11)."""

from __future__ import annotations

import pytest

from hawedit.sentences import Sentence
from hawedit.transcripts import Word
from hawedit.variants import LengthVariant, plan_length_variants


def _make_sentence(text: str, start_ms: int, end_ms: int, complete: bool = True) -> Sentence:
    words = text.split()
    n = len(words)
    dur = (end_ms - start_ms) // n
    word_objs = tuple(
        Word(
            w=w,
            start_ms=start_ms + i * dur,
            end_ms=start_ms + (i + 1) * dur if i < n - 1 else end_ms,
            conf=0.95,
        )
        for i, w in enumerate(words)
    )
    return Sentence(words=word_objs, complete=complete)


def test_plan_length_variants_enforces_sentence_completeness() -> None:
    """Variants must only include complete sentences; incomplete trailing fragments are dropped."""
    s1 = _make_sentence("ئەمە ڕستەی یەکەمە و تەواوە.", 0, 7_000, complete=True)
    s2 = _make_sentence("ئەمە ڕستەی دووەمە و تەواوە.", 7_500, 15_000, complete=True)
    s3_incomplete = _make_sentence("ئەمە ڕستەیەکی ناتەواوە", 15_500, 22_000, complete=False)

    variants = plan_length_variants([s1, s2, s3_incomplete], targets_s=(15, 30))
    # Should produce only the 15s variant made of s1+s2 (15,000 ms)
    assert len(variants) == 1
    assert variants[0].target_s == 15
    assert variants[0].duration_ms == 15_000
    assert len(variants[0].sentences) == 2
    assert all(s.complete for s in variants[0].sentences)


def test_plan_length_variants_anchors_on_hook_sentence() -> None:
    """All length variants must start at the beginning of sentence 0 (the hook)."""
    s1 = _make_sentence("دەستپێکی سەرەکی و گرنگ.", 10_000, 17_000)
    s2 = _make_sentence("ڕوونکردنەوەی بەشێک لە بابەتەکە.", 17_500, 25_000)
    s3 = _make_sentence("بەشی سێیەم و قسەی زیاتر.", 25_500, 39_000)

    variants = plan_length_variants([s1, s2, s3], targets_s=(15, 30))
    assert len(variants) == 2
    for v in variants:
        assert v.in_ms == 10_000
        assert v.sentences[0] == s1


def test_plan_length_variants_selects_optimal_sub_spans_for_targets() -> None:
    """Selects the best prefix of complete sentences minimizing duration deviation."""
    s1 = _make_sentence("سەرەتا.", 0, 6_000)
    s2 = _make_sentence("پاشان ناوەڕۆک دێت.", 6_500, 14_000)
    s3 = _make_sentence("دواتر نموونە دەهێنینەوە.", 14_500, 29_000)
    s4 = _make_sentence("کۆتایی و ئەنجامگیری.", 29_500, 58_000)

    variants = plan_length_variants([s1, s2, s3, s4], targets_s=(15, 30, 60))
    assert len(variants) == 3

    v15 = variants[0]
    assert v15.target_s == 15
    assert v15.duration_ms == 14_000  # s1 + s2 = 14s (diff 1s)

    v30 = variants[1]
    assert v30.target_s == 30
    assert v30.duration_ms == 29_000  # s1 + s2 + s3 = 29s (diff 1s)

    v60 = variants[2]
    assert v60.target_s == 60
    assert v60.duration_ms == 58_000  # s1 + s2 + s3 + s4 = 58s (diff 2s)


def test_plan_length_variants_handles_short_clips_gracefully() -> None:
    """A 20-second clip generates 15s variant but omits unreachable 30s and 60s variants."""
    s1 = _make_sentence("قسەی کورت.", 0, 8_000)
    s2 = _make_sentence("پوختە و تەواو.", 8_500, 18_000)

    variants = plan_length_variants([s1, s2], targets_s=(15, 30, 60))
    assert len(variants) == 1
    assert variants[0].target_s == 15
    assert variants[0].duration_ms == 18_000


def test_length_variant_validates_invariants_and_serializes() -> None:
    """LengthVariant validates parameters and serializes cleanly to dict."""
    s = _make_sentence("دەق.", 0, 15_000)

    # Valid variant
    v = LengthVariant(
        target_s=15,
        label="15s",
        in_ms=0,
        out_ms=15_000,
        duration_ms=15_000,
        sentence_indices=(0,),
        sentences=(s,),
    )
    v_dict = v.to_dict()
    assert v_dict["target_s"] == 15
    assert v_dict["duration_ms"] == 15_000
    assert v_dict["sentences_count"] == 1

    # Invalid: non-positive target_s
    with pytest.raises(ValueError, match="target_s must be positive"):
        LengthVariant(
            target_s=0,
            label="0s",
            in_ms=0,
            out_ms=15_000,
            duration_ms=15_000,
            sentence_indices=(0,),
            sentences=(s,),
        )

    # Invalid: out_ms <= in_ms
    with pytest.raises(ValueError, match="out_ms .* must be > in_ms"):
        LengthVariant(
            target_s=15,
            label="15s",
            in_ms=15_000,
            out_ms=15_000,
            duration_ms=0,
            sentence_indices=(0,),
            sentences=(s,),
        )

    # Invalid: duration_ms mismatch
    with pytest.raises(ValueError, match="duration_ms .* must equal out_ms - in_ms"):
        LengthVariant(
            target_s=15,
            label="15s",
            in_ms=0,
            out_ms=15_000,
            duration_ms=10_000,
            sentence_indices=(0,),
            sentences=(s,),
        )
