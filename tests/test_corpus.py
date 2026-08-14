"""M0.6 — the labelled Sorani set's manifest, and the §8.1 coverage it has to satisfy.

§8.1 does not ask for "several hours of Kurdish". It asks for several hours across a named
list: Hewlêr · Slemani · Mukriyan · formal news · casual podcast · ckb–English and ckb–Arabic
code-switching · noisy environments · overlapping speakers · named entities and political
terminology. And §4.4 forbids collapsing the dialects: "A single aggregate CER hides the
dialect where the product is actually used."

A corpus that quietly covers six of those categories still produces a number — a
confident-looking, wrong one. So coverage is validated, and what is missing is named.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hawedit.corpus import (
    Condition,
    Corpus,
    CorpusItem,
    Dialect,
    IncompleteCoverage,
    InvalidCorpusItem,
    Provenance,
)


def an_item(
    item_id: str = "itm-001",
    dialect: Dialect = Dialect.HEWLER,
    conditions: tuple[Condition, ...] = (Condition.FORMAL_NEWS,),
    duration_s: float = 30.0,
    **kwargs: object,
) -> CorpusItem:
    payload: dict[str, object] = {
        "item_id": item_id,
        "audio_path": f"audio/{item_id}.wav",
        "reference_ckb": "ئه‌مه‌ زۆر باشه‌",
        "dialect": dialect,
        "conditions": frozenset(conditions),
        "duration_s": duration_s,
        "speaker_count": 1,
    }
    payload.update(kwargs)
    return CorpusItem(**payload)  # type: ignore[arg-type]


def a_full_corpus() -> Corpus:
    """One item per (dialect, condition) cell — the minimum §8.1 shape."""
    items = []
    for dialect in Dialect:
        for condition in Condition:
            extra: dict[str, object] = {}
            if condition is Condition.CODE_SWITCH_EN:
                extra["code_switch_spans"] = ("machine learning",)
            elif condition is Condition.CODE_SWITCH_AR:
                extra["code_switch_spans"] = ("جمهورية العراق",)
            elif condition is Condition.NAMED_ENTITIES:
                extra["named_entities"] = ("هەولێر",)
            elif condition is Condition.OVERLAPPING_SPEAKERS:
                extra["speaker_count"] = 2
            items.append(
                an_item(
                    item_id=f"{dialect.value}-{condition.value}",
                    dialect=dialect,
                    conditions=(condition,),
                    duration_s=600.0,
                    **extra,
                )
            )
    return Corpus(tuple(items))


# --- the §8.1 category list is the schema ---------------------------------------------


def test_the_three_dialects_of_section_4_4_are_the_dialect_enum() -> None:
    assert {d.value for d in Dialect} == {"hewler", "slemani", "mukriyan"}


def test_every_section_8_1_condition_is_representable() -> None:
    assert {c.value for c in Condition} == {
        "formal_news",
        "casual_podcast",
        "code_switch_en",
        "code_switch_ar",
        "noisy",
        "overlapping_speakers",
        "named_entities",
    }


# --- item-level consistency: catch corpus bugs at authoring time ----------------------


def test_a_code_switch_item_without_annotated_spans_is_refused() -> None:
    """Labelling an item ckb–English without the spans makes its code-switch error
    unmeasurable, and D-008 says unmeasured must not read as zero."""
    with pytest.raises(InvalidCorpusItem, match="code_switch_spans"):
        an_item(conditions=(Condition.CODE_SWITCH_EN,))


def test_a_named_entity_item_without_annotated_entities_is_refused() -> None:
    with pytest.raises(InvalidCorpusItem, match="named_entities"):
        an_item(conditions=(Condition.NAMED_ENTITIES,))


def test_an_overlapping_speaker_item_needs_more_than_one_speaker() -> None:
    with pytest.raises(InvalidCorpusItem, match="speaker_count"):
        an_item(conditions=(Condition.OVERLAPPING_SPEAKERS,), speaker_count=1)


def test_an_item_without_a_reference_transcript_is_refused() -> None:
    with pytest.raises(InvalidCorpusItem, match="reference"):
        an_item(reference_ckb="   ")


def test_an_item_with_no_duration_is_refused() -> None:
    with pytest.raises(InvalidCorpusItem, match="duration"):
        an_item(duration_s=0.0)


def test_an_item_with_no_conditions_is_refused() -> None:
    with pytest.raises(InvalidCorpusItem, match="condition"):
        an_item(conditions=())


def test_the_reference_transcript_is_kept_exactly_as_labelled() -> None:
    """The reference is raw text (invariant #1). Normalization happens at scoring time."""
    as_labelled = "ئه‌مه‌ كوردي ۲۰۲۵"
    assert an_item(reference_ckb=as_labelled).reference_ckb == as_labelled


# --- coverage -------------------------------------------------------------------------


def test_a_complete_corpus_satisfies_section_8_1() -> None:
    a_full_corpus().assert_section_8_1_coverage()


def test_a_missing_dialect_is_named_not_just_counted() -> None:
    full = a_full_corpus()
    without_mukriyan = Corpus(tuple(i for i in full.items if i.dialect is not Dialect.MUKRIYAN))
    with pytest.raises(IncompleteCoverage, match="mukriyan"):
        without_mukriyan.assert_section_8_1_coverage()


def test_a_missing_condition_is_named() -> None:
    full = a_full_corpus()
    without_noise = Corpus(tuple(i for i in full.items if Condition.NOISY not in i.conditions))
    with pytest.raises(IncompleteCoverage, match="noisy"):
        without_noise.assert_section_8_1_coverage()


def test_a_condition_covered_in_only_one_dialect_is_still_incomplete() -> None:
    """§4.4's point: 'noisy' measured only in Hewlêr says nothing about Mukriyan."""
    full = a_full_corpus()
    trimmed = Corpus(
        tuple(
            i
            for i in full.items
            if Condition.NOISY not in i.conditions or i.dialect is Dialect.HEWLER
        )
    )
    with pytest.raises(IncompleteCoverage):
        trimmed.assert_section_8_1_coverage()


def test_coverage_reports_duration_per_dialect_never_only_the_total() -> None:
    coverage = a_full_corpus().coverage()
    assert set(coverage.hours_by_dialect) == set(Dialect)
    for dialect in Dialect:
        assert coverage.hours_by_dialect[dialect] == pytest.approx(7 * 600.0 / 3600.0)
    assert coverage.total_hours == pytest.approx(3 * 7 * 600.0 / 3600.0)


def test_coverage_lists_the_missing_cells() -> None:
    full = a_full_corpus()
    trimmed = Corpus(tuple(i for i in full.items if i.dialect is not Dialect.SLEMANI))
    missing = trimmed.coverage().missing_cells
    assert (Dialect.SLEMANI, Condition.FORMAL_NEWS) in missing
    assert (Dialect.HEWLER, Condition.FORMAL_NEWS) not in missing


def test_a_short_corpus_is_flagged_even_when_every_cell_is_populated() -> None:
    """§8.1 asks for 'several hours'. One 30 s clip per cell covers the grid and measures
    nothing."""
    thin = Corpus(tuple(_shrink(i) for i in a_full_corpus().items))
    assert thin.coverage().meets_minimum_hours is False
    with pytest.raises(IncompleteCoverage, match="hours"):
        thin.assert_section_8_1_coverage()


def _shrink(item: CorpusItem) -> CorpusItem:
    return CorpusItem(
        item_id=item.item_id,
        audio_path=item.audio_path,
        reference_ckb=item.reference_ckb,
        dialect=item.dialect,
        conditions=item.conditions,
        duration_s=30.0,
        named_entities=item.named_entities,
        code_switch_spans=item.code_switch_spans,
        speaker_count=item.speaker_count,
    )


# --- manifest round trip --------------------------------------------------------------


def test_manifest_round_trips(tmp_path: Path) -> None:
    corpus = a_full_corpus()
    path = tmp_path / "corpus.json"
    path.write_text(corpus.to_json(), encoding="utf-8")
    assert Corpus.load(path) == corpus


def test_an_unknown_dialect_in_a_manifest_fails_loudly(tmp_path: Path) -> None:
    path = tmp_path / "corpus.json"
    path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "item_id": "x",
                        "audio_path": "a.wav",
                        "reference_ckb": "ئەمە",
                        "dialect": "badini",
                        "conditions": ["formal_news"],
                        "duration_s": 10.0,
                        "speaker_count": 1,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(InvalidCorpusItem, match="badini"):
        Corpus.load(path)


def test_missing_audio_is_reported_separately_from_schema_validity(tmp_path: Path) -> None:
    """The manifest can be authored before the audio lands — that is M0.12's whole state."""
    corpus = a_full_corpus()
    missing = corpus.missing_audio(root=tmp_path)
    assert len(missing) == len(corpus.items), "no audio exists under an empty root"


# --- interim / unlabelled corpora (M0.6b) ---------------------------------------------


def an_unlabelled_item(item_id: str = "cv-001", duration_s: float = 5.0) -> CorpusItem:
    return CorpusItem(
        item_id=item_id,
        audio_path=f"clips/{item_id}.mp3",
        reference_ckb="ئەمە زۆر باشە",
        dialect=None,
        conditions=frozenset(),
        duration_s=duration_s,
    )


def test_an_item_may_be_explicitly_unlabelled() -> None:
    """A public corpus has no dialect labels. Inventing one would be fabricated evidence."""
    assert an_unlabelled_item().is_labelled is False


def test_a_partially_labelled_item_is_refused() -> None:
    """Either both, or neither. A dialect with no condition is a half-labelled item that
    would silently fill a coverage cell it cannot support."""
    with pytest.raises(InvalidCorpusItem, match="condition"):
        an_item(conditions=())
    with pytest.raises(InvalidCorpusItem, match="dialect"):
        CorpusItem(
            item_id="x",
            audio_path="x.wav",
            reference_ckb="ئەمە",
            dialect=None,
            conditions=frozenset({Condition.NOISY}),
            duration_s=10.0,
        )


def test_unlabelled_hours_never_fill_a_coverage_cell() -> None:
    corpus = Corpus(tuple(an_unlabelled_item(f"cv-{i}", 600.0) for i in range(30)))
    coverage = corpus.coverage()
    assert len(coverage.missing_cells) == len(Dialect) * len(Condition)
    assert coverage.unlabelled_hours == pytest.approx(5.0)
    assert coverage.labelled_hours == 0.0


def test_unlabelled_hours_do_not_count_toward_the_section_8_1_minimum() -> None:
    """Five hours of unlabelled read speech is not five hours of §8.1 coverage."""
    corpus = Corpus(tuple(an_unlabelled_item(f"cv-{i}", 600.0) for i in range(30)))
    assert corpus.coverage().meets_minimum_hours is False


def test_a_corpus_reports_labelled_and_unlabelled_hours_separately() -> None:
    mixed = Corpus((*a_full_corpus().items, an_unlabelled_item("cv-x", 3600.0)))
    coverage = mixed.coverage()
    assert coverage.unlabelled_hours == pytest.approx(1.0)
    assert coverage.labelled_hours == pytest.approx(3 * 7 * 600.0 / 3600.0)
    assert coverage.total_hours == pytest.approx(coverage.labelled_hours + 1.0)


def test_an_interim_corpus_says_so() -> None:
    corpus = Corpus(
        (an_unlabelled_item(),),
        provenance=Provenance(name="Common Voice ckb", licence="CC0-1.0", interim=True),
    )
    assert corpus.provenance.interim
    assert "Common Voice" in corpus.provenance.name


def test_a_provenance_without_a_licence_is_refused() -> None:
    """Every corpus that enters this system has an audited licence — no exceptions."""
    with pytest.raises(ValueError, match="licence"):
        Provenance(name="somebody's scrape", licence="", interim=True)


def test_an_interim_corpus_still_round_trips_through_the_manifest(tmp_path: Path) -> None:
    corpus = Corpus(
        (an_unlabelled_item(),),
        provenance=Provenance(name="Common Voice ckb", licence="CC0-1.0", interim=True),
    )
    path = tmp_path / "interim.json"
    path.write_text(corpus.to_json(), encoding="utf-8")
    assert Corpus.load(path) == corpus


# --- §8.1's coverage grid, parsed from the frozen blueprint rather than retyped ------------
#
# `test_the_three_dialects_of_section_4_4_are_the_dialect_enum` and
# `test_every_section_8_1_condition_is_representable` compared the enums against literal sets
# typed into this file, and this file referenced BLUEPRINT.md nowhere — so the grid certified
# itself. `tests/test_registry.py` has parsed §7 out of the blueprint from the start; §8.1 never
# got the same treatment, and M0.6's row claims "(3 dialects × 7 conditions)" implements §8.1's
# list. D-091.
#
# The mapping is deliberately explicit because §8.1's phrasing does not line up one-to-one with
# the enum: "Kurdish–English and Kurdish–Arabic code-switching" is ONE §8.1 item covering TWO
# members. That is the same shape as §4.1's single "Numerals" row covering three numeral systems,
# which is precisely how M0.3 came to claim five collisions were handled when four were (D-076).
# Counting §8.1's items and comparing to `len(Condition)` would reproduce that error.

_BLUEPRINT = Path(__file__).resolve().parents[1] / "BLUEPRINT.md"

# Each §8.1 coverage phrase, mapped to the enum members it covers.
_SECTION_8_1_DIALECTS: dict[str, Dialect] = {
    "Hewlêr": Dialect.HEWLER,
    "Slemani": Dialect.SLEMANI,
    "Mukriyan": Dialect.MUKRIYAN,
}
_SECTION_8_1_CONDITIONS: dict[str, frozenset[Condition]] = {
    "formal news": frozenset({Condition.FORMAL_NEWS}),
    "casual podcast": frozenset({Condition.CASUAL_PODCAST}),
    # One phrase, two members — see the note above.
    "Kurdish–English and Kurdish–Arabic code-switching": frozenset(
        {Condition.CODE_SWITCH_EN, Condition.CODE_SWITCH_AR}
    ),
    "noisy environments": frozenset({Condition.NOISY}),
    "overlapping speakers": frozenset({Condition.OVERLAPPING_SPEAKERS}),
    "named entities and political terminology": frozenset({Condition.NAMED_ENTITIES}),
}


def _section_8_1_coverage_items() -> list[str]:
    """§8.1's coverage list, read out of the frozen blueprint."""
    for line in _BLUEPRINT.read_text(encoding="utf-8").splitlines():
        if "Several hours across:" in line:
            bolded = line.split("**")[1]
            return [item.strip().rstrip(".") for item in bolded.split("·")]
    raise AssertionError("§8.1's 'Several hours across:' coverage line was not found")


def test_section_8_1_coverage_line_is_parseable() -> None:
    """Guard the guard: if §8.1's shape changes these tests must fail loudly, not vacuously."""
    items = _section_8_1_coverage_items()
    assert len(items) == 9, items


def test_every_section_8_1_coverage_item_maps_to_the_enums() -> None:
    """Set equality both ways, as `test_registry.py` does for §7.

    Left to right: a category §8.1 adds has no mapping and fails here rather than being silently
    unrepresentable. Right to left: an enum member nobody can point at a §8.1 phrase fails too.
    """
    items = set(_section_8_1_coverage_items())
    mapped = set(_SECTION_8_1_DIALECTS) | set(_SECTION_8_1_CONDITIONS)
    assert items == mapped, (
        f"§8.1 lists {sorted(items - mapped)} with no mapping; "
        f"mapped-but-absent: {sorted(mapped - items)}"
    )
    assert set(_SECTION_8_1_DIALECTS.values()) == set(Dialect)
    covered: set[Condition] = set()
    for members in _SECTION_8_1_CONDITIONS.values():
        covered |= members
    assert covered == set(Condition), (
        f"conditions §8.1 does not cover: {sorted(c.value for c in set(Condition) - covered)}"
    )


def test_the_hours_floor_matches_the_decision_that_records_it() -> None:
    """`MINIMUM_HOURS` was referenced by no test at all, so it could drift from D-009.

    §8.1 asks for "several hours" without a number; D-009 fixes 3.0 as "the smallest quantity
    'several' honestly describes". The value is parsed out of D-009 rather than retyped here, so
    changing the floor requires changing the record — which is the point of recording it. Measured
    before this existed: 3.0 → 1.0 left the whole suite green.
    """
    import re

    from hawedit.corpus import MINIMUM_HOURS

    decisions = (Path(__file__).resolve().parents[1] / "DECISIONS.md").read_text(encoding="utf-8")
    heading = next(line for line in decisions.splitlines() if line.startswith("## D-009"))
    recorded = re.search(r"([0-9]+\.[0-9]+)-hour floor", heading)
    assert recorded is not None, f"D-009's heading no longer states the floor: {heading!r}"
    assert float(recorded.group(1)) == MINIMUM_HOURS, (
        f"MINIMUM_HOURS is {MINIMUM_HOURS} and D-009 records {recorded.group(1)}. Changing the "
        f"floor means amending the decision, not only the constant."
    )
