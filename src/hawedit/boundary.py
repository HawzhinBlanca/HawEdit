"""§3 Stage 5 boundary fusion, and Kurdish invariant #2.

    HARD CONSTRAINT — sentence boundaries from forced alignment
        anchor_in  = start of the first complete selected sentence
        anchor_out = end   of the last  complete selected sentence

    SOFT ADJUSTMENT — may only extend OUTWARD
        final_in  = earliest of { anchor_in,  vad_onset − 120 ms,
                                  preceding shot_cut within 400 ms,
                                  speaker_turn_start }
        final_out = latest   of { anchor_out + 200 ms tail, natural silence,
                                  following shot_cut within 400 ms,
                                  speaker_turn_end, timelens_interval_end }

    INVARIANT (assert before render, reject on failure)
        final_in  <= anchor_in
        final_out >= anchor_out

The structure is the whole design. The anchors come from forced alignment and are hard; every
other signal is advisory and may only push the clip **outward**. A soft input that would pull
a boundary inward is discarded rather than applied — which is why `anchor_in` is itself a
member of the `earliest of` set and `anchor_out + tail` of the `latest of` set. The invariant
then holds by construction, and is *still* asserted separately, because §3 Stage 5 says to
assert it before render and a `Boundary` can arrive from somewhere this module did not build
it: deserialized from §5 JSON, or produced by a future stage.

§3 Stage 5 on why this one rule earns its prominence: "This single invariant accounts for most
of the perceived quality gap between an auto-clipper that feels professional and one that
feels broken."

TimeLens2 appears here only as `timelens_interval_end_ms` — a number. §3 Stage 5: it "returns
intervals containing relevant visual evidence. It does not produce editorial cuts". Treating
it as one input among five is what keeps a visual model from silently truncating a sentence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final


def _strict_bool(value: object, field: str) -> bool:
    """Accept only a real boolean.

    `bool("false")` is `True`, so a JSON document carrying the string "false" for
    `sentence_complete` used to deserialize into a clip that passed the render gate. A
    contract that coerces its own refusal into an approval is worse than no contract —
    audit finding #3.
    """
    if not isinstance(value, bool):
        raise ValueError(
            f"{field} must be a JSON boolean, got {type(value).__name__} {value!r}. "
            f"Coercing it would let the string 'false' read as true."
        )
    return value


__all__ = [
    "SHOT_CUT_WINDOW_MS",
    "TAIL_MS",
    "VAD_LEAD_IN_MS",
    "Boundary",
    "BoundaryInputs",
    "BoundaryInvariantViolated",
    "IncompleteSentence",
    "assert_boundary_invariant",
    "fuse_boundary",
]

# The three constants §3 Stage 5 states literally.
VAD_LEAD_IN_MS: Final = 120
TAIL_MS: Final = 200
SHOT_CUT_WINDOW_MS: Final = 400


class IncompleteSentence(ValueError):
    """Raised when a candidate's sentence did not close. §5: reject, never render."""


class BoundaryInvariantViolated(ValueError):
    """Raised when Kurdish invariant #2 fails. The render gate."""


@dataclass(frozen=True, slots=True)
class BoundaryInputs:
    """Everything Stage 5 fuses: one hard pair of anchors and five advisory signals."""

    anchor_in_ms: int
    anchor_out_ms: int
    sentence_complete: bool
    vad_onset_ms: int | None = None
    natural_silence_ms: int | None = None
    shot_cuts_ms: tuple[int, ...] = field(default=())
    speaker_turn_start_ms: int | None = None
    speaker_turn_end_ms: int | None = None
    timelens_interval_end_ms: int | None = None


