"""§8.1's diarization arm: "pyannote Community-1 vs 3.1 on Kurdish multi-speaker material
(DER, plus boundary-reconciliation quality against your word alignment)."

Two metrics, and the second is the one that matters more here than the literature suggests.

**DER** is the standard decomposition — missed speech, false alarm, speaker confusion, over
total reference speech — with the speaker mapping chosen to minimise confusion, since
diarizer labels are arbitrary.

**Boundary reconciliation** exists because of what diarization is *for* in this system. §3
Stage 5 lists `speaker_turn_start` and `speaker_turn_end` among the five inputs to boundary
fusion, and §3 Stage 0 explains that Community-1 was chosen over the alternatives for its
exclusive diarization, "which makes reconciliation with transcript timestamps materially
easier — directly relevant to Stage 5". A diarizer with a good DER whose turn boundaries sit
200 ms away from every word boundary is worse for this pipeline than one with a slightly
worse DER that lands on the words.

Exclusivity is asserted rather than assumed: Community-1's exclusive output is the property
the blueprint selected it for, and silently accepting overlapping segments would let a
non-exclusive diarizer through the benchmark looking fine.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import pairwise, permutations
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from hawedit2.transcripts import Word

__all__ = [
    "MAX_SPEAKERS_FOR_EXACT_MAPPING",
    "BoundaryReconciliation",
    "DiarizationError",
    "OverlappingSegments",
    "Segment",
    "boundary_reconciliation",
    "diarization_error_rate",
]

# The optimal speaker mapping is found by exhaustive search. Interview and podcast material
# — what this system processes — is a handful of speakers, and 8! is 40320 mappings, which is
# instant. Beyond that the search would need the Hungarian algorithm; refusing is honest,
# guessing a greedy mapping would quietly report a DER that is not the minimum.
MAX_SPEAKERS_FOR_EXACT_MAPPING: Final = 8


class OverlappingSegments(ValueError):
    """Raised when a segment set is not exclusive (two speakers at the same instant)."""


@dataclass(frozen=True, slots=True)
class Segment:
    """One speaker's turn, in milliseconds."""

    start_ms: int
    end_ms: int
    speaker: str

    def __post_init__(self) -> None:
        if self.end_ms <= self.start_ms:
            raise ValueError(
                f"segment for {self.speaker!r} ends at or before it starts "
                f"({self.start_ms} → {self.end_ms})"
            )

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


def assert_exclusive(segments: Sequence[Segment]) -> None:
    """Refuse a segment set in which two segments overlap.

    §3 Stage 0 selected Community-1 specifically for *exclusive* speaker diarization. A
    benchmark that silently accepted overlapping output would score a diarizer on a
    property the pipeline cannot use.

    Raises:
        OverlappingSegments: two segments cover the same instant.
    """
    ordered = sorted(segments, key=lambda s: s.start_ms)
    for earlier, later in pairwise(ordered):
        if later.start_ms < earlier.end_ms:
            raise OverlappingSegments(
                f"segments overlap: {earlier.speaker!r} runs to {earlier.end_ms} ms while "
                f"{later.speaker!r} starts at {later.start_ms} ms. §3 Stage 0 expects "
                f"exclusive diarization."
            )


@dataclass(frozen=True, slots=True)
class DiarizationError:
    """A DER with its components, because the components are what you act on."""

    missed_ms: int
    false_alarm_ms: int
    confusion_ms: int
    total_speech_ms: int
    speaker_mapping: tuple[tuple[str, str], ...]

    @property
    def der(self) -> float:
        return (self.missed_ms + self.false_alarm_ms + self.confusion_ms) / self.total_speech_ms


def _speaker_at(segments: Sequence[Segment], start: int, end: int) -> str | None:
    for segment in segments:
        if segment.start_ms <= start and segment.end_ms >= end:
            return segment.speaker
    return None


def _boundaries(*groups: Iterable[Segment]) -> list[int]:
    points: set[int] = set()
    for group in groups:
        for segment in group:
            points.add(segment.start_ms)
            points.add(segment.end_ms)
    return sorted(points)


