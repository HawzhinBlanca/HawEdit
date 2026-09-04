"""Length variants (15s, 30s, 60s) for multi-duration social distribution (Task T2.11).

Implements sentence-complete sub-span planning inside winning clips per BLUEPRINT §5
durations contract, ensuring every variant preserves complete Kurdish sentences,
anchors on the hook sentence, and complies with delivery reconciliation.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

from hawedit.sentences import Sentence, assert_deliverable_order

__all__ = [
    "DEFAULT_TARGET_DURATIONS_S",
    "LengthVariant",
    "plan_length_variants",
]

DEFAULT_TARGET_DURATIONS_S: Final[tuple[int, ...]] = (15, 30, 60)


@dataclass(frozen=True, slots=True)
class LengthVariant:
    """One duration variant sub-span composed of complete sentences."""

    target_s: int
    label: str
    in_ms: int
    out_ms: int
    duration_ms: int
    sentence_indices: tuple[int, ...]
    sentences: tuple[Sentence, ...]

    def __post_init__(self) -> None:
        if self.target_s <= 0:
            raise ValueError(f"target_s must be positive, got {self.target_s}")
        if self.out_ms <= self.in_ms:
            raise ValueError(f"out_ms ({self.out_ms}) must be > in_ms ({self.in_ms})")
        if self.duration_ms != self.out_ms - self.in_ms:
            raise ValueError(
                f"duration_ms ({self.duration_ms}) must equal out_ms - in_ms "
                f"({self.out_ms - self.in_ms})"
            )
        if not self.sentences:
            raise ValueError("LengthVariant must contain at least one sentence")
        for s in self.sentences:
            if not s.complete:
                raise ValueError(
                    f"LengthVariant sentence {s.text!r} has complete=False. "
                    "All sentences in a variant must be complete."
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_s": self.target_s,
            "label": self.label,
            "in_ms": self.in_ms,
            "out_ms": self.out_ms,
            "duration_ms": self.duration_ms,
            "sentence_indices": list(self.sentence_indices),
            "sentences_count": len(self.sentences),
        }


def plan_length_variants(
    sentences: Sequence[Sentence],
    *,
    targets_s: Sequence[int] = DEFAULT_TARGET_DURATIONS_S,
    min_ratio: float = 0.65,
    max_ratio: float = 1.35,
) -> tuple[LengthVariant, ...]:
    """Plan sentence-complete length variants inside a sequence of sentences.

    Parameters:
        sentences: Contiguous sequence of sentences from the parent clip.
        targets_s: Target durations in seconds (e.g. 15, 30, 60).
        min_ratio: Minimum fraction of target duration to accept.
        max_ratio: Maximum fraction of target duration to accept.

    Returns:
        Tuple of distinct LengthVariant objects, sorted by duration.
    """
    if not sentences:
        return ()

    assert_deliverable_order(sentences)

    # Only sentences with complete == True are eligible for inclusion
    complete_sentences = tuple(s for s in sentences if s.complete)
    if not complete_sentences:
        return ()

    variants: list[LengthVariant] = []
    seen_spans: set[tuple[int, int]] = set()

    # Pre-calculate prefixes anchored on the hook (sentence 0)
    hook_start_ms = complete_sentences[0].start_ms

    for target in targets_s:
        if target <= 0:
            continue

        target_ms = target * 1000
        min_ms = int(round(target_ms * min_ratio))
        max_ms = int(round(target_ms * max_ratio))

        best_k: int | None = None
        best_diff = float("inf")

        for k in range(1, len(complete_sentences) + 1):
            dur = complete_sentences[k - 1].end_ms - hook_start_ms
            if min_ms <= dur <= max_ms:
                diff = abs(dur - target_ms)
                if diff < best_diff:
                    best_diff = diff
                    best_k = k

        # If no hook prefix fits within tolerance, check if the full clip fits
        if best_k is None and len(complete_sentences) > 1:
            total_dur = complete_sentences[-1].end_ms - hook_start_ms
            if min_ms <= total_dur <= max_ms:
                best_k = len(complete_sentences)

        if best_k is not None:
            selected_sub = complete_sentences[:best_k]
            span = (hook_start_ms, selected_sub[-1].end_ms)
            if span not in seen_spans:
                seen_spans.add(span)
                variants.append(
                    LengthVariant(
                        target_s=target,
                        label=f"{target}s",
                        in_ms=span[0],
                        out_ms=span[1],
                        duration_ms=span[1] - span[0],
                        sentence_indices=tuple(range(best_k)),
                        sentences=selected_sub,
                    )
                )

    variants.sort(key=lambda v: v.duration_ms)
    return tuple(variants)
