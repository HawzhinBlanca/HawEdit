"""Multi-moment story assembly and unified editorial judging (§3 Stage 6, pro-edit T6).

Assembles non-contiguous sentence highlights across an episode into a single coherent story reel.
Re-offsets word and sentence timestamps onto a unified continuous timeline [0, total_duration_ms]
while preserving Kurdish invariant #1 (exact surface words) and invariant #2 (complete sentences).

The entire assembled narrative is scored as one unit by the editorial judge (AC-7), enforcing
strict §2 thresholds on hook strength and misleading-edit risk (AC-8).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from hawedit.clip import (
    MAX_MISLEADING_EDIT_RISK,
    MIN_HOOK_SCORE,
    EditorialBelowThreshold,
)
from hawedit.judge import EditorialJudge, InputMode, JudgeRequest, JudgeVerdict
from hawedit.normalize import normalize_sorani
from hawedit.sentences import Sentence
from hawedit.transcripts import Word

__all__ = [
    "AssembledReel",
    "AssemblySpan",
    "assemble_spans",
    "judge_assembly",
]


@dataclass(frozen=True, slots=True)
class AssemblySpan:
    """One contiguous source span participating in an assembled reel."""

    span_index: int
    source_in_ms: int
    source_out_ms: int
    duration_ms: int
    sentences: tuple[Sentence, ...]

    def __post_init__(self) -> None:
        if self.span_index < 0:
            raise ValueError(f"span_index must be non-negative, got {self.span_index}")
        if self.source_out_ms <= self.source_in_ms:
            raise ValueError(
                f"source_out_ms ({self.source_out_ms}) must be > in_ms ({self.source_in_ms})"
            )
        if self.duration_ms != self.source_out_ms - self.source_in_ms:
            expected = self.source_out_ms - self.source_in_ms
            raise ValueError(f"duration_ms ({self.duration_ms}) must equal {expected}")
        if not self.sentences:
            raise ValueError("AssemblySpan must contain at least one sentence")


@dataclass(frozen=True, slots=True)
class AssembledReel:
    """An assembled multi-moment reel with continuous re-offset timestamps."""

    spans: tuple[AssemblySpan, ...]
    assembled_sentences: tuple[Sentence, ...]
    total_duration_ms: int
    raw_text: str
    norm_text: str

    def __post_init__(self) -> None:
        if not self.spans:
            raise ValueError("AssembledReel must contain at least one span")
        if self.total_duration_ms <= 0:
            raise ValueError(f"total_duration_ms must be positive, got {self.total_duration_ms}")
        if not self.assembled_sentences:
            raise ValueError("AssembledReel must contain assembled sentences")


def assemble_spans(span_groups: Sequence[Sequence[Sentence]]) -> AssembledReel:
    """Assemble multiple non-contiguous sentence groups into a continuous timeline.

    Args:
        span_groups: A sequence of sentence groups, each representing a contiguous source span.

    Returns:
        An AssembledReel with re-offset word timestamps starting at t=0.

    Raises:
        ValueError: If span_groups is empty, or any sentence is incomplete or has no words.
    """
    if not span_groups:
        raise ValueError("Cannot assemble an empty sequence of span groups")

    spans: list[AssemblySpan] = []
    assembled_sentences: list[Sentence] = []
    current_timeline_offset_ms = 0

    for span_idx, group in enumerate(span_groups):
        sentence_tuple = tuple(group)
        if not sentence_tuple:
            raise ValueError(f"Span group {span_idx} is empty")

        for sent in sentence_tuple:
            if not sent.complete:
                raise ValueError(
                    f"Kurdish invariant #2 violation: sentence {sent.text!r} is incomplete"
                )
            if not sent.words:
                raise ValueError(f"Sentence in span {span_idx} has no words")

        group_in_ms = sentence_tuple[0].start_ms
        group_out_ms = sentence_tuple[-1].end_ms
        if group_out_ms <= group_in_ms:
            raise ValueError(f"Invalid span timing: in_ms={group_in_ms} >= out_ms={group_out_ms}")

        duration_ms = group_out_ms - group_in_ms

        # Re-offset word timestamps for this span onto the assembled continuous timeline
        for sent in sentence_tuple:
            shifted_words: list[Word] = []
            for word in sent.words:
                rel_start = word.start_ms - group_in_ms
                rel_end = word.end_ms - group_in_ms
                if rel_start < 0 or rel_end < rel_start:
                    raise ValueError(
                        f"Word {word.w!r} [{word.start_ms}:{word.end_ms}] outside span"
                    )
                shifted_words.append(
                    Word(
                        w=word.w,
                        start_ms=current_timeline_offset_ms + rel_start,
                        end_ms=current_timeline_offset_ms + rel_end,
                        conf=word.conf,
                    )
                )
            assembled_sentences.append(Sentence(words=tuple(shifted_words), complete=True))

        spans.append(
            AssemblySpan(
                span_index=span_idx,
                source_in_ms=group_in_ms,
                source_out_ms=group_out_ms,
                duration_ms=duration_ms,
                sentences=sentence_tuple,
            )
        )
        current_timeline_offset_ms += duration_ms

    raw_text = " ".join(sent.text for sent in assembled_sentences)
    norm_text = normalize_sorani(raw_text)

    return AssembledReel(
        spans=tuple(spans),
        assembled_sentences=tuple(assembled_sentences),
        total_duration_ms=current_timeline_offset_ms,
        raw_text=raw_text,
        norm_text=norm_text,
    )


def judge_assembly(reel: AssembledReel, judge: EditorialJudge) -> JudgeVerdict:
    """Score an assembled multi-moment reel with the editorial judge and enforce §2 thresholds.

    Per AC-7, the judge scores the assembled narrative as a unified reel rather than individual
    source spans.
    Per AC-8, the §2 editorial thresholds apply directly to the assembled verdict.

    Args:
        reel: The assembled multi-moment reel.
        judge: An authenticated EditorialJudge implementation.

    Returns:
        The validated JudgeVerdict.

    Raises:
        EditorialBelowThreshold: If hook, misleading risk, self-containment, or fidelity fail.
    """
    approx_tokens = max(1, len(reel.norm_text.split()) * 2)
    candidate_id = f"assembly-{len(reel.spans)}spans-{reel.total_duration_ms}ms"

    request = JudgeRequest(
        candidate_id=candidate_id,
        mode=InputMode.STAGE_4_TRANSCRIPT_FIRST,
        tokens=approx_tokens,
        text_ckb=reel.norm_text,
        clip_in_ms=0,
        clip_out_ms=reel.total_duration_ms,
    )

    verdict = judge.judge(request)

    # Enforce AC-8 editorial thresholds
    if verdict.hook_score < MIN_HOOK_SCORE:
        raise EditorialBelowThreshold(
            f"Assembled reel hook score {verdict.hook_score:.2f} < {MIN_HOOK_SCORE:.2f}"
        )
    if verdict.misleading_edit_risk > MAX_MISLEADING_EDIT_RISK:
        risk = verdict.misleading_edit_risk
        raise EditorialBelowThreshold(
            f"Assembled reel misleading edit risk {risk:.2f} > {MAX_MISLEADING_EDIT_RISK:.2f}"
        )
    if not verdict.self_contained:
        raise EditorialBelowThreshold("Assembled reel was judged not self-contained")
    if verdict.meaning_fidelity < 1.0:
        raise EditorialBelowThreshold(
            f"Assembled reel meaning fidelity {verdict.meaning_fidelity:.2f} is below 1.00"
        )

    return verdict
