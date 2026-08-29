"""Unit tests for Silence Tightening (pro-edit T4, AC-4, AC-5)."""

from __future__ import annotations

import pytest

from hawedit.boundary import Boundary
from hawedit.clip import Clip, ClipTranscript, DiscoveryPath, Editorial, Output, Qc
from hawedit.sentences import Sentence
from hawedit.silence import (
    tighten_clip,
    tighten_sentences,
    tighten_silence,
)
from hawedit.transcripts import AsrProvenance, Word


def _make_word(w: str, start_ms: int, end_ms: int, conf: float = 0.95) -> Word:
    return Word(w=w, start_ms=start_ms, end_ms=end_ms, conf=conf)


def _make_dummy_clip(words: tuple[Word, ...], silence_removed_ms: int = 0) -> Clip:
    boundary = Boundary(
        anchor_in_ms=0,
        anchor_out_ms=10_000,
        final_in_ms=0,
        final_out_ms=10_000,
        in_extended_by=None,
        out_extended_by=None,
        sentence_complete=True,
    )
    return Clip(
        clip_id="c-1",
        media_id="test_media_001",
        media_sha256="a" * 64,
        in_ms=0,
        out_ms=10_000,
        discovery_path=DiscoveryPath.VERBAL,
        boundary=boundary,
        transcript=ClipTranscript(
            raw_ckb=" ".join(w.w for w in words),
            norm_ckb=" ".join(w.w for w in words),
            en_aux=None,
            words=words,
            asr=AsrProvenance(
                canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi", mean_logprob=-0.21
            ),
        ),
        editorial=Editorial(
            hook_score=0.85,
            self_contained=True,
            meaning_fidelity=1.0,
            misleading_edit_risk=0.08,
            cultural_landing=0.90,
            narrative_role="test",
            judge="gemini-2.5-pro",
        ),
        output=Output(
            title_ckb="تێست",
            description_ckb="وەسف",
            crop_target="9:16",
            caption_style="word_by_word",
            durations=(10,),
            silence_removed_ms=silence_removed_ms,
        ),
        qc=Qc(auto_pass=True),
    )


def test_a_long_internal_pause_is_removed() -> None:
    """AC-4: An internal pause exceeding the threshold is tightened to target_gap_ms."""
    words = (
        _make_word("کوردستان", 1000, 1500),
        # 1200ms pause (1500 to 2700) > threshold of 600ms
        _make_word("ئارامە", 2700, 3200),
    )

    tightened, removed_ms = tighten_silence(
        words,
        threshold_ms=600,
        target_gap_ms=150,
    )

    # Excess pause = 1200 - 150 = 1050ms
    assert removed_ms == 1050
    assert len(tightened) == 2
    assert tightened[0].start_ms == 1000
    assert tightened[0].end_ms == 1500
    # Second word shifted earlier by 1050ms: 2700 - 1050 = 1650
    assert tightened[1].start_ms == 1650
    assert tightened[1].end_ms == 2150
    # New gap is exactly 1650 - 1500 = 150ms
    assert tightened[1].start_ms - tightened[0].end_ms == 150


def test_captions_shift_with_the_removed_silence() -> None:
    """AC-4: Every later word and caption event shifts earlier by the removed duration."""
    words = (
        _make_word("ئێمە", 0, 500),
        # Pause 1: 1000ms (500 to 1500) -> trimmed to 150ms (excess 850ms)
        _make_word("لە", 1500, 1800),
        # Pause 2: 200ms (1800 to 2000) <= threshold 600ms (no trim)
        _make_word("شاردا", 2000, 2500),
        # Pause 3: 1500ms (2500 to 4000) -> trimmed to 150ms (excess 1350ms)
        _make_word("دەژین", 4000, 4600),
    )

    tightened, total_removed_ms = tighten_silence(
        words,
        threshold_ms=600,
        target_gap_ms=150,
    )

    # Total removed = 850 + 1350 = 2200ms
    assert total_removed_ms == 2200
    assert len(tightened) == 4

    # Word 0: unchanged
    assert tightened[0].start_ms == 0
    assert tightened[0].end_ms == 500

    # Word 1: shifted by 850ms -> 1500 - 850 = 650, 1800 - 850 = 950
    assert tightened[1].start_ms == 650
    assert tightened[1].end_ms == 950

    # Word 2: shifted by 850ms -> 2000 - 850 = 1150, 2500 - 850 = 1650
    assert tightened[2].start_ms == 1150
    assert tightened[2].end_ms == 1650

    # Word 3: shifted by 850 + 1350 = 2200ms -> 4000 - 2200 = 1800, 4600 - 2200 = 2400
    assert tightened[3].start_ms == 1800
    assert tightened[3].end_ms == 2400


def test_the_removed_total_is_recorded() -> None:
    """AC-5: The delivered clip contract records the removed total duration."""
    words = (
        _make_word("پێشەوا", 100, 600),
        _make_word("قازی", 1800, 2300),  # 1200ms pause -> 1050ms removed
    )
    clip = _make_dummy_clip(words, silence_removed_ms=0)

    updated_clip, removed = tighten_clip(clip, threshold_ms=600, target_gap_ms=150)

    assert removed == 1050
    assert updated_clip.output is not None
    assert updated_clip.output.silence_removed_ms == 1050
    # Serialized dictionary preserves the field
    clip_dict = updated_clip.to_dict()
    assert clip_dict["output"]["silence_removed_ms"] == 1050

    # Reconstructed from dict matches
    restored = Clip.from_dict(clip_dict)
    assert restored.output is not None
    assert restored.output.silence_removed_ms == 1050


def test_tighten_sentences_preserves_grouping_and_completeness() -> None:
    s1 = Sentence(
        words=(
            _make_word("تۆ", 0, 400),
            _make_word("دەتوانی", 1200, 1700),  # 800ms gap -> 650ms removed
        ),
        complete=True,
    )
    s2 = Sentence(
        words=(
            _make_word("بڕۆیت", 3000, 3500),  # 1300ms gap from s1 -> 1150ms removed
        ),
        complete=False,
    )

    tightened_sentences, total_removed = tighten_sentences(
        [s1, s2], threshold_ms=600, target_gap_ms=150
    )

    assert total_removed == 650 + 1150
    assert len(tightened_sentences) == 2
    assert tightened_sentences[0].complete is True
    assert tightened_sentences[1].complete is False
    assert len(tightened_sentences[0].words) == 2
    assert len(tightened_sentences[1].words) == 1


def test_tighten_silence_input_validation() -> None:
    words = (_make_word("وشە", 0, 100),)
    with pytest.raises(ValueError, match="threshold_ms must be positive"):
        tighten_silence(words, threshold_ms=0)

    with pytest.raises(ValueError, match="target_gap_ms cannot be negative"):
        tighten_silence(words, target_gap_ms=-1)

    with pytest.raises(ValueError, match="must be strictly less than threshold_ms"):
        tighten_silence(words, threshold_ms=500, target_gap_ms=500)


def test_tighten_silence_short_or_empty_sequence() -> None:
    assert tighten_silence(()) == ((), 0)
    w = _make_word("تەنیا", 100, 300)
    assert tighten_silence((w,)) == ((w,), 0)
