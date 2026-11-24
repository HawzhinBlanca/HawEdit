"""Tests for C4 topic-segmentation candidate discovery (MIT TextTiling, zero API/GPU)."""

from __future__ import annotations

import pytest

from hawedit.clip import DiscoveryPath
from hawedit.discovery import Candidate, merge_candidates
from hawedit.sentences import Sentence, segment_sentences
from hawedit.topic_segmenter import (
    SoraniTfIdfEmbedder,
    TextTilerConfig,
    discover_topics,
    text_tile_depths,
)
from hawedit.transcripts import (
    AsrProvenance,
    NormalizedTranscript,
    RawTranscript,
    Word,
    normalize_transcript,
)


def _make_transcript(
    sentence_specs: list[tuple[list[str], int, int]],
    media_id: str = "ep-c4",
) -> NormalizedTranscript:
    words: list[Word] = []
    texts: list[str] = []
    for tokens, start_ms, end_ms in sentence_specs:
        step = max(1, (end_ms - start_ms) // max(1, len(tokens)))
        cur = start_ms
        for idx, tok in enumerate(tokens):
            w_end = end_ms if idx == len(tokens) - 1 else cur + step
            words.append(Word(w=tok, start_ms=cur, end_ms=w_end, conf=0.95))
            cur = w_end
        texts.append(" ".join(tokens))
    raw = RawTranscript(
        media_id=media_id,
        text_ckb=" ".join(texts),
        words=tuple(words),
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
    )
    return normalize_transcript(raw)


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    return sum(val * b.get(key, 0.0) for key, val in a.items())


def test_topic_segmenter_refuses_raw_transcript() -> None:
    """AC1: Invariant #3 refuses RawTranscript before embedding or discovery."""
    raw = RawTranscript(
        media_id="ep-raw",
        text_ckb="ئەمە تەواوە.",
        words=(
            Word(w="ئەمە", start_ms=0, end_ms=500, conf=0.9),
            Word(w="تەواوە.", start_ms=500, end_ms=1_200, conf=0.9),
        ),
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
    )
    with pytest.raises(TypeError, match="norm"):
        discover_topics(raw)  # type: ignore[arg-type]


def test_sorani_embedder_captures_topic_cohesion_with_clitics() -> None:
    """AC2: §4.1 tokens and 3-grams group clitic variants over unrelated topics."""
    embedder = SoraniTfIdfEmbedder()
    vectors = embedder.embed(
        [
            "كتێب خوێندنەوە زانستە.",  # Arabic kaf + clitic base
            "کتێبەکەم بۆ خوێندنەوەیە.",  # Normalized Sorani kaf + possessive clitic
            "هەسارە و گەردوون و ئەستێرەکان.",  # Distinct astronomy topic
        ]
    )
    assert len(vectors) == 3
    same_topic_sim = _cosine(vectors[0], vectors[1])
    diff_topic_sim = _cosine(vectors[0], vectors[2])
    assert same_topic_sim > diff_topic_sim
    assert same_topic_sim > 0.2


def test_texttiler_splits_at_topic_shift_with_sentence_complete_spans() -> None:
    """AC3: Sharp topic transition produces a TextTiling depth peak and sentence-complete spans."""
    topic_a = [
        (["پەرەپێدانی", "ژیری", "دەستکرد", "گرنگە."], 0, 10_000),
        (["مۆدێلی", "ژیری", "دەستکرد", "خێرایە."], 11_000, 22_000),
        (["پڕۆگرامسازی", "ئەمڕۆ", "ژیری", "دەوێت."], 23_000, 34_000),
        (["ئامرازی", "تازەی", "ژیری", "دروستکرا."], 35_000, 45_000),
    ]
    topic_b = [
        (["چێشتخانەی", "کوردی", "خواردنی", "بەتامە."], 46_000, 58_000),
        (["برنج", "و", "کەباب", "خۆشە."], 59_000, 70_000),
        (["چێشتلێنان", "هونەرێکی", "کۆنە."], 71_000, 82_000),
        (["خواردنی", "نیوەڕۆ", "ئامادەیە."], 83_000, 95_000),
    ]
    transcript = _make_transcript(topic_a + topic_b)
    sentences = segment_sentences(transcript.words)
    assert len(sentences) == 8

    # Check raw depth profile peaks cleanly at sentence gap 3 (end of topic_a / start of topic_b)
    vecs = SoraniTfIdfEmbedder().embed([s.text for s in sentences])
    depths = text_tile_depths(vecs, block_size=3, smoothing_passes=1)
    assert len(depths) == 7
    assert depths[3] == max(depths)

    cands = discover_topics(
        transcript,
        sentences=sentences,
        config=TextTilerConfig(block_size=3, min_span_ms=30_000, max_span_ms=90_000),
    )
    assert len(cands) == 2
    assert cands[0].path is DiscoveryPath.VERBAL
    assert {c.span for c in cands} == {(0, 45_000), (46_000, 95_000)}
    assert all("topic" in c.candidate_id for c in cands)
    assert [c.rank for c in cands] == [1, 2]


def test_topic_segments_respect_min_and_max_duration_bounds() -> None:
    """AC4: Over-long topics split cleanly and under-short topics merge along sentences."""
    # Create 12 sentences spanning ~180s across multiple topics.
    specs: list[tuple[list[str], int, int]] = []
    # Topic A: 8 sentences = 120s (> 90s max) with slight internal sub-shift at index 3..4
    for idx in range(8):
        vocab = (
            ["سیاسەت", "یاسا", "پەرلەمان", f"w{idx}."]
            if idx < 4
            else ["ئابووری", "بازاڕ", "دراو", f"w{idx}."]
        )
        specs.append((vocab, idx * 15_000, idx * 15_000 + 14_000))
    # Topic B (tiny 8s slice) + Topic C (40s)
    specs.append((["نان", "چا", "خواردن."], 120_000, 128_000))
    specs.append((["وێنە", "سینەما", "شانۆ."], 129_000, 149_000))
    specs.append((["ئەکتەر", "سینەما", "فیلم."], 150_000, 169_000))

    transcript = _make_transcript(specs)
    sentences = segment_sentences(transcript.words)
    cands = discover_topics(
        transcript,
        sentences=sentences,
        config=TextTilerConfig(block_size=2, min_span_ms=30_000, max_span_ms=90_000),
    )
    assert cands
    valid_starts = {s.start_ms for s in sentences}
    valid_ends = {s.end_ms for s in sentences}
    for cand in cands:
        dur = cand.out_ms - cand.in_ms
        assert 30_000 <= dur <= 90_000, cand
        assert cand.in_ms in valid_starts
        assert cand.out_ms in valid_ends


def test_topic_segmenter_handles_short_inputs_and_refuses_invalid_params() -> None:
    """AC6: Too-short inputs emit (); invalid block_size or min_span_ms raise ValueError."""
    with pytest.raises(ValueError, match="block_size"):
        TextTilerConfig(block_size=0)
    with pytest.raises(ValueError, match="min_span_ms"):
        TextTilerConfig(min_span_ms=0)
    with pytest.raises(ValueError, match="max_span_ms"):
        TextTilerConfig(min_span_ms=40_000, max_span_ms=30_000)

    short = _make_transcript(
        [
            (["سڵاو", "هاوڕێ."], 0, 5_000),
            (["چۆنیت", "ئەمڕۆ."], 6_000, 12_000),
        ]
    )
    assert discover_topics(short) == ()

    # Incomplete trailing fragment must never enter candidates; leaving too little duration emits ()
    frag_only = _make_transcript([(["تەواو", "نەبوو"], 0, 40_000)])
    frag_sents = (Sentence(words=frag_only.words, complete=False),)
    assert discover_topics(frag_only, sentences=frag_sents) == ()


def test_topic_candidates_merge_with_path_a_preserving_unique_wins() -> None:
    """AC5: Path A keeps rank precedence over C4 while union drops nothing."""
    from hawedit.discovery import combine_verbal_candidates

    path_a = [
        Candidate("ep-c4-verbal-1", "ep-c4", 0, 35_000, DiscoveryPath.VERBAL, rank=1, score=0.9),
    ]
    c4_topics = [
        Candidate("ep-c4-topic-1", "ep-c4", 0, 35_000, DiscoveryPath.VERBAL, rank=1, score=0.8),
        Candidate(
            "ep-c4-topic-2", "ep-c4", 60_000, 95_000, DiscoveryPath.VERBAL, rank=2, score=0.7
        ),
    ]
    combined = combine_verbal_candidates(path_a, c4_topics)
    assert [c.candidate_id for c in combined] == [
        "ep-c4-verbal-1",
        "ep-c4-topic-1",
        "ep-c4-topic-2",
    ]
    assert [c.rank for c in combined] == [1, 2, 3]

    # Visual candidate matching 0..35_000 MUST be claimed by Path A rank 1, not C4 topic-1
    visual = [
        Candidate("ep-c4-visual-1", "ep-c4", 0, 35_000, DiscoveryPath.VISUAL, rank=1, score=0.85)
    ]
    merged = merge_candidates(list(combined), visual)
    by_id = {m.candidate_id: m for m in merged}
    assert by_id["ep-c4-verbal-1"].discovery_path is DiscoveryPath.BOTH
    assert by_id["ep-c4-topic-2"].discovery_path is DiscoveryPath.VERBAL
    assert len(merged) == 3
