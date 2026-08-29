"""Silence tightening for pro editing.

Removes dead air between words without altering what was said.

AC-4: Internal pauses above threshold_ms are tightened to target_gap_ms, and every later word
and caption shifts earlier by the removed duration so synchronization is strictly preserved.

AC-5: The total removed silence is recorded in the delivered output contract, reconciling the
clip's duration and its source span.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Final

from hawedit.clip import Clip, ClipTranscript, Output
from hawedit.sentences import Sentence
from hawedit.transcripts import Word

__all__ = [
    "DEFAULT_SILENCE_THRESHOLD_MS",
    "DEFAULT_TARGET_GAP_MS",
    "tighten_clip",
    "tighten_sentences",
    "tighten_silence",
]

DEFAULT_SILENCE_THRESHOLD_MS: Final = 600
DEFAULT_TARGET_GAP_MS: Final = 150


def tighten_silence(
    words: Sequence[Word],
    *,
    threshold_ms: int = DEFAULT_SILENCE_THRESHOLD_MS,
    target_gap_ms: int = DEFAULT_TARGET_GAP_MS,
) -> tuple[tuple[Word, ...], int]:
    """Tighten pauses between consecutive words that exceed `threshold_ms`.

    Returns a tuple of (tightened_words, total_removed_ms).
    Every word following a trimmed gap is shifted earlier by the trimmed amount,
    preserving exact word durations, confidences, and relative speech pacing.

    Raises:
        ValueError: if threshold_ms <= 0, target_gap_ms < 0, or target_gap_ms >= threshold_ms.
    """
    if threshold_ms <= 0:
        raise ValueError(f"threshold_ms must be positive, got {threshold_ms}")
    if target_gap_ms < 0:
        raise ValueError(f"target_gap_ms cannot be negative, got {target_gap_ms}")
    if target_gap_ms >= threshold_ms:
        raise ValueError(
            f"target_gap_ms ({target_gap_ms}) must be strictly less than "
            f"threshold_ms ({threshold_ms})"
        )

    if len(words) <= 1:
        return tuple(words), 0

    tightened: list[Word] = [words[0]]
    cumulative_shift_ms = 0

    for i in range(1, len(words)):
        prev = words[i - 1]
        curr = words[i]

        original_gap = curr.start_ms - prev.end_ms
        if original_gap > threshold_ms:
            excess = original_gap - target_gap_ms
            cumulative_shift_ms += excess

        tightened.append(
            Word(
                w=curr.w,
                start_ms=curr.start_ms - cumulative_shift_ms,
                end_ms=curr.end_ms - cumulative_shift_ms,
                conf=curr.conf,
            )
        )

    return tuple(tightened), cumulative_shift_ms


def tighten_sentences(
    sentences: Sequence[Sentence],
    *,
    threshold_ms: int = DEFAULT_SILENCE_THRESHOLD_MS,
    target_gap_ms: int = DEFAULT_TARGET_GAP_MS,
) -> tuple[tuple[Sentence, ...], int]:
    """Tighten pauses across a sequence of sentences while preserving grouping.

    Returns (tightened_sentences, total_removed_ms).
    """
    if not sentences:
        return (), 0

    all_words: list[Word] = []
    sentence_word_counts: list[int] = []
    for s in sentences:
        sentence_word_counts.append(len(s.words))
        all_words.extend(s.words)

    tightened_words, total_removed = tighten_silence(
        all_words,
        threshold_ms=threshold_ms,
        target_gap_ms=target_gap_ms,
    )

    reconstructed: list[Sentence] = []
    word_offset = 0
    for idx, count in enumerate(sentence_word_counts):
        s_words = tightened_words[word_offset : word_offset + count]
        reconstructed.append(Sentence(words=s_words, complete=sentences[idx].complete))
        word_offset += count

    return tuple(reconstructed), total_removed


def tighten_clip(
    clip: Clip,
    *,
    threshold_ms: int = DEFAULT_SILENCE_THRESHOLD_MS,
    target_gap_ms: int = DEFAULT_TARGET_GAP_MS,
) -> tuple[Clip, int]:
    """Tighten silence in a Clip contract, recording total removed ms in output.

    Returns (updated_clip, total_removed_ms).
    """
    tightened_words, total_removed = tighten_silence(
        clip.transcript.words,
        threshold_ms=threshold_ms,
        target_gap_ms=target_gap_ms,
    )

    updated_transcript = ClipTranscript(
        raw_ckb=clip.transcript.raw_ckb,
        norm_ckb=clip.transcript.norm_ckb,
        en_aux=clip.transcript.en_aux,
        words=tightened_words,
        asr=clip.transcript.asr,
    )

    updated_output: Output | None = None
    if clip.output is not None:
        updated_output = Output(
            title_ckb=clip.output.title_ckb,
            description_ckb=clip.output.description_ckb,
            crop_target=clip.output.crop_target,
            caption_style=clip.output.caption_style,
            durations=clip.output.durations,
            hashtags_ckb=clip.output.hashtags_ckb,
            silence_removed_ms=clip.output.silence_removed_ms + total_removed,
        )

    updated_clip = replace(
        clip,
        transcript=updated_transcript,
        output=updated_output,
    )

    return updated_clip, total_removed
