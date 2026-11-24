"""§3 Stage 3 multimodal acoustic profiling and teaser-overlap benchmark (D-356).

Lightweight, deterministic, CPU-only acoustic cue extraction over Stage 0's PCM WAV and Stage 2's
aligned sentences using only stdlib ``wave`` and ``numpy`` (no external model weights). Feeds
compact vocal-delivery tags (``high-energy``, ``burst``, ``fast``) into Path A and blends acoustic
excitement into C4 topic-segmentation candidates.

Also provides ``evaluate_teaser_overlap`` for deterministic precision/recall/F1 evaluation of
discovered or delivered clip spans against verified human-picked teaser gold source regions.
"""

from __future__ import annotations

import math
import wave
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from hawedit.sentences import Sentence
from hawedit.transcripts import Word

__all__ = [
    "BURST_COUNT_THRESHOLD",
    "BURST_FRAME_MS",
    "BURST_STD_FACTOR",
    "FAST_SPEECH_WPS_THRESHOLD",
    "HIGH_ENERGY_Z_THRESHOLD",
    "SentenceAudioMetrics",
    "TeaserGoldSpan",
    "TeaserOverlapReport",
    "analyze_sentence_audio",
    "analyze_word_energy_peaks",
    "evaluate_teaser_overlap",
]

BURST_FRAME_MS: Final[int] = 100
BURST_STD_FACTOR: Final[float] = 1.5
HIGH_ENERGY_Z_THRESHOLD: Final[float] = 1.0
BURST_COUNT_THRESHOLD: Final[int] = 2
FAST_SPEECH_WPS_THRESHOLD: Final[float] = 3.2
_RMS_DB_FLOOR: Final[float] = -120.0
_EPS: Final[float] = 1e-6


@dataclass(frozen=True, slots=True)
class SentenceAudioMetrics:
    """Acoustic energy, burst, and delivery-rate profile for one aligned sentence."""

    sentence_index: int
    rms_db: float
    rms_z: float
    peak_burst_count: int
    speech_rate_wps: float
    pause_before_ms: int
    excitement_score: float
    tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TeaserGoldSpan:
    """One verified human-picked opening teaser source span in milliseconds."""

    label: str
    start_ms: int
    end_ms: int

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("TeaserGoldSpan.label must be non-empty")
        if self.start_ms < 0:
            raise ValueError(f"TeaserGoldSpan.start_ms must be >= 0, got {self.start_ms}")
        if self.end_ms <= self.start_ms:
            raise ValueError(
                f"TeaserGoldSpan.end_ms ({self.end_ms}) must exceed start_ms ({self.start_ms})"
            )


@dataclass(frozen=True, slots=True)
class TeaserOverlapReport:
    """Deterministic overlap benchmark of predicted clip spans against gold teaser spans."""

    predicted_count: int
    gold_count: int
    hits: int
    precision: float
    recall: float
    f1: float
    per_gold_overlap_ms: tuple[tuple[str, int], ...]


