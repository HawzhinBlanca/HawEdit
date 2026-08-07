"""§4.2 sentence segmentation over aligned words, and the §5 anchors derived from it.

§4.2: "Sentence segmentation runs on the aligned output using Kurdish punctuation *plus* VAD
pauses. ASR punctuation for low-resource languages is unreliable; never rely on it alone."

The second half is the design constraint. An OmniASR transcript of Kurdish conversation may
carry no sentence-final punctuation at all; a segmenter that splits only on `.` returns one
enormous sentence, §5's anchors collapse onto the whole segment, and "a clip never starts or
ends mid-sentence" quietly stops meaning anything while every test still passes. So a
boundary is punctuation **or** a sufficient pause, and the pause path is exercised on
unpunctuated input by the test suite.

**Completeness is the flag §5 spends.** A sentence closed by punctuation or by a pause ended
where the speaker ended it. A trailing run of words that simply ran out of segment did not —
it is a fragment, `complete=False`, and §5's contract on that is blunt: `sentence_complete ==
false ⇒ reject, never render`. `anchors_for` therefore ignores fragments entirely and returns
`None` when nothing complete is present, rather than offering a plausible-looking anchor. §3
Stage 5: "If no sentence boundary exists within tolerance, extend to the next one or reject
the candidate."
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Final

from hawedit.transcripts import Word

__all__ = [
    "DEFAULT_PAUSE_MS",
    "KURDISH_SENTENCE_FINAL",
    "Sentence",
    "anchors_for",
    "segment_sentences",
]

# Sentence-final marks in Kurdish text. The Arabic-script forms matter as much as the ASCII
# ones: `؟` U+061F and `۔` U+06D4 are what a Kurdish keyboard produces, and a segmenter that
# only knows `?` and `.` will silently miss every question in a real transcript.
KURDISH_SENTENCE_FINAL: Final[frozenset[str]] = frozenset({".", "!", "?", "؟", "۔", "…"})

# How much silence ends a sentence when punctuation does not. §4.2 mandates using pauses but
# names no threshold; 500 ms is a conversational sentence break rather than a breath. It is a
# tunable awaiting real audio — see DECISIONS.md D-014 — not a constant to trust.
DEFAULT_PAUSE_MS: Final = 500


@dataclass(frozen=True, slots=True)
class Sentence:
    """One sentence of aligned speech, and whether it actually finished."""

    words: tuple[Word, ...]
    complete: bool

    @property
    def start_ms(self) -> int:
        return self.words[0].start_ms

    @property
    def end_ms(self) -> int:
        return self.words[-1].end_ms

    @property
    def text(self) -> str:
        """The raw surface forms, joined. Not normalized — invariant #1 governs from here."""
        return " ".join(word.w for word in self.words)


def _ends_with_sentence_punctuation(word: Word) -> bool:
    return bool(word.w) and word.w[-1] in KURDISH_SENTENCE_FINAL


def segment_sentences(
    words: Sequence[Word],
    pause_ms: int = DEFAULT_PAUSE_MS,
    vad_pauses: Sequence[tuple[int, int]] = (),
) -> tuple[Sentence, ...]:
    """Split aligned words into sentences on Kurdish punctuation or a sufficient pause.

    Args:
        words: aligned words in time order (from `forced_alignment.align_words`).
        pause_ms: silence at or above this ends a sentence.
        vad_pauses: explicit `(start_ms, end_ms)` silences from Stage 0's VAD. Used in
            addition to the gaps between word timings, because VAD sees silence that word
            boundaries alone do not reveal.

    Returns:
        Sentences in order. The final one is `complete=False` when the words simply ran out
        rather than reaching a boundary.

    Raises:
        ValueError: `pause_ms` is not positive.
    """
    if pause_ms <= 0:
        raise ValueError(
            "pause_ms must be positive: a non-positive pause threshold would end a sentence "
            "at every word boundary."
        )
    if not words:
        return ()

    vad_silences = [(start, end) for start, end in vad_pauses if end - start >= pause_ms]

    def pause_follows(earlier: Word, later: Word) -> bool:
        if later.start_ms - earlier.end_ms >= pause_ms:
            return True
        return any(start >= earlier.end_ms and end <= later.start_ms for start, end in vad_silences)

    sentences: list[Sentence] = []
    current: list[Word] = [words[0]]
    for earlier, later in pairwise(words):
        if _ends_with_sentence_punctuation(earlier) or pause_follows(earlier, later):
            sentences.append(Sentence(words=tuple(current), complete=True))
            current = [later]
        else:
            current.append(later)

    # The tail closed properly only if its last word carries sentence-final punctuation;
    # otherwise the segment ran out mid-thought and this is a fragment.
    sentences.append(
        Sentence(words=tuple(current), complete=_ends_with_sentence_punctuation(current[-1]))
    )
    return tuple(sentences)


def anchors_for(sentences: Sequence[Sentence]) -> tuple[int, int] | None:
    """The §5 hard boundary anchors for a selection of sentences.

    §5: `anchor_in` is the start of the first *complete* selected sentence and `anchor_out`
    the end of the last. Fragments are excluded rather than rounded off — §5's contract is
    that `sentence_complete == false` means reject, never render.

    Returns:
        `(anchor_in_ms, anchor_out_ms)`, or `None` when the selection contains no complete
        sentence. `None` is the honest answer: §3 Stage 5 says extend to the next boundary
        or reject the candidate, and inventing an anchor here is precisely how a clip that
        starts mid-sentence reaches a client.
    """
    complete = [s for s in sentences if s.complete]
    if not complete:
        return None
    return complete[0].start_ms, complete[-1].end_ms
