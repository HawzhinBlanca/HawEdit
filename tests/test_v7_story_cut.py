"""Unit tests for V7 viral story director: cold-open teaser & middle-tangent condenser (D-378)."""

from __future__ import annotations

import pytest

from hawedit.assembly import (
    AssemblySpan,
    ViralStoryPlan,
    assembled_splice_filter,
    plan_viral_story_cut,
)
from hawedit.captions import build_ass
from hawedit.condenser import interval_overlap_ms, score_interior_sentence
from hawedit.sentences import Sentence, assert_deliverable_order
from hawedit.transcripts import Word


def _make_words(
    tokens: list[str],
    start_ms: int,
    word_dur_ms: int = 400,
    gap_ms: int = 20,
) -> tuple[Word, ...]:
    words: list[Word] = []
    cursor = start_ms
    for tok in tokens:
        words.append(Word(w=tok, start_ms=cursor, end_ms=cursor + word_dur_ms, conf=0.95))
        cursor += word_dur_ms + gap_ms
    return tuple(words)


def _make_sentence(
    tokens: list[str],
    start_ms: int,
    *,
    word_dur_ms: int = 400,
    gap_ms: int = 20,
    complete: bool = True,
) -> Sentence:
    return Sentence(
        words=_make_words(tokens, start_ms, word_dur_ms=word_dur_ms, gap_ms=gap_ms),
        complete=complete,
    )


def _assert_zero_split_words(plan: ViralStoryPlan, sentences: tuple[Sentence, ...]) -> None:
    all_words = [w for s in sentences for w in s.words]
    for sp in plan.spans:
        for cut in (sp.source_in_ms, sp.source_out_ms):
            for w in all_words:
                assert not (w.start_ms < cut < w.end_ms), (
                    f"Span {sp.span_index} cut at {cut} ms splits word "
                    f"{w.w!r} [{w.start_ms}..{w.end_ms}]"
                )


def test_interval_overlap_ms_merges_overlapping_intervals() -> None:
    """Overlapping excited intervals are merged so overlap never double-counts."""
    # Window [1000, 5000] overlapped by [500, 2500], [2000, 3500], and [4500, 6000].
    # Merged overlap inside [1000, 5000] = [1000, 3500] (2500) + [4500, 5000] (500) = 3000 ms.
    ov = interval_overlap_ms(1_000, 5_000, [(500, 2_500), (2_000, 3_500), (4_500, 6_000)])
    assert ov == 3_000
    assert interval_overlap_ms(1_000, 5_000, ()) == 0

    with pytest.raises(ValueError, match="Invalid interval"):
        interval_overlap_ms(1_000, 5_000, [(3_000, 3_000)])


def test_score_interior_sentence_ranks_excited_payoff_bridge_above_filler_tangent() -> None:
    """Excited, dense, payoff-adjacent bridge outscores slow filler-heavy middle tangent."""
    tangent = _make_sentence(
        ["یەعنی", "دەزانی", "وەڵا", "ئاوا", "جاران", "قسان", "بوو"],
        start_ms=15_000,
        word_dur_ms=3_800,
        gap_ms=100,
    )  # ~27.2s slow filler ramble
    bridge = _make_sentence(
        ["ژیری", "دەستکرد", "کوردیەکەیان", "زۆر", "باش", "گۆڕیوە", "ئێستا"],
        start_ms=48_000,
        word_dur_ms=400,
        gap_ms=20,
    )  # ~2.9s dense bridge

    score_tangent = score_interior_sentence(
        tangent,
        clip_in_ms=0,
        clip_out_ms=70_000,
        payoff_at_ms=62_000,
        excited_intervals_ms=[(48_000, 52_000)],
    )
    score_bridge = score_interior_sentence(
        bridge,
        clip_in_ms=0,
        clip_out_ms=70_000,
        payoff_at_ms=62_000,
        excited_intervals_ms=[(48_000, 52_000)],
    )
    assert 0.0 <= score_tangent < score_bridge <= 1.0


