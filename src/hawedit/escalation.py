"""§3 Stage 1 — routing hard segments to the validator.

    "compute mean token log-probability per segment from CTC posteriors. Route the bottom
    quartile, and any segment where LLM-7B and CTC-3B disagree materially, to the validator.
    Never escalate on duration or word-count heuristics."

Two signals, and one explicit prohibition.

**Confidence.** The bottom quartile by mean token log-probability, taken from the CTC
posteriors — which is the whole reason CTC-3B runs alongside the canonical model (§3 Stage 1:
the LLM decoder emits no frame-level posteriors). A quartile, not a fixed threshold: log-prob
scales vary with audio and model, so an absolute cutoff would escalate everything on one
recording and nothing on the next.

**Disagreement.** Two models reading the same audio differently is evidence independent of
either one's confidence, so a segment can be escalated while looking perfectly confident.
Disagreement is measured on *normalized* text (§4.1) — the two models typing the same Kurdish
with different keyboards is not disagreement, and scoring it as such would burn the
validator's 4 GiB on nothing.

**The prohibition is load-bearing.** Length is the cheap proxy for difficulty, and it is
wrong: a 38-second segment of clean studio speech needs no validator, while three seconds of
overlapping Slemani conversation does. `duration_s` is carried on the score for reporting
only — no code path reads it, and a test asserts that identical batches differing only in
duration produce identical decisions.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from hawedit.metrics import normalized_cer
from hawedit.transcripts import RawTranscript

__all__ = [
    "DEFAULT_DISAGREEMENT_CER",
    "EscalationDecision",
    "SegmentScore",
    "materially_disagree",
    "scores_from_transcript",
    "select_for_validation",
]

# How far apart the two models' hypotheses must be to count as "materially" disagreeing.
# §3 Stage 1 does not put a number on it — see DECISIONS.md D-015. Measured as normalized
# CER between the two, so a §4.1 encoding difference scores zero.
DEFAULT_DISAGREEMENT_CER: Final = 0.15


@dataclass(frozen=True, slots=True)
class SegmentScore:
    """One VAD segment's evidence, as Stage 1 produces it."""

    segment_id: str
    mean_logprob: float
    llm_text: str
    ctc_text: str
    # Reporting only. Deliberately unused by the decision — see the module docstring.
    duration_s: float

    def __post_init__(self) -> None:
        if self.mean_logprob > 0.0:
            raise ValueError(
                f"{self.segment_id}: mean_logprob must be a log-probability (<= 0), got "
                f"{self.mean_logprob}. Escalation ranks on CTC posteriors; a wrong scale here "
                f"silently inverts the quartile."
            )


@dataclass(frozen=True, slots=True)
class EscalationDecision:
    """Whether a segment goes to the validator, and why."""

    segment_id: str
    escalate: bool
    reason: str


def materially_disagree(
    llm_text: str,
    ctc_text: str,
    threshold_cer: float = DEFAULT_DISAGREEMENT_CER,
) -> bool:
    """Whether the two models' hypotheses differ enough to warrant the validator.

    Compared after §4.1 normalization, so the same Kurdish typed two ways is agreement.
    """
    if not llm_text.strip() or not ctc_text.strip():
        # One model produced nothing where the other produced speech. That is the strongest
        # disagreement available, and CER would raise on the empty reference.
        return llm_text.strip() != ctc_text.strip()
    return normalized_cer(llm_text, ctc_text) >= threshold_cer


def scores_from_transcript(transcript: RawTranscript) -> tuple[SegmentScore, ...]:
    """The §3 Stage 1 evidence a finished transcript carries, as escalation input.

    This is the missing link that left `select_for_validation` with no caller in `src/`: D-109
    put each segment's `mean_logprob` in the artifact, D-135 put both hypotheses beside it, and
    this turns them into scores. Reading from the artifact rather than from live model objects is
    deliberate — the rule can then be re-run against a transcript from disk, which is how a
    threshold gets tuned (§8.2) without paying for inference again.

    Segments carrying no CTC hypothesis are still scored: their confidence quartile is real, and
    `materially_disagree` treats one empty side as a disagreement, which is the honest reading of
    "one model produced nothing here".

    `segment_id` is the segment's own span on the media clock, so a decision points at audio
    rather than at a list position that changes when a region fails to align (D-103).
    """
    return tuple(
        SegmentScore(
            segment_id=f"{scored.start_ms}-{scored.end_ms}",
            mean_logprob=scored.mean_logprob,
            llm_text=scored.llm_text,
            ctc_text=scored.ctc_text,
            duration_s=(scored.end_ms - scored.start_ms) / 1000.0,
        )
        for scored in transcript.segment_confidence
    )


def select_for_validation(
    scores: Sequence[SegmentScore],
    threshold_cer: float = DEFAULT_DISAGREEMENT_CER,
) -> tuple[EscalationDecision, ...]:
    """Decide which segments go to the validator, returning a decision for every segment.

    The confidence quartile is `len(scores) // 4` segments — with fewer than four there is
    no bottom quarter and confidence escalates nothing, though disagreement still applies.

    Returns:
        One decision per input segment, in input order. Every decision carries its reason;
        a routing choice nobody can explain is one nobody can tune.
    """
    if not scores:
        return ()

    quartile_size = len(scores) // 4
    lowest = sorted(scores, key=lambda s: s.mean_logprob)[:quartile_size]
    low_confidence = {s.segment_id for s in lowest}

    decisions: list[EscalationDecision] = []
    for segment in scores:
        disagrees = materially_disagree(segment.llm_text, segment.ctc_text, threshold_cer)
        in_quartile = segment.segment_id in low_confidence

        if in_quartile and disagrees:
            reason = (
                f"bottom-quartile confidence (mean logprob {segment.mean_logprob:.3f}) and "
                f"the models disagree materially"
            )
        elif in_quartile:
            reason = f"bottom-quartile confidence (mean logprob {segment.mean_logprob:.3f})"
        elif disagrees:
            reason = (
                f"LLM and CTC disagree materially (normalized CER >= {threshold_cer:.2f}) "
                f"despite mean logprob {segment.mean_logprob:.3f}"
            )
        else:
            reason = f"confident (mean logprob {segment.mean_logprob:.3f}) and the models agree"

        decisions.append(
            EscalationDecision(
                segment_id=segment.segment_id,
                escalate=in_quartile or disagrees,
                reason=reason,
            )
        )
    return tuple(decisions)
