"""Silence tightening for pro editing.

Removes dead air between words without altering what was said.

AC-4: Internal pauses above threshold_ms are tightened to target_gap_ms, and every later word
and caption shifts earlier by the removed duration so synchronization is strictly preserved.

AC-5: The total removed silence is recorded in the delivered output contract, reconciling the
clip's duration and its source span.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass, replace
from typing import Any, Final

from hawedit.clip import Clip, ClipTranscript, Output
from hawedit.sentences import Sentence
from hawedit.transcripts import Word

__all__ = [
    "DEFAULT_SILENCE_THRESHOLD_MS",
    "DEFAULT_TARGET_GAP_MS",
    "KURDISH_FILLER_TOKENS",
    "SilencePlan",
    "SilencePolicy",
    "plan_silence_tightening",
    "remap_timestamp",
    "silence_trim_filter",
    "tighten_clip",
    "tighten_sentences",
    "tighten_silence",
]

DEFAULT_SILENCE_THRESHOLD_MS: Final = 600
DEFAULT_TARGET_GAP_MS: Final = 150

# Conversational Kurdish filler tokens and hesitation markers that add zero semantic value
KURDISH_FILLER_TOKENS: Final[frozenset[str]] = frozenset(
    {
        "یەعنی",
        "یەعنى",
        "ئەها",
        "وەڵا",
        "وەڵڵا",
        "بەوەڵا",
        "بەوەڵڵا",
        "دەزانی",
        "دەزانى",
        "ئەزانی",
        "ئەزانى",
        "ڕاستییەکەی",
        "تێدەگەی",
        "تێدەگەیت",
        "دیارە",
        "ئیتر",
        "ئەوەبوو",
        "ئەوە بوو",
        "وابوو",
        "ئەوجا",
        "مەبەستم",
        "دەنا",
        "ئەرێ",
        "بۆ نموونە",
        "وەک وتم",
        "وەکو وتم",
    }
)

_PUNCT_CHARS: Final[str] = " \t\n\r.,!?:؛،؟"


def _identify_filler_words(
    words: Sequence[Word],
    filler_tokens: Collection[str] | None,
    *,
    detect_restarts: bool = True,
) -> tuple[list[bool], int]:
    """Identify filler words in a sequence, handling punctuation and multi-word phrases.

    Also detects false starts (truncated tokens followed by full tokens within 1.5s)
    and repeated n-grams (repeated phrases within 3s).
    """
    if not words:
        return [], 0

    norm_fillers = {tok.strip().strip(_PUNCT_CHARS) for tok in filler_tokens or () if tok.strip()}
    norm_fillers = {t for t in norm_fillers if t}

    single_fillers = {t for t in norm_fillers if " " not in t}
    phrase_fillers = [tuple(t.split()) for t in norm_fillers if " " in t]

    cleaned_words = [w.w.strip(_PUNCT_CHARS) for w in words]
    is_filler = [w in single_fillers for w in cleaned_words]

    for phrase in phrase_fillers:
        p_len = len(phrase)
        for i in range(len(words) - p_len + 1):
            if tuple(cleaned_words[i + k] for k in range(p_len)) == phrase:
                for k in range(p_len):
                    is_filler[i + k] = True

    if detect_restarts and len(words) >= 2:
        # 1. False-start detection: truncated word prefixed to following word within 1.5s
        for i in range(len(words) - 1):
            w1 = cleaned_words[i]
            w2 = cleaned_words[i + 1]
            gap_ms = words[i + 1].start_ms - words[i].end_ms
            if 0 <= gap_ms <= 1500 and len(w1) >= 2 and len(w2) > len(w1) and w2.startswith(w1):
                is_filler[i] = True

        # 2. Repeated n-gram detection (n=3, 2, 1 within 3s)
        for n in (3, 2, 1):
            for i in range(len(words) - 2 * n + 1):
                chunk1 = tuple(cleaned_words[i : i + n])
                chunk2 = tuple(cleaned_words[i + n : i + 2 * n])
                if chunk1 and chunk1 == chunk2 and not any(is_filler[i + k] for k in range(n)):
                    gap_ms = words[i + n].start_ms - words[i + n - 1].end_ms
                    if 0 <= gap_ms <= 3000:
                        for k in range(n):
                            is_filler[i + k] = True

    if all(is_filler):
        is_filler = [False] * len(words)

    excised_count = sum(1 for f in is_filler if f)
    return is_filler, excised_count


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
    excised_word_count: int = 0
    protected_intervals_ms: tuple[tuple[int, int], ...] = ()
    review_required: bool = False
    review_reasons: tuple[str, ...] = ()

    @property
    def effective_duration_ms(self) -> int:
        """Physical duration of the clip after dead air is excised."""
        return (self.clip_out_ms - self.clip_in_ms) - self.total_removed_ms

    @property
    def cut_points_ms(self) -> tuple[int, ...]:
        """Output-timeline timestamps (ms from 0) where retained interval cuts occur.

        Useful for scheduling camera framing switches / punch-ins synchronously on cuts.
        """
        if len(self.retained_intervals_ms) <= 1:
            return ()
        cuts: list[int] = []
        timeline_pos = 0
        for start_ms, end_ms in self.retained_intervals_ms[:-1]:
            timeline_pos += end_ms - start_ms
            cuts.append(timeline_pos)
        return tuple(cuts)


@dataclass(frozen=True)
class SilencePolicy:
    """Policy governing silence tightening, speech protection, and pause preservation."""

    threshold_ms: int = DEFAULT_SILENCE_THRESHOLD_MS
    target_gap_ms: int = DEFAULT_TARGET_GAP_MS
    min_word_conf: float = 0.0
    protect_quiet_speech: bool = True
    protect_uncertain_alignment: bool = True
    review_uncertain: bool = False
    min_trim_duration_ms: int = 50


def _merge_intervals(intervals: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge overlapping and contiguous closed-open millisecond intervals."""
    merged: list[tuple[int, int]] = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if not merged:
            merged.append((start, end))
        else:
            prev_s, prev_e = merged[-1]
            if start <= prev_e:
                merged[-1] = (prev_s, max(prev_e, end))
            else:
                merged.append((start, end))
    return merged


