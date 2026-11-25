"""Tests for Lane A (D-356): multimodal acoustic discovery and teaser-overlap benchmark."""

from __future__ import annotations

import json
import wave
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from hawedit.audio_signals import (
    SentenceAudioMetrics,
    TeaserGoldSpan,
    analyze_sentence_audio,
    evaluate_teaser_overlap,
)
from hawedit.normalize import normalize_sorani
from hawedit.path_a import PathADiscovery, discover_verbal
from hawedit.sentences import Sentence, segment_sentences
from hawedit.topic_segmenter import TextTilerConfig, discover_topics
from hawedit.transcripts import (
    AsrProvenance,
    NormalizedTranscript,
    RawTranscript,
    Word,
    normalize_transcript,
)


def _write_pcm16_wav(
    path: Path,
    samples: np.ndarray[Any, np.dtype[np.float32]],
    *,
    sample_rate: int = 16_000,
    channels: int = 1,
) -> None:
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype("<i2")
    if channels > 1:
        pcm = np.repeat(pcm[:, np.newaxis], channels, axis=1).reshape(-1)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())


def _make_sentence(
    tokens: list[str], start_ms: int, end_ms: int, *, complete: bool = True
) -> Sentence:
    step = max(1, (end_ms - start_ms) // max(1, len(tokens)))
    words: list[Word] = []
    cur = start_ms
    for idx, tok in enumerate(tokens):
        w_end = end_ms if idx == len(tokens) - 1 else cur + step
        words.append(Word(w=tok, start_ms=cur, end_ms=w_end, conf=0.95))
        cur = w_end
    return Sentence(words=tuple(words), complete=complete)


def _make_transcript(
    sentence_specs: list[tuple[list[str], int, int]],
    media_id: str = "ep-c10",
) -> NormalizedTranscript:
    words: list[Word] = []
    texts: list[str] = []
    for tokens, start_ms, end_ms in sentence_specs:
        sent = _make_sentence(tokens, start_ms, end_ms)
        words.extend(sent.words)
        texts.append(" ".join(tokens))
    raw = RawTranscript(
        media_id=media_id,
        text_ckb=" ".join(texts),
        words=tuple(words),
        asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi"),
    )
    return normalize_transcript(raw)


class _RecordingApi:
    """Offline Path A transport capturing prompts and returning canned sentence candidates."""

    def __init__(self, payload: list[dict[str, Any]] | None = None) -> None:
        self.payload = (
            payload
            if payload is not None
            else [{"start_sentence": 0, "end_sentence": 1, "score": 0.9, "reason_ckb": "خاڵی گرنگ"}]
        )
        self.bodies: list[dict[str, Any]] = []

    def __call__(
        self, url: str, body: bytes | None, _headers: Mapping[str, str]
    ) -> tuple[int, str]:
        if body:
            self.bodies.append(json.loads(body))
        if "countTokens" in url:
            return 200, json.dumps({"totalTokens": 1_500})
        return 200, json.dumps(
            {
                "candidates": [
                    {"content": {"parts": [{"text": json.dumps({"candidates": self.payload})}]}}
                ]
            }
        )

    @property
    def prompt(self) -> str:
        return str(self.bodies[-1]["contents"][0]["parts"][0]["text"])


def test_analyze_sentence_audio_detects_energy_peaks_and_rate(tmp_path: Path) -> None:
    """AC-A1: Deterministic CPU profiler computes rms_z, 100ms bursts, speech rate, and pauses."""
    sr = 16_000
    total_s = 12.0
    t = np.arange(int(sr * total_s), dtype=np.float32) / sr
    # Calm background speech level (~0.04 amplitude) across the full 12s clip.
    signal = (0.04 * np.sin(2.0 * np.pi * 220.0 * t)).astype(np.float32)

    # Sentence 3 (7.2s..9.2s): sustained higher energy + 3 distinct 100ms vocal bursts.
    s3_lo, s3_hi = int(7.2 * sr), int(9.2 * sr)
    signal[s3_lo:s3_hi] = (0.18 * np.sin(2.0 * np.pi * 330.0 * t[s3_lo:s3_hi])).astype(np.float32)
    for burst_start_s in (7.4, 8.0, 8.6):
        b_lo = int(burst_start_s * sr)
        b_hi = b_lo + int(0.1 * sr)
        signal[b_lo:b_hi] = (0.85 * np.sin(2.0 * np.pi * 440.0 * t[b_lo:b_hi])).astype(np.float32)

    wav_mono = tmp_path / "audio_mono.wav"
    wav_stereo = tmp_path / "audio_stereo.wav"
    _write_pcm16_wav(wav_mono, signal, sample_rate=sr, channels=1)
    _write_pcm16_wav(wav_stereo, signal, sample_rate=sr, channels=2)

    sentences = (
        _make_sentence(["ئەمە", "یەکەم", "ڕستەیە."], 0, 2_000),  # 1.5 wps
        _make_sentence(["ئەمە", "دووەم", "ڕستەیە."], 2_100, 4_000),  # 100 ms pause
        _make_sentence(["ئەمە", "سێیەم", "ڕستەیە."], 4_200, 6_000),  # 200 ms pause
        # 1_200 ms dramatic pause before sentence 3; 8 words in 2.0s => 4.0 wps ("fast")
        _make_sentence(
            ["بەڕاستی", "ئەمە", "خاڵێکی", "زۆر", "سەیر", "و", "گرنگ", "بوو!"],
            7_200,
            9_200,
        ),
        _make_sentence(["لە", "کۆتاییدا", "تەواو."], 9_500, 11_500),
    )

    metrics = analyze_sentence_audio(wav_mono, sentences)
    metrics_repeat = analyze_sentence_audio(wav_mono, sentences)
    metrics_stereo = analyze_sentence_audio(wav_stereo, sentences)

    assert metrics == metrics_repeat
    assert metrics == metrics_stereo
    assert len(metrics) == len(sentences)
    assert [m.sentence_index for m in metrics] == [0, 1, 2, 3, 4]

    calm = metrics[0]
    excited = metrics[3]

    assert calm.pause_before_ms == 0
    assert excited.pause_before_ms == 1_200
    assert calm.tags == ()
    assert excited.rms_z >= 1.0
    assert excited.peak_burst_count == 3
    assert excited.speech_rate_wps == pytest.approx(4.0, abs=0.05)
    assert excited.tags == ("high-energy", "burst", "fast")
    assert excited.rms_db > calm.rms_db
    assert 0.0 <= calm.excitement_score < excited.excitement_score <= 1.0

    # Empty sentence list returns (); empty WAV or missing file fails-stop.
    assert analyze_sentence_audio(wav_mono, ()) == ()
    empty_wav = tmp_path / "empty.wav"
    _write_pcm16_wav(empty_wav, np.empty(0, dtype=np.float32), sample_rate=sr)
    with pytest.raises(ValueError, match="zero frames"):
        analyze_sentence_audio(empty_wav, sentences)
    with pytest.raises(FileNotFoundError):
        analyze_sentence_audio(tmp_path / "missing.wav", sentences)


def test_evaluate_teaser_overlap_computes_precision_recall_and_hits() -> None:
    """AC-A3: Deterministic precision, recall, F1, hits, and per-gold overlap coverage."""
    golds = (
        TeaserGoldSpan(label="g1", start_ms=10_000, end_ms=16_000),  # 6s
        TeaserGoldSpan(label="g2", start_ms=50_000, end_ms=58_000),  # 8s
        TeaserGoldSpan(label="g3", start_ms=100_000, end_ms=105_000),  # 5s
    )
    preds = (
        (8_000, 14_000),  # overlaps g1 by 4_000 ms (hit)
        (57_000, 75_000),  # overlaps g2 by 1_000 ms (< 1_500 ms threshold -> miss)
        (98_000, 120_000),  # overlaps g3 by 5_000 ms (hit)
        (200_000, 240_000),  # false positive (miss)
    )

    report = evaluate_teaser_overlap(preds, golds, min_overlap_ms=1_500)
    assert report.predicted_count == 4
    assert report.gold_count == 3
    assert report.hits == 2
    assert report.precision == pytest.approx(0.5, abs=1e-4)
    assert report.recall == pytest.approx(2.0 / 3.0, abs=1e-4)
    expected_f1 = 2.0 * 0.5 * (2.0 / 3.0) / (0.5 + 2.0 / 3.0)
    assert report.f1 == pytest.approx(expected_f1, abs=1e-4)
    assert report.per_gold_overlap_ms == (("g1", 4_000), ("g2", 1_000), ("g3", 5_000))

    # One long clip spanning two nearby gold spans keeps precision <= 1.0 and merges overlap.
    nearby_golds = (
        TeaserGoldSpan(label="a", start_ms=10_000, end_ms=14_000),
        TeaserGoldSpan(label="b", start_ms=20_000, end_ms=25_000),
    )
    multi = evaluate_teaser_overlap(((8_000, 30_000),), nearby_golds, min_overlap_ms=1_500)
    assert multi.hits == 2
    assert multi.recall == 1.0
    assert multi.precision == 1.0
    assert multi.f1 == 1.0
    assert multi.per_gold_overlap_ms == (("a", 4_000), ("b", 5_000))

    # Empty inputs produce clean zeros; invalid arguments fail-stop.
    empty = evaluate_teaser_overlap((), golds)
    assert empty.hits == 0 and empty.precision == 0.0 and empty.recall == 0.0 and empty.f1 == 0.0
    with pytest.raises(ValueError, match="min_overlap_ms"):
        evaluate_teaser_overlap(preds, golds, min_overlap_ms=0)
    with pytest.raises(ValueError, match="Invalid predicted span"):
        evaluate_teaser_overlap(((5_000, 5_000),), golds)


def test_path_a_annotates_high_energy_and_burst_sentences(tmp_path: Path) -> None:
    """AC-A2 (Path A): Acoustic tags annotate matching lines and preserve text-only callers."""
    transcript = _make_transcript(
        [
            (["ڕۆژنامەوانی", "کوردی", "لە", "هەولێر."], 0, 2_000),
            (["ئەمە", "خاڵی", "هەرە", "گرنگە", "بۆ", "ئێمە."], 2_500, 4_500),
            (["با", "بە", "وردی", "باسی", "بکەین."], 5_000, 7_000),
        ],
        media_id="ep-path-a-audio",
    )
    sentences = segment_sentences(transcript.words)
    metrics = (
        SentenceAudioMetrics(
            sentence_index=0,
            rms_db=-24.0,
            rms_z=-0.5,
            peak_burst_count=0,
            speech_rate_wps=2.0,
            pause_before_ms=0,
            excitement_score=0.25,
            tags=(),
        ),
        SentenceAudioMetrics(
            sentence_index=1,
            rms_db=-10.0,
            rms_z=1.8,
            peak_burst_count=3,
            speech_rate_wps=3.5,
            pause_before_ms=500,
            excitement_score=0.90,
            tags=("high-energy", "burst", "fast"),
        ),
        SentenceAudioMetrics(
            sentence_index=2,
            rms_db=-22.0,
            rms_z=0.1,
            peak_burst_count=0,
            speech_rate_wps=2.5,
            pause_before_ms=500,
            excitement_score=0.38,
            tags=(),
        ),
    )

    api_plain = _RecordingApi()
    PathADiscovery(api_key="test-key", transport=api_plain, sleep=lambda _s: None, k=1).discover(
        transcript, sentences=sentences
    )
    assert "[high-energy" not in api_plain.prompt
    assert "30–55 s" not in api_plain.prompt

    api_audio = _RecordingApi()
    found = discover_verbal(
        transcript,
        api_key="test-key",
        transport=api_audio,
        sleep=lambda _s: None,
        k=1,
        sentences=sentences,
        audio_metrics=metrics,
    )
    assert len(found) == 1
    assert f"[0] {normalize_sorani(sentences[0].text)} (2.0s)\n" in api_audio.prompt
    assert (
        f"[1] {normalize_sorani(sentences[1].text)} (2.0s) [high-energy, burst, fast]"
        in api_audio.prompt
    )
    assert f"[2] {normalize_sorani(sentences[2].text)} (2.0s)" in api_audio.prompt
    assert "[2] " in api_audio.prompt and "[high-energy" not in api_audio.prompt.split("[2] ")[1]
    assert "30–55 s" in api_audio.prompt

    # Cache digest separates text-only and multimodal calls cleanly.
    api_c1 = _RecordingApi()
    c1 = PathADiscovery(
        api_key="test-key", transport=api_c1, sleep=lambda _s: None, k=2, cache_dir=tmp_path
    )
    c1.discover(transcript, sentences=sentences)
    assert len(c1.billed_calls) == 2

    api_c2 = _RecordingApi()
    c2 = PathADiscovery(
        api_key="test-key", transport=api_c2, sleep=lambda _s: None, k=2, cache_dir=tmp_path
    )
    c2.discover(transcript, sentences=sentences, audio_metrics=metrics)
    assert len(c2.billed_calls) == 2, "multimodal audio_metrics must not reuse text-only cache"


def test_discover_topics_boosts_high_energy_viral_duration_candidates() -> None:
    """AC-A2 (C4): Acoustic excitement + 35-65s viral preference boost C4 candidate ranking."""
    # Topic A: 4 sentences spanning 86s (outside 35-65s sweet spot) — quiet delivery.
    topic_a = [
        (["پەرەپێدانی", "ژیری", "دەستکرد", "گرنگە."], 0, 21_000),
        (["مۆدێلی", "ژیری", "دەستکرد", "خێرایە."], 22_000, 43_000),
        (["پڕۆگرامسازی", "ئەمڕۆ", "ژیری", "دەوێت."], 44_000, 64_000),
        (["ئامرازی", "تازەی", "ژیری", "دروستکرا."], 65_000, 86_000),
    ]
    # Topic B: 4 sentences spanning 48s (right inside 35-65s viral sweet spot) — high energy.
    topic_b = [
        (["چێشتخانەی", "کوردی", "خواردنی", "بەتامە."], 87_000, 98_000),
        (["برنج", "و", "کەباب", "خۆشە."], 99_000, 110_000),
        (["چێشتلێنان", "هونەرێکی", "کۆنە."], 111_000, 122_000),
        (["خواردنی", "نیوەڕۆ", "ئامادەیە."], 123_000, 135_000),
    ]
    transcript = _make_transcript(topic_a + topic_b, media_id="ep-c4-audio")
    sentences = segment_sentences(transcript.words)
    assert len(sentences) == 8

    cfg = TextTilerConfig(block_size=3, min_span_ms=30_000, max_span_ms=90_000)
    baseline = discover_topics(transcript, sentences=sentences, config=cfg)
    assert len(baseline) == 2

    metrics = tuple(
        SentenceAudioMetrics(
            sentence_index=idx,
            rms_db=-26.0 if idx < 4 else -9.0,
            rms_z=-0.8 if idx < 4 else 1.9,
            peak_burst_count=0 if idx < 4 else 3,
            speech_rate_wps=1.5 if idx < 4 else 3.6,
            pause_before_ms=0 if idx == 0 else 1_000,
            excitement_score=0.15 if idx < 4 else 0.92,
            tags=() if idx < 4 else ("high-energy", "burst", "fast"),
        )
        for idx in range(len(sentences))
    )

    fused = discover_topics(transcript, sentences=sentences, config=cfg, audio_metrics=metrics)
    assert len(fused) == 2
    assert fused[0].span == (87_000, 135_000), "high-energy 48s viral topic must rank #1"
    assert fused[1].span == (0, 86_000)
    assert fused[0].score is not None and fused[1].score is not None
    assert 0.0 <= fused[1].score < fused[0].score <= 1.0
    assert fused[0].score - fused[1].score >= 0.20

    # Verify viral 35-65s duration preference works even when excitement is equal.
    equal_metrics = tuple(
        SentenceAudioMetrics(
            sentence_index=idx,
            rms_db=-16.0,
            rms_z=0.5,
            peak_burst_count=1,
            speech_rate_wps=2.5,
            pause_before_ms=0,
            excitement_score=0.60,
            tags=(),
        )
        for idx in range(len(sentences))
    )
    by_span_base = {c.span: c.score for c in baseline}
    by_span_dur = {
        c.span: c.score
        for c in discover_topics(
            transcript, sentences=sentences, config=cfg, audio_metrics=equal_metrics
        )
    }
    b_base = by_span_base[(87_000, 135_000)]
    a_base = by_span_base[(0, 86_000)]
    b_dur = by_span_dur[(87_000, 135_000)]
    a_dur = by_span_dur[(0, 86_000)]
    assert b_base is not None and a_base is not None and b_dur is not None and a_dur is not None
    assert (b_dur - a_dur) > (b_base - a_base), "48s viral span must gain relative to 86s span"


def test_path_a_k_voting_tolerates_single_transient_unusable_run() -> None:
    """K-run voting survives a single transient JudgeUnusable run when >= min_votes succeed."""
    from hawedit.gemini import JudgeUnusable

    transcript = _make_transcript(
        [
            (["ڕۆژنامەوانی", "کوردی", "لە", "هەولێر."], 0, 2_000),
            (["ئەمە", "خاڵی", "هەرە", "گرنگە."], 2_500, 4_500),
            (["با", "بە", "وردی", "باسی", "بکەین."], 5_000, 7_000),
        ],
        media_id="ep-path-a-flaky",
    )
    sentences = segment_sentences(transcript.words)
    good_payload = json.dumps(
        {
            "candidates": [
                {"start_sentence": 0, "end_sentence": 2, "score": 0.9, "reason_ckb": "خاڵی گرنگ"}
            ]
        }
    )

    class _FlakyApi:
        def __init__(self, fail_calls: set[int]) -> None:
            self.fail_calls = fail_calls
            self.calls = 0

        def __call__(
            self, url: str, body: bytes | None, _headers: Mapping[str, str]
        ) -> tuple[int, str]:
            if "countTokens" in url:
                return 200, json.dumps({"totalTokens": 1_500})
            self.calls += 1
            if self.calls in self.fail_calls:
                return 200, json.dumps({"candidates": [{"content": {"parts": [{"text": "bad"}]}}]})
            return 200, json.dumps(
                {"candidates": [{"content": {"parts": [{"text": good_payload}]}}]}
            )

    # 1 bad run out of 5 still leaves 4 >= min_votes (3) -> succeeds cleanly.
    resilient = PathADiscovery(
        api_key="test-key",
        transport=_FlakyApi({2}),
        sleep=lambda _s: None,
        k=5,
        min_votes=3,
    )
    found = resilient.discover(transcript, sentences=sentences)
    assert len(found) == 1
    assert found[0].span == (0, 7_000)

    # 3 bad runs out of 5 leaves only 2 < min_votes (3) -> strict fail-stop.
    broken = PathADiscovery(
        api_key="test-key",
        transport=_FlakyApi({1, 2, 3}),
        sleep=lambda _s: None,
        k=5,
        min_votes=3,
    )
    with pytest.raises(JudgeUnusable):
        broken.discover(transcript, sentences=sentences)
