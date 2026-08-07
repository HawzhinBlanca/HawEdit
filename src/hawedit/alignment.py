"""§8.1's "alignment accuracy from CTC emissions", and Kurdish invariant #5.

    #5  Word timings come from OmniASR CTC Viterbi alignment only.

§4.2 puts word-level forced alignment among the three things that decide whether this system
works: "ASR gives you text, not reliable word timing. Boundaries that don't land on sentence
edges produce clips that feel broken regardless of model quality." The sentence anchors in
§5, and the hard boundary invariant in §3 Stage 5, are computed from these numbers — so an
alignment error does not stay an alignment error, it becomes a clip that starts mid-word.

Invariant #5 is enforced at construction (`AsrProvenance`) rather than described in a
comment. §4.2 excludes `mms-300m-1130-forced-aligner` and the `ctc-forced-aligner` package on
CC-BY-NC-4.0 grounds, and §3 Stage 1 explains why the CTC model runs in parallel at all: the
LLM decoder emits no frame-level posteriors, so it cannot produce timings. Exactly one source
is admissible, and anything else is refused before it can be stored and trusted.

Scoring compares two word sequences by their text and times only the words that actually
match, because the timing of a word the model never produced measures nothing. Matching is
normalization-insensitive so a §4.1 keyboard difference is not counted as a missing word.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Final

from hawedit.normalize import normalize_sorani

if TYPE_CHECKING:
    from hawedit.transcripts import AsrProvenance, Word

__all__ = [
    "CTC_VITERBI",
    "DEFAULT_TOLERANCE_MS",
    "AlignmentAccuracy",
    "assert_ctc_viterbi",
    "score_alignment",
]

# The only admissible aligner (invariant #5). §5's contract spells it exactly this way.
CTC_VITERBI: Final = "ctc_viterbi"

# A boundary this far from the reference is "on the word". 50 ms is roughly one frame of
# 24 fps video and below the threshold at which a cut reads as early or late — but it is a
# reporting parameter, not a quality gate, and it is recorded alongside every result so a
# rate is never quoted without the tolerance that produced it.
DEFAULT_TOLERANCE_MS: Final = 50


def assert_ctc_viterbi(aligner: str | None) -> None:
    """Refuse any source of word timings other than CTC Viterbi alignment (invariant #5).

    Raises:
        ValueError: `aligner` is missing or is not `ctc_viterbi`.
    """
    if aligner != CTC_VITERBI:
        raise ValueError(
            f"word timings must come from {CTC_VITERBI!r} (Kurdish invariant #5), got "
            f"{aligner!r}. §4.2: alignment runs on OmniASR CTC-3B emissions — the LLM "
            f"decoder emits no frame-level posteriors, and the NC-licensed aligners are "
            f"excluded by §7."
        )


@dataclass(frozen=True, slots=True)
class AlignmentAccuracy:
    """How closely hypothesised word timings track the reference."""

    matched_words: int
    reference_words: int
    mean_onset_abs_error_ms: float
    mean_offset_abs_error_ms: float
    within_tolerance_rate: float
    tolerance_ms: int

    @property
    def coverage(self) -> float:
        """Share of reference words that matched by text and could therefore be timed.

        Reported next to the errors on purpose: a tiny mean error over two matched words
        out of sixty is not a good alignment, it is a bad transcription.
        """
        return self.matched_words / self.reference_words


def score_alignment(
    reference: Sequence[Word],
    hypothesis: Sequence[Word],
    provenance: AsrProvenance,
    tolerance_ms: int = DEFAULT_TOLERANCE_MS,
) -> AlignmentAccuracy | None:
    """Score hypothesised word timings against reference timings.

    Only words matching by normalized text are timed; `coverage` reports how many that was.

    Returns:
        The accuracy, or `None` when no word matched — a mean error over zero words would
        otherwise be 0.0, which is the best possible score in a report.

    Raises:
        ValueError: the timings did not come from CTC Viterbi alignment (invariant #5).
    """
    assert_ctc_viterbi(provenance.aligner)
    if not reference:
        return None

    reference_keys = [normalize_sorani(w.w) for w in reference]
    hypothesis_keys = [normalize_sorani(w.w) for w in hypothesis]

    onset_errors: list[int] = []
    offset_errors: list[int] = []
    matcher = SequenceMatcher(a=reference_keys, b=hypothesis_keys, autojunk=False)
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            ref_word = reference[block.a + offset]
            hyp_word = hypothesis[block.b + offset]
            onset_errors.append(abs(ref_word.start_ms - hyp_word.start_ms))
            offset_errors.append(abs(ref_word.end_ms - hyp_word.end_ms))

    if not onset_errors:
        return None

    boundaries = onset_errors + offset_errors
    within = sum(1 for error in boundaries if error <= tolerance_ms)
    return AlignmentAccuracy(
        matched_words=len(onset_errors),
        reference_words=len(reference),
        mean_onset_abs_error_ms=sum(onset_errors) / len(onset_errors),
        mean_offset_abs_error_ms=sum(offset_errors) / len(offset_errors),
        within_tolerance_rate=within / len(boundaries),
        tolerance_ms=tolerance_ms,
    )
