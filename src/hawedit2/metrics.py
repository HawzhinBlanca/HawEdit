"""§8.1 accuracy metrics: normalized CER, spacing-free CER, named-entity error, code-switch
error.

§8.1's point is comparability, not novelty: "Published CERs across different models are
computed on different datasets with different normalization — they are not comparable. Only
this harness produces comparable numbers." Two consequences run through this module.

**Everything is scored on normalized text (invariant #3).** Scoring raw would charge a model
for the §4.1 encoding collisions — a keyboard difference, not a transcription error — and the
resulting CER would not be comparable across corpora that happen to use different keyboards.
Spacing-free CER goes one step further and drops whitespace entirely, because Sorani is
morphologically rich with heavy clitic attachment (§2) and its spacing is genuinely
unreliable; §8.1 asks for both views for that reason.

**Unmeasured is `None`, never 0.0.** An item with no annotated entities has no named-entity
error rate. Returning 0.0 would render in a report as a perfect score, which is precisely the
silent failure §1 says to avoid ("Fail visible, not silent").

Cost: `edit_distance` is the plain O(n·m) dynamic program over a rolling row. That is fine
for the sub-40 s VAD units §3 Stage 0 produces (a few hundred characters), which is the unit
§8.1 scores. Scoring a whole episode as one string is quadratic and should be done per
segment; if that ever becomes the bottleneck, the measurement justifies a bit-parallel
implementation, not a guess.
"""

from __future__ import annotations

from collections.abc import Sequence

from hawedit2.normalize import normalize_sorani

__all__ = [
    "cer",
    "code_switch_error_rate",
    "edit_distance",
    "named_entity_error_rate",
    "normalized_cer",
    "spacing_free_cer",
    "substring_edit_distance",
]


def edit_distance(a: str, b: str) -> int:
    """Levenshtein distance in Unicode codepoints.

    Codepoints, not bytes: Kurdish characters are multi-byte in UTF-8, and a byte-wise
    distance would inflate every CER in this system by a factor of roughly two.
    """
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(
                min(
                    previous[j] + 1,  # deletion
                    current[j - 1] + 1,  # insertion
                    previous[j - 1] + (ca != cb),  # substitution
                )
            )
        previous = current
    return previous[-1]


def substring_edit_distance(needle: str, haystack: str) -> int:
    """Fewest edits turning some substring of `haystack` into `needle`.

    The span-scoped metrics need this: a code-switched phrase is annotated on its own, and
    it has to be located in a hypothesis that surrounds it with unrelated Kurdish. Free
    prefix and suffix on the haystack; no free ends on the needle.
    """
    if not needle:
        return 0
    if not haystack:
        return len(needle)

    # Row 0 is all zeros: a match may begin at any offset in the haystack.
    previous = [0] * (len(haystack) + 1)
    for i, cn in enumerate(needle, start=1):
        current = [i]
        for j, ch in enumerate(haystack, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (cn != ch),
                )
            )
        previous = current
    return min(previous)


def cer(reference: str, hypothesis: str) -> float:
    """Character error rate: edits / reference length, on the strings as given.

    Not clipped at 1.0 — a model that hallucinates past the end of the reference should be
    able to score above it. Prefer `normalized_cer` for anything reported; this primitive
    scores whatever it is handed, including raw text.

    Raises:
        ValueError: `reference` is empty, which makes the rate undefined. A benchmark item
            with no reference transcript is a corpus bug and must be loud.
    """
    if not reference:
        raise ValueError(
            "empty reference: character error rate is undefined without a reference "
            "transcript. This is a corpus defect — fix the labelled set, do not score it."
        )
    return edit_distance(reference, hypothesis) / len(reference)


def normalized_cer(reference: str, hypothesis: str) -> float:
    """CER after §4.1 normalization of both sides — the §8.1 headline accuracy metric."""
    return cer(normalize_sorani(reference), normalize_sorani(hypothesis))


def _strip_whitespace(text: str) -> str:
    return "".join(text.split())


def spacing_free_cer(reference: str, hypothesis: str) -> float:
    """Normalized CER with all whitespace removed from both sides.

    §4.1 notes that KLPT strips outer whitespace but leaves internal runs (D-006), and §2
    notes Sorani's heavy clitic attachment. Together they mean word boundaries are not a
    reliable thing to score a model on; this view removes them from the question.
    """
    return cer(
        _strip_whitespace(normalize_sorani(reference)),
        _strip_whitespace(normalize_sorani(hypothesis)),
    )


def named_entity_error_rate(hypothesis: str, entities: Sequence[str]) -> float | None:
    """Fraction of reference named entities that did not survive transcription.

    §8.1 calls for named entities and political terminology specifically: they are the
    low-frequency tokens an ASR model is most likely to smooth into something plausible, and
    for a media organisation a wrong name is a different class of error from a wrong particle.

    An entity counts as surviving when it appears in the normalized hypothesis exactly
    (normalization-insensitive, so a keyboard difference is not scored as a lost name).
    Deliberately strict: a name that is 90% right is still the wrong name in a caption.

    Returns:
        The error rate, or `None` when no entities were annotated — unmeasured is not 0.0.
    """
    if not entities:
        return None
    normalized_hypothesis = normalize_sorani(hypothesis)
    missed = sum(1 for entity in entities if normalize_sorani(entity) not in normalized_hypothesis)
    return missed / len(entities)


def code_switch_error_rate(hypothesis: str, spans: Sequence[str]) -> float | None:
    """Mean CER over the annotated code-switched spans, located anywhere in `hypothesis`.

    §8.1 asks for Kurdish–English and Kurdish–Arabic code-switching as its own metric because
    an ASR model tuned for `ckb` can transcribe the Kurdish around a switch perfectly and
    still destroy the switch itself — which an aggregate CER dilutes into invisibility.

    Each span is scored by its best alignment against any substring of the hypothesis, since
    the span is annotated in isolation but appears embedded in surrounding Kurdish.

    Returns:
        The mean rate, or `None` when no spans were annotated — unmeasured is not 0.0.
    """
    if not spans:
        return None
    normalized_hypothesis = normalize_sorani(hypothesis)
    rates: list[float] = []
    for span in spans:
        normalized_span = normalize_sorani(span)
        if not normalized_span:
            raise ValueError(
                "empty code-switch span after normalization — this is a corpus defect, "
                "fix the labelled set rather than scoring an undefined span."
            )
        distance = substring_edit_distance(normalized_span, normalized_hypothesis)
        rates.append(distance / len(normalized_span))
    return sum(rates) / len(rates)