def _read_pcm_mono_float32(audio_path: Path) -> tuple[Any, int]:
    """Read a mono or multi-channel PCM WAV into a normalized 1-D float32 numpy array."""
    import numpy as np

    with wave.open(str(audio_path), "rb") as wf:
        sample_rate = wf.getframerate()
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        n_frames = wf.getnframes()
        if sample_rate <= 0:
            raise ValueError(f"Invalid WAV sample rate: {sample_rate}")
        if n_channels < 1:
            raise ValueError(f"Invalid WAV channel count: {n_channels}")
        raw_bytes = wf.readframes(n_frames)

    if n_frames == 0:
        return np.empty(0, dtype=np.float32), sample_rate

    if sampwidth == 2:
        samples = np.frombuffer(raw_bytes, dtype="<i2").astype(np.float32) / 32768.0
    elif sampwidth == 1:
        samples = (np.frombuffer(raw_bytes, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sampwidth == 3:
        raw_u8 = np.frombuffer(raw_bytes, dtype=np.uint8).reshape(-1, 3)
        packed = (
            raw_u8[:, 0].astype(np.int32)
            | (raw_u8[:, 1].astype(np.int32) << 8)
            | (raw_u8[:, 2].astype(np.int32) << 16)
        )
        # Sign-extend 24-bit signed PCM into 32-bit signed integers.
        signed = (packed << 8) >> 8
        samples = signed.astype(np.float32) / 8388608.0
    elif sampwidth == 4:
        samples = np.frombuffer(raw_bytes, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported PCM WAV sample width: {sampwidth} bytes")

    if n_channels > 1:
        samples = samples.reshape(-1, n_channels).mean(axis=1, dtype=np.float32)

    return samples, sample_rate


def _count_local_peaks_above(values: Sequence[float], threshold: float) -> int:
    """Count distinct local maxima (including flat peak plateaus) strictly above ``threshold``."""
    n = len(values)
    if n == 0:
        return 0

    peaks = 0
    idx = 0
    while idx < n:
        val = values[idx]
        end = idx
        while end + 1 < n and values[end + 1] == val:
            end += 1

        if val > threshold:
            higher_than_left = idx == 0 or val > values[idx - 1]
            higher_than_right = end == n - 1 or val > values[end + 1]
            # Avoid counting an entirely flat segment (no local rise or fall at either edge)
            # unless it is a single-frame spike strictly exceeding the episode threshold.
            if (higher_than_left and higher_than_right) and not (
                idx == 0 and end == n - 1 and n > 1
            ):
                peaks += 1
        idx = end + 1
    return peaks


def analyze_sentence_audio(
    audio_path: Path,
    sentences: Sequence[Sentence],
) -> tuple[SentenceAudioMetrics, ...]:
    """Compute deterministic acoustic excitement and delivery metrics per aligned sentence.

    Args:
        audio_path: Path to a PCM WAV file (typically Stage 0's 16 kHz mono ``audio.wav``).
        sentences: Time-ordered aligned ``Sentence`` instances from Stage 2.

    Returns:
        Tuple of ``SentenceAudioMetrics`` aligned 1-to-1 with ``sentences`` by index.

    Raises:
        FileNotFoundError: ``audio_path`` does not exist.
        ValueError: WAV is malformed, unsupported sample width, or empty for non-empty sentences.
    """
    import numpy as np

    samples, sample_rate = _read_pcm_mono_float32(audio_path)
    if not sentences:
        return ()

    total_samples = int(samples.size)
    if total_samples == 0:
        raise ValueError(f"Audio WAV contains zero frames: {audio_path}")

    # Compute 100 ms frame RMS envelope once for the whole episode.
    win_samples = max(1, int(round(sample_rate * (BURST_FRAME_MS / 1000.0))))
    n_full_frames = total_samples // win_samples
    if n_full_frames > 0:
        trimmed = samples[: n_full_frames * win_samples].reshape(n_full_frames, win_samples)
        frame_rms_arr = np.sqrt(np.mean(trimmed * trimmed, axis=1, dtype=np.float64))
        ep_frame_mean = float(np.mean(frame_rms_arr))
        ep_frame_std = float(np.std(frame_rms_arr))
        burst_threshold = ep_frame_mean + BURST_STD_FACTOR * ep_frame_std
        frame_rms_list: list[float] = frame_rms_arr.tolist()
    else:
        single_rms = float(np.sqrt(np.mean(samples * samples, dtype=np.float64)))
        frame_rms_list = [single_rms]
        burst_threshold = single_rms

    # First pass: raw per-sentence linear RMS & dBFS.
    sent_rms: list[float] = []
    sent_rms_db: list[float] = []
    sent_sample_bounds: list[tuple[int, int]] = []
    for sent in sentences:
        s_idx = max(0, min(total_samples, int(round(sent.start_ms * sample_rate / 1000.0))))
        e_idx = max(s_idx, min(total_samples, int(round(sent.end_ms * sample_rate / 1000.0))))
        sent_sample_bounds.append((s_idx, e_idx))
        if e_idx <= s_idx:
            rms = 0.0
            rms_db = _RMS_DB_FLOOR
        else:
            seg = samples[s_idx:e_idx]
            rms = float(np.sqrt(np.mean(seg * seg, dtype=np.float64)))
            rms_db = 20.0 * math.log10(max(rms, _EPS))
        sent_rms.append(rms)
        sent_rms_db.append(rms_db)

    rms_arr = np.asarray(sent_rms, dtype=np.float64)
    mean_rms = float(np.mean(rms_arr))
    std_rms = float(np.std(rms_arr))

    results: list[SentenceAudioMetrics] = []
    n_frames_env = len(frame_rms_list)
    for idx, sent in enumerate(sentences):
        rms_z = (sent_rms[idx] - mean_rms) / std_rms if std_rms > 1e-9 else 0.0

        s_idx, e_idx = sent_sample_bounds[idx]
        if n_frames_env > 0 and e_idx > s_idx:
            f_start = min(n_frames_env - 1, s_idx // win_samples)
            f_end = min(n_frames_env, max(f_start + 1, (e_idx + win_samples - 1) // win_samples))
            peak_burst_count = _count_local_peaks_above(
                frame_rms_list[f_start:f_end],
                burst_threshold,
            )
        else:
            peak_burst_count = 0

        dur_s = max(1e-3, (sent.end_ms - sent.start_ms) / 1000.0)
        speech_rate_wps = len(sent.words) / dur_s
        pause_before_ms = 0 if idx == 0 else max(0, sent.start_ms - sentences[idx - 1].end_ms)

        energy_norm = 1.0 / (1.0 + math.exp(-max(-10.0, min(10.0, rms_z))))
        burst_norm = min(1.0, peak_burst_count / 3.0)
        rate_norm = max(0.0, min(1.0, (speech_rate_wps - 1.0) / 3.0))
        excitement = round(
            max(0.0, min(1.0, 0.50 * energy_norm + 0.30 * burst_norm + 0.20 * rate_norm)),
            4,
        )

        tags_list: list[str] = []
        if rms_z >= HIGH_ENERGY_Z_THRESHOLD:
            tags_list.append("high-energy")
        if peak_burst_count >= BURST_COUNT_THRESHOLD:
            tags_list.append("burst")
        if speech_rate_wps >= FAST_SPEECH_WPS_THRESHOLD:
            tags_list.append("fast")

        results.append(
            SentenceAudioMetrics(
                sentence_index=idx,
                rms_db=round(sent_rms_db[idx], 2),
                rms_z=round(rms_z, 4),
                peak_burst_count=peak_burst_count,
                speech_rate_wps=round(speech_rate_wps, 4),
                pause_before_ms=pause_before_ms,
                excitement_score=excitement,
                tags=tuple(tags_list),
            )
        )

    return tuple(results)


def _read_pcm_mono_slice_float32(
    audio_path: Path, start_ms: int, end_ms: int
) -> tuple[Any, int, int]:
    """Read only ``[start_ms, end_ms]`` of a PCM WAV into a normalized mono float32 array."""
    import numpy as np

    with wave.open(str(audio_path), "rb") as wf:
        sample_rate = wf.getframerate()
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        total_frames = wf.getnframes()
        if sample_rate <= 0:
            raise ValueError(f"Invalid WAV sample rate: {sample_rate}")
        if n_channels < 1:
            raise ValueError(f"Invalid WAV channel count: {n_channels}")
        start_frame = max(0, min(total_frames, int(round(start_ms * sample_rate / 1000.0))))
        end_frame = max(start_frame, min(total_frames, int(round(end_ms * sample_rate / 1000.0))))
        if end_frame <= start_frame:
            return np.empty(0, dtype=np.float32), sample_rate, start_frame
        wf.setpos(start_frame)
        raw_bytes = wf.readframes(end_frame - start_frame)

    if sampwidth == 2:
        samples = np.frombuffer(raw_bytes, dtype="<i2").astype(np.float32) / 32768.0
    elif sampwidth == 1:
        samples = (np.frombuffer(raw_bytes, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sampwidth == 3:
        raw_u8 = np.frombuffer(raw_bytes, dtype=np.uint8).reshape(-1, 3)
        packed = (
            raw_u8[:, 0].astype(np.int32)
            | (raw_u8[:, 1].astype(np.int32) << 8)
            | (raw_u8[:, 2].astype(np.int32) << 16)
        )
        signed = (packed << 8) >> 8
        samples = signed.astype(np.float32) / 8388608.0
    elif sampwidth == 4:
        samples = np.frombuffer(raw_bytes, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported PCM WAV sample width: {sampwidth} bytes")

    if n_channels > 1:
        samples = samples.reshape(-1, n_channels).mean(axis=1, dtype=np.float32)

    return samples, sample_rate, start_frame


def analyze_word_energy_peaks(
    audio_path: Path,
    words: Sequence[Word],
    *,
    payoff_at_ms: int | None = None,
    top_fraction: float = 0.25,
    min_z: float = 0.55,
    merge_gap_ms: int = 450,
    payoff_window_ms: int = 1_200,
) -> tuple[tuple[int, int], ...]:
    """Identify sub-phrase vocal-emphasis and payoff intervals at word granularity (D-365).

    Prevents long continuous Sorani utterances from saturating 100% of karaoke words in the
    excited accent colour by selecting only genuine vocal-energy peaks (strictly capped at
    ``top_fraction`` of spoken words) plus an optional spotlight around ``payoff_at_ms``.
    Returns merged source-timeline ``(start_ms, end_ms)`` intervals.
    """
    import numpy as np

    if not words:
        return ()
    if not (0.0 < top_fraction <= 1.0):
        raise ValueError(f"top_fraction must be in (0, 1], got {top_fraction!r}")
    if merge_gap_ms < 0:
        raise ValueError(f"merge_gap_ms must be non-negative, got {merge_gap_ms!r}")

    span_start_ms = min(w.start_ms for w in words)
    span_end_ms = max(w.end_ms for w in words)
    samples, sample_rate, start_frame = _read_pcm_mono_slice_float32(
        audio_path, span_start_ms, span_end_ms
    )
    total_slice = int(samples.size)
    if total_slice == 0:
        return ()

    word_rms: list[float] = []
    for word in words:
        s_idx = max(
            0, min(total_slice, int(round(word.start_ms * sample_rate / 1000.0)) - start_frame)
        )
        e_idx = max(
            s_idx, min(total_slice, int(round(word.end_ms * sample_rate / 1000.0)) - start_frame)
        )
        if e_idx <= s_idx:
            word_rms.append(0.0)
        else:
            seg = samples[s_idx:e_idx]
            word_rms.append(float(np.sqrt(np.mean(seg * seg, dtype=np.float64))))

    rms_arr = np.asarray(word_rms, dtype=np.float64)
    mean_rms = float(np.mean(rms_arr))
    std_rms = float(np.std(rms_arr))
    z_scores = (
        [(r - mean_rms) / std_rms for r in word_rms] if std_rms > 1e-9 else [0.0] * len(words)
    )

    # 3-word local neighbourhood weighting favours genuine multi-word vocal punches over mic pops.
    n = len(words)
    local_scores: list[float] = []
    for idx in range(n):
        neighbor_peak = z_scores[idx]
        if idx > 0:
            neighbor_peak = max(neighbor_peak, z_scores[idx - 1])
        if idx + 1 < n:
            neighbor_peak = max(neighbor_peak, z_scores[idx + 1])
        local_scores.append(0.65 * z_scores[idx] + 0.35 * neighbor_peak)

    max_peaks = max(2, int(round(n * top_fraction)))
    candidates = [idx for idx, score in enumerate(local_scores) if score >= min_z]
    candidates.sort(key=lambda idx: local_scores[idx], reverse=True)
    selected_indices: set[int] = set(candidates[:max_peaks])

    if payoff_at_ms is not None and span_start_ms <= payoff_at_ms <= span_end_ms:
        p_lo = payoff_at_ms - payoff_window_ms
        p_hi = payoff_at_ms + payoff_window_ms
        for idx, word in enumerate(words):
            if word.end_ms >= p_lo and word.start_ms <= p_hi:
                selected_indices.add(idx)

    if not selected_indices:
        return ()

    raw_spans = sorted(
        (words[idx].start_ms, words[idx].end_ms)
        for idx in selected_indices
        if words[idx].end_ms > words[idx].start_ms
    )
    if not raw_spans:
        return ()

    merged: list[tuple[int, int]] = [raw_spans[0]]
    for s_ms, e_ms in raw_spans[1:]:
        prev_s, prev_e = merged[-1]
        if s_ms - prev_e <= merge_gap_ms:
            merged[-1] = (prev_s, max(prev_e, e_ms))
        else:
            merged.append((s_ms, e_ms))
    return tuple(merged)


def _span_overlap_ms(a_start: int, a_end: int, b_start: int, b_end: int) -> int:
    return max(0, min(a_end, b_end) - max(a_start, b_start))


def _merged_intersection_ms(
    spans: Sequence[tuple[int, int]],
    target_start: int,
    target_end: int,
) -> int:
    """Total milliseconds of ``[target_start, target_end]`` covered by the union of ``spans``."""
    intervals: list[tuple[int, int]] = []
    for s, e in spans:
        lo = max(s, target_start)
        hi = min(e, target_end)
        if hi > lo:
            intervals.append((lo, hi))
    if not intervals:
        return 0
    intervals.sort()
    total = 0
    cur_lo, cur_hi = intervals[0]
    for lo, hi in intervals[1:]:
        if lo <= cur_hi:
            cur_hi = max(cur_hi, hi)
        else:
            total += cur_hi - cur_lo
            cur_lo, cur_hi = lo, hi
    total += cur_hi - cur_lo
    return total


def evaluate_teaser_overlap(
    predicted_spans_ms: Sequence[tuple[int, int]],
    gold_spans: Sequence[TeaserGoldSpan],
    *,
    min_overlap_ms: int = 1_500,
) -> TeaserOverlapReport:
    """Measure precision, recall, F1, and per-gold overlap against verified teaser source spans.

    A gold span is counted as a hit when at least one predicted span overlaps it by at least
    ``min_overlap_ms`` milliseconds. Precision counts the fraction of predicted spans that overlap
    at least one gold span by ``>= min_overlap_ms``, keeping both precision and recall bounded in
    ``[0.0, 1.0]`` even when a single long clip covers multiple nearby teaser fragments.
    """
    if isinstance(min_overlap_ms, bool) or min_overlap_ms <= 0:
        raise ValueError(f"min_overlap_ms must be a positive integer, got {min_overlap_ms!r}")

    validated_preds: list[tuple[int, int]] = []
    for p_start, p_end in predicted_spans_ms:
        if p_start < 0 or p_end <= p_start:
            raise ValueError(
                f"Invalid predicted span ({p_start}, {p_end}): expected 0 <= start < end"
            )
        validated_preds.append((p_start, p_end))

    per_gold_overlap: list[tuple[str, int]] = []
    gold_hits = 0
    for gold in gold_spans:
        covered_ms = _merged_intersection_ms(validated_preds, gold.start_ms, gold.end_ms)
        per_gold_overlap.append((gold.label, covered_ms))
        if any(
            _span_overlap_ms(p_start, p_end, gold.start_ms, gold.end_ms) >= min_overlap_ms
            for p_start, p_end in validated_preds
        ):
            gold_hits += 1

    pred_hits = 0
    for p_start, p_end in validated_preds:
        if any(
            _span_overlap_ms(p_start, p_end, gold.start_ms, gold.end_ms) >= min_overlap_ms
            for gold in gold_spans
        ):
            pred_hits += 1

    predicted_count = len(validated_preds)
    gold_count = len(gold_spans)
    precision = pred_hits / predicted_count if predicted_count > 0 else 0.0
    recall = gold_hits / gold_count if gold_count > 0 else 0.0
    f1 = (2.0 * precision * recall / (precision + recall)) if (precision + recall) > 0.0 else 0.0

    return TeaserOverlapReport(
        predicted_count=predicted_count,
        gold_count=gold_count,
        hits=gold_hits,
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        per_gold_overlap_ms=tuple(per_gold_overlap),
    )