def test_condense_drops_middle_tangent_and_preserves_hook_and_payoff() -> None:
    """Multi-sentence clip > 48s drops lowest-scoring middle tangent, never S0 or final payoff."""
    # S0: 12s hook/setup (1000..13000)
    s0 = _make_sentence(
        ["بەڕای", "من", "ژیری", "دەستکرد", "وەرگێڕان", "لە", "کوردستان", "دەگۆڕێت"],
        start_ms=1_000,
        word_dur_ms=1_400,
        gap_ms=100,
    )
    # S1: 30s rambling filler tangent (14000..44000)
    s1 = _make_sentence(
        ["یەعنی", "دەزانی", "وەڵا", "ئاوا", "خەڵک", "باس", "دەکەن", "بۆیە"],
        start_ms=14_000,
        word_dur_ms=3_650,
        gap_ms=100,
    )
    # S2: 8s dense bridge near payoff (45000..53000)
    s2 = _make_sentence(
        [
            "کۆمپانیاکان",
            "کەسێکیان",
            "داناوە",
            "تەنیا",
            "وەرگێڕانی",
            "ناوخۆیی",
            "بکات",
            "هەموو",
            "ڕۆژێک",
        ],
        start_ms=45_000,
        word_dur_ms=800,
        gap_ms=80,
    )
    # S3: 15s final payoff (54500..69500)
    s3 = _make_sentence(
        ["ئەم", "ژیرە", "دەستکردانە", "کوردیەکەیان", "زۆر", "زۆر", "جوانە", "ئێستا", "ئەنجامە"],
        start_ms=54_500,
        word_dur_ms=1_550,
        gap_ms=100,
    )
    sents = (s0, s1, s2, s3)
    clip_in = 880
    clip_out = s3.end_ms + 200

    plan = plan_viral_story_cut(
        sents,
        clip_in,
        clip_out,
        payoff_at_ms=58_000,
        excited_intervals_ms=[(46_000, 52_000), (56_000, 62_000)],
        target_max_ms=48_000,
        target_min_ms=30_000,
        enable_cold_open=False,
        enable_condense=True,
        boundary_pad_ms=80,
    )

    assert plan.applied_condense is True
    assert plan.applied_cold_open is False
    assert 0 in plan.kept_sentence_indices
    assert 3 in plan.kept_sentence_indices
    assert 1 in plan.dropped_sentence_indices
    assert 2 in plan.kept_sentence_indices
    assert 30_000 <= plan.output_duration_ms <= 48_000
    assert len(plan.spans) == 2
    assert all(sp.role == "body" for sp in plan.spans)

    # Verify E3 padding on interior cut boundaries (exact 80 ms where pauses are >= 160 ms).
    assert plan.spans[0].source_out_ms == s0.end_ms + 80
    assert plan.spans[1].source_in_ms == s2.start_ms - 80
    _assert_zero_split_words(plan, sents)
    assert_deliverable_order(plan.remapped_sentences)


def test_condense_respects_target_min_ms_floor() -> None:
    """Condensation never drops sentences if doing so would push duration below target_min_ms."""
    # S0: 10s, S1: 35s (dropping S1 leaves only 20s < target_min_ms=30s!), S2: 10s -> total 56s
    s0 = _make_sentence(["سەرەتای", "باسەکە", "گرنگە", "زۆر"], start_ms=1_000, word_dur_ms=2_400)
    s1 = _make_sentence(
        ["یەعنی", "دەزانی", "وەڵا", "ئاوا", "باس"], start_ms=12_000, word_dur_ms=6_900
    )
    s2 = _make_sentence(
        ["کۆتایی", "ئەنجامەکەیە", "دڵنیا", "بە"], start_ms=48_000, word_dur_ms=2_400
    )
    sents = (s0, s1, s2)
    clip_in = 880
    clip_out = s2.end_ms + 200

    plan = plan_viral_story_cut(
        sents,
        clip_in,
        clip_out,
        target_max_ms=48_000,
        target_min_ms=30_000,
        enable_cold_open=False,
        enable_condense=True,
    )

    assert plan.applied_condense is False
    assert plan.kept_sentence_indices == (0, 1, 2)
    assert plan.dropped_sentence_indices == ()
    assert plan.output_duration_ms == clip_out - clip_in


