"""M0.15 — measuring how often §4.1's collisions actually occur in real Kurdish.

§0 asserts normalization is failure mode #1: "your search index silently fails to match
text that looks identical on screen." The blueprint states it; nobody has measured it on
this project's own data. This module measures it, and the number it produces is the
justification for §4.1 being MANDATORY rather than advisory.

The metric that matters is not "how many strings contain a ZWNJ". It is how many *distinct*
raw forms collapse onto the same normalized form — because each of those collapses is one
pair of index entries that would never have matched each other.
"""

from __future__ import annotations

import pytest

from hawedit.collisions import COLLISIONS, measure_collisions


def test_a_corpus_with_no_collisions_reports_none() -> None:
    report = measure_collisions(["ئەمە", "زۆر", "باشە"])
    assert report.items_changed_by_normalization == 0
    assert report.changed_rate == 0.0
    assert report.index_collision_rate == 0.0


def test_the_zwnj_form_is_detected() -> None:
    report = measure_collisions(["ئه‌مه‌"])
    assert report.counts_by_collision["he_plus_zwnj"] == 1
    assert report.items_changed_by_normalization == 1


def test_arabic_yeh_and_kaf_are_detected_separately() -> None:
    report = measure_collisions(["كوردي"])
    assert report.counts_by_collision["arabic_yeh"] == 1
    assert report.counts_by_collision["arabic_kaf"] == 1


def test_both_numeral_systems_are_detected() -> None:
    report = measure_collisions(["ساڵی ۲۰۲۵", "ساڵی ٢٠٢٥"])
    assert report.counts_by_collision["farsi_numerals"] == 1
    assert report.counts_by_collision["eastern_arabic_numerals"] == 1


def test_counts_are_per_item_not_per_occurrence() -> None:
    """One item containing four Arabic yehs is one affected item, not four."""
    report = measure_collisions(["يييي"])
    assert report.counts_by_collision["arabic_yeh"] == 1


def test_the_index_collision_rate_is_the_number_that_matters() -> None:
    """Two spellings of one word are two index entries that never match — until §4.1."""
    report = measure_collisions(["كوردي", "کوردی"])
    assert report.distinct_raw == 2
    assert report.distinct_normalized == 1
    assert report.index_collision_rate == pytest.approx(0.5)


def test_merged_groups_name_the_forms_that_collapse() -> None:
    report = measure_collisions(["كوردي", "کوردی", "زۆر"])
    merged = {frozenset(group) for group in report.merged_groups}
    assert frozenset({"كوردي", "کوردی"}) in merged
    assert not any("زۆر" in group for group in report.merged_groups)


def test_duplicate_raw_forms_are_not_counted_as_a_collision() -> None:
    """The same string twice is one index entry, not a merge §4.1 rescued."""
    report = measure_collisions(["کوردی", "کوردی"])
    assert report.distinct_raw == 1
    assert report.index_collision_rate == 0.0


def test_an_empty_corpus_measures_nothing_rather_than_zero() -> None:
    report = measure_collisions([])
    assert report.index_collision_rate is None
    assert report.changed_rate is None


def test_every_declared_collision_has_a_counter() -> None:
    report = measure_collisions(["ئەمە"])
    assert set(report.counts_by_collision) == set(COLLISIONS)


def test_the_collision_set_is_section_4_1_plus_what_measurement_found() -> None:
    """Four from §4.1's table, plus one the table omits and the real lexicon revealed.

    Conjunctive `و` is a known gap (D-003) and is deliberately not counted — counting it
    would imply we handle it.
    """
    assert set(COLLISIONS) == {
        "he_plus_zwnj",
        "arabic_yeh",
        "arabic_kaf",
        "farsi_numerals",
        "eastern_arabic_numerals",
        "heh_doachashmee",  # not in §4.1 — see D-013
    }


def test_heh_doachashmee_merges_in_word_context() -> None:
    """U+06BE vs U+0647. Every merge found in the real Sorani lexicon was this pair."""
    report = measure_collisions(["بەرهەم", "بەرھەم"])
    assert report.counts_by_collision["heh_doachashmee"] == 1
    assert report.distinct_raw == 2
    assert report.distinct_normalized == 1


def test_heh_doachashmee_is_not_normalized_in_isolation() -> None:
    """Measured, not assumed: KLPT's rule is contextual. Pinned so a library update that
    changes it is visible rather than silently shifting every index key."""
    from hawedit.normalize import normalize_sorani

    assert normalize_sorani("ھ") == "ھ"
