"""Silence tightening for pro editing.

Removes dead air between words without altering what was said.

AC-4: Internal pauses above threshold_ms are tightened to target_gap_ms, and every later word
and caption shifts earlier by the removed duration so synchronization is strictly preserved.

AC-5: The total removed silence is recorded in the delivered output contract, reconciling the
clip's duration and its source span.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Final

from hawedit.clip import Clip, ClipTranscript, Output
from hawedit.sentences import Sentence
from hawedit.transcripts import Word

__all__ = [
    "DEFAULT_SILENCE_THRESHOLD_MS",
    "DEFAULT_TARGET_GAP_MS",
    "SilencePlan",
    "plan_silence_tightening",
    "remap_timestamp",
    "silence_trim_filter",
    "tighten_clip",
    "tighten_sentences",
    "tighten_silence",
]

DEFAULT_SILENCE_THRESHOLD_MS: Final = 600
DEFAULT_TARGET_GAP_MS: Final = 150


@dataclass(frozen=True)
class SilencePlan:
    """Execution plan for audio/video silence tightening."""

    clip_in_ms: int
    clip_out_ms: int
    threshold_ms: int
    target_gap_ms: int
    retained_intervals_ms: tuple[tuple[int, int], ...]
    removed_intervals_ms: tuple[tuple[int, int], ...]
    total_removed_ms: int

    @property
    def effective_duration_ms(self) -> int:
        """Physical duration of the clip after dead air is excised."""
        return (self.clip_out_ms - self.clip_in_ms) - self.total_removed_ms


def plan_silence_tightening(
    words: Sequence[Word],
    clip_in_ms: int,
    clip_out_ms: int,
    *,
    threshold_ms: int = DEFAULT_SILENCE_THRESHOLD_MS,
    target_gap_ms: int = DEFAULT_TARGET_GAP_MS,
) -> SilencePlan:
    """Compute exact retained and excised intervals for a clip.

    All interval bounds are relative to `clip_in_ms` (0 to clip_duration_ms).
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
    if clip_out_ms <= clip_in_ms:
        raise ValueError(
            f"clip_out_ms ({clip_out_ms}) must be strictly greater than clip_in_ms ({clip_in_ms})"
        )

    clip_dur = clip_out_ms - clip_in_ms
    clip_words = [w for w in words if w.end_ms > clip_in_ms and w.start_ms < clip_out_ms]

    if len(clip_words) <= 1:
        return SilencePlan(
            clip_in_ms=clip_in_ms,
            clip_out_ms=clip_out_ms,
            threshold_ms=threshold_ms,
            target_gap_ms=target_gap_ms,
            retained_intervals_ms=((0, clip_dur),),
            removed_intervals_ms=(),
            total_removed_ms=0,
        )

    removed: list[tuple[int, int]] = []
    for i in range(1, len(clip_words)):
        prev = clip_words[i - 1]
        curr = clip_words[i]
        gap_start = max(clip_in_ms, prev.end_ms)
        gap_end = min(clip_out_ms, curr.start_ms)
        gap = gap_end - gap_start

        if gap > threshold_ms:
            cut_start = gap_start + target_gap_ms
            cut_end = gap_end
            if cut_end > cut_start:
                removed.append((cut_start - clip_in_ms, cut_end - clip_in_ms))

    if not removed:
        return SilencePlan(
            clip_in_ms=clip_in_ms,
            clip_out_ms=clip_out_ms,
            threshold_ms=threshold_ms,
            target_gap_ms=target_gap_ms,
            retained_intervals_ms=((0, clip_dur),),
            removed_intervals_ms=(),
            total_removed_ms=0,
        )

    retained: list[tuple[int, int]] = []
    curr_pos = 0
    for r_start, r_end in removed:
        if r_start > curr_pos:
            retained.append((curr_pos, r_start))
        curr_pos = r_end
    if curr_pos < clip_dur:
        retained.append((curr_pos, clip_dur))

    total_removed = sum(r_end - r_start for r_start, r_end in removed)

    return SilencePlan(
        clip_in_ms=clip_in_ms,
        clip_out_ms=clip_out_ms,
        threshold_ms=threshold_ms,
        target_gap_ms=target_gap_ms,
        retained_intervals_ms=tuple(retained),
        removed_intervals_ms=tuple(removed),
        total_removed_ms=total_removed,
    )


def remap_timestamp(t_source_ms: int, plan: SilencePlan) -> int:
    """Remap a source timestamp to the tightened clip timeline (0-based).

    If t_source_ms falls inside an excised interval, it is clamped to that interval's
    start on the tightened timeline.
    """
    t_clip = max(0, min(plan.clip_out_ms - plan.clip_in_ms, t_source_ms - plan.clip_in_ms))
    cumulative_shift = 0
    for rem_start, rem_end in plan.removed_intervals_ms:
        if t_clip <= rem_start:
            break
        if t_clip >= rem_end:
            cumulative_shift += rem_end - rem_start
        else:
            return rem_start - cumulative_shift
    return t_clip - cumulative_shift


def silence_trim_filter(retained_intervals_ms: Sequence[tuple[int, int]]) -> str:
    """Generate FFmpeg filtergraph segments to trim and concatenate retained intervals.

    Returns empty string if retained_intervals_ms has <= 1 interval.
    Outputs video pad [v_tightened] and audio pad [a_tightened].
    """
    if len(retained_intervals_ms) <= 1:
        return ""

    parts: list[str] = []
    concat_inputs: list[str] = []
    for idx, (start_ms, end_ms) in enumerate(retained_intervals_ms):
        s_sec = start_ms / 1000.0
        e_sec = end_ms / 1000.0
        parts.append(
            f"[0:v]trim=start={s_sec:.3f}:end={e_sec:.3f},setpts=PTS-STARTPTS[v{idx}];"
            f"[0:a]atrim=start={s_sec:.3f}:end={e_sec:.3f},asetpts=PTS-STARTPTS[a{idx}]"
        )
        concat_inputs.append(f"[v{idx}][a{idx}]")
    parts.append(
        f"{''.join(concat_inputs)}concat=n={len(retained_intervals_ms)}:v=1:a=1[v_tightened][a_tightened]"
    )
    return ";".join(parts)


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