@dataclass(frozen=True, slots=True)
class Boundary:
    """§5's `boundary` block: the anchors, the final cut, and which input moved it.

    Deliberately **not** self-validating. `assert_boundary_invariant` is the render gate, and
    a type that could not represent a violation would give that gate nothing to catch — a
    boundary deserialized from another stage's JSON has to be checkable on arrival.
    """

    anchor_in_ms: int
    anchor_out_ms: int
    final_in_ms: int
    final_out_ms: int
    in_extended_by: str | None
    out_extended_by: str | None
    sentence_complete: bool
    confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor_in_ms": self.anchor_in_ms,
            "anchor_out_ms": self.anchor_out_ms,
            "final_in_ms": self.final_in_ms,
            "final_out_ms": self.final_out_ms,
            "in_extended_by": self.in_extended_by,
            "out_extended_by": self.out_extended_by,
            "sentence_complete": self.sentence_complete,
            "confidence": self.confidence,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Boundary:
        """Rebuild from §5 JSON. Does **not** validate — call the render gate explicitly."""
        return Boundary(
            anchor_in_ms=int(data["anchor_in_ms"]),
            anchor_out_ms=int(data["anchor_out_ms"]),
            final_in_ms=int(data["final_in_ms"]),
            final_out_ms=int(data["final_out_ms"]),
            in_extended_by=data.get("in_extended_by"),
            out_extended_by=data.get("out_extended_by"),
            sentence_complete=_strict_bool(data["sentence_complete"], "sentence_complete"),
            confidence=data.get("confidence"),
        )


def assert_boundary_invariant(boundary: Boundary) -> None:
    """Kurdish invariant #2. §3 Stage 5: assert before render, reject on failure.

    Raises:
        BoundaryInvariantViolated: the clip would start or end mid-sentence, or its
            sentence never closed.
    """
    # A real boolean, not merely something truthy. `Boundary` is deliberately not
    # self-validating so that *this* function can be the universal net — its docstring says a
    # boundary arriving as JSON from another stage "has to be checkable on arrival". The
    # strict-bool guard was wired into `Boundary.from_dict` alone, so anything built by another
    # route reached here with sentence_complete="false" and passed, because a non-empty string
    # is truthy. Kurdish invariant #2 is "reject, never render"; that rendered. Found by the
    # independent review of 2026-08-07.
    if not isinstance(boundary.sentence_complete, bool):
        raise BoundaryInvariantViolated(
            f"sentence_complete is {boundary.sentence_complete!r} "
            f"({type(boundary.sentence_complete).__name__}), not a boolean. "
            f"bool({boundary.sentence_complete!r}) would be "
            f"{bool(boundary.sentence_complete)} — a coercion here decides whether a clip that "
            f"never finished its sentence reaches a client (Kurdish invariant #2)."
        )
    if not boundary.sentence_complete:
        raise BoundaryInvariantViolated(
            "sentence_complete is false — reject, never render (Kurdish invariant #2). §3 "
            "Stage 5: if no sentence boundary exists within tolerance, extend to the next "
            "one or reject the candidate."
        )
    if boundary.final_in_ms > boundary.anchor_in_ms:
        raise BoundaryInvariantViolated(
            f"final_in ({boundary.final_in_ms} ms) is after anchor_in "
            f"({boundary.anchor_in_ms} ms): the clip would start mid-sentence. Soft inputs "
            f"may only extend outward (Kurdish invariant #2)."
        )
    if boundary.final_out_ms < boundary.anchor_out_ms:
        raise BoundaryInvariantViolated(
            f"final_out ({boundary.final_out_ms} ms) is before anchor_out "
            f"({boundary.anchor_out_ms} ms): the clip would end mid-sentence. Soft inputs "
            f"may only extend outward (Kurdish invariant #2)."
        )


