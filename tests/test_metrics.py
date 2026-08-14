"""M0.5 — the §8.1 accuracy metrics.

    normalized CER · spacing-free CER · named-entity error · code-switch error

§8.1 is blunt about why these exist: "Published CERs across different models are computed on
different datasets with different normalization — they are not comparable. Only this harness
produces comparable numbers." So the tests below are mostly about *comparability*: the same
Kurdish sentence typed two ways must score 0, and a metric that has not been measured must
never come back as 0.0.
"""

from __future__ import annotations

import pytest

from hawedit.metrics import (
    cer,
    code_switch_error_rate,
    edit_distance,
    named_entity_error_rate,
    normalized_cer,
    spacing_free_cer,
    substring_edit_distance,
)

# The same Kurdish sentence, typed on two different keyboards. Identical on screen.
ZWNJ_FORM = "ئه‌مه‌ كوردي یه‌"
PRECOMPOSED_FORM = "ئەمە کوردی یە"


# --- primitives -----------------------------------------------------------------------


def test_edit_distance_basics() -> None:
    assert edit_distance("", "") == 0
    assert edit_distance("abc", "abc") == 0
    assert edit_distance("", "abc") == 3
    assert edit_distance("abc", "") == 3
    assert edit_distance("abc", "abd") == 1  # substitution
    assert edit_distance("abc", "abcd") == 1  # insertion
    assert edit_distance("abcd", "abc") == 1  # deletion
    assert edit_distance("kitten", "sitting") == 3


def test_edit_distance_counts_codepoints_not_bytes() -> None:
    """Kurdish characters are multi-byte. A byte-wise distance would inflate every CER."""
    assert edit_distance("ە", "ه") == 1
    assert edit_distance("کوردی", "کوردی") == 0
    assert len("کوردی".encode()) > len("کوردی"), "the test is vacuous if these are 1-byte"


def test_edit_distance_is_symmetric() -> None:
    assert edit_distance("ئەمە", "ئەم") == edit_distance("ئەم", "ئەمە")


# --- CER ------------------------------------------------------------------------------


def test_cer_of_identical_text_is_zero() -> None:
    assert cer("ئەمە زۆر باشە", "ئەمە زۆر باشە") == 0.0


def test_cer_is_errors_over_reference_length() -> None:
    assert cer("abcd", "abce") == pytest.approx(0.25)


def test_cer_may_exceed_one_when_the_hypothesis_runs_long() -> None:
    """Standard CER is not clipped. A hallucinating model should be able to score > 1."""
    assert cer("ab", "abcdefgh") > 1.0


def test_cer_refuses_an_empty_reference() -> None:
    """A benchmark item with no reference is a corpus bug. Fail visible, not silent."""
    with pytest.raises(ValueError, match="empty reference"):
        cer("", "anything")


# --- normalized CER: the metric §8.1 actually asks for --------------------------------


def test_normalized_cer_scores_two_encodings_of_one_sentence_as_perfect() -> None:
    """The whole reason §8.1 says "normalized": these differ as strings, not as Kurdish.

    Scored raw, a model would be charged for a keyboard difference it did not make.
    """
    assert cer(ZWNJ_FORM, PRECOMPOSED_FORM) > 0.0, "vacuous unless raw CER sees a difference"
    assert normalized_cer(ZWNJ_FORM, PRECOMPOSED_FORM) == 0.0


def test_normalized_cer_still_catches_real_errors() -> None:
    """Normalization must not launder genuine mistakes into a passing score."""
    assert normalized_cer("ئەمە زۆر باشە", "ئەمە زۆر خراپە") > 0.0


def test_normalized_cer_unifies_numerals() -> None:
    assert normalized_cer("ساڵی ۲۰۲۵", "ساڵی 2025") == 0.0


# --- spacing-free CER -----------------------------------------------------------------


def test_spacing_free_cer_forgives_spacing_alone() -> None:
    """Sorani is clitic-heavy (§2) and its spacing is unreliable; §8.1 asks for both views."""
    spaced = "ئەمە زۆر باشە"
    differently_spaced = "ئەمە  زۆر باشە"
    assert normalized_cer(spaced, differently_spaced) > 0.0
    assert spacing_free_cer(spaced, differently_spaced) == 0.0


def test_spacing_free_cer_still_catches_real_errors() -> None:
    assert spacing_free_cer("ئەمە زۆر باشە", "ئەمە زۆر خراپە") > 0.0


def test_spacing_free_cer_also_normalizes() -> None:
    assert spacing_free_cer(ZWNJ_FORM, PRECOMPOSED_FORM) == 0.0


# --- substring alignment, used by the span-scoped metrics -----------------------------


def test_substring_edit_distance_ignores_surrounding_context() -> None:
    assert substring_edit_distance("کوردی", "ئەمە کوردی یە") == 0


def test_substring_edit_distance_reports_the_best_match() -> None:
    assert substring_edit_distance("کوردی", "ئەمە کوردا یە") == 1


def test_substring_edit_distance_of_an_absent_needle_is_its_length() -> None:
    assert substring_edit_distance("abc", "xyz") == 3


# --- named-entity error ---------------------------------------------------------------


def test_named_entity_error_is_zero_when_every_entity_survives() -> None:
    hyp = "سەرۆک بارزانی لە هەولێر بوو"
    assert named_entity_error_rate(hyp, ("بارزانی", "هەولێر")) == 0.0