def _subtract_intervals(
    base_intervals: Sequence[tuple[int, int]],
    sub_intervals: Sequence[tuple[int, int]],
    *,
    min_duration: int = 50,
) -> list[tuple[int, int]]:
    """Subtract `sub_intervals` from `base_intervals`.

    Returns the portions of `base_intervals` that do not overlap any interval
    in `sub_intervals`, dropping fragments shorter than `min_duration`.
    """
    if not sub_intervals:
        return [(s, e) for s, e in base_intervals if e - s >= min_duration]

    merged_sub = _merge_intervals(sub_intervals)
    result: list[tuple[int, int]] = []

    for b_start, b_end in base_intervals:
        if b_end <= b_start:
            continue
        current_pieces: list[tuple[int, int]] = [(b_start, b_end)]
        for s_start, s_end in merged_sub:
            next_pieces: list[tuple[int, int]] = []
            for p_start, p_end in current_pieces:
                if s_end <= p_start or s_start >= p_end:
                    next_pieces.append((p_start, p_end))
                else:
                    if s_start > p_start:
                        next_pieces.append((p_start, s_start))
                    if s_end < p_end:
                        next_pieces.append((s_end, p_end))
            current_pieces = next_pieces
            if not current_pieces:
                break

        for piece_start, piece_end in current_pieces:
            if piece_end - piece_start >= min_duration:
                result.append((piece_start, piece_end))

    return _merge_intervals(result)


