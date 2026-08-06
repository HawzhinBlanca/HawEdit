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

from hawedit2.corpus import (
    Condition,
    Corpus,
    CorpusItem,
    Dialect,
    IncompleteCoverage,
    InvalidCorpusItem,
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
