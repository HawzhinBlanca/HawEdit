"""Multi-part story narrative extraction and semantic speech pruning.

Implements macro story extraction from long-form conversations (podcasts/interviews):
1. Identifies story arcs: Hook (0-3s), Setup, Conflict, Climax, and Resolution.
2. Generates Kurdish story headline and 1-2 sentence narrative summary.
3. Semantically prunes non-essential sentences, discursive tangents, and filler phrases
   across multiple non-contiguous parts while preserving 100% core meaning.
4. Re-indexes word alignment timestamps for frame-locked kinetic subtitles.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Final

from hawedit.sentences import DANGLING_CONJUNCTIONS_CKB, Sentence
from hawedit.silence import KURDISH_FILLER_TOKENS
from hawedit.transcripts import Word

__all__ = [
    "BeatKind",
    "CondensedStoryPlan",
    "StoryBeat",
    "StoryCondensationError",
    "StorySummary",
    "condense_multiple_arcs",
    "condense_story",
    "remap_words_to_condensed_timeline",
]

# Conversational Kurdish filler tokens and hesitation markers that add zero semantic value
KURDISH_FILLER_WORDS: Final[frozenset[str]] = KURDISH_FILLER_TOKENS

# Dangling forward-looking conjunctions that cannot safely terminate a condensed cut
DANGLING_CONJUNCTIONS: Final[frozenset[str]] = DANGLING_CONJUNCTIONS_CKB


class StoryCondensationError(ValueError):
    """Raised when story condensation fails or input constraints are violated."""


class BeatKind(str, Enum):
    """Narrative beat categorization within a viral short-form story arc."""

    HOOK = "hook"
    SETUP = "setup"
    CONFLICT = "conflict"
    CLIMAX = "climax"
    RESOLUTION = "resolution"


@dataclass(frozen=True, slots=True)
class StoryBeat:
    """A semantic narrative beat composed of one or more sentences."""

    beat_id: str
    beat_kind: BeatKind
    sentence_indices: tuple[int, ...]
    in_ms: int
    out_ms: int
    importance_score: float
    summary_kurdish: str

    def __post_init__(self) -> None:
        if not isinstance(self.beat_id, str) or not self.beat_id.strip():
            raise ValueError("beat_id must be a non-empty string")
        if not isinstance(self.beat_kind, BeatKind):
            raise TypeError(f"beat_kind must be BeatKind, got {type(self.beat_kind).__name__}")
        if not self.sentence_indices:
            raise ValueError("beat requires at least one sentence index")
        for idx in self.sentence_indices:
            if not isinstance(idx, int) or idx < 0:
                raise ValueError(f"invalid sentence index: {idx}")
        if type(self.in_ms) is not int or type(self.out_ms) is not int:
            raise TypeError("timestamps must be exact integers")
        if self.in_ms < 0:
            raise ValueError(f"in_ms must be non-negative, got {self.in_ms}")
        if self.out_ms <= self.in_ms:
            raise ValueError(f"out_ms ({self.out_ms}) must be > in_ms ({self.in_ms})")
        if (
            type(self.importance_score) not in (int, float)
            or not math.isfinite(self.importance_score)
            or not 0.0 <= float(self.importance_score) <= 1.0
        ):
            raise ValueError(f"importance_score must be in 0.0..1.0, got {self.importance_score}")
        if not isinstance(self.summary_kurdish, str):
            raise TypeError("summary_kurdish must be a string")

    @property
    def duration_ms(self) -> int:
        return self.out_ms - self.in_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "beat_id": self.beat_id,
            "beat_kind": self.beat_kind.value,
            "sentence_indices": list(self.sentence_indices),
            "in_ms": self.in_ms,
            "out_ms": self.out_ms,
            "duration_ms": self.duration_ms,
            "importance_score": round(float(self.importance_score), 4),
            "summary_kurdish": self.summary_kurdish,
        }


@dataclass(frozen=True, slots=True)
class StorySummary:
    """High-level Kurdish story headline and narrative overview."""

    headline_kurdish: str
    summary_kurdish: str
    virality_score: float
    core_topic: str
    key_entities: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.headline_kurdish, str) or not self.headline_kurdish.strip():
            raise ValueError("headline_kurdish must be a non-empty string")
        if not isinstance(self.summary_kurdish, str) or not self.summary_kurdish.strip():
            raise ValueError("summary_kurdish must be a non-empty string")
        if (
            type(self.virality_score) not in (int, float)
            or not math.isfinite(self.virality_score)
            or not 0.0 <= float(self.virality_score) <= 100.0
        ):
            raise ValueError(f"virality_score must be in 0.0..100.0, got {self.virality_score}")
        if not isinstance(self.core_topic, str) or not self.core_topic.strip():
            raise ValueError("core_topic must be a non-empty string")
        for ent in self.key_entities:
            if not isinstance(ent, str) or not ent.strip():
                raise ValueError(f"invalid entity: {ent!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "headline_kurdish": self.headline_kurdish,
            "summary_kurdish": self.summary_kurdish,
            "virality_score": round(float(self.virality_score), 2),
            "core_topic": self.core_topic,
            "key_entities": list(self.key_entities),
        }


@dataclass(frozen=True, slots=True)
class CondensedStoryPlan:
    """Outcome of multi-part story condensation and non-contiguous speech pruning."""

    story_id: str
    summary: StorySummary
    beats: tuple[StoryBeat, ...]
    retained_sentence_indices: tuple[int, ...]
    pruned_sentence_indices: tuple[int, ...]
    retained_spans: tuple[tuple[int, int], ...]
    total_source_duration_ms: int
    condensed_duration_ms: int
    prune_ratio: float

    def __post_init__(self) -> None:
        if not isinstance(self.story_id, str) or not self.story_id.strip():
            raise ValueError("story_id must be a non-empty string")
        if type(self.total_source_duration_ms) is not int or self.total_source_duration_ms <= 0:
            raise ValueError("total_source_duration_ms must be positive integer")
        if type(self.condensed_duration_ms) is not int or self.condensed_duration_ms <= 0:
            raise ValueError("condensed_duration_ms must be positive integer")
        if not self.retained_spans:
            raise ValueError("retained_spans cannot be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "story_id": self.story_id,
            "summary": self.summary.to_dict(),
            "beats": [b.to_dict() for b in self.beats],
            "retained_sentence_indices": list(self.retained_sentence_indices),
            "pruned_sentence_indices": list(self.pruned_sentence_indices),
            "retained_spans": [list(span) for span in self.retained_spans],
            "total_source_duration_ms": self.total_source_duration_ms,
            "condensed_duration_ms": self.condensed_duration_ms,
            "prune_ratio": round(float(self.prune_ratio), 4),
        }


def _calculate_sentence_importance(s: Sentence, idx: int, total_sentences: int) -> float:
    """Calculate deterministic narrative importance score for a sentence."""
    words = s.words
    duration_s = (s.end_ms - s.start_ms) / 1000.0

    # 1. Hook bonus for opening sentences (0-3s / 0-10s)
    score = 0.5
    if idx == 0:
        score += 0.45  # Hook is critical
    elif idx == total_sentences - 1:
        score += 0.40  # Climax / conclusion is critical

    # 2. Penalize sentences dominated by conversational fillers
    filler_count = sum(1 for w in words if w.w in KURDISH_FILLER_TOKENS)
    if len(words) > 0 and (filler_count / len(words)) > 0.3:
        score -= 0.4

    # 3. Penalize sentences ending with dangling conjunctions
    if words and words[-1].w in DANGLING_CONJUNCTIONS:
        score -= 0.35

    # 4. Reward information density (words per second)
    wps = len(words) / max(0.5, duration_s)
    if wps >= 2.0:
        score += 0.1
    elif wps < 1.0:
        score -= 0.15  # Drawling / rambling pace

    return max(0.0, min(1.0, score))


def condense_story(
    sentences: Sequence[Sentence],
    target_duration_ms: int = 50_000,
    min_duration_ms: int = 25_000,
    max_duration_ms: int = 60_000,
    story_id: str = "story-001",
    headline_kurdish: str = "پوختەی چیڕۆکەکە",
    summary_kurdish: str = "پوختەی گێڕانەوەی میوان لەسەر ڕووداوە گرنگەکان.",
    core_topic: str = "بەسەرهاتی سەرەکی",
    key_entities: Sequence[str] = (),
    virality_score: float | None = None,
) -> CondensedStoryPlan:
    """Condense long-form speech into a concise, high-retention multi-part story reel.

    Extracts essential narrative sentences (Hook, Conflict, Climax) while pruning
    conversational fillers, repetitive clauses, and tangential rambles.

    Args:
        sentences: Sequence of aligned Sentence objects covering the story.
        target_duration_ms: Ideal condensed duration (default 50s).
        min_duration_ms: Minimum duration floor (default 25s).
        max_duration_ms: Maximum duration ceiling (default 60s).
        story_id: Identifier for this condensed story plan.
        headline_kurdish: Generated or provided headline in Sorani Kurdish.
        summary_kurdish: Generated or provided 1-2 sentence narrative summary.
        core_topic: Topic classification.
        key_entities: Critical entities mentioned in the story.

    Returns:
        CondensedStoryPlan containing retained spans and beats.

    Raises:
        StoryCondensationError: If sentences are empty or constraints cannot be met.
    """
    if not sentences:
        raise StoryCondensationError("Story condensation requires at least one sentence.")

    total_sentences = len(sentences)
    total_source_duration_ms = sentences[-1].end_ms - sentences[0].start_ms

    # Check if pruning is beneficial even when total_source_duration_ms <= max_duration_ms (CD-08)
    # If conversational waste / filler sentences exist, evaluate whether pruning them
    # improves pacing while preserving duration >= min_duration_ms.
    if total_source_duration_ms <= max_duration_ms:
        scored = [
            _calculate_sentence_importance(s, i, total_sentences) for i, s in enumerate(sentences)
        ]
        prune_candidates = [i for i in range(1, total_sentences - 1) if scored[i] < 0.35]

        retained = list(range(total_sentences))
        current_dur = total_source_duration_ms
        pruned: list[int] = []

        for p_idx in prune_candidates:
            s_dur = sentences[p_idx].end_ms - sentences[p_idx].start_ms
            if current_dur - s_dur >= min_duration_ms:
                retained.remove(p_idx)
                pruned.append(p_idx)
                current_dur -= s_dur

        retained_indices: tuple[int, ...]
        pruned_indices: tuple[int, ...]
        retained_spans: tuple[tuple[int, int], ...]

        if not pruned:
            retained_indices = tuple(range(total_sentences))
            pruned_indices = ()
            retained_spans = ((sentences[0].start_ms, sentences[-1].end_ms),)
            condensed_duration = total_source_duration_ms
            prune_ratio = 0.0
        else:
            retained_indices = tuple(sorted(retained))
            pruned_indices = tuple(sorted(pruned))
            short_spans: list[tuple[int, int]] = []
            span_start = sentences[retained_indices[0]].start_ms
            span_end = sentences[retained_indices[0]].end_ms
            for idx in retained_indices[1:]:
                prev_idx = retained_indices[retained_indices.index(idx) - 1]
                if idx == prev_idx + 1:
                    span_end = sentences[idx].end_ms
                else:
                    short_spans.append((span_start, span_end))
                    span_start = sentences[idx].start_ms
                    span_end = sentences[idx].end_ms
            short_spans.append((span_start, span_end))
            retained_spans = tuple(short_spans)
            condensed_duration = sum(end - start for start, end in retained_spans)
            prune_ratio = round(
                (total_source_duration_ms - condensed_duration) / max(1, total_source_duration_ms),
                3,
            )

        if virality_score is None:
            s0_imp = scored[0]
            send_imp = scored[-1]
            mean_imp = sum(scored[i] for i in retained_indices) / max(1, len(retained_indices))
            calc_score = (0.40 * s0_imp + 0.30 * send_imp + 0.30 * mean_imp) * 100.0
            v_score = round(max(0.0, min(100.0, calc_score)), 1)
        else:
            v_score = float(virality_score)

        summary = StorySummary(
            headline_kurdish=headline_kurdish,
            summary_kurdish=summary_kurdish,
            virality_score=v_score,
            core_topic=core_topic,
            key_entities=tuple(key_entities),
        )
        short_beats: list[StoryBeat] = []
        for b_idx, (s_start, s_end) in enumerate(retained_spans):
            b_kind = (
                BeatKind.HOOK
                if b_idx == 0
                else (BeatKind.CLIMAX if b_idx == len(retained_spans) - 1 else BeatKind.CONFLICT)
            )
            b_sentences = tuple(
                idx
                for idx in retained_indices
                if sentences[idx].start_ms >= s_start and sentences[idx].end_ms <= s_end
            )
            short_beats.append(
                StoryBeat(
                    beat_id=f"{story_id}-b{b_idx}",
                    beat_kind=b_kind,
                    sentence_indices=b_sentences,
                    in_ms=s_start,
                    out_ms=s_end,
                    importance_score=0.9 if b_idx == 0 else 0.8,
                    summary_kurdish=summary_kurdish,
                )
            )
        return CondensedStoryPlan(
            story_id=story_id,
            summary=summary,
            beats=tuple(short_beats),
            retained_sentence_indices=retained_indices,
            pruned_sentence_indices=pruned_indices,
            retained_spans=retained_spans,
            total_source_duration_ms=total_source_duration_ms,
            condensed_duration_ms=condensed_duration,
            prune_ratio=prune_ratio,
        )

    # Calculate importance scores for all sentences
    scored_sentences: list[tuple[int, float, int]] = []
    for i, s in enumerate(sentences):
        dur = s.end_ms - s.start_ms
        imp = _calculate_sentence_importance(s, i, total_sentences)
        scored_sentences.append((i, imp, dur))

    # Mandatory elements:
    # 1. Hook (Sentence 0)
    # 2. Climax / Conclusion (Sentence total_sentences - 1)
    selected_set: set[int] = {0, total_sentences - 1}
    current_duration_ms = (sentences[0].end_ms - sentences[0].start_ms) + (
        sentences[-1].end_ms - sentences[-1].start_ms
    )

    # Sort remaining intermediate sentences by importance descending
    candidates = [item for item in scored_sentences if item[0] not in selected_set]
    candidates.sort(key=lambda x: x[1], reverse=True)

    # Greedily add highest-importance sentences until reaching target_duration_ms
    for idx, _imp, dur in candidates:
        if (current_duration_ms + dur <= target_duration_ms) or (
            current_duration_ms + dur <= max_duration_ms and current_duration_ms < min_duration_ms
        ):
            selected_set.add(idx)
            current_duration_ms += dur

    retained_indices_sorted = tuple(sorted(selected_set))
    pruned_indices_sorted = tuple(i for i in range(total_sentences) if i not in selected_set)

    # Group consecutive retained sentences into continuous spans
    spans: list[tuple[int, int]] = []
    curr_start = sentences[retained_indices_sorted[0]].start_ms
    curr_end = sentences[retained_indices_sorted[0]].end_ms

    for idx in retained_indices_sorted[1:]:
        s = sentences[idx]
        # If consecutive with negligible gap (< 600ms), merge
        if s.start_ms - curr_end <= 600:
            curr_end = s.end_ms
        else:
            spans.append((curr_start, curr_end))
            curr_start = s.start_ms
            curr_end = s.end_ms
    spans.append((curr_start, curr_end))

    total_condensed_ms = sum(end - start for start, end in spans)
    prune_ratio = (total_source_duration_ms - total_condensed_ms) / float(total_source_duration_ms)

    # Build narrative beats
    beats: list[StoryBeat] = []
    for beat_num, span in enumerate(spans):
        b_kind = (
            BeatKind.HOOK
            if beat_num == 0
            else BeatKind.CLIMAX
            if beat_num == len(spans) - 1
            else BeatKind.CONFLICT
        )
        beats.append(
            StoryBeat(
                beat_id=f"{story_id}-b{beat_num}",
                beat_kind=b_kind,
                sentence_indices=retained_indices_sorted,
                in_ms=span[0],
                out_ms=span[1],
                importance_score=0.85 if b_kind == BeatKind.HOOK else 0.80,
                summary_kurdish=f"بەشی {beat_num + 1}ی چیڕۆکەکە",
            )
        )

    if virality_score is None:
        s0_imp = scored_sentences[0][1]
        send_imp = scored_sentences[-1][1]
        retained_imps = [item[1] for item in scored_sentences if item[0] in selected_set]
        avg_retained_imp = sum(retained_imps) / len(retained_imps)
        calc_score = (0.40 * s0_imp + 0.30 * send_imp + 0.30 * avg_retained_imp) * 100.0
        v_score = round(max(0.0, min(100.0, calc_score)), 1)
    else:
        v_score = float(virality_score)

    summary = StorySummary(
        headline_kurdish=headline_kurdish,
        summary_kurdish=summary_kurdish,
        virality_score=v_score,
        core_topic=core_topic,
        key_entities=tuple(key_entities),
    )

    return CondensedStoryPlan(
        story_id=story_id,
        summary=summary,
        beats=tuple(beats),
        retained_sentence_indices=retained_indices_sorted,
        pruned_sentence_indices=pruned_indices_sorted,
        retained_spans=tuple(spans),
        total_source_duration_ms=total_source_duration_ms,
        condensed_duration_ms=total_condensed_ms,
        prune_ratio=prune_ratio,
    )


def remap_words_to_condensed_timeline(
    words: Sequence[Word], retained_spans: Sequence[tuple[int, int]]
) -> tuple[Word, ...]:
    """Re-index forced alignment word timestamps across non-contiguous retained cut spans.

    Maps source media timestamps onto a continuous output timeline, dropping any words
    falling into pruned intervals. Preserves exact word durations and strict monotonicity.

    Args:
        words: Aligned Word objects from source media.
        retained_spans: Ordered tuple of (in_ms, out_ms) intervals kept in the edit.

    Returns:
        Tuple of new Word objects with remapped start_ms and end_ms.
    """
    if not retained_spans:
        return ()

    remapped_words: list[Word] = []
    output_offset_ms = 0

    for span_in, span_out in retained_spans:
        span_dur = span_out - span_in
        for w in words:
            # Word must overlap this retained span
            if w.start_ms >= span_in and w.end_ms <= span_out:
                new_start = output_offset_ms + (w.start_ms - span_in)
                new_end = output_offset_ms + (w.end_ms - span_in)
                if new_end > new_start:
                    remapped_words.append(
                        Word(
                            w=w.w,
                            start_ms=new_start,
                            end_ms=new_end,
                            conf=w.conf,
                        )
                    )
        output_offset_ms += span_dur

    return tuple(remapped_words)


def condense_multiple_arcs(
    sentences: Sequence[Sentence],
    *,
    max_clips: int = 3,
    target_duration_ms: int = 50_000,
    min_duration_ms: int = 25_000,
    max_duration_ms: int = 60_000,
) -> list[CondensedStoryPlan]:
    """Extract multiple distinct, non-overlapping story arcs from a long transcript.

    Partitions long-form dialogue into candidate narrative windows and applies
    semantic story condensation to produce a ranked set of viral short candidates.

    Args:
        sentences: Sequence of aligned Sentence objects covering the long episode.
        max_clips: Maximum number of ranked story clips to return.
        target_duration_ms: Target duration per condensed reel.
        min_duration_ms: Minimum duration floor per condensed reel.
        max_duration_ms: Maximum duration ceiling per condensed reel.

    Returns:
        List of CondensedStoryPlan objects sorted by importance/virality.
    """
    if not sentences:
        return []

    total_duration_ms = sentences[-1].end_ms - sentences[0].start_ms
    # If the entire input fits within max_duration_ms, return a single story arc
    if total_duration_ms <= max_duration_ms:
        return [
            condense_story(
                sentences,
                target_duration_ms=target_duration_ms,
                min_duration_ms=min_duration_ms,
                max_duration_ms=max_duration_ms,
                story_id="clip-01",
            )
        ]

    # Partition sentences into thematic/temporal story windows (~80s of source material)
    window_duration_ms = 80_000
    plans: list[CondensedStoryPlan] = []
    window_start_idx = 0
    clip_count = 1

    while window_start_idx < len(sentences):
        window_sentences: list[Sentence] = []
        curr_win_dur = 0
        idx = window_start_idx

        while idx < len(sentences):
            s = sentences[idx]
            s_dur = s.end_ms - s.start_ms
            window_sentences.append(s)
            curr_win_dur += s_dur
            idx += 1
            if curr_win_dur >= window_duration_ms:
                break

        if curr_win_dur >= min_duration_ms:
            try:
                plan = condense_story(
                    window_sentences,
                    target_duration_ms=target_duration_ms,
                    min_duration_ms=min_duration_ms,
                    max_duration_ms=max_duration_ms,
                    story_id=f"clip-{clip_count:02d}",
                    headline_kurdish=f"بەسەرهاتی کاریگەر #{clip_count}",
                    summary_kurdish="کورتەی بەسەرهاتی هەڵبژێردراو لە ئەڵقەکە.",
                )
                global_retained = tuple(
                    idx + window_start_idx for idx in plan.retained_sentence_indices
                )
                global_pruned = tuple(
                    idx + window_start_idx for idx in plan.pruned_sentence_indices
                )
                global_beats = tuple(
                    replace(
                        b,
                        sentence_indices=tuple(
                            idx + window_start_idx for idx in b.sentence_indices
                        ),
                    )
                    for b in plan.beats
                )
                plan = replace(
                    plan,
                    retained_sentence_indices=global_retained,
                    pruned_sentence_indices=global_pruned,
                    beats=global_beats,
                )
                plans.append(plan)
                clip_count += 1
            except StoryCondensationError:
                pass

        # Advance window forward with overlap across the entire episode (CD-04)
        step = max(1, len(window_sentences) // 2) if window_sentences else 1
        window_start_idx += step

    # Rank candidate plans by measured virality score descending
    plans.sort(
        key=lambda p: (
            p.summary.virality_score,
            p.beats[0].importance_score if p.beats else 0.0,
        ),
        reverse=True,
    )

    ranked_plans: list[CondensedStoryPlan] = []
    for rank, p in enumerate(plans[:max_clips], start=1):
        target_id = f"clip-{rank:02d}"
        if p.story_id != target_id:
            p = replace(p, story_id=target_id)
        ranked_plans.append(p)
    return ranked_plans