def test_named_entity_error_counts_the_entities_that_did_not_survive() -> None:
    hyp = "سەرۆک بارزانی لە شار بوو"
    assert named_entity_error_rate(hyp, ("بارزانی", "هەولێر")) == pytest.approx(0.5)


def test_named_entity_matching_is_normalization_insensitive() -> None:
    """§8.1 measures whether the *name* survived, not which keyboard produced it."""
    assert named_entity_error_rate("ئەمە کوردی یە", ("كوردي",)) == 0.0


def test_named_entity_error_is_none_when_nothing_was_annotated() -> None:
    """Unmeasured must never render as 0.0 — that reads as a perfect score in a report."""
    assert named_entity_error_rate("anything", ()) is None


# --- code-switch error ----------------------------------------------------------------


def test_code_switch_error_is_zero_when_the_switched_span_survives() -> None:
    hyp = "ئەمە machine learning ـە"
    assert code_switch_error_rate(hyp, ("machine learning",)) == 0.0


def test_code_switch_error_scores_a_garbled_span() -> None:
    hyp = "ئەمە machine lurning ـە"
    rate = code_switch_error_rate(hyp, ("machine learning",))
    assert rate is not None and 0.0 < rate < 1.0


def test_code_switch_error_finds_the_span_anywhere_in_the_hypothesis() -> None:
    assert code_switch_error_rate("machine learning زۆر باشە", ("machine learning",)) == 0.0


def test_code_switch_error_averages_over_spans() -> None:
    hyp = "machine learning و ئەمە"
    rate = code_switch_error_rate(hyp, ("machine learning", "deep learning"))
    assert rate is not None and rate > 0.0


def test_code_switch_error_is_none_when_nothing_was_annotated() -> None:
    assert code_switch_error_rate("anything", ()) is None


def test_arabic_code_switch_spans_are_supported() -> None:
    """§8.1 asks for Kurdish–Arabic as well as Kurdish–English code-switching."""
    assert code_switch_error_rate("ئەمە جمهورية العراق ـە", ("جمهورية العراق",)) == 0.0


# --- a blank annotation is a corpus defect, not a perfect score ---------------------------
#
# `"" in anything` is True, so an empty entity counted as a name that SURVIVED and scored 0.0 —
# the same value as a name transcribed perfectly. `code_switch_error_rate` already refused the
# same input; `named_entity_error_rate` did not. Measured: `CorpusItem(named_entities=("",))`
# constructs without complaint and scores 0.0, so a blank label silently inflated §8.1's
# accuracy. Found by the second adversarial pass. D-089.


def test_a_blank_named_entity_is_refused_not_scored_as_found() -> None:
    for blank in ("", "   ", "\u200c"):
        with pytest.raises(ValueError, match="empty named entity"):
            named_entity_error_rate("سەرۆک بارزانی لە شار", (blank,))
    # And when it is one entry among several, so the refusal is not order-dependent.
    with pytest.raises(ValueError, match="empty named entity"):
        named_entity_error_rate("سەرۆک بارزانی لە شار", ("بارزانی", ""))


def test_nothing_annotated_is_still_none_rather_than_a_refusal() -> None:
    """The distinction the fix must preserve: an empty tuple is unmeasured, not malformed."""
    assert named_entity_error_rate("anything", ()) is None
    assert code_switch_error_rate("anything", ()) is None


def test_real_entities_are_still_scored(  # the control for the refusal above
) -> None:
    """A guard that refused every annotation would pass the refusal test and break scoring."""
    assert named_entity_error_rate("سەرۆک بارزانی لە هەولێر", ("بارزانی", "هەولێر")) == 0.0
    assert named_entity_error_rate("سەرۆک لە شار بوو", ("بارزانی",)) == 1.0


# D-008's fourth recorded choice: "Matching is exact after §4.1 normalization … a name 90% right
# is still the wrong name in a burned-in caption … Strictness here is deliberate." D-008 closes
# by claiming all four choices are tested. Three were. This one was not, so a fuzzy match could
# be introduced with the suite green.


def test_a_near_miss_name_is_scored_as_an_error_not_a_match() -> None:
    """One letter wrong is the wrong name — §8.2 calls misleading output the error that matters."""
    # بارزانا vs the annotated بارزانی: same length, final letter differs.
    assert named_entity_error_rate("سەرۆک بارزانا لە شار", ("بارزانی",)) == 1.0
    # A truncation is also a miss, not a partial credit.
    assert named_entity_error_rate("سەرۆک بارزان لە شار", ("بارزانی",)) == 1.0


def test_strictness_does_not_reject_a_mere_keyboard_difference(  # the control for strictness
) -> None:
    """The other half of D-008's choice: normalization-insensitive, so Arabic ي/ك still match.

    Without this, "strict" could be implemented as byte equality and both tests would pass.
    """
    assert named_entity_error_rate("ئەمە کوردی یە", ("كوردي",)) == 0.0


def test_a_blank_code_switch_span_is_refused() -> None:
    """The sibling guard was implemented correctly and never tested.

    Found while auditing the fix above: removing `code_switch_error_rate`'s empty-span refusal
    left the suite green, so the one metric that got this right was as revertible as the one that
    got it wrong. Both call sites of `_normalized_annotation` are pinned now.
    """
    for blank in ("", "   "):
        with pytest.raises(ValueError, match="empty code-switch span"):
            code_switch_error_rate("this is machine learning", (blank,))
    with pytest.raises(ValueError, match="empty code-switch span"):
        code_switch_error_rate("this is machine learning", ("machine learning", ""))
