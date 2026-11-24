"""§3 Stage 3 C4 — zero-API topic-segmentation candidate discovery (MIT TextTiling).

Clean-room Hearst (1997) TextTiling over sentence embeddings with zero AGPL code, zero cloud API
calls, and zero GPU requirements. Defaults to a Sorani-aware TF-IDF embedder built from
`hawedit.index`'s normalized word tokens and boundary-padded character 3-grams behind a pluggable
`SentenceEmbedder` protocol (D-345).

Every emitted candidate spans a contiguous run of complete sentences (`Sentence.complete == True`),
mapped deterministically to CTC word boundaries (`start_ms .. end_ms`) and tagged with
`DiscoveryPath.VERBAL` so Stage 3 merges them alongside Path A without changing §5's path enum.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from hawedit.audio_signals import SentenceAudioMetrics
from hawedit.clip import MAX_CANDIDATE_SPAN_MS, MIN_CANDIDATE_SPAN_MS, DiscoveryPath
from hawedit.discovery import Candidate
from hawedit.index import (
    DEFAULT_NGRAM_SIZE,
    DEFAULT_NGRAM_WEIGHT,
    character_ngrams,
    index_tokens,
)
from hawedit.normalize import normalize_sorani
from hawedit.sentences import Sentence, segment_sentences
from hawedit.transcripts import NormalizedTranscript, assert_model_input

__all__ = [
    "SentenceEmbedder",
    "SoraniTfIdfEmbedder",
    "TextTilerConfig",
    "discover_topics",
    "text_tile_depths",
]

EmbeddingVector = Mapping[str, float] | Sequence[float]


class SentenceEmbedder(Protocol):
    """Protocol for producing comparable sentence embeddings (sparse mappings or dense vectors)."""

    def embed(self, sentences: Sequence[str]) -> Sequence[EmbeddingVector]:
        """Return one embedding vector per input sentence in order."""


@dataclass(frozen=True, slots=True)
class TextTilerConfig:
    """Configuration for Hearst TextTiling block scoring and clip duration bounds."""

    block_size: int = 3
    smoothing_passes: int = 1
    threshold_std_factor: float = 0.5
    min_span_ms: int = MIN_CANDIDATE_SPAN_MS
    max_span_ms: int = MAX_CANDIDATE_SPAN_MS

    def __post_init__(self) -> None:
        if isinstance(self.block_size, bool) or self.block_size < 1:
            raise ValueError(f"block_size must be at least 1, got {self.block_size}")
        if isinstance(self.smoothing_passes, bool) or self.smoothing_passes < 0:
            raise ValueError(f"smoothing_passes must be non-negative, got {self.smoothing_passes}")
        if not math.isfinite(self.threshold_std_factor) or self.threshold_std_factor < 0.0:
            raise ValueError(
                f"threshold_std_factor must be finite and non-negative, "
                f"got {self.threshold_std_factor}"
            )
        if isinstance(self.min_span_ms, bool) or self.min_span_ms <= 0:
            raise ValueError(f"min_span_ms must be positive, got {self.min_span_ms}")
        if isinstance(self.max_span_ms, bool) or self.max_span_ms < self.min_span_ms:
            raise ValueError(
                f"max_span_ms ({self.max_span_ms}) must be >= min_span_ms ({self.min_span_ms})"
            )


class SoraniTfIdfEmbedder:
    """Offline, CPU-only Sorani embedder combining §4.1 word tokens and character n-grams."""

    def __init__(
        self,
        *,
        ngram_size: int = DEFAULT_NGRAM_SIZE,
        ngram_weight: float = DEFAULT_NGRAM_WEIGHT,
    ) -> None:
        if ngram_size < 1:
            raise ValueError(f"ngram_size must be at least 1, got {ngram_size}")
        if not math.isfinite(ngram_weight) or ngram_weight < 0.0:
            raise ValueError(f"ngram_weight must be non-negative finite, got {ngram_weight}")
        self.ngram_size = ngram_size
        self.ngram_weight = ngram_weight

    def embed(self, sentences: Sequence[str]) -> tuple[dict[str, float], ...]:
        """Return L2-normalized sparse TF-IDF vectors over words and character n-grams."""
        n_docs = len(sentences)
        if n_docs == 0:
            return ()

        doc_terms: list[dict[str, float]] = []
        df: Counter[str] = Counter()
        for sentence in sentences:
            counts: dict[str, float] = {}
            tokens = index_tokens(sentence)
            for token in tokens:
                w_key = f"w:{token}"
                counts[w_key] = counts.get(w_key, 0.0) + 1.0
                if self.ngram_weight > 0.0:
                    for gram in character_ngrams(token, size=self.ngram_size):
                        g_key = f"g:{gram}"
                        counts[g_key] = counts.get(g_key, 0.0) + self.ngram_weight
            doc_terms.append(counts)
            for key in counts:
                df[key] += 1

        vectors: list[dict[str, float]] = []
        for counts in doc_terms:
            if not counts:
                vectors.append({})
                continue
            weighted: dict[str, float] = {}
            norm_sq = 0.0
            for key, tf in counts.items():
                idf = math.log((1.0 + n_docs) / (1.0 + df[key])) + 1.0
                val = tf * idf
                weighted[key] = val
                norm_sq += val * val
            if norm_sq <= 0.0:
                vectors.append({})
                continue
            inv_norm = 1.0 / math.sqrt(norm_sq)
            vectors.append({key: val * inv_norm for key, val in weighted.items()})
        return tuple(vectors)


def _to_sparse_unit(
    vector: EmbeddingVector, expected_dense_dim: int | None
) -> tuple[dict[str, float], int | None]:
    sparse: dict[str, float] = {}
    if isinstance(vector, Mapping):
        for raw_key, raw_val in vector.items():
            val = float(raw_val)
            if not math.isfinite(val):
                raise ValueError(f"embedding contains non-finite value {val!r} at {raw_key!r}")
            if val != 0.0:
                sparse[str(raw_key)] = val
        return sparse, expected_dense_dim

    dense_len = len(vector)
    if expected_dense_dim is not None and dense_len != expected_dense_dim:
        raise ValueError(
            f"inconsistent dense embedding dimensions: expected {expected_dense_dim}, "
            f"got {dense_len}"
        )
    for idx, raw_val in enumerate(vector):
        val = float(raw_val)
        if not math.isfinite(val):
            raise ValueError(f"embedding contains non-finite value {val!r} at index {idx}")
        if val != 0.0:
            sparse[f"d:{idx}"] = val
    return sparse, dense_len


def _sparse_cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    dot = sum(val * b.get(key, 0.0) for key, val in a.items())
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0
    return max(-1.0, min(1.0, dot / (norm_a * norm_b)))


def _mean_sparse_unit(vectors: Sequence[dict[str, float]]) -> dict[str, float]:
    acc: dict[str, float] = {}
    for vec in vectors:
        for key, val in vec.items():
            acc[key] = acc.get(key, 0.0) + val
    norm_sq = sum(v * v for v in acc.values())
    if norm_sq <= 0.0:
        return {}
    inv = 1.0 / math.sqrt(norm_sq)
    return {k: v * inv for k, v in acc.items() if v != 0.0}


def text_tile_depths(
    vectors: Sequence[EmbeddingVector],
    *,
    block_size: int = 3,
    smoothing_passes: int = 1,
) -> tuple[float, ...]:
    """Compute Hearst (1997) TextTiling depth scores for each adjacent sentence gap."""
    if block_size < 1:
        raise ValueError(f"block_size must be at least 1, got {block_size}")
    if smoothing_passes < 0:
        raise ValueError(f"smoothing_passes must be non-negative, got {smoothing_passes}")
    if len(vectors) < 2:
        return ()

    sparse_vecs: list[dict[str, float]] = []
    dense_dim: int | None = None
    for vec in vectors:
        sparse, dense_dim = _to_sparse_unit(vec, dense_dim)
        sparse_vecs.append(sparse)

    n_gaps = len(sparse_vecs) - 1
    sims: list[float] = []
    for gap in range(n_gaps):
        left_block = _mean_sparse_unit(sparse_vecs[max(0, gap - block_size + 1) : gap + 1])
        right_block = _mean_sparse_unit(
            sparse_vecs[gap + 1 : min(len(sparse_vecs), gap + 1 + block_size)]
        )
        sims.append(_sparse_cosine(left_block, right_block))

    smoothed = sims
    for _ in range(smoothing_passes):
        next_s: list[float] = []
        for idx in range(n_gaps):
            left = smoothed[max(0, idx - 1)]
            center = smoothed[idx]
            right = smoothed[min(n_gaps - 1, idx + 1)]
            next_s.append(0.25 * left + 0.50 * center + 0.25 * right)
        smoothed = next_s

    depths: list[float] = []
    for gap in range(n_gaps):
        left_peak = smoothed[gap]
        pos = gap
        while pos > 0 and smoothed[pos - 1] >= left_peak:
            pos -= 1
            left_peak = smoothed[pos]

        right_peak = smoothed[gap]
        pos = gap
        while pos < n_gaps - 1 and smoothed[pos + 1] >= right_peak:
            pos += 1
            right_peak = smoothed[pos]

        depth = max(0.0, (left_peak - smoothed[gap]) + (right_peak - smoothed[gap]))
        depths.append(depth)
    return tuple(depths)


def _complete_sentence_runs(
    sentences: Sequence[Sentence],
) -> list[tuple[tuple[int, Sentence], ...]]:
    runs: list[tuple[tuple[int, Sentence], ...]] = []
    current: list[tuple[int, Sentence]] = []
    for idx, sent in enumerate(sentences):
        if sent.complete:
            current.append((idx, sent))
        else:
            if current:
                runs.append(tuple(current))
                current = []
    if current:
        runs.append(tuple(current))
    return runs


def _viral_duration_score(duration_ms: int) -> float:
    """Smooth viral-duration preference peaking at 1.0 across 35-65 s."""
    dur_s = max(0.0, duration_ms / 1000.0)
    if 35.0 <= dur_s <= 65.0:
        return 1.0
    if dur_s < 35.0:
        return math.exp(-0.5 * ((35.0 - dur_s) / 15.0) ** 2)
    return math.exp(-0.5 * ((dur_s - 65.0) / 20.0) ** 2)


def _span_duration_ms(run: Sequence[Sentence], start_idx: int, end_idx: int) -> int:
    return run[end_idx].end_ms - run[start_idx].start_ms


def _split_segment_if_overlong(
    run: Sequence[Sentence],
    depths: Sequence[float],
    start_idx: int,
    end_idx: int,
    min_span_ms: int,
    max_span_ms: int,
) -> list[tuple[int, int]]:
    stack = [(start_idx, end_idx)]
    result: list[tuple[int, int]] = []
    while stack:
        lo, hi = stack.pop()
        if hi <= lo or _span_duration_ms(run, lo, hi) <= max_span_ms:
            result.append((lo, hi))
            continue

        target_mid_ms = 0.5 * (run[lo].start_ms + run[hi].end_ms)
        # Prefer interior cut preserving >= min_span_ms on both sides, highest depth first.
        both_valid = [
            gap
            for gap in range(lo, hi)
            if _span_duration_ms(run, lo, gap) >= min_span_ms
            and _span_duration_ms(run, gap + 1, hi) >= min_span_ms
        ]
        pool = both_valid or [
            gap
            for gap in range(lo, hi)
            if _span_duration_ms(run, lo, gap) >= min_span_ms
            or _span_duration_ms(run, gap + 1, hi) >= min_span_ms
        ]
        if not pool:
            pool = list(range(lo, hi))

        best_gap = max(
            pool,
            key=lambda g: (depths[g], -abs(run[g].end_ms - target_mid_ms)),
        )
        stack.append((best_gap + 1, hi))
        stack.append((lo, best_gap))
    return result


def _shape_run_segments(
    run: Sequence[Sentence],
    depths: Sequence[float],
    config: TextTilerConfig,
) -> list[tuple[int, int]]:
    n_sents = len(run)
    if n_sents == 0:
        return []

    positive = [d for d in depths if d > 0.0]
    cut_gaps: list[int] = []
    if positive:
        mean_d = sum(positive) / len(positive)
        var_d = sum((d - mean_d) ** 2 for d in positive) / len(positive)
        cutoff = max(0.0, mean_d + config.threshold_std_factor * math.sqrt(var_d))
        n_gaps = len(depths)
        for gap, depth in enumerate(depths):
            is_peak = (gap == 0 or depth >= depths[gap - 1]) and (
                gap == n_gaps - 1 or depth >= depths[gap + 1]
            )
            if depth > 0.0 and is_peak and depth >= cutoff:
                cut_gaps.append(gap)

    initial: list[tuple[int, int]] = []
    cur_start = 0
    for gap in cut_gaps:
        initial.append((cur_start, gap))
        cur_start = gap + 1
    initial.append((cur_start, n_sents - 1))

    # Split over-long topic segments strictly along complete sentence gaps.
    segments: list[tuple[int, int]] = []
    for seg_start, seg_end in initial:
        segments.extend(
            _split_segment_if_overlong(
                run,
                depths,
                seg_start,
                seg_end,
                config.min_span_ms,
                config.max_span_ms,
            )
        )

    # Greedily merge sub-floor segments (< min_span_ms) across the shallowest depth valley.
    merged = True
    while merged and len(segments) >= 2:
        merged = False
        short_indices = [
            idx
            for idx, (s, e) in enumerate(segments)
            if _span_duration_ms(run, s, e) < config.min_span_ms
        ]
        if not short_indices:
            break
        # Merge the shortest segment first so tiny islands consolidate before larger ones.
        idx = min(
            short_indices, key=lambda i: _span_duration_ms(run, segments[i][0], segments[i][1])
        )
        options: list[tuple[float, int, tuple[int, int]]] = []
        if idx > 0:
            left_s, left_e = segments[idx - 1]
            _, cur_e = segments[idx]
            if _span_duration_ms(run, left_s, cur_e) <= config.max_span_ms:
                options.append((depths[left_e], idx - 1, (left_s, cur_e)))
        if idx < len(segments) - 1:
            cur_s, cur_e = segments[idx]
            _, right_e = segments[idx + 1]
            if _span_duration_ms(run, cur_s, right_e) <= config.max_span_ms:
                options.append((depths[cur_e], idx, (cur_s, right_e)))
        if options:
            options.sort(key=lambda item: item[0])
            _, remove_idx, new_span = options[0]
            segments[remove_idx : remove_idx + 2] = [new_span]
            merged = True

    return [(s, e) for s, e in segments if _span_duration_ms(run, s, e) >= config.min_span_ms]


def _score_segment(
    sparse_vecs: Sequence[dict[str, float]],
    depths: Sequence[float],
    max_depth: float,
    start_idx: int,
    end_idx: int,
) -> float:
    seg_vecs = sparse_vecs[start_idx : end_idx + 1]
    centroid = _mean_sparse_unit(seg_vecs)
    cohesion = (
        sum(_sparse_cosine(v, centroid) for v in seg_vecs) / len(seg_vecs) if seg_vecs else 0.0
    )
    flanking: list[float] = []
    if start_idx > 0:
        flanking.append(depths[start_idx - 1])
    if end_idx < len(depths):
        flanking.append(depths[end_idx])
    if max_depth > 0.0 and flanking:
        prominence = min(1.0, max(flanking) / max_depth)
        raw = 0.5 * cohesion + 0.5 * prominence
    else:
        raw = cohesion
    return round(max(0.0, min(1.0, raw)), 4)


def discover_topics(
    transcript: NormalizedTranscript,
    *,
    sentences: Sequence[Sentence] | None = None,
    embedder: SentenceEmbedder | None = None,
    config: TextTilerConfig | None = None,
    audio_metrics: Sequence[SentenceAudioMetrics] | None = None,
) -> tuple[Candidate, ...]:
    """Discover contiguous, sentence-complete topical clip candidates without API calls."""
    assert_model_input(transcript)
    cfg = config or TextTilerConfig()
    active_embedder = embedder or SoraniTfIdfEmbedder()
    resolved_sentences = (
        tuple(sentences) if sentences is not None else segment_sentences(transcript.words)
    )
    if not resolved_sentences:
        return ()

    metrics_by_idx = (
        {m.sentence_index: m for m in audio_metrics} if audio_metrics is not None else None
    )

    scored_spans: list[tuple[float, int, int]] = []
    for indexed_run in _complete_sentence_runs(resolved_sentences):
        run_indices = [orig_idx for orig_idx, _ in indexed_run]
        run = tuple(sent for _, sent in indexed_run)
        if len(run) < 2 * cfg.block_size:
            continue
        if run[-1].end_ms - run[0].start_ms < cfg.min_span_ms:
            continue

        norm_texts = [normalize_sorani(sent.text) for sent in run]
        raw_vecs = active_embedder.embed(norm_texts)
        if len(raw_vecs) != len(run):
            raise ValueError(f"embedder returned {len(raw_vecs)} vectors for {len(run)} sentences")
        sparse_vecs: list[dict[str, float]] = []
        dense_dim: int | None = None
        for vec in raw_vecs:
            sp, dense_dim = _to_sparse_unit(vec, dense_dim)
            sparse_vecs.append(sp)

        depths = text_tile_depths(
            sparse_vecs,
            block_size=cfg.block_size,
            smoothing_passes=cfg.smoothing_passes,
        )
        max_depth = max(depths, default=0.0)
        for seg_start, seg_end in _shape_run_segments(run, depths, cfg):
            in_ms = run[seg_start].start_ms
            out_ms = run[seg_end].end_ms
            if out_ms <= in_ms:
                continue
            score = _score_segment(sparse_vecs, depths, max_depth, seg_start, seg_end)
            if metrics_by_idx is not None:
                seg_exc = [
                    metrics_by_idx[orig_idx].excitement_score
                    for orig_idx in run_indices[seg_start : seg_end + 1]
                    if orig_idx in metrics_by_idx
                ]
                mean_excitement = sum(seg_exc) / len(seg_exc) if seg_exc else 0.0
                dur_pref = _viral_duration_score(out_ms - in_ms)
                score = round(
                    max(0.0, min(1.0, 0.55 * score + 0.30 * mean_excitement + 0.15 * dur_pref)),
                    4,
                )
            scored_spans.append((score, in_ms, out_ms))

    scored_spans.sort(key=lambda item: (-item[0], item[1]))
    return tuple(
        Candidate(
            candidate_id=f"{transcript.media_id}-topic-{rank}",
            media_id=transcript.media_id,
            in_ms=in_ms,
            out_ms=out_ms,
            path=DiscoveryPath.VERBAL,
            rank=rank,
            score=score,
        )
        for rank, (score, in_ms, out_ms) in enumerate(scored_spans, start=1)
    )
