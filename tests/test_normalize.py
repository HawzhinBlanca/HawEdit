"""M0.3 — §4.1 Sorani normalization.

§0 names this as failure mode #1: "Skip normalization and your search index silently fails
to match text that looks identical on screen." So the tests are written around that failure
— two encodings of the same visible Kurdish sentence must compare equal after normalization
— not merely around calling the library.

Every collision in the §4.1 table gets a case, including the one KLPT does **not** handle:
that case asserts today's behaviour so the day it changes, the suite says so (D-003).
"""

from __future__ import annotations

import pytest

from hawedit2.normalize import normalize_sorani

# The §4.1 collision table: (label, as-typed, as-it-should-normalize)
SECTION_4_1_COLLISIONS = [
    # "ه" + ZWNJ vs "ە" — both are everywhere in real text.
    ("he_plus_zwnj", "ئه‌مه‌ زۆر باشه‌", "ئەمە زۆر باشە"),
    # Arabic keyboards emit ي and ك; Kurdish uses the Farsi forms ی and ک.
    ("arabic_yeh_kaf", "كوردي", "کوردی"),
    # Farsi numerals.
    ("farsi_numerals", "ساڵی ۲۰۲۵", "ساڵی 2025"),
    # Eastern Arabic numerals.
    ("eastern_arabic_numerals", "ساڵی ٢٠٢٥", "ساڵی 2025"),
]


@pytest.mark.parametrize(
    ("label", "typed", "expected"),
    SECTION_4_1_COLLISIONS,
    ids=[c[0] for c in SECTION_4_1_COLLISIONS],
)
def test_section_4_1_collision_is_normalized(label: str, typed: str, expected: str) -> None:
    assert normalize_sorani(typed) == expected


def test_the_actual_failure_mode_two_encodings_of_one_sentence_compare_equal() -> None:
    """This is what §4.1 is really about: an index that silently fails to match.

    Both spellings render identically on screen. Unnormalized they are different strings,
    so BM25 scores them as unrelated documents and nobody can see why.
    """
    zwnj_form = "ئه‌مه‌ كوردي یه‌"
    precomposed_form = "ئەمە کوردی یە"
    assert zwnj_form != precomposed_form, "the test is vacuous if these are already equal"
    assert normalize_sorani(zwnj_form) == normalize_sorani(precomposed_form)


def test_normalization_is_idempotent() -> None:
    """norm(norm(x)) == norm(x). Stage 1 writes norm once; nothing downstream may drift."""
    for _, typed, _expected in SECTION_4_1_COLLISIONS:
        once = normalize_sorani(typed)
        assert normalize_sorani(once) == once


def test_normalization_is_deterministic() -> None:
    text = "ئه‌مه‌ ساڵی ۲۰۲۵ه‌"
    assert normalize_sorani(text) == normalize_sorani(text)


def test_normalization_does_not_mutate_its_input() -> None:
    """Invariant #1's spirit at the function level: the raw form survives the call."""
    typed = "ئه‌مه‌"
    before = typed
    normalize_sorani(typed)
    assert typed == before


def test_conjunctive_waw_separation_is_part_of_normalization() -> None:
    """§4.1's fifth collision, closed in M1.7. The rule and its measurements: `tests/test_waw.py`.

    D-003 left this unimplemented because separation needs a lexicon and guessing corrupts
    real words. D-026 implements it against KLPT's dictionary as a refusal rather than a
    prediction, and the exhaustive safety check — no dictionary word is ever split — lives
    next to the rule.
    """
    assert normalize_sorani("وکتێبەکان") == "و کتێبەکان"


def test_the_ambiguous_join_is_still_left_alone() -> None:
    """D-003's example. Neither reading of `وتو` has lexicon support, so neither is chosen."""
    assert normalize_sorani("من وتو") == "من وتو"


def test_full_kurdish_character_set_survives_normalization() -> None:
    """§4.3 lists the Kurdish-specific glyphs. Normalization must not eat any of them."""
    kurdish_specific = "ڕ ڵ ۆ ێ چ ژ پ گ ە"
    normalized = normalize_sorani(kurdish_specific)
    for char in "ڕڵۆێچژپگە":
        assert char in normalized, f"normalization dropped {char!r}"


def test_latin_and_empty_input_are_safe() -> None:
    assert normalize_sorani("") == ""
    assert normalize_sorani("hello world") == "hello world"


def test_normalization_strips_but_does_not_collapse_whitespace() -> None:
    """Measured, not assumed: KLPT strips the ends and leaves internal runs alone.

    Pinned because it is exactly the kind of behaviour a library update changes quietly.
    It matters twice over — §8.1 asks for a *spacing-free* CER alongside the normalized one
    precisely because Sorani spacing is unreliable, and word alignment (§4.2) must key off
    the raw transcript's tokens, not this string.
    """
    assert normalize_sorani("   ") == ""
    assert normalize_sorani("  ئەمە  ") == "ئەمە"
    assert normalize_sorani("ئەمە    زۆر") == "ئەمە    زۆر", (
        "internal runs are preserved — spacing-free CER exists to absorb this"
    )
