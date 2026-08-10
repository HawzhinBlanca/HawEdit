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

import re
import subprocess
import sys
from pathlib import Path

import pytest

from hawedit.collisions import COLLISIONS, measure_collisions

ROOT = Path(__file__).resolve().parents[1]
MEASURE = ROOT / "scripts" / "measure_collisions.py"
EVIDENCE = ROOT / "evidence" / "collision-incidence.md"


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


# --- D-160: M0.15's numbers are only worth having if the one step that produces them runs ----


def _measured() -> str:
    """`scripts/measure_collisions.py` over the bundled lexicon, as its own docstring documents.

    Run as a subprocess rather than imported, because two of the three things that were broken
    are only reachable that way: the module-level path resolution, and stdout's encoding.
    """
    result = subprocess.run(
        [sys.executable, str(MEASURE)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, (
        f"M0.15's reproduce command exits {result.returncode}. Its evidence file's figures "
        f"cannot be re-derived by the step that documents them.\n{result.stderr[-800:]}"
    )
    return result.stdout


def _figure(pattern: str, summary: str) -> str:
    """One captured figure from the script's summary line, or a failure naming what was missing.

    The summary is the artifact being read, so a pattern that stops matching means the script's
    output shape changed — which must fail loudly here rather than raise `AttributeError` on a
    `None` match somewhere further down.
    """
    match = re.search(pattern, summary)
    assert match is not None, f"{pattern!r} matched nothing in the measured summary: {summary!r}"
    return match.group(1)


def test_the_reproduce_command_for_m0_15_actually_runs() -> None:
    """It did not, on this platform, for four days.

    `KLPT_DIC` was assembled as `.venv/lib/python3.11/site-packages/…` — a POSIX venv layout
    with a version segment Windows does not use — so the script died with `FileNotFoundError`
    before measuring anything. Asking the installed package (`klpt.__file__`) is what
    `tests/test_waw.py` already did. D-160.
    """
    stdout = _measured()
    assert "24894 items" in stdout, stdout[:400]
    # The Kurdish merge groups are the finding, and printing them is where it failed second:
    # a script gets cp1252 stdout on Windows, so the summary line went out and the word pairs
    # raised `UnicodeEncodeError` — exit 1 with the headline already printed, which reads like
    # success to anything checking only the first line.
    assert "بەرهەم | بەرھەم" in stdout, "the merged groups did not survive stdout's encoding"


def test_the_evidence_file_still_states_what_the_script_measures() -> None:
    """The numbers M0.15 is DONE on, bound to the code that produces them.

    Parsed from `evidence/collision-incidence.md` rather than written here, so the evidence file
    is what goes stale-or-red: a KLPT update or a `normalize_sorani` change moves the measurement
    and this fails naming both figures, instead of the document quietly describing a run nobody
    can repeat.
    """
    stdout = _measured()
    summary = next(line for line in stdout.splitlines() if "items," in line)
    evidence = EVIDENCE.read_text(encoding="utf-8")

    measured = {
        "items": int(_figure(r"(\d+) items,", summary)),
        "changed_rate": _figure(r"([\d.]+)% altered", summary),
        "distinct_raw": int(_figure(r"(\d+) distinct raw forms", summary)),
        "distinct_normalized": int(_figure(r"-> (\d+) normalized", summary)),
        "collision_rate": _figure(r"\(([\d.]+)% would have failed", summary),
    }

    assert f"**{measured['items']:,} entries" in evidence, (
        f"the corpus is {measured['items']:,} entries; the evidence file says otherwise"
    )
    assert f"| {measured['distinct_raw']:,} |" in evidence
    assert f"| {measured['distinct_normalized']:,} |" in evidence
    assert f"**{measured['collision_rate']}%**" in evidence
    assert f"**{measured['changed_rate']}%**" in evidence

    # The control: the headline figure must be the one the script emits, not merely *a* number
    # present in the document. 0.21% and 0.84% both appear in that file, so a check that only
    # asked "is this percentage mentioned" would pass with the two swapped.
    collision_row = next(
        line for line in evidence.splitlines() if "failed to match" in line and "|" in line
    )
    assert f"**{measured['collision_rate']}%**" in collision_row, collision_row
    assert f"{measured['changed_rate']}%" not in collision_row, (
        f"the altered-items rate is standing in the collision row: {collision_row}"
    )


def test_every_merge_the_evidence_quotes_is_still_produced() -> None:
    """The finding is the word pairs, not the percentage — `دهۆک`/`دھۆک` is *Duhok*.

    A control on the test above: the figures could match while the merges changed entirely.
    """
    stdout = _measured()
    quoted = re.findall(r"([؀-ۿ‌]+)\s*\|\s*([؀-ۿ‌]+)", EVIDENCE.read_text(encoding="utf-8"))
    assert len(quoted) >= 6, f"the evidence file quotes {len(quoted)} pairs; it listed six"
    missing = [f"{a} | {b}" for a, b in quoted if f"{a} | {b}" not in stdout]
    assert not missing, f"the evidence quotes merges the script no longer produces: {missing}"
