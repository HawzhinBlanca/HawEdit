"""Unit tests for Silence Tightening (pro-edit T4, AC-4, AC-5)."""

from __future__ import annotations

import pytest

from hawedit.boundary import Boundary
from hawedit.clip import Clip, ClipTranscript, DiscoveryPath, Editorial, Output, Qc
from hawedit.sentences import Sentence
from hawedit.silence import (
    KURDISH_FILLER_TOKENS,
    SilencePlan,
    plan_silence_tightening,
    remap_timestamp,
    silence_trim_filter,
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


def test_plan_silence_tightening_identifies_dead_air_and_retained_intervals() -> None:
    words = (
        _make_word("سلێمانی", 1000, 2000),
        # Gap: 2000 to 3500 = 1500 ms (> 600 threshold). Keep 150 -> Excise 2150 to 3500 (1350 ms).
        _make_word("جووانە", 3500, 4500),
    )
    # Clip: 500 to 6000 (total duration 5500 ms)
    plan = plan_silence_tightening(
        words,
        clip_in_ms=500,
        clip_out_ms=6000,
        threshold_ms=600,
        target_gap_ms=150,
    )

    assert plan.total_removed_ms == 1350
    assert plan.effective_duration_ms == 5500 - 1350  # 4150 ms
    assert len(plan.removed_intervals_ms) == 1
    # Relative to clip_in_ms (500):
    # Cut in source is [2150, 3500] -> [1650, 3000] in clip time
    assert plan.removed_intervals_ms[0] == (1650, 3000)
    assert len(plan.retained_intervals_ms) == 2
    assert plan.retained_intervals_ms[0] == (0, 1650)
    assert plan.retained_intervals_ms[1] == (3000, 5500)


def test_plan_silence_tightening_no_excess_pause_returns_single_interval() -> None:
    words = (
        _make_word("هەولێر", 1000, 1800),
        # Gap: 1800 to 2200 = 400 ms (<= 600 threshold)
        _make_word("گەورەیە", 2200, 3000),
    )
    plan = plan_silence_tightening(
        words,
        clip_in_ms=500,
        clip_out_ms=4000,
        threshold_ms=600,
        target_gap_ms=150,
    )

    assert plan.total_removed_ms == 0
    assert plan.effective_duration_ms == 3500
    assert plan.removed_intervals_ms == ()
    assert plan.retained_intervals_ms == ((0, 3500),)


def test_plan_silence_tightening_input_validation() -> None:
    words = (_make_word("وشە", 100, 200),)
    with pytest.raises(ValueError, match="threshold_ms must be positive"):
        plan_silence_tightening(words, 0, 1000, threshold_ms=0)
    with pytest.raises(ValueError, match="target_gap_ms cannot be negative"):
        plan_silence_tightening(words, 0, 1000, target_gap_ms=-1)
    with pytest.raises(ValueError, match="must be strictly less than threshold_ms"):
        plan_silence_tightening(words, 0, 1000, threshold_ms=400, target_gap_ms=400)
    with pytest.raises(ValueError, match="clip_out_ms .* must be strictly greater than clip_in_ms"):
        plan_silence_tightening(words, 1000, 1000)


def test_remap_timestamp_shifts_events_accurately() -> None:
    words = (
        _make_word("یەک", 1000, 2000),
        # Pause: 2000 to 4000 = 2000 ms. Keep 150 -> Remove 2150 to 4000 (1850 ms).
        _make_word("دوو", 4000, 5000),
    )
    plan = plan_silence_tightening(
        words,
        clip_in_ms=0,
        clip_out_ms=6000,
        threshold_ms=600,
        target_gap_ms=150,
    )

    # Before the excised interval:
    assert remap_timestamp(0, plan) == 0
    assert remap_timestamp(1500, plan) == 1500
    assert remap_timestamp(2150, plan) == 2150

    # Inside the excised interval (clamped to start of gap):
    assert remap_timestamp(2500, plan) == 2150
    assert remap_timestamp(3500, plan) == 2150

    # At boundary of resume:
    assert remap_timestamp(4000, plan) == 2150  # 4000 - 1850 = 2150

    # After the excised interval (shifted by 1850 ms):
    assert remap_timestamp(4500, plan) == 4500 - 1850  # 2650
    assert remap_timestamp(6000, plan) == 6000 - 1850  # 4150 == effective_duration_ms


def test_silence_trim_filter_generates_valid_ffmpeg_filtergraph() -> None:
    # Single interval -> empty string
    assert silence_trim_filter(((0, 5000),)) == ""
    assert silence_trim_filter(()) == ""

    # Two intervals
    filt = silence_trim_filter(((0, 1500), (3000, 5000)))
    assert "[0:v]trim=start=0.000:end=1.500,setpts=PTS-STARTPTS[v0]" in filt
    assert "[0:a]atrim=start=0.000:end=1.500,asetpts=PTS-STARTPTS[a0]" in filt
    assert "[0:v]trim=start=3.000:end=5.000,setpts=PTS-STARTPTS[v1]" in filt
    assert "[0:a]atrim=start=3.000:end=5.000,asetpts=PTS-STARTPTS[a1]" in filt
    assert "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v_tightened][a_tightened]" in filt


def test_plan_silence_tightening_excises_kurdish_filler_tokens() -> None:
    """AC-4+: Conversational Kurdish filler tokens are excised with excess pause tightened."""
    words = (
        _make_word("ئێمە", 1000, 1500),
        _make_word("یەعنی", 1600, 2000),  # Kurdish filler token
        _make_word("دانیشتووین", 2100, 2600),
    )
    plan = plan_silence_tightening(
        words,
        clip_in_ms=500,
        clip_out_ms=3000,
        threshold_ms=400,
        target_gap_ms=100,
        filler_tokens=KURDISH_FILLER_TOKENS,
    )

    assert plan.excised_word_count == 1
    assert len(plan.removed_intervals_ms) == 1
    # Speech of "یەعنی" [1600, 2000] is completely inside excised span
    rem_start, rem_end = plan.removed_intervals_ms[0]
    # In clip time (source - 500):
    # 1600 in source -> 1100 in clip time
    # 2000 in source -> 1500 in clip time
    assert rem_start <= 1600 - 500
    assert rem_end >= 2000 - 500
    # Surviving words "ئێمە" [1000, 1500] (clip: [500, 1000]) and
    # "دانیشتووین" [2100, 2600] (clip: [1600, 2100]) are strictly preserved in retained intervals
    assert plan.retained_intervals_ms[0][0] <= 500
    assert plan.retained_intervals_ms[0][1] >= 1000
    assert plan.retained_intervals_ms[1][0] <= 1600
    assert plan.retained_intervals_ms[1][1] >= 2100


def test_tighten_silence_excises_filler_and_shifts_monotonically() -> None:
    """AC-4+: Filler words are omitted from tightened output and subsequent words shifted."""
    words = (
        _make_word("ماڵێک", 0, 500),
        _make_word("وەڵا", 600, 1000),  # Kurdish filler
        _make_word("هاتن", 1100, 1600),
    )
    tightened, removed_ms = tighten_silence(
        words,
        threshold_ms=400,
        target_gap_ms=100,
        filler_tokens=KURDISH_FILLER_TOKENS,
    )

    assert len(tightened) == 2
    assert tightened[0].w == "ماڵێک"
    assert tightened[1].w == "هاتن"
    # Word durations preserved
    assert tightened[0].end_ms - tightened[0].start_ms == 500
    assert tightened[1].end_ms - tightened[1].start_ms == 500
    # Shifted earlier
    assert removed_ms > 0
    assert tightened[1].start_ms < 1100
    assert tightened[1].start_ms >= tightened[0].end_ms


def test_tighten_sentences_with_fillers_reconstructs_clean_sentences() -> None:
    """AC-4+: Sentence boundaries and grouping are preserved when filler words are excised."""
    s1 = Sentence(
        words=(
            _make_word("ئەها", 0, 300),  # Leading filler
            _make_word("ئەمڕۆ", 400, 900),
        ),
        complete=True,
    )
    s2 = Sentence(
        words=(
            _make_word("پڕۆژەکە", 1500, 2000),
            _make_word("دەزانی", 2100, 2400),  # Trailing filler
        ),
        complete=True,
    )
    tightened_s, removed_ms = tighten_sentences(
        [s1, s2],
        threshold_ms=400,
        target_gap_ms=100,
        filler_tokens=KURDISH_FILLER_TOKENS,
    )

    assert len(tightened_s) == 2
    assert len(tightened_s[0].words) == 1
    assert tightened_s[0].words[0].w == "ئەمڕۆ"
    assert len(tightened_s[1].words) == 1
    assert tightened_s[1].words[0].w == "پڕۆژەکە"
    assert removed_ms > 0


def test_silence_plan_cut_points_ms_property() -> None:
    """SilencePlan.cut_points_ms returns exact output timeline interior cuts."""
    # Retained: [0, 1000], [2000, 3500] (duration 1000, then duration 1500)
    plan = SilencePlan(
        clip_in_ms=0,
        clip_out_ms=5000,
        threshold_ms=400,
        target_gap_ms=100,
        retained_intervals_ms=((0, 1000), (2000, 3500)),
        removed_intervals_ms=((1000, 2000),),
        total_removed_ms=1000,
        excised_word_count=0,
    )
    assert plan.cut_points_ms == (1000,)

    # Single retained interval -> no interior cuts
    single_plan = SilencePlan(
        clip_in_ms=0,
        clip_out_ms=5000,
        threshold_ms=400,
        target_gap_ms=100,
        retained_intervals_ms=((0, 5000),),
        removed_intervals_ms=(),
        total_removed_ms=0,
    )
    assert single_plan.cut_points_ms == ()


def test_all_words_filler_safety_guard() -> None:
    """If all words in a span are fillers, safety guard preserves all words."""
    words = (
        _make_word("وەڵا", 0, 400),
        _make_word("یەعنی", 500, 900),
    )
    plan = plan_silence_tightening(
        words,
        clip_in_ms=0,
        clip_out_ms=1000,
        threshold_ms=400,
        target_gap_ms=100,
        filler_tokens=KURDISH_FILLER_TOKENS,
    )
    # Safety guard triggered: not all excised
    assert plan.excised_word_count == 0
    tightened, removed = tighten_silence(
        words,
        threshold_ms=400,
        target_gap_ms=100,
        filler_tokens=KURDISH_FILLER_TOKENS,
    )
    assert len(tightened) == 2