def fuse_boundary(inputs: BoundaryInputs, confidence: float | None = None) -> Boundary:
    """Fuse the hard anchors with the advisory signals, per §3 Stage 5.

    Args:
        inputs: the anchors and whichever advisory signals are available. Every advisory
            signal is optional — the anchors alone produce a valid boundary.
        confidence: §5's `boundary.confidence`, if the caller has one.

    Returns:
        A `Boundary` satisfying Kurdish invariant #2 by construction, naming which input
        moved each edge so a reviewer can see why a clip runs where it does.

    Raises:
        IncompleteSentence: `sentence_complete` is false.
        ValueError: the anchors are malformed, or `confidence` is outside [0, 1].
    """
    if not inputs.sentence_complete:
        raise IncompleteSentence(
            "sentence_complete is false — §5's contract is reject, never render. A candidate "
            "whose sentence did not close has no valid anchor to extend from."
        )
    if inputs.anchor_in_ms < 0 or inputs.anchor_out_ms < 0:
        raise ValueError("anchors must not be negative")
    if inputs.anchor_out_ms <= inputs.anchor_in_ms:
        raise ValueError(
            f"anchor_out ({inputs.anchor_out_ms} ms) must be after anchor_in "
            f"({inputs.anchor_in_ms} ms) — a clip cannot end before it starts."
        )
    if confidence is not None and not 0.0 <= confidence <= 1.0:
        raise ValueError(f"confidence must be within [0, 1], got {confidence}")

    # --- in point: earliest of the candidates, anchor_in included so nothing pulls inward
    in_candidates: list[tuple[int, str | None]] = [(inputs.anchor_in_ms, None)]
    if inputs.vad_onset_ms is not None:
        in_candidates.append((inputs.vad_onset_ms - VAD_LEAD_IN_MS, "vad_onset"))
    if inputs.speaker_turn_start_ms is not None:
        in_candidates.append((inputs.speaker_turn_start_ms, "speaker_turn_start"))
    preceding_cuts = [
        cut
        for cut in inputs.shot_cuts_ms
        if cut <= inputs.anchor_in_ms and inputs.anchor_in_ms - cut <= SHOT_CUT_WINDOW_MS
    ]
    if preceding_cuts:
        in_candidates.append((min(preceding_cuts), "shot_cut"))

    final_in_ms, in_extended_by = min(in_candidates, key=lambda candidate: candidate[0])
    if final_in_ms < 0:
        # A clip cannot start before the media does. Clamping here is safe for the
        # invariant: 0 <= anchor_in always, because negative anchors are refused above.
        final_in_ms, in_extended_by = 0, in_extended_by

    # --- out point: latest of the candidates, tail always present
    out_candidates: list[tuple[int, str | None]] = [(inputs.anchor_out_ms + TAIL_MS, "tail")]
    if inputs.natural_silence_ms is not None:
        out_candidates.append((inputs.natural_silence_ms, "natural_silence"))
    if inputs.speaker_turn_end_ms is not None:
        out_candidates.append((inputs.speaker_turn_end_ms, "speaker_turn_end"))
    if inputs.timelens_interval_end_ms is not None:
        out_candidates.append((inputs.timelens_interval_end_ms, "timelens_interval_end"))
    following_cuts = [
        cut
        for cut in inputs.shot_cuts_ms
        if cut >= inputs.anchor_out_ms and cut - inputs.anchor_out_ms <= SHOT_CUT_WINDOW_MS
    ]
    if following_cuts:
        out_candidates.append((max(following_cuts), "shot_cut"))

    final_out_ms, out_extended_by = max(out_candidates, key=lambda candidate: candidate[0])

    boundary = Boundary(
        anchor_in_ms=inputs.anchor_in_ms,
        anchor_out_ms=inputs.anchor_out_ms,
        final_in_ms=final_in_ms,
        final_out_ms=final_out_ms,
        in_extended_by=in_extended_by,
        out_extended_by=out_extended_by,
        sentence_complete=True,
        confidence=confidence,
    )
    # Belt and braces: the construction above cannot violate the invariant, and §3 Stage 5
    # still says to assert it. A future edit to the candidate sets fails here, not in a clip.
    assert_boundary_invariant(boundary)
    return boundary
