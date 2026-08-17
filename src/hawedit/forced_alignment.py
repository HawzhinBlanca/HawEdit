"""§4.2 — Viterbi forced alignment against OmniASR CTC-3B emissions.

§4.2 is unusually direct about what this has to be: "Implement Viterbi forced alignment
against OmniASR CTC-3B emissions. You already run the acoustic model, so there is no second
model and no alignment mismatch. This is a real engineering module with its own tests, not a
library call — Meta does not ship timestamp extraction as a finished feature." §7 attributes
it to us in the registry ("Custom Viterbi on CTC emissions | in-house"), and both
`mms-300m-1130-forced-aligner` and the `ctc-forced-aligner` package are excluded on
CC-BY-NC-4.0 grounds.

**Why the CTC model exists at all.** §3 Stage 1: the LLM decoder emits no frame-level
posteriors, so it cannot produce timings. CTC-3B runs in parallel on GPU 1 for exactly this
output, from the same acoustic family as the canonical transcript.

**The algorithm.** Standard CTC forced alignment. The target token sequence is expanded with
blanks interleaved — `[blank, t₀, blank, t₁, …, blank]` — and a Viterbi pass over
frames × states finds the highest-scoring monotone path, with the CTC transition rule: a
state may be entered from itself, from its predecessor, or by skipping a blank, and the skip
is only legal when it does not merge two identical adjacent tokens. That last clause is the
whole reason this is an algorithm rather than a per-frame argmax: without it, `دد` and `د`
are indistinguishable.

**What downstream code is owed.** Spans are monotone, non-overlapping, and every token gets
at least one frame. §5's `anchor_in_ms`/`anchor_out_ms` are derived from these, and the
Stage 5 hard invariant (`final_in <= anchor_in`) is only meaningful if the anchors are sound.
Infeasible input raises rather than returning a best-effort alignment — a silently wrong
timing becomes a clip that starts mid-word, and nothing downstream can detect it.

No third-party numerics: the DP is over `frames × (2·tokens + 1)` states, which for a sub-40 s
VAD unit (§3 Stage 0) is small enough that adding a dependency would cost more than it saves.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

from hawedit.transcripts import Word

__all__ = [
    "AlignmentInfeasible",
    "TokenSpan",
    "align_words",
    "collapse_ctc_path",
    "greedy_ctc_tokens",
    "minimum_frames",
    "viterbi_align",
]

_NEGATIVE_INFINITY = float("-inf")


class AlignmentInfeasible(ValueError):
    """Raised when no monotone path can emit the target tokens from these emissions."""


@dataclass(frozen=True, slots=True)
class TokenSpan:
    """The frames a single target token occupies, and how well they supported it."""

    token_id: int
    start_frame: int
    end_frame: int  # inclusive
    mean_logprob: float

    @property
    def frames(self) -> int:
        return self.end_frame - self.start_frame + 1


def collapse_ctc_path(best_path: Sequence[int], blank_id: int) -> tuple[int, ...]:
    """Collapse a per-frame best path into CTC's output: repeats merged, blanks dropped.

    Split out of `greedy_ctc_tokens` so the argmax can happen where the tensor lives. Measured on
    a 200-frame segment against a 32,000-token vocabulary, taking the argmax in Python costs
    **210 ms** and materialising the matrix with `.tolist()` another **183 ms** — about **215 s**
    across the real 38-minute file's 547 segments — where `tensor.argmax(dim=-1).tolist()` costs
    **2.03 ms**, or **1.1 s** over the same run. This half is O(frames) and stays pure. D-135.
    """
    decoded: list[int] = []
    previous: int | None = None
    for best in best_path:
        if best != previous and best != blank_id:
            decoded.append(best)
        previous = best
    return tuple(decoded)


def greedy_ctc_tokens(emissions: Sequence[Sequence[float]], blank_id: int) -> tuple[int, ...]:
    """CTC's own hypothesis from the same posteriors Viterbi aligns against.

    Best path per frame, consecutive repeats collapsed, blanks dropped — the standard CTC
    greedy decode. `viterbi_align` answers "where is *this* text"; this answers "what does the
    acoustic model say on its own", which is the other half of §3 Stage 1's escalation rule:
    route "any segment where LLM-7B and CTC-3B disagree materially".

    **The emissions must span the full vocabulary.** `asr._align_emissions` compacts them to
    the columns the LLM's own tokens occupy, because Viterbi never needs the rest. Decoding from
    that compacted matrix would confine CTC to the LLM's vocabulary and the two hypotheses could
    then only differ in order — the disagreement trigger would be structurally unable to fire on
    a substituted word, which is the case it exists for. D-135.

    No threshold and no model: an argmax and two filters over data Stage 1 already holds.

    Raises:
        ValueError: the matrix is empty or ragged, or `blank_id` is outside the vocabulary.
    """
    if not emissions:
        raise ValueError("no emissions: cannot decode an empty posterior matrix")
    vocabulary = len(emissions[0])
    for index, row in enumerate(emissions):
        if len(row) != vocabulary:
            raise ValueError(
                f"emissions frame {index} has width {len(row)}, expected {vocabulary}. A ragged "
                f"matrix means frames and vocabulary were transposed upstream."
            )
    if not 0 <= blank_id < vocabulary:
        raise ValueError(f"blank_id {blank_id} is outside the vocabulary of {vocabulary}")

    return collapse_ctc_path(
        [max(range(vocabulary), key=row.__getitem__) for row in emissions], blank_id
    )


def minimum_frames(tokens: Sequence[int]) -> int:
    """Fewest frames that could emit `tokens` under CTC.

    One frame per token, plus one for the mandatory blank between each pair of identical
    adjacent tokens — CTC collapses a repeat that is not separated by a blank.
    """
    if not tokens:
        return 0
    required = len(tokens)
    for earlier, later in pairwise(tokens):
        if earlier == later:
            required += 1
    return required


def _validate(emissions: Sequence[Sequence[float]], tokens: Sequence[int], blank_id: int) -> int:
    if not emissions:
        raise ValueError("no emissions: cannot align against an empty posterior matrix")
    if not tokens:
        raise ValueError("no tokens: there is nothing to align")

    vocabulary = len(emissions[0])
    for index, row in enumerate(emissions):
        if len(row) != vocabulary:
            raise ValueError(
                f"emissions frame {index} has width {len(row)}, expected {vocabulary}. A "
                f"ragged matrix means frames and vocabulary were transposed upstream."
            )
    if not 0 <= blank_id < vocabulary:
        raise ValueError(f"blank_id {blank_id} is outside the vocabulary of {vocabulary}")
    for token in tokens:
        if not 0 <= token < vocabulary:
            raise ValueError(
                f"token id {token} is outside the vocabulary of {vocabulary} — the "
                f"transcript was tokenized with a different model than these emissions."
            )

    needed = minimum_frames(tokens)
    if len(emissions) < needed:
        _infeasible(len(emissions), tokens, needed)
    return vocabulary


def _infeasible(frames: int, tokens: Sequence[int], needed: int) -> None:
    raise AlignmentInfeasible(
        f"{frames} frames cannot emit {len(tokens)} tokens: CTC needs at least {needed} "
        f"frames (one per token, plus a blank between each repeated pair). Aligning anyway "
        f"would invent timings, and a wrong word boundary becomes a clip that starts "
        f"mid-word with nothing downstream able to detect it."
    )


def viterbi_align(
    emissions: Sequence[Sequence[float]],
    tokens: Sequence[int],
    blank_id: int = 0,
) -> tuple[TokenSpan, ...]:
    """Align `tokens` to `emissions` and return one frame span per token.

    Args:
        emissions: per-frame log-probabilities over the CTC vocabulary, `frames × vocab`.
        tokens: the target token ids, in transcript order.
        blank_id: the CTC blank symbol's index.

    Returns:
        One `TokenSpan` per token, in order, monotone and non-overlapping.

    Raises:
        ValueError: malformed input (empty, ragged, or out-of-vocabulary).
        AlignmentInfeasible: too few frames to emit the tokens under CTC.
    """
    _validate(emissions, tokens, blank_id)

    # Interleave blanks: [blank, t0, blank, t1, ..., blank].
    extended: list[int] = [blank_id]
    for token in tokens:
        extended.append(token)
        extended.append(blank_id)
    states = len(extended)
    frames = len(emissions)

    scores = [[_NEGATIVE_INFINITY] * states for _ in range(frames)]
    backpointers = [[-1] * states for _ in range(frames)]

    scores[0][0] = emissions[0][extended[0]]
    if states > 1:
        scores[0][1] = emissions[0][extended[1]]

    for frame in range(1, frames):
        row = emissions[frame]
        previous = scores[frame - 1]
        for state in range(states):
            best_score = previous[state]
            best_previous = state
            if state >= 1 and previous[state - 1] > best_score:
                best_score = previous[state - 1]
                best_previous = state - 1
            # The skip transition. Legal only into a non-blank state whose token differs
            # from the one two states back — otherwise CTC would collapse the repeat.
            if (
                state >= 2
                and extended[state] != blank_id
                and extended[state] != extended[state - 2]
                and previous[state - 2] > best_score
            ):
                best_score = previous[state - 2]
                best_previous = state - 2
            if best_score == _NEGATIVE_INFINITY:
                continue
            scores[frame][state] = best_score + row[extended[state]]
            backpointers[frame][state] = best_previous

    final_candidates = [states - 1] + ([states - 2] if states >= 2 else [])
    end_state = max(final_candidates, key=lambda s: scores[frames - 1][s])
    if scores[frames - 1][end_state] == _NEGATIVE_INFINITY:
        _infeasible(frames, tokens, minimum_frames(tokens))

    # Backtrack to a state per frame.
    path = [0] * frames
    state = end_state
    for frame in range(frames - 1, -1, -1):
        path[frame] = state
        state = backpointers[frame][state]
        if state == -1 and frame > 0:
            _infeasible(frames, tokens, minimum_frames(tokens))

    # Odd states are tokens; state 2k+1 is tokens[k].
    starts: dict[int, int] = {}
    ends: dict[int, int] = {}
    totals: dict[int, float] = {}
    for frame, state_at_frame in enumerate(path):
        if state_at_frame % 2 == 0:
            continue  # blank
        index = (state_at_frame - 1) // 2
        starts.setdefault(index, frame)
        ends[index] = frame
        totals[index] = totals.get(index, 0.0) + emissions[frame][tokens[index]]

    if len(starts) != len(tokens):
        _infeasible(frames, tokens, minimum_frames(tokens))

    spans: list[TokenSpan] = []
    for index, token in enumerate(tokens):
        start, end = starts[index], ends[index]
        span_frames = end - start + 1
        spans.append(
            TokenSpan(
                token_id=token,
                start_frame=start,
                end_frame=end,
                mean_logprob=totals[index] / span_frames,
            )
        )
    return tuple(spans)


def align_words(
    emissions: Sequence[Sequence[float]],
    words: Sequence[tuple[str, Sequence[int]]],
    frame_duration_ms: float,
    blank_id: int = 0,
) -> tuple[Word, ...]:
    """Align tokenized words and return them with millisecond timings.

    Tokenization is model-specific and stays outside this module: the caller supplies each
    word's surface form together with its token ids, so the aligner never has to guess how
    the acoustic model's vocabulary segments Kurdish.

    Word times are frame-quantised and half-open — a word ends where the next may begin, so
    two adjacent words never claim the same millisecond and a clip boundary is never
    ambiguous.

    Confidence is `exp(mean log-probability)` over the word's frames: the same quantity §3
    Stage 1 escalates on ("mean token log-probability per segment from CTC posteriors"),
    expressed as a probability for §5's `conf` field.

    Raises:
        ValueError: a word carries no tokens, or the emissions are malformed.
        AlignmentInfeasible: too few frames for the token sequence.
    """
    if frame_duration_ms <= 0:
        raise ValueError("frame_duration_ms must be positive")

    flat_tokens: list[int] = []
    boundaries: list[tuple[int, int]] = []
    for surface, token_ids in words:
        if not token_ids:
            raise ValueError(
                f"word {surface!r} has no tokens. A word with no acoustic evidence cannot be "
                f"timed, and giving it a zero-length span would put a caption on nothing."
            )
        boundaries.append((len(flat_tokens), len(flat_tokens) + len(token_ids) - 1))
        flat_tokens.extend(token_ids)

    spans = viterbi_align(emissions, flat_tokens, blank_id=blank_id)

    aligned: list[Word] = []
    for (surface, _), (first, last) in zip(words, boundaries, strict=True):
        start_frame = spans[first].start_frame
        end_frame = spans[last].end_frame
        covered = spans[first : last + 1]
        mean_logprob = sum(s.mean_logprob * s.frames for s in covered) / sum(
            s.frames for s in covered
        )
        aligned.append(
            Word(
                w=surface,
                start_ms=round(start_frame * frame_duration_ms),
                end_ms=round((end_frame + 1) * frame_duration_ms),
                conf=math.exp(mean_logprob),
            )
        )
    return tuple(aligned)