def plan_silence_tightening(
    words: Sequence[Word],
    clip_in_ms: int,
    clip_out_ms: int,
    *,
    threshold_ms: int = DEFAULT_SILENCE_THRESHOLD_MS,
    target_gap_ms: int = DEFAULT_TARGET_GAP_MS,
    filler_tokens: Collection[str] | None = None,
    speech_intervals: Sequence[tuple[int, int]] = (),
    protected_intervals: Sequence[tuple[int, int] | Any] = (),
    uncertain_intervals: Sequence[tuple[int, int]] = (),
    min_word_conf: float = 0.0,
    review_uncertain: bool = False,
    policy: SilencePolicy | None = None,
) -> SilencePlan:
    """Compute exact retained and excised intervals for a clip.

    All interval bounds are relative to `clip_in_ms` (0 to clip_duration_ms).
    Protects quiet speech, protected beats, and uncertain alignment from being excised.
    """
    if policy is not None:
        if threshold_ms == DEFAULT_SILENCE_THRESHOLD_MS:
            threshold_ms = policy.threshold_ms
        if target_gap_ms == DEFAULT_TARGET_GAP_MS:
            target_gap_ms = policy.target_gap_ms
        if min_word_conf == 0.0:
            min_word_conf = policy.min_word_conf
        if not review_uncertain:
            review_uncertain = policy.review_uncertain
        min_trim_ms = policy.min_trim_duration_ms
    else:
        min_trim_ms = 50

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

    # Collect all intervals (clip-relative) that MUST NOT be excised
    speech_preserve: list[tuple[int, int]] = []
    if speech_intervals and (policy is None or policy.protect_quiet_speech):
        for s_s, s_e in speech_intervals:
            if s_e > clip_in_ms and s_s < clip_out_ms:
                rel_s = max(0, s_s - clip_in_ms)
                rel_e = min(clip_dur, s_e - clip_in_ms)
                if rel_e > rel_s:
                    speech_preserve.append((rel_s, rel_e))

    protected_preserve: list[tuple[int, int]] = []
    for p in protected_intervals:
        if isinstance(p, tuple) and len(p) >= 2:
            p_s, p_e = int(p[0]), int(p[1])
        else:
            p_obj: Any = p
            if hasattr(p_obj, "start_ms") and hasattr(p_obj, "end_ms"):
                min_ret = getattr(p_obj, "min_retained_duration_ms", 0)
                p_s = int(p_obj.start_ms)
                p_e = p_s + min_ret if min_ret > 0 else int(p_obj.end_ms)
            else:
                continue
        if p_e > clip_in_ms and p_s < clip_out_ms:
            rel_s = max(0, p_s - clip_in_ms)
            rel_e = min(clip_dur, p_e - clip_in_ms)
            if rel_e > rel_s:
                protected_preserve.append((rel_s, rel_e))

    uncertain_preserve: list[tuple[int, int]] = []
    if policy is None or policy.protect_uncertain_alignment:
        for u_s, u_e in uncertain_intervals:
            if u_e > clip_in_ms and u_s < clip_out_ms:
                rel_s = max(0, u_s - clip_in_ms)
                rel_e = min(clip_dur, u_e - clip_in_ms)
                if rel_e > rel_s:
                    uncertain_preserve.append((rel_s, rel_e))
        if min_word_conf > 0.0:
            for w in clip_words:
                if w.conf < min_word_conf:
                    rel_s = max(0, w.start_ms - target_gap_ms - clip_in_ms)
                    rel_e = min(clip_dur, w.end_ms + target_gap_ms - clip_in_ms)
                    if rel_e > rel_s:
                        uncertain_preserve.append((rel_s, rel_e))

    to_preserve = _merge_intervals([*speech_preserve, *protected_preserve, *uncertain_preserve])

    if len(clip_words) == 0:
        return SilencePlan(
            clip_in_ms=clip_in_ms,
            clip_out_ms=clip_out_ms,
            threshold_ms=threshold_ms,
            target_gap_ms=target_gap_ms,
            retained_intervals_ms=((0, clip_dur),),
            removed_intervals_ms=(),
            total_removed_ms=0,
            excised_word_count=0,
            protected_intervals_ms=(),
            review_required=review_uncertain and bool(uncertain_preserve),
            review_reasons=(),
        )

    is_filler, excised_count = _identify_filler_words(clip_words, filler_tokens)

    if excised_count == 0:
        if len(clip_words) <= 1:
            return SilencePlan(
                clip_in_ms=clip_in_ms,
                clip_out_ms=clip_out_ms,
                threshold_ms=threshold_ms,
                target_gap_ms=target_gap_ms,
                retained_intervals_ms=((0, clip_dur),),
                removed_intervals_ms=(),
                total_removed_ms=0,
                excised_word_count=0,
                protected_intervals_ms=(),
                review_required=review_uncertain and bool(uncertain_preserve),
                review_reasons=(),
            )
        raw_removed: list[tuple[int, int]] = []
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
                    raw_removed.append((cut_start - clip_in_ms, cut_end - clip_in_ms))
    else:
        surviving_indices = [i for i, f in enumerate(is_filler) if not f]
        raw_removed = []

        # 1. Leading filler words before first surviving word
        if surviving_indices[0] > 0:
            first_surv = clip_words[surviving_indices[0]]
            lead_cut_start = max(0, clip_words[0].start_ms - clip_in_ms)
            sil_lead = max(0, first_surv.start_ms - clip_words[surviving_indices[0] - 1].end_ms)
            keep_lead = min(target_gap_ms, sil_lead)
            lead_cut_end = (first_surv.start_ms - keep_lead) - clip_in_ms
            if lead_cut_end > lead_cut_start:
                raw_removed.append((lead_cut_start, lead_cut_end))

        # 2. Gaps between consecutive surviving words
        for idx in range(1, len(surviving_indices)):
            prev_surv = clip_words[surviving_indices[idx - 1]]
            curr_surv = clip_words[surviving_indices[idx]]
            gap_start = max(clip_in_ms, prev_surv.end_ms)
            gap_end = min(clip_out_ms, curr_surv.start_ms)
            fillers_in_gap = [
                clip_words[k] for k in range(surviving_indices[idx - 1] + 1, surviving_indices[idx])
            ]

            if not fillers_in_gap:
                gap = gap_end - gap_start
                if gap > threshold_ms:
                    cut_start = gap_start + target_gap_ms
                    cut_end = gap_end
                    if cut_end > cut_start:
                        raw_removed.append((cut_start - clip_in_ms, cut_end - clip_in_ms))
            else:
                f_first = fillers_in_gap[0]
                f_last = fillers_in_gap[-1]
                sil_before = max(0, f_first.start_ms - gap_start)
                sil_after = max(0, gap_end - f_last.end_ms)
                keep_before = min(target_gap_ms // 2, sil_before)
                keep_after = min(target_gap_ms - keep_before, sil_after)
                cut_start = gap_start + keep_before
                cut_end = gap_end - keep_after
                if cut_end > cut_start:
                    raw_removed.append((cut_start - clip_in_ms, cut_end - clip_in_ms))

        # 3. Trailing filler words after last surviving word
        if surviving_indices[-1] < len(clip_words) - 1:
            last_surv = clip_words[surviving_indices[-1]]
            first_trail = clip_words[surviving_indices[-1] + 1]
            last_trail = clip_words[-1]
            sil_trail = max(0, first_trail.start_ms - last_surv.end_ms)
            keep_trail = min(target_gap_ms, sil_trail)
            trail_cut_start = (last_surv.end_ms + keep_trail) - clip_in_ms
            trail_cut_end = min(clip_dur, last_trail.end_ms - clip_in_ms)
            if trail_cut_end > trail_cut_start:
                raw_removed.append((trail_cut_start, trail_cut_end))

    # Detect preserved intervals and review triggers
    preserved_source_spans: list[tuple[int, int]] = []
    review_reasons: list[str] = []
    review_needed = False

    for r_s, r_e in raw_removed:
        for p_s, p_e in to_preserve:
            ov_s = max(r_s, p_s)
            ov_e = min(r_e, p_e)
            if ov_s < ov_e:
                preserved_source_spans.append((ov_s + clip_in_ms, ov_e + clip_in_ms))

        for u_s, u_e in uncertain_preserve:
            ov_s = max(r_s, u_s)
            ov_e = min(r_e, u_e)
            if ov_s < ov_e:
                review_needed = True
                review_reasons.append(
                    f"Candidate removal [{r_s + clip_in_ms}..{r_e + clip_in_ms}]ms intersects "
                    f"uncertain interval [{ov_s + clip_in_ms}..{ov_e + clip_in_ms}]ms; "
                    "retained for review rather than classified as disposable silence"
                )

    filtered_removed = _subtract_intervals(raw_removed, to_preserve, min_duration=min_trim_ms)
    merged_removed = _merge_intervals(filtered_removed)

    if not merged_removed:
        return SilencePlan(
            clip_in_ms=clip_in_ms,
            clip_out_ms=clip_out_ms,
            threshold_ms=threshold_ms,
            target_gap_ms=target_gap_ms,
            retained_intervals_ms=((0, clip_dur),),
            removed_intervals_ms=(),
            total_removed_ms=0,
            excised_word_count=excised_count,
            protected_intervals_ms=tuple(_merge_intervals(preserved_source_spans)),
            review_required=review_needed or (review_uncertain and bool(uncertain_preserve)),
            review_reasons=tuple(review_reasons),
        )

    retained: list[tuple[int, int]] = []
    curr_pos = 0
    for r_start, r_end in merged_removed:
        if r_start > curr_pos:
            retained.append((curr_pos, r_start))
        curr_pos = r_end
    if curr_pos < clip_dur:
        retained.append((curr_pos, clip_dur))

    total_removed = sum(r_end - r_start for r_start, r_end in merged_removed)

    return SilencePlan(
        clip_in_ms=clip_in_ms,
        clip_out_ms=clip_out_ms,
        threshold_ms=threshold_ms,
        target_gap_ms=target_gap_ms,
        retained_intervals_ms=tuple(retained),
        removed_intervals_ms=tuple(merged_removed),
        total_removed_ms=total_removed,
        excised_word_count=excised_count,
        protected_intervals_ms=tuple(_merge_intervals(preserved_source_spans)),
        review_required=review_needed or (review_uncertain and bool(uncertain_preserve)),
        review_reasons=tuple(review_reasons),
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
    filler_tokens: Collection[str] | None = None,
    speech_intervals: Sequence[tuple[int, int]] = (),
    protected_intervals: Sequence[tuple[int, int] | Any] = (),
    uncertain_intervals: Sequence[tuple[int, int]] = (),
    min_word_conf: float = 0.0,
    review_uncertain: bool = False,
    policy: SilencePolicy | None = None,
) -> tuple[tuple[Word, ...], int]:
    """Tighten pauses and excise conversational filler words between consecutive words.

    Returns a tuple of (tightened_words, total_removed_ms).
    Every word following an excised span is shifted earlier by the removed amount,
    preserving exact word durations, confidences, and relative speech pacing.

    Raises:
        ValueError: if threshold_ms <= 0, target_gap_ms < 0, or target_gap_ms >= threshold_ms.
    """
    if policy is not None:
        if threshold_ms == DEFAULT_SILENCE_THRESHOLD_MS:
            threshold_ms = policy.threshold_ms
        if target_gap_ms == DEFAULT_TARGET_GAP_MS:
            target_gap_ms = policy.target_gap_ms

    if threshold_ms <= 0:
        raise ValueError(f"threshold_ms must be positive, got {threshold_ms}")
    if target_gap_ms < 0:
        raise ValueError(f"target_gap_ms cannot be negative, got {target_gap_ms}")
    if target_gap_ms >= threshold_ms:
        raise ValueError(
            f"target_gap_ms ({target_gap_ms}) must be strictly less than "
            f"threshold_ms ({threshold_ms})"
        )

    if not words:
        return (), 0

    is_filler, excised_count = _identify_filler_words(words, filler_tokens)
    surviving_words = [w for i, w in enumerate(words) if not is_filler[i]]
    if len(surviving_words) <= 1 and excised_count == 0:
        return tuple(words), 0

    clip_in_ms = min(w.start_ms for w in words)
    clip_out_ms = max(w.end_ms for w in words)
    plan = plan_silence_tightening(
        words,
        clip_in_ms=clip_in_ms,
        clip_out_ms=clip_out_ms,
        threshold_ms=threshold_ms,
        target_gap_ms=target_gap_ms,
        filler_tokens=filler_tokens,
        speech_intervals=speech_intervals,
        protected_intervals=protected_intervals,
        uncertain_intervals=uncertain_intervals,
        min_word_conf=min_word_conf,
        review_uncertain=review_uncertain,
        policy=policy,
    )

    if plan.total_removed_ms == 0:
        return tuple(surviving_words), 0

    tightened: list[Word] = []
    for w in surviving_words:
        new_start = remap_timestamp(w.start_ms, plan) + clip_in_ms
        dur = w.end_ms - w.start_ms
        tightened.append(
            Word(
                w=w.w,
                start_ms=new_start,
                end_ms=new_start + dur,
                conf=w.conf,
            )
        )

    return tuple(tightened), plan.total_removed_ms


def tighten_sentences(
    sentences: Sequence[Sentence],
    *,
    threshold_ms: int = DEFAULT_SILENCE_THRESHOLD_MS,
    target_gap_ms: int = DEFAULT_TARGET_GAP_MS,
    filler_tokens: Collection[str] | None = None,
    speech_intervals: Sequence[tuple[int, int]] = (),
    protected_intervals: Sequence[tuple[int, int] | Any] = (),
    uncertain_intervals: Sequence[tuple[int, int]] = (),
    min_word_conf: float = 0.0,
    review_uncertain: bool = False,
    policy: SilencePolicy | None = None,
) -> tuple[tuple[Sentence, ...], int]:
    """Tighten pauses across a sequence of sentences while preserving grouping.

    Returns (tightened_sentences, total_removed_ms).
    """
    if not sentences:
        return (), 0

    all_words: list[Word] = []
    sentence_word_tags: list[int] = []
    for s_idx, s in enumerate(sentences):
        for w in s.words:
            all_words.append(w)
            sentence_word_tags.append(s_idx)

    tightened_words, total_removed = tighten_silence(
        all_words,
        threshold_ms=threshold_ms,
        target_gap_ms=target_gap_ms,
        filler_tokens=filler_tokens,
        speech_intervals=speech_intervals,
        protected_intervals=protected_intervals,
        uncertain_intervals=uncertain_intervals,
        min_word_conf=min_word_conf,
        review_uncertain=review_uncertain,
        policy=policy,
    )

    if not filler_tokens:
        reconstructed: list[Sentence] = []
        word_offset = 0
        for s in sentences:
            count = len(s.words)
            s_words = tightened_words[word_offset : word_offset + count]
            reconstructed.append(Sentence(words=s_words, complete=s.complete))
            word_offset += count
        return tuple(reconstructed), total_removed

    is_filler, _ = _identify_filler_words(all_words, filler_tokens)

    surviving_tags = [sentence_word_tags[i] for i, f in enumerate(is_filler) if not f]
    by_sentence: dict[int, list[Word]] = {i: [] for i in range(len(sentences))}
    for word, s_idx in zip(tightened_words, surviving_tags, strict=True):
        by_sentence[s_idx].append(word)

    reconstructed_s: list[Sentence] = []
    for s_idx, s in enumerate(sentences):
        s_words = tuple(by_sentence[s_idx])
        if s_words:
            reconstructed_s.append(Sentence(words=s_words, complete=s.complete))

    if not reconstructed_s and sentences:
        return tuple(sentences), 0

    return tuple(reconstructed_s), total_removed


def tighten_clip(
    clip: Clip,
    *,
    threshold_ms: int = DEFAULT_SILENCE_THRESHOLD_MS,
    target_gap_ms: int = DEFAULT_TARGET_GAP_MS,
    filler_tokens: Collection[str] | None = None,
    speech_intervals: Sequence[tuple[int, int]] = (),
    protected_intervals: Sequence[tuple[int, int] | Any] = (),
    uncertain_intervals: Sequence[tuple[int, int]] = (),
    min_word_conf: float = 0.0,
    review_uncertain: bool = False,
    policy: SilencePolicy | None = None,
) -> tuple[Clip, int]:
    """Tighten silence in a Clip contract, recording total removed ms in output.

    Returns (updated_clip, total_removed_ms).
    """
    tightened_words, total_removed = tighten_silence(
        clip.transcript.words,
        threshold_ms=threshold_ms,
        target_gap_ms=target_gap_ms,
        filler_tokens=filler_tokens,
        speech_intervals=speech_intervals,
        protected_intervals=protected_intervals,
        uncertain_intervals=uncertain_intervals,
        min_word_conf=min_word_conf,
        review_uncertain=review_uncertain,
        policy=policy,
    )

    new_text = " ".join(w.w for w in tightened_words)
    updated_transcript = ClipTranscript(
        raw_ckb=new_text,
        norm_ckb=new_text,
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
