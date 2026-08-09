"""M1.2 — §4.2 sentence segmentation, and the anchors §5 derives from it.

§4.2: "Sentence segmentation runs on the aligned output using Kurdish punctuation *plus* VAD
pauses. ASR punctuation for low-resource languages is unreliable; never rely on it alone."

That last clause is the design constraint, not a caveat: a segmenter that splits only on `.`
returns one enormous sentence for a Kurdish podcast, and §3 Stage 5's anchors — and through
them the whole "a clip never starts or ends mid-sentence" guarantee — silently degrade to
nothing.

`complete` is the flag §5 spends as `sentence_complete`, whose contract is blunt:
`false ⇒ reject, never render`.
"""

from __future__ import annotations

import pytest

from hawedit.sentences import (
    DEFAULT_PAUSE_MS,
    KURDISH_SENTENCE_FINAL,
    anchors_for,
    segment_sentences,
)
from hawedit.transcripts import Word


def words(*specs: tuple[str, int, int]) -> tuple[Word, ...]:
    return tuple(Word(w=w, start_ms=s, end_ms=e, conf=0.95) for w, s, e in specs)


# --- punctuation ----------------------------------------------------------------------


def test_kurdish_sentence_final_punctuation_is_recognised() -> None:
    """Arabic-script question mark and full stop, not just the ASCII ones."""
    assert {".", "؟", "!", "۔"} <= KURDISH_SENTENCE_FINAL


def test_a_full_stop_ends_a_sentence() -> None:
    aligned = words(("ئەمە", 0, 300), ("باشە.", 300, 700), ("دواتر", 800, 1100))
    sentences = segment_sentences(aligned)
    assert len(sentences) == 2
    assert sentences[0].text == "ئەمە باشە."
    assert (sentences[0].start_ms, sentences[0].end_ms) == (0, 700)


def test_the_arabic_question_mark_ends_a_sentence() -> None:
    aligned = words(("چۆنی؟", 0, 500), ("باشم", 600, 900))
    assert len(segment_sentences(aligned)) == 2


# --- pauses: the half §4.2 says never to omit -----------------------------------------


def test_a_long_pause_ends_a_sentence_without_any_punctuation() -> None:
    """The case that matters: ASR for a low-resource language emits no punctuation at all."""
    aligned = words(("ئەمە", 0, 300), ("باشە", 300, 700), ("دواتر", 2000, 2400))
    sentences = segment_sentences(aligned, pause_ms=DEFAULT_PAUSE_MS)
    assert len(sentences) == 2
    assert sentences[0].text == "ئەمە باشە"
    assert sentences[1].text == "دواتر"


def test_a_short_gap_does_not_end_a_sentence() -> None:
    aligned = words(("ئەمە", 0, 300), ("زۆر", 350, 600), ("باشە", 650, 900))
    assert len(segment_sentences(aligned, pause_ms=DEFAULT_PAUSE_MS)) == 1


def test_punctuation_alone_would_have_returned_one_sentence() -> None:
    """Demonstrates the failure §4.2 warns about — and that we do not have it."""
    unpunctuated = words(
        ("یەک", 0, 300), ("دوو", 300, 600), ("سێ", 3000, 3300), ("چوار", 3300, 3600)
    )
    assert not any(w.w[-1] in KURDISH_SENTENCE_FINAL for w in unpunctuated)
    assert len(segment_sentences(unpunctuated)) == 2


def test_explicit_vad_pauses_are_honoured() -> None:
    """VAD knows about silence the word gaps do not show — §3 Stage 0 produces it."""
    aligned = words(("ئەمە", 0, 300), ("باشە", 320, 700))
    assert len(segment_sentences(aligned)) == 1
    assert len(segment_sentences(aligned, vad_pauses=((300, 320),), pause_ms=10)) == 2


# --- completeness: what §5 spends as sentence_complete --------------------------------


def test_a_sentence_closed_by_punctuation_is_complete() -> None:
    aligned = words(("ئەمە", 0, 300), ("باشە.", 300, 700))
    assert segment_sentences(aligned)[0].complete is True


def test_a_sentence_closed_by_a_pause_is_complete() -> None:
    aligned = words(("ئەمە", 0, 300), ("باشە", 300, 700), ("دواتر.", 2000, 2400))
    assert segment_sentences(aligned)[0].complete is True


def test_a_trailing_fragment_is_incomplete() -> None:
    """The segment ran out mid-thought. §5: false => reject, never render."""
    aligned = words(("ئەمە", 0, 300), ("باشە.", 300, 700), ("بەڵام", 800, 1100))
    sentences = segment_sentences(aligned)
    assert sentences[-1].complete is False


def test_no_words_yields_no_sentences() -> None:
    assert segment_sentences(()) == ()


# --- §5 anchors ------------------------------------------------------------------------