def test_condense_skips_two_sentence_clip() -> None:
    """A 2-sentence clip has no interior sentences (1..N-2) and never drops S0 or S1."""
    s0 = _make_sentence(
        ["یەکەم", "ڕستەی", "چیرۆکەکە", "لێرەوە", "دەست", "پێدەکات"],
        start_ms=1_000,
        word_dur_ms=4_500,
    )
    s1 = _make_sentence(
        ["دووەم", "ڕستە", "ئەنجامی", "گەورەی", "تێدایە", "لێرەدا"],
        start_ms=30_000,
        word_dur_ms=4_500,
    )
    sents = (s0, s1)
    plan = plan_viral_story_cut(
        sents,
        880,
        s1.end_ms + 200,
        target_max_ms=48_000,
        enable_cold_open=False,
        enable_condense=True,
    )
    assert plan.applied_condense is False
    assert plan.kept_sentence_indices == (0, 1)


def test_cold_open_extracts_payoff_clause_with_exact_remapped_timeline() -> None:
    """Cold open places a 1.8-3.4s payoff clause at t=0 and shifts body captions to exact ms."""
    s0 = _make_sentence(
        ["لەم", "ماوەیەدا", "کۆمپانیایەکی", "تەکنەلۆژی", "مۆدێلێکی", "نوێی", "بڵاوکردەوە"],
        start_ms=10_000,
        word_dur_ms=1_800,
        gap_ms=100,
    )
    s1 = _make_sentence(
        ["خەڵک", "پرسیاری", "زۆر", "دەکەن", "دەربارەی", "کاریگەری", "داهاتووی", "کارەکان"],
        start_ms=25_000,
        word_dur_ms=1_500,
        gap_ms=100,
    )
    # Standalone 2.5s climax sentence at t=40s (with >= 1000 ms pause before and 200 ms tail after)
    s2 = _make_sentence(
        ["ژیری", "دەستکرد", "شتی", "زۆر", "گەورە", "بدۆزێتەوە"],
        start_ms=40_000,
        word_dur_ms=380,
        gap_ms=20,
    )
    sents = (s0, s1, s2)
    clip_in = 9_880
    clip_out = s2.end_ms + 200

    plan = plan_viral_story_cut(
        sents,
        clip_in,
        clip_out,
        payoff_at_ms=41_000,
        target_max_ms=48_000,
        enable_cold_open=True,
        enable_condense=True,
        boundary_pad_ms=80,
    )

    assert plan.applied_cold_open is True
    assert plan.applied_condense is False
    assert len(plan.spans) == 2
    assert plan.spans[0].role == "cold_open"
    assert plan.spans[1].role == "body"
    assert 1_800 <= plan.spans[0].duration_ms <= 3_400
    assert plan.cold_open_text == s2.text
    assert plan.cold_open_source_in_ms == s2.start_ms - 80
    assert plan.cold_open_source_out_ms == s2.end_ms + 80
    assert plan.spans[1].source_in_ms == clip_in
    assert plan.spans[1].source_out_ms == clip_out

    # Verify exact millisecond caption remapping across cold-open + body.
    assert len(plan.remapped_sentences) == 4  # 1 cold-open + 3 body sentences
    co_dur = plan.spans[0].duration_ms
    # First word of cold open sits at exact lead pad (80 ms)
    assert plan.remapped_sentences[0].words[0].start_ms == 80
    assert plan.remapped_sentences[0].words[-1].end_ms == co_dur - 80
    # First word of body sentence 0 sits at co_dur + (s0.start_ms - clip_in)
    assert plan.remapped_sentences[1].words[0].start_ms == co_dur + (s0.start_ms - clip_in)
    assert plan.remapped_sentences[-1].words[-1].end_ms == plan.output_duration_ms - 200

    _assert_zero_split_words(plan, sents)
    assert_deliverable_order(plan.remapped_sentences)

    # Confirm FFmpeg filtergraph & ASS subtitle generation accept the plan cleanly.
    filt = assembled_splice_filter(plan.spans)
    assert "concat=n=2:v=1:a=1[v_concat][a_concat]" in filt
    ass_text = build_ass(
        plan.remapped_sentences,
        clip_in_ms=0,
        clip_duration_ms=plan.output_duration_ms,
    )
    assert "Dialogue:" in ass_text
    assert "بدۆزێتەوە" in ass_text


