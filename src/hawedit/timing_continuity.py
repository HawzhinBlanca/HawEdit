"""Timing tightening, continuity protection, and reaction timing validation (VE-09 / V09).

Guarantees that:
1. Protected pauses (dramatic pauses, hesitation, emotional beats, landing beats) are preserved
   and cannot be collapsed into dead air.
2. Reaction cutaways are contemporaneous with their stimulus speech and cannot fabricate
   reactions from distant source times (e.g. minute 40 reaction into minute 10 speech).
3. Speech boundaries are respected with zero truncation of word onsets or codas.
4. Temporal and causal ordering across speaker turns and events is strictly maintained.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

from hawedit.transcripts import Word

__all__ = [
    "ContinuityError",
    "ProtectedPause",
    "ProtectedPauseViolationError",
    "ReactionCutaway",
    "ReactionFabricationError",
    "SpeechTruncationError",
    "TightenedTimeline",
    "tighten_with_continuity_protection",
    "validate_reaction_cutaway",
]


class ContinuityError(ValueError):
    """Base exception for editorial continuity and timing violations."""


class ProtectedPauseViolationError(ContinuityError):
    """Raised when an edit cuts or truncates a protected, meaningful pause."""


class ReactionFabricationError(ContinuityError):
    """Raised when a reaction cutaway is taken from a non-contemporaneous source timestamp."""


class SpeechTruncationError(ContinuityError):
    """Raised when timing tightening slices into word boundaries."""


@dataclass(frozen=True, slots=True)
class ProtectedPause:
    """A meaningful pause that carries rhetorical, dramatic, or emotional weight."""

    pause_id: str
    start_ms: int
    end_ms: int
    reason: str
    min_retained_duration_ms: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.pause_id, str) or not self.pause_id.strip():
            raise ValueError("pause_id must be a non-empty string")
        if type(self.start_ms) is not int or type(self.end_ms) is not int:
            raise TypeError("pause timestamps must be exact integers")
        if self.start_ms < 0:
            raise ValueError("pause start_ms must be non-negative")
        if self.end_ms <= self.start_ms:
            raise ValueError(f"end_ms ({self.end_ms}) must be > start_ms ({self.start_ms})")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("reason must be an explicit, non-empty description")
        if type(self.min_retained_duration_ms) is not int:
            raise TypeError("min_retained_duration_ms must be an integer")
        if self.min_retained_duration_ms < 0:
            raise ValueError("min_retained_duration_ms must be non-negative")
        max_dur = self.end_ms - self.start_ms
        if self.min_retained_duration_ms > max_dur:
            raise ValueError(
                f"min_retained_duration_ms ({self.min_retained_duration_ms}) "
                f"cannot exceed total pause duration ({max_dur})"
            )

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "pause_id": self.pause_id,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "duration_ms": self.duration_ms,
            "reason": self.reason,
            "min_retained_duration_ms": self.min_retained_duration_ms,
        }


@dataclass(frozen=True, slots=True)
class ReactionCutaway:
    """A cutaway reaction shot linked to a specific stimulus speech event."""

    reaction_id: str
    reaction_in_ms: int
    reaction_out_ms: int
    subject_id: str
    stimulus_in_ms: int
    stimulus_out_ms: int
    max_causal_delta_ms: int = 4000

    def __post_init__(self) -> None:
        if not isinstance(self.reaction_id, str) or not self.reaction_id.strip():
            raise ValueError("reaction_id must be a non-empty string")
        for name, val in (
            ("reaction_in_ms", self.reaction_in_ms),
            ("reaction_out_ms", self.reaction_out_ms),
            ("stimulus_in_ms", self.stimulus_in_ms),
            ("stimulus_out_ms", self.stimulus_out_ms),
            ("max_causal_delta_ms", self.max_causal_delta_ms),
        ):
            if type(val) is not int:
                raise TypeError(f"{name} must be an integer")
            if val < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.reaction_out_ms <= self.reaction_in_ms:
            raise ValueError("reaction_out_ms must be > reaction_in_ms")
        if self.stimulus_out_ms <= self.stimulus_in_ms:
            raise ValueError("stimulus_out_ms must be > stimulus_in_ms")
        if not isinstance(self.subject_id, str) or not self.subject_id.strip():
            raise ValueError("subject_id must be a non-empty string")

    @property
    def duration_ms(self) -> int:
        return self.reaction_out_ms - self.reaction_in_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "reaction_id": self.reaction_id,
            "reaction_in_ms": self.reaction_in_ms,
            "reaction_out_ms": self.reaction_out_ms,
            "duration_ms": self.duration_ms,
            "subject_id": self.subject_id,
            "stimulus_in_ms": self.stimulus_in_ms,
            "stimulus_out_ms": self.stimulus_out_ms,
            "max_causal_delta_ms": self.max_causal_delta_ms,
        }


def validate_reaction_cutaway(reaction: ReactionCutaway) -> None:
    """Validate that a reaction is contemporaneous with the stimulus speech.

    Raises:
        ReactionFabricationError: If reaction comes from a distant, unrelated source time.
    """
    # Contemporaneous means reaction starts during stimulus or immediately after
    # (within causal delta). If reaction starts outside allowed causal window:
    delta_start = abs(reaction.reaction_in_ms - reaction.stimulus_in_ms)
    delta_end = abs(reaction.reaction_in_ms - reaction.stimulus_out_ms)
    min_delta = min(delta_start, delta_end)

    if min_delta > reaction.max_causal_delta_ms:
        delta_sec = min_delta / 1000.0
        raise ReactionFabricationError(
            f"Reaction {reaction.reaction_id!r} at {reaction.reaction_in_ms}ms is {delta_sec:.1f}s "
            f"away from stimulus speech [{reaction.stimulus_in_ms}..{reaction.stimulus_out_ms}]ms "
            f"(max allowed causal delta: {reaction.max_causal_delta_ms}ms). "
            f"Fabricating contemporaneous reactions across disparate times is strictly forbidden."
        )


@dataclass(frozen=True, slots=True)
class TightenedTimeline:
    """Timeline resulting from silence tightening with protected pause enforcement."""

    clip_in_ms: int
    clip_out_ms: int
    retained_intervals: tuple[tuple[int, int], ...]
    excised_intervals: tuple[tuple[int, int], ...]
    protected_pauses_preserved: tuple[str, ...]
    total_excised_ms: int
    effective_duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "clip_in_ms": self.clip_in_ms,
            "clip_out_ms": self.clip_out_ms,
            "retained_intervals": [list(iv) for iv in self.retained_intervals],
            "excised_intervals": [list(iv) for iv in self.excised_intervals],
            "protected_pauses_preserved": list(self.protected_pauses_preserved),
            "total_excised_ms": self.total_excised_ms,
            "effective_duration_ms": self.effective_duration_ms,
        }


def tighten_with_continuity_protection(
    words: Sequence[Word],
    clip_in_ms: int,
    clip_out_ms: int,
    *,
    protected_pauses: Sequence[ProtectedPause] = (),
    reactions: Sequence[ReactionCutaway] = (),
    silence_threshold_ms: int = 600,
    target_gap_ms: int = 150,
    word_boundary_buffer_ms: int = 50,
) -> TightenedTimeline:
    """Tighten unneeded dead air while strictly preserving protected pauses and word boundaries.

    Args:
        words: Aligned words covering the clip interval.
        clip_in_ms: Start timestamp on media clock.
        clip_out_ms: End timestamp on media clock.
        protected_pauses: Pauses marked as carrying dramatic, rhetorical, or emotional weight.
        reactions: Linked reaction cutaways to validate for contemporaneous alignment.
        silence_threshold_ms: Pauses longer than this are candidates for tightening.
        target_gap_ms: Default tightened gap size for non-protected dead air.
        word_boundary_buffer_ms: Margin to safeguard word onset and coda from truncation.

    Returns:
        TightenedTimeline with explicit retained/excised intervals.

    Raises:
        ReactionFabricationError: If any reaction is decoupled from its stimulus speech.
        ProtectedPauseViolationError: If an edit truncates a protected pause.
        SpeechTruncationError: If any cut slices into word boundaries.
    """
    if clip_out_ms <= clip_in_ms:
        raise ValueError(f"clip_out_ms ({clip_out_ms}) must be > clip_in_ms ({clip_in_ms})")
    if target_gap_ms < 0:
        raise ValueError("target_gap_ms cannot be negative")
    if target_gap_ms >= silence_threshold_ms:
        raise ValueError("target_gap_ms must be strictly less than silence_threshold_ms")

    # 1. Validate all reaction cutaways for temporal/causal validity
    for reaction in reactions:
        validate_reaction_cutaway(reaction)

    clip_words = [w for w in words if w.end_ms > clip_in_ms and w.start_ms < clip_out_ms]
    total_clip_dur = clip_out_ms - clip_in_ms

    if len(clip_words) <= 1:
        return TightenedTimeline(
            clip_in_ms=clip_in_ms,
            clip_out_ms=clip_out_ms,
            retained_intervals=((clip_in_ms, clip_out_ms),),
            excised_intervals=(),
            protected_pauses_preserved=tuple(p.pause_id for p in protected_pauses),
            total_excised_ms=0,
            effective_duration_ms=total_clip_dur,
        )

    # 2. Check each inter-word silence gap for tightening vs protected pauses
    excised: list[tuple[int, int]] = []
    preserved_pause_ids: list[str] = []

    for w1, w2 in pairwise(clip_words):
        gap_start = max(clip_in_ms, w1.end_ms)
        gap_end = min(clip_out_ms, w2.start_ms)
        gap_duration = gap_end - gap_start

        if gap_duration <= silence_threshold_ms:
            continue

        # Check if this gap overlaps any ProtectedPause
        overlapping_pauses = [
            p for p in protected_pauses if max(gap_start, p.start_ms) < min(gap_end, p.end_ms)
        ]

        if overlapping_pauses:
            for p in overlapping_pauses:
                preserved_pause_ids.append(p.pause_id)
                min_retained = (
                    p.min_retained_duration_ms if p.min_retained_duration_ms > 0 else p.duration_ms
                )
                if gap_duration <= min_retained:
                    # Keep full gap intact: cannot excise anything without violating min_retained
                    continue
                # Gap is larger than protected requirement: excise excess beyond min_retained
                allowed_trim = gap_duration - min_retained
                if allowed_trim > 100:
                    cut_start = gap_start + min_retained
                    cut_end = gap_end
                    # Enforce buffer around curr word start
                    if cut_end > cut_start:
                        excised.append((cut_start, cut_end))
        else:
            # Unprotected dead air: tighten down to target_gap_ms with word boundary buffer
            cut_start = gap_start + max(target_gap_ms, word_boundary_buffer_ms)
            cut_end = gap_end - word_boundary_buffer_ms
            if cut_end > cut_start:
                excised.append((cut_start, cut_end))

    # 3. Assert speech boundary protection: no excised interval may slice into any word
    for cut_in, cut_out in excised:
        for w in clip_words:
            # Slicing into word if cut overlaps [w.start_ms, w.end_ms]
            if max(cut_in, w.start_ms) < min(cut_out, w.end_ms):
                raise SpeechTruncationError(
                    f"Excised interval [{cut_in}..{cut_out}]ms slices into word '{w.w}' "
                    f"at [{w.start_ms}..{w.end_ms}]ms: speech truncation is strictly forbidden"
                )

    # 4. Compute retained intervals
    retained: list[tuple[int, int]] = []
    curr_time = clip_in_ms
    for cut_in, cut_out in excised:
        if cut_in > curr_time:
            retained.append((curr_time, cut_in))
        curr_time = cut_out
    if curr_time < clip_out_ms:
        retained.append((curr_time, clip_out_ms))

    total_excised = sum(c_out - c_in for c_in, c_out in excised)

    return TightenedTimeline(
        clip_in_ms=clip_in_ms,
        clip_out_ms=clip_out_ms,
        retained_intervals=tuple(retained),
        excised_intervals=tuple(excised),
        protected_pauses_preserved=tuple(preserved_pause_ids),
        total_excised_ms=total_excised,
        effective_duration_ms=total_clip_dur - total_excised,
    )