def test_anchors_come_from_complete_sentences_only() -> None:
    aligned = words(("یەک", 0, 300), ("دوو.", 300, 700), ("سێ", 800, 1100))
    sentences = segment_sentences(aligned)
    anchors = anchors_for(sentences)
    assert anchors is not None
    assert anchors == (0, 700), "the incomplete trailing fragment must not set an anchor"


def test_anchors_span_first_to_last_complete_sentence() -> None:
    aligned = words(("یەک", 0, 300), ("دوو.", 300, 700), ("سێ", 1500, 1800), ("چوار.", 1800, 2200))
    assert anchors_for(segment_sentences(aligned)) == (0, 2200)


def test_a_selection_with_no_complete_sentence_has_no_anchors() -> None:
    """§3 Stage 5: "If no sentence boundary exists within tolerance, extend to the next one
    or reject the candidate." Returning a plausible anchor here is how a broken clip ships."""
    aligned = words(("بەڵام", 0, 300), ("ئەوە", 300, 700))
    sentences = segment_sentences(aligned)
    assert all(not s.complete for s in sentences)
    assert anchors_for(sentences) is None


def test_anchor_out_is_never_before_anchor_in() -> None:
    aligned = words(("یەک", 0, 300), ("دوو.", 300, 700))
    anchors = anchors_for(segment_sentences(aligned))
    assert anchors is not None
    assert anchors[1] >= anchors[0]


def test_sentences_carry_their_words_for_caption_line_breaking() -> None:
    """§4.3.5: line breaks are inserted from the word alignment, not by libass."""
    aligned = words(("ئەمە", 0, 300), ("زۆر", 300, 600), ("باشە.", 600, 900))
    sentence = segment_sentences(aligned)[0]
    assert len(sentence.words) == 3
    assert sentence.words[0].start_ms == 0


def test_a_non_positive_pause_threshold_is_refused() -> None:
    with pytest.raises(ValueError, match="pause"):
        segment_sentences(words(("ئەمە", 0, 300)), pause_ms=0)


# --- §4.2's VAD-pause half is currently inert ---------------------------------------------
#
# This test documents a DEFECT, not a desired behaviour. When it goes red, the fix has landed:
# update the M1.2 row, close BLOCKED.md #14, and delete this test.
#
# `pause_follows` reaches its VAD branch only when the word gap is *below* `pause_ms`, and that
# branch requires a silence contained in `[earlier.end_ms, later.start_ms]` whose own length is
# *at least* `pause_ms` — which forces the gap to be at least `pause_ms`. The two conditions
# cannot both hold, so no `vad_pauses` value can ever split a sentence. Measured by brute force
# over 3,528 candidate silences: zero splits. D-081.


def test_vad_pauses_currently_cannot_split_a_sentence() -> None:
    """A defect pinned so the dead branch cannot be mistaken for a working feature."""
    words = (
        Word(w="یەک", start_ms=0, end_ms=1_000, conf=0.9),
        Word(w="دوو", start_ms=1_100, end_ms=2_000, conf=0.9),
    )
    # A 400 ms silence sitting exactly where §4.2 would have it end the sentence.
    for silence in ((1_000, 1_400), (900, 1_500), (1_000, 1_100), (0, 2_000)):
        segmented = segment_sentences(words, vad_pauses=(silence,), pause_ms=400)
        assert len(segmented) == 1, (
            f"a VAD silence {silence} split the sentence — the branch is no longer dead, which "
            "is the intended fix. Update M1.2, close BLOCKED.md #14 and delete this test."
        )

    # The control: the word-gap half of the rule does work, so this is specifically the VAD
    # half being inert rather than segmentation being broken.
    far_apart = (
        Word(w="یەک", start_ms=0, end_ms=1_000, conf=0.9),
        Word(w="دوو", start_ms=1_500, end_ms=2_000, conf=0.9),
    )
    assert len(segment_sentences(far_apart, vad_pauses=(), pause_ms=400)) == 2


def test_the_recorded_pause_threshold_is_where_the_split_actually_happens() -> None:
    """D-014's 500 ms, asserted as a boundary rather than followed as a symbol.

    Every other pause test here passes `pause_ms=DEFAULT_PAUSE_MS`, so they follow the constant
    wherever it goes: measured 2026-08-09, changing it to 800 left all 1,170 tests green. Symbolic
    use reads as coverage and measures nothing.

    So this one uses literal gaps either side of the recorded value. Changing the threshold means
    editing this test in the same commit — a visible edit, the same trade
    `scripts/test-count.floor` makes. D-098.
    """
    assert DEFAULT_PAUSE_MS == 500, "D-014 records 500 ms; the gaps below are chosen around it"

    at_the_threshold = words(("ئەمە", 0, 300), ("دواتر", 800, 1100))
    assert len(segment_sentences(at_the_threshold)) == 2, (
        "a gap of exactly 500 ms must split — at the threshold, not past it"
    )

    just_under = words(("ئەمە", 0, 300), ("دواتر", 799, 1100))
    assert len(segment_sentences(just_under)) == 1, (
        "a 499 ms gap must not split, or the recorded threshold is not the one in force"
    )