def test_cold_open_uses_highest_energy_late_sentence_without_payoff_ms() -> None:
    """When payoff_at_ms is None, cold open picks the highest-energy late sentence (t >= 40%)."""
    s0 = _make_sentence(
        ["پێشەکی", "ئاسایی", "دەربارەی", "تەکنەلۆژیا", "لە", "جیهاندا"],
        start_ms=1_000,
        word_dur_ms=2_200,
    )
    s1 = _make_sentence(
        ["هەندێک", "زانیاری", "تەواو", "ئارام", "لە", "ناوەڕاستدا"],
        start_ms=16_000,
        word_dur_ms=2_000,
    )
    # Late high-energy 2.4s sentence at 31s (well past 40% of 37s clip)
    s2 = _make_sentence(
        ["ئەم", "گۆڕانکارییە", "هەموو", "شتێک", "دەگۆڕێت", "ئێستا"],
        start_ms=31_000,
        word_dur_ms=370,
        gap_ms=20,
    )
    s3 = _make_sentence(
        ["بەڵێ", "ئەوە", "ڕاستییەکە", "لە", "کۆتاییدا"],
        start_ms=35_000,
        word_dur_ms=500,
        gap_ms=20,
    )
    sents = (s0, s1, s2, s3)
    clip_in = 880
    clip_out = s3.end_ms + 200

    plan = plan_viral_story_cut(
        sents,
        clip_in,
        clip_out,
        payoff_at_ms=None,
        excited_intervals_ms=[(30_900, 33_500)],
        enable_cold_open=True,
        enable_condense=False,
    )

    assert plan.applied_cold_open is True
    assert plan.cold_open_text == s2.text
    assert plan.spans[0].role == "cold_open"
    _assert_zero_split_words(plan, sents)


def test_cold_open_never_starts_on_mid_clause_starter_or_ends_on_dangling_word() -> None:
    """Cold-open clause extractor rejects dependent starters and dangling closers."""
    s0 = _make_sentence(
        ["سەرەتای", "باسەکە", "لێرەدا", "دەست", "پێدەکات", "ئێستا"],
        start_ms=1_000,
        word_dur_ms=3_000,
    )
    # Late sentence with back-to-back CTC words (gap=0) containing dependent starters & prepositions
    ctc_words = (
        Word(w="چونکە", start_ms=22_000, end_ms=22_400, conf=0.95),
        Word(w="نییە", start_ms=22_400, end_ms=22_800, conf=0.95),
        Word(w="ئەم", start_ms=22_800, end_ms=23_200, conf=0.95),
        Word(w="ژیری", start_ms=23_200, end_ms=23_700, conf=0.95),
        Word(w="دەستکردە", start_ms=23_700, end_ms=24_300, conf=0.95),
        Word(w="کوردیەکەی", start_ms=24_300, end_ms=24_900, conf=0.95),
        Word(w="نایابە", start_ms=24_900, end_ms=25_400, conf=0.95),
        Word(w="و", start_ms=25_400, end_ms=25_600, conf=0.95),
        Word(w="لە", start_ms=25_600, end_ms=25_900, conf=0.95),
        Word(w="کوردستان", start_ms=25_900, end_ms=26_600, conf=0.95),
        Word(w="بڵاوە", start_ms=26_600, end_ms=27_200, conf=0.95),
    )
    s1 = Sentence(words=ctc_words, complete=True)
    sents = (s0, s1)

    plan = plan_viral_story_cut(
        sents,
        880,
        27_400,
        payoff_at_ms=24_500,
        enable_cold_open=True,
        enable_condense=False,
    )

    assert plan.applied_cold_open is True
    assert plan.cold_open_text is not None
    tokens = plan.cold_open_text.split()
    assert tokens[0] not in {"چونکە", "نییە", "و", "لە"}
    assert tokens[-1] not in {"و", "لە", "بۆ", "ئەم"}
    assert plan.cold_open_text == "ئەم ژیری دەستکردە کوردیەکەی نایابە"
    _assert_zero_split_words(plan, sents)