def diarization_error_rate(
    reference: Sequence[Segment],
    hypothesis: Sequence[Segment],
) -> DiarizationError | None:
    """Diarization error rate, with the speaker mapping that minimises confusion.

    Returns:
        The error and its breakdown, or `None` when the reference contains no speech —
        a 0.0 there would be a perfect score for measuring nothing.

    Raises:
        OverlappingSegments: either set is non-exclusive (§3 Stage 0).
        ValueError: more distinct speakers than the exact mapping search supports.
    """
    assert_exclusive(reference)
    assert_exclusive(hypothesis)

    total_speech = sum(s.duration_ms for s in reference)
    if not total_speech:
        return None

    reference_speakers = sorted({s.speaker for s in reference})
    hypothesis_speakers = sorted({s.speaker for s in hypothesis})
    if max(len(reference_speakers), len(hypothesis_speakers)) > MAX_SPEAKERS_FOR_EXACT_MAPPING:
        raise ValueError(
            f"more than {MAX_SPEAKERS_FOR_EXACT_MAPPING} speakers: the optimal mapping is "
            f"found by exhaustive search, and a greedy fallback would report a DER that is "
            f"not the minimum without saying so."
        )

    points = _boundaries(reference, hypothesis)
    intervals = [
        (start, end, _speaker_at(reference, start, end), _speaker_at(hypothesis, start, end))
        for start, end in pairwise(points)
    ]

    missed = sum(end - start for start, end, ref, hyp in intervals if ref and not hyp)
    false_alarm = sum(end - start for start, end, ref, hyp in intervals if hyp and not ref)

    best: tuple[int, tuple[tuple[str, str], ...]] | None = None
    longer, shorter = (
        (hypothesis_speakers, reference_speakers)
        if len(hypothesis_speakers) >= len(reference_speakers)
        else (reference_speakers, hypothesis_speakers)
    )
    for candidate in permutations(longer, len(shorter)):
        mapping = dict(zip(candidate, shorter, strict=True))
        if longer is reference_speakers:  # keep the mapping keyed by hypothesis speaker
            mapping = {v: k for k, v in mapping.items()}
        confusion = sum(
            end - start
            for start, end, ref, hyp in intervals
            if ref and hyp and mapping.get(hyp) != ref
        )
        pairs = tuple(sorted(mapping.items()))
        if best is None or confusion < best[0]:
            best = (confusion, pairs)

    confusion_ms, speaker_mapping = best if best is not None else (0, ())
    return DiarizationError(
        missed_ms=missed,
        false_alarm_ms=false_alarm,
        confusion_ms=confusion_ms,
        total_speech_ms=total_speech,
        speaker_mapping=speaker_mapping,
    )


@dataclass(frozen=True, slots=True)
class BoundaryReconciliation:
    """How close speaker-turn boundaries land to word boundaries from forced alignment."""

    boundaries: int
    mean_abs_error_ms: float
    within_tolerance_rate: float
    tolerance_ms: int


def boundary_reconciliation(
    turns: Sequence[Segment],
    words: Sequence[Word],
    tolerance_ms: int = 120,
) -> BoundaryReconciliation | None:
    """Distance from each speaker-turn boundary to the nearest word boundary.

    This is the §8.1 clause "boundary-reconciliation quality against your word alignment",
    and it is the number that decides whether a diarizer is useful to §3 Stage 5, where
    `speaker_turn_start` and `speaker_turn_end` are two of the five boundary inputs. A turn
    boundary landing mid-word cannot extend a clip to a sentence edge.

    The default tolerance is 120 ms — the same order as the 120 ms VAD onset lead-in §3
    Stage 5 applies — but it is recorded with the result, since a rate without its tolerance
    means nothing.

    Returns:
        The reconciliation, or `None` when there are no turns or no words to compare.
    """
    if not turns or not words:
        return None

    word_boundaries = sorted({w.start_ms for w in words} | {w.end_ms for w in words})
    errors: list[int] = []
    for turn in turns:
        for point in (turn.start_ms, turn.end_ms):
            errors.append(min(abs(point - boundary) for boundary in word_boundaries))

    within = sum(1 for error in errors if error <= tolerance_ms)
    return BoundaryReconciliation(
        boundaries=len(errors),
        mean_abs_error_ms=sum(errors) / len(errors),
        within_tolerance_rate=within / len(errors),
        tolerance_ms=tolerance_ms,
    )
