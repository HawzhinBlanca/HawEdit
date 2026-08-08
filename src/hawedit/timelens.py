"""Â§3 Stage 5 â€” TimeLens2-4B's output, and which of its intervals Stage 5 may use.

Â§3 Stage 5 opens with a warning, in bold, before it gives any formula:

    **TimeLens2-4B returns intervals containing relevant visual evidence. It does not produce
    editorial cuts and cannot locate a speech-only idea without transcript timing.** Treat its
    output as one input among five.

`boundary.py` has honoured the second sentence since it was written: the interval is one soft
signal among five and may only extend outward, so a visual model can never truncate a Kurdish
sentence. What it could not honour was the first, because what arrived was
`timelens_interval_end_ms` â€” a bare integer with no way to ask which interval produced it.

Â§3 writes the out-point rule as `latest of { â€¦, timelens_interval_end }`, and the naive reading
of "latest" is `max()` over every interval the model returned for the episode. That reading
turns an interval at 5:00 into the out-point of a clip anchored at 10â€“14 s: `final_out` becomes
305 000 ms, Kurdish invariant #2 is satisfied â€” `final_out >= anchor_out`, generously â€” and the
clip runs from one Kurdish sentence into five minutes of unrelated footage with every check
green. The invariant constrains *direction*. Nothing constrained *relevance*.

So this module does the selection Â§3 leaves implicit, and does it by the rule Â§3 states: the
model reports evidence *contained in* an interval, and an interval that shares no footage with
the anchored idea is evidence about a different moment. Only overlapping intervals are
eligible. And because a fix that lives only here would leave the next hand-built
`BoundaryInputs` free to pass the bare integer again â€” the exact "one call site over" mistake
this codebase has now made twice â€” `fuse_boundary` requires the interval's start alongside its
end and checks the overlap itself.

The model is `BLOCKED.md` #2 (GPU) and #6 (weights). This is the type it will return.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from hawedit.registry import resolve_role
from hawedit.visual_index import SceneWindow

__all__ = [
    "TIMELENS_MODEL",
    "VisualEvidenceInterval",
    "interval_end_for_fusion",
]

TIMELENS_MODEL: Final = "MCG-NJU/TimeLens2-4B"
_EVIDENCE_ROLE: Final = frozenset({"temporal_evidence"})

# The model answers in seconds to one decimal, and ffmpeg's `fps` filter samples at interval
# centres, so the last frame sits half an interval before the window's nominal end. A span
# reported as reaching the end is therefore allowed to exceed it by that rounding — but not by
# more, which is the difference between tail rounding and a moment the model was never shown.
_SPAN_TOLERANCE_S: Final = 0.05


@dataclass(frozen=True, slots=True)
class VisualEvidenceInterval:
    """A span TimeLens2 says contains visual evidence, and what it says is in it.

    Not a cut. Â§3 Stage 5 is explicit that this model "does not produce editorial cuts", and
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
                "interval carries no claim. Â§3 applies the same rule to SV6D â€” 'Reject output "
                "where a claim has no timeline evidence' â€” and the converse holds here: a span "
                "of time asserting nothing is not evidence, and it would still move a boundary."
            )
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be within [0, 1], got {self.confidence}")

    @classmethod
    def from_window(
        cls,
        window: SceneWindow,
        start_s: float,
        end_s: float,
        claim: str,
        confidence: float | None = None,
        model_id: str = TIMELENS_MODEL,
    ) -> VisualEvidenceInterval:
        """A model's window-relative span, on the media's clock.

        TimeLens2 is shown one window and answers in seconds from **its** start;
        `start_ms`/`end_ms` here are media-absolute, and so is everything `boundary.py` fuses.
        Those two agree for exactly the windows that begin at 0. Measured on the fixture: asked
        about the blue "2" scene while shown only that scene — 2800..4162 ms — the model returned
        `[[0.0, 0.8]]`, which unshifted is 0..800 ms, a span inside the *first* scene of the
        episode.

        That is the M6.1 defect through a different door. M6.1 exists because a bare interval end
        let §3's "latest of { …, timelens_interval_end }" reach across an episode; the relevance
        gate closes that by requiring overlap with the anchored sentence. An unshifted interval
        passes the gate whenever it happens to overlap — and then extends the clip using evidence
        from somewhere else entirely, with Kurdish invariant #2 still satisfied because the
        invariant constrains direction.

        Doing the arithmetic here rather than in the adapter means a second producer — a batch
        grounder, a rehydrated JSON document — cannot omit it.

        Raises:
            ValueError: the span is not inside the window the model was shown. A model reporting
                a moment outside its own input has no footage behind the claim, and once shifted
                the number would land in a neighbouring scene and read as evidence.
        """
        duration_s = window.duration_ms / 1000.0
        if not 0.0 <= start_s < end_s <= duration_s + _SPAN_TOLERANCE_S:
            raise ValueError(
                f"{window.window_id} spans {duration_s:.3f} s and the model returned "
                f"{start_s}..{end_s} s. A span outside the window is not evidence about it, and "
                f"shifted onto the media's clock it would point into an adjacent scene."
            )
        return cls(
            media_id=window.media_id,
            start_ms=window.in_ms + round(start_s * 1000),
            end_ms=window.in_ms + round(end_s * 1000),
            claim=claim,
            confidence=confidence,
            model_id=model_id,
        )

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
    """The single number Â§3 Stage 5's out-point rule takes from TimeLens2 â€” or `None`.

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

    # Relevance first, magnitude second. Doing it the other way round â€” max() over every
    # interval â€” is the five-minute clip this module exists to prevent.
    relevant = [i for i in intervals if i.overlaps(anchor_in_ms, anchor_out_ms)]
    if not relevant:
        return None
    latest = max(i.end_ms for i in relevant)
    # An overlapping interval that ends before the anchor does is about this moment but cannot
    # extend it outward. Reporting it would put "timelens_interval_end" into `out_extended_by`
    # for a boundary TimeLens2 did not move.
    return latest if latest > anchor_out_ms else None