def test_combined_condense_and_cold_open_never_teases_dropped_tangent() -> None:
    """When both condense and cold open run, the teaser comes strictly from kept body spans."""
    s0 = _make_sentence(
        ["پێشەکی", "گرنگی", "باسەکە", "لەسەر", "کوردستانە"],
        start_ms=1_000,
        word_dur_ms=2_400,
    )  # 12s
    s1 = _make_sentence(
        ["یەعنی", "دەزانی", "وەڵا", "ئاوا", "قسان", "بوو", "جاران"],
        start_ms=14_500,
        word_dur_ms=4_800,
    )  # 33.7s middle tangent -> dropped!
    s2 = _make_sentence(
        ["کۆمپانیاکان", "کێشەی", "وەرگێڕانیان", "هەبوو", "ساڵانێک", "لێرە"],
        start_ms=50_000,
        word_dur_ms=1_500,
    )  # 9.1s bridge
    s3 = _make_sentence(
        ["ئێستا", "ژیری", "دەستکرد", "کوردیەکەی", "زۆر", "باش", "تێدەگات", "بێگومان"],
        start_ms=61_000,
        word_dur_ms=1_500,
    )  # 12.1s
    s4 = _make_sentence(
        ["هەموو", "کارەکان", "خێراتر", "دەکرێن", "بە", "دڵنیایی"],
        start_ms=75_000,
        word_dur_ms=400,
        gap_ms=20,
    )  # 2.5s punchline
    sents = (s0, s1, s2, s3, s4)
    clip_in = 880
    clip_out = s4.end_ms + 200

    plan = plan_viral_story_cut(
        sents,
        clip_in,
        clip_out,
        payoff_at_ms=76_000,
        excited_intervals_ms=[(74_900, 77_600)],
        target_max_ms=48_000,
        target_min_ms=30_000,
        enable_cold_open=True,
        enable_condense=True,
    )

    assert plan.applied_condense is True
    assert plan.applied_cold_open is True
    assert 1 in plan.dropped_sentence_indices
    assert plan.spans[0].role == "cold_open"
    assert all(sp.role == "body" for sp in plan.spans[1:])
    assert plan.cold_open_text == s4.text
    # Cold open must lie within one of the kept body spans (never inside dropped s1).
    assert any(
        sp.source_in_ms <= plan.spans[0].source_in_ms
        and plan.spans[0].source_out_ms <= sp.source_out_ms
        for sp in plan.spans[1:]
    )
    assert plan.output_duration_ms < plan.source_duration_ms
    _assert_zero_split_words(plan, sents)
    assert_deliverable_order(plan.remapped_sentences)


def test_single_sentence_flat_clip_under_target_max_returns_clean_noop() -> None:
    """Single-sentence <= 48s clip with no payoff/excitement/pauses returns clean no-op."""
    tokens = [f"وشە{i}" for i in range(60)]
    s0 = _make_sentence(tokens, start_ms=5_000, word_dur_ms=550, gap_ms=0)  # 33.0s continuous
    clip_in = 4_880
    clip_out = s0.end_ms + 200

    plan = plan_viral_story_cut(
        (s0,),
        clip_in,
        clip_out,
        payoff_at_ms=None,
        excited_intervals_ms=(),
        target_max_ms=48_000,
        enable_cold_open=True,
        enable_condense=True,
    )

    assert plan.is_noop is True
    assert plan.applied_cold_open is False
    assert plan.applied_condense is False
    assert plan.cold_open_text is None
    assert plan.kept_sentence_indices == (0,)
    assert plan.dropped_sentence_indices == ()
    assert len(plan.spans) == 1
    assert plan.spans[0].role == "body"
    assert plan.spans[0].source_in_ms == clip_in
    assert plan.spans[0].source_out_ms == clip_out
    assert plan.output_duration_ms == plan.source_duration_ms
    assert plan.remapped_sentences[0].words[0].start_ms == 120


