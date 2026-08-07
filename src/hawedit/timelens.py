"""§3 Stage 5 — TimeLens2-4B's output, and which of its intervals Stage 5 may use.

§3 Stage 5 opens with a warning, in bold, before it gives any formula:

    **TimeLens2-4B returns intervals containing relevant visual evidence. It does not produce
    editorial cuts and cannot locate a speech-only idea without transcript timing.** Treat its
    output as one input among five.

`boundary.py` has honoured the second sentence since it was written: the interval is one soft
signal among five and may only extend outward, so a visual model can never truncate a Kurdish
sentence. What it could not honour was the first, because what arrived was
`timelens_interval_end_ms` — a bare integer with no way to ask which interval produced it.

§3 writes the out-point rule as `latest of { …, timelens_interval_end }`, and the naive reading
of "latest" is `max()` over every interval the model returned for the episode. That reading
turns an interval at 5:00 into the out-point of a clip anchored at 10–14 s: `final_out` becomes
305 000 ms, Kurdish invariant #2 is satisfied — `final_out >= anchor_out`, generously — and the
clip runs from one Kurdish sentence into five minutes of unrelated footage with every check
green. The invariant constrains *direction*. Nothing constrained *relevance*.

So this module does the selection §3 leaves implicit, and does it by the rule §3 states: the
model reports evidence *contained in* an interval, and an interval that shares no footage with
the anchored idea is evidence about a different moment. Only overlapping intervals are
eligible. And because a fix that lives only here would leave the next hand-built
`BoundaryInputs` free to pass the bare integer again — the exact "one call site over" mistake
this codebase has now made twice — `fuse_boundary` requires the interval's start alongside its
end and checks the overlap itself.

The model is `BLOCKED.md` #2 (GPU) and #6 (weights). This is the type it will return.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from hawedit.registry import resolve_role

__all__ = [
    "TIMELENS_MODEL",
    "VisualEvidenceInterval",
    "interval_end_for_fusion",
]

TIMELENS_MODEL: Final = "MCG-NJU/TimeLens2-4B"
_EVIDENCE_ROLE: Final = frozenset({"temporal_evidence"})


@dataclass(frozen=True, slots=True)
class VisualEvidenceInterval:
    """A span TimeLens2 says contains visual evidence, and what it says is in it.

    Not a cut. §3 Stage 5 is explicit that this model "does not produce editorial cuts", and
    the type is named for what it is so that no call site can read it as one.
    """

    media_id: str
    start_ms: int
    end_ms: int
    claim: str
    confidence: float | None = None
    model_id: str = TIMELENS_MODEL

    def __post_init__(self) -> None:
        resolve_role(self.model_id, _EVIDENCE_ROLE, "the visual temporal evidence model")
        if self.start_ms < 0:
            raise ValueError(f"interval start is negative: {self.start_ms} ms")
        if self.end_ms <= self.start_ms:
            raise ValueError(
                f"interval spans {self.start_ms}..{self.end_ms}, which has no length. A span "
                f"occupying no time cannot contain evidence of anything."
            )
        if not self.claim.strip():
            raise ValueError(
                "interval carries no claim. §3 applies the same rule to SV6D — 'Reject output "
                "where a claim has no timeline evidence' — and the converse holds here: a span "
                "of time asserting nothing is not evidence, and it would still move a boundary."
            )
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be within [0, 1], got {self.confidence}")

    @property
    def span(self) -> tuple[int, int]:
        return self.start_ms, self.end_ms

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    def overlaps(self, in_ms: int, out_ms: int) -> bool:
        """True when this interval shares real footage with `[in_ms, out_ms)`.

        Touching at a single instant is not overlap: an interval beginning exactly where the
        anchored idea ends contains none of it.
        """
        return self.start_ms < out_ms and self.end_ms > in_ms

    def to_dict(self) -> dict[str, object]:
        return {
            "media_id": self.media_id,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "claim": self.claim,
            "confidence": self.confidence,
            "model_id": self.model_id,
        }


def interval_end_for_fusion(
    intervals: Sequence[VisualEvidenceInterval],
    anchor_in_ms: int,
    anchor_out_ms: int,
    media_id: str | None = None,
) -> int | None:
    """The single number §3 Stage 5's out-point rule takes from TimeLens2 — or `None`.

    `None` means "this model has nothing to say about this moment", which is not the same as
    "this model says the clip ends at zero". `fuse_boundary` treats an absent signal as no
    adjustment, so absence stays a refusal rather than becoming permission.

    Raises:
        ValueError: the anchors are malformed, or an interval belongs to other media.
    """
    if anchor_out_ms <= anchor_in_ms:
        raise ValueError(
            f"anchor_out ({anchor_out_ms} ms) must be after anchor_in ({anchor_in_ms} ms)"
        )
    if media_id is not None:
        foreign = sorted({i.media_id for i in intervals} - {media_id})
        if foreign:
            # Loudly, not by skipping: a media_id typo would otherwise discard an episode's
            # whole visual evidence and produce a run indistinguishable from one that had none.
            raise ValueError(
                f"visual evidence for media {foreign!r} was passed while fusing {media_id!r}"
            )

    # Relevance first, magnitude second. Doing it the other way round — max() over every
    # interval — is the five-minute clip this module exists to prevent.
    relevant = [i for i in intervals if i.overlaps(anchor_in_ms, anchor_out_ms)]
    if not relevant:
        return None
    latest = max(i.end_ms for i in relevant)
    # An overlapping interval that ends before the anchor does is about this moment but cannot
    # extend it outward. Reporting it would put "timelens_interval_end" into `out_extended_by`
    # for a boundary TimeLens2 did not move.
    return latest if latest > anchor_out_ms else None