def test_short_clip_under_25s_returns_clean_noop() -> None:
    """Clips shorter than 25 s never add a cold open or condense."""
    s0 = _make_sentence(["سەرەتای", "باس", "لێرەیە", "ئێستا"], start_ms=1_000, word_dur_ms=2_000)
    s1 = _make_sentence(["کۆتایی", "پەیامەکە", "گرنگە", "زۆر"], start_ms=10_000, word_dur_ms=2_000)
    clip_in = 880
    clip_out = s1.end_ms + 200  # ~17.4s

    plan = plan_viral_story_cut((s0, s1), clip_in, clip_out, payoff_at_ms=14_000)

    assert plan.is_noop is True
    assert plan.applied_cold_open is False
    assert plan.applied_condense is False
    assert len(plan.spans) == 1


def test_fail_stop_invalid_inputs_and_invariants() -> None:
    """Invalid parameters, incomplete sentences, and bad roles raise loudly (zero fallbacks)."""
    s0 = _make_sentence(["وشەی", "یەکەم", "تەواوە"], start_ms=1_000, word_dur_ms=500)
    incomplete = _make_sentence(
        ["نیوەچڵ", "چونکە"], start_ms=3_000, word_dur_ms=500, complete=False
    )

    with pytest.raises(ValueError, match="at least one sentence"):
        plan_viral_story_cut((), 0, 10_000)

    with pytest.raises(ValueError, match="Invalid clip range"):
        plan_viral_story_cut((s0,), 5_000, 4_000)

    with pytest.raises(ValueError, match="boundary_pad_ms"):
        plan_viral_story_cut((s0,), 900, 3_000, boundary_pad_ms=20)

    with pytest.raises(ValueError, match="boundary_pad_ms"):
        plan_viral_story_cut((s0,), 900, 3_000, boundary_pad_ms=150)

    with pytest.raises(ValueError, match="invariant #2"):
        plan_viral_story_cut((s0, incomplete), 900, 5_000)

    with pytest.raises(ValueError, match="payoff_at_ms"):
        plan_viral_story_cut((s0,), 900, 3_000, payoff_at_ms=9_999)

    with pytest.raises(ValueError, match="outside clip"):
        plan_viral_story_cut((s0,), 1_200, 3_000)

    with pytest.raises(ValueError, match="Invalid excited interval"):
        plan_viral_story_cut((s0,), 900, 3_000, excited_intervals_ms=[(2_000, 1_500)])

    with pytest.raises(ValueError, match="AssemblySpan.role"):
        AssemblySpan(
            span_index=0,
            source_in_ms=900,
            source_out_ms=3_000,
            duration_ms=2_100,
            sentences=(s0,),
            role="teaser",
        )


def test_viral_story_plan_to_dict_round_trip_structure() -> None:
    """ViralStoryPlan.to_dict() emits structured JSON-safe metadata for run artifacts."""
    s0 = _make_sentence(["پێشەکی", "کورت", "لە", "کوردستان"], start_ms=1_000, word_dur_ms=3_000)
    s1 = _make_sentence(
        ["ئەنجامی", "گرنگ", "لێرەدا", "دەردەکەوێت", "ئێستا"],
        start_ms=24_000,
        word_dur_ms=450,
        gap_ms=20,
    )
    plan = plan_viral_story_cut((s0, s1), 880, s1.end_ms + 200, payoff_at_ms=25_000)
    data = plan.to_dict()

    assert data["applied_cold_open"] is True
    assert data["applied_condense"] is False
    assert data["cold_open_text"] == s1.text
    assert data["output_duration_ms"] == plan.output_duration_ms
    assert len(data["spans"]) == 2
    assert data["spans"][0]["role"] == "cold_open"
    assert data["spans"][1]["role"] == "body"
