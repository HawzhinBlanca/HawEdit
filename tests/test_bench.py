"""M0.9 — the benchmark runner, the report, and §8.1's decision rule.

§8.1's decision rule: "LLM-7B stays canonical unless another model shows a material accuracy
gain on *your* audio at acceptable throughput." Three clauses, each of which the code has to
honour — and §4.4 adds a fourth constraint, because a challenger that wins on average while
losing in Mukriyan is not a win, it is an average.

The rule is deliberately hard to satisfy. §1: "No model changes without measurement." §7:
"Every figure above is vendor- or author-reported and not independently replicated."
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hawedit.asr import (
    ASRResult,
    Hardware,
    MeasurementSession,
    SegmentTranscript,
)
from hawedit.asr import OmniAsrAdapter as OmniAsrAdapterReal
from hawedit.bench import (
    MATERIAL_GAIN_RATIO,
    BenchmarkReport,
    decide_canonical,
    run_benchmark,
)
from hawedit.corpus import Condition, Corpus, CorpusItem, Dialect, Provenance

HAWAPC01 = Hardware(host="hawapc01", accelerator="2x RTX 3090 Ti")
INCUMBENT = "omniASR_LLM_7B_v2"
CHALLENGER = "omniASR_CTC_3B_v2"

PERFECT = "ئەمە زۆر باشە"


class ScriptedAdapter:
    """Returns a preset hypothesis per item id, so accuracy is exactly what a test says."""

    def __init__(self, model_id: str, by_item: dict[str, str]) -> None:
        self.model_id = model_id
        self._by_item = by_item

    def transcribe(self, audio_path: Path, duration_s: float) -> ASRResult:
        return ASRResult(text_raw=self._by_item[audio_path.stem])


def an_item(item_id: str, dialect: Dialect, duration_s: float = 60.0) -> CorpusItem:
    return CorpusItem(
        item_id=item_id,
        audio_path=f"{item_id}.wav",
        reference_ckb=PERFECT,
        dialect=dialect,
        conditions=frozenset({Condition.FORMAL_NEWS}),
        duration_s=duration_s,
    )


TWO_DIALECT_CORPUS = Corpus(
    (
        an_item("hew-1", Dialect.HEWLER),
        an_item("muk-1", Dialect.MUKRIYAN),
    )
)


def a_session(step: float = 6.0) -> MeasurementSession:
    times = iter([i * step for i in range(1000)])
    return MeasurementSession(hardware=HAWAPC01, clock=lambda: next(times))


def a_run(
    incumbent_text: dict[str, str],
    challenger_text: dict[str, str] | None = None,
    step: float = 6.0,
) -> BenchmarkReport:
    adapters = [ScriptedAdapter(INCUMBENT, incumbent_text)]
    if challenger_text is not None:
        adapters.append(ScriptedAdapter(CHALLENGER, challenger_text))
    return run_benchmark(TWO_DIALECT_CORPUS, adapters, a_session(step))


# --- the report ------------------------------------------------------------------------


def test_the_report_never_gives_only_an_aggregate() -> None:
    """§4.4: "A single aggregate CER hides the dialect where the product is actually used.""" ""
    report = a_run({"hew-1": PERFECT, "muk-1": PERFECT})
    model = report.models[INCUMBENT]
    assert set(model.normalized_cer_by_dialect) == {Dialect.HEWLER, Dialect.MUKRIYAN}
    assert model.normalized_cer is not None


def test_a_perfect_transcription_scores_zero() -> None:
    report = a_run({"hew-1": PERFECT, "muk-1": PERFECT})
    assert report.models[INCUMBENT].normalized_cer == 0.0


def test_encoding_differences_are_not_scored_as_errors() -> None:
    """The reference and the hypothesis differ only by keyboard. §4.1, and D-008."""
    other_encoding = "ئه‌مه‌ زۆر باشه‌"
    report = a_run({"hew-1": other_encoding, "muk-1": other_encoding})
    assert report.models[INCUMBENT].normalized_cer == 0.0


def test_per_dialect_scores_are_independent() -> None:
    report = a_run({"hew-1": PERFECT, "muk-1": "ئەمە زۆر خراپە"})
    model = report.models[INCUMBENT]
    assert model.normalized_cer_by_dialect[Dialect.HEWLER] == 0.0
    assert model.normalized_cer_by_dialect[Dialect.MUKRIYAN] > 0.0


def test_the_report_records_the_hardware_and_the_adapter_implementations() -> None:
    """Without these two facts the numbers are not reproducible or trustworthy."""
    report = a_run({"hew-1": PERFECT, "muk-1": PERFECT})
    assert report.hardware.host == "hawapc01"
    assert report.models[INCUMBENT].adapter_impls == ("test_bench.ScriptedAdapter",)


def test_the_report_records_real_time_factor() -> None:
    report = a_run({"hew-1": PERFECT, "muk-1": PERFECT}, step=6.0)
    assert report.models[INCUMBENT].mean_rtf == pytest.approx(0.1)


def test_the_report_serialises_to_json() -> None:
    """Asserted on parsed key paths, not on substrings of the document.

    `assert "hewler" in payload` was the previous mechanism and it measured nothing about the
    per-dialect numbers: with `normalized_cer_by_dialect` deleted from `ModelReport.to_dict()`
    the string still occurred **seven** times — once in `coverage.hours_by_dialect` and six
    times in `coverage.missing_cells` — so the assertion was satisfied by a block of the report
    that has nothing to do with per-model accuracy. D-094.
    """
    report = a_run({"hew-1": PERFECT, "muk-1": PERFECT})
    document = json.loads(report.to_json())
    assert document["hardware"]["host"] == "hawapc01"
    assert INCUMBENT in document["models"]
    assert set(document["models"][INCUMBENT]["normalized_cer_by_dialect"]) == {
        "hewler",
        "mukriyan",
    }


def test_the_report_carries_the_corpus_coverage_it_was_run_on() -> None:
    """A headline CER from a corpus missing five of 21 cells must not look unqualified."""
    report = a_run({"hew-1": PERFECT, "muk-1": PERFECT})
    assert report.coverage.missing_cells, "this two-item corpus is deliberately incomplete"
    assert report.coverage.total_hours > 0


# --- §8.1 decision rule ----------------------------------------------------------------


def complete_corpus() -> Corpus:
    """A §8.1-complete set: every dialect x condition cell, and past the hours floor.

    Required for any test that expects a *successful* promotion — an incomplete corpus
    blocks the switch outright (audit finding #2).
    """
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
            name = f"{dialect.value}-{condition.value}"
            items.append(
                CorpusItem(
                    item_id=name,
                    audio_path=f"{name}.wav",
                    reference_ckb=PERFECT,
                    dialect=dialect,
                    conditions=frozenset({condition}),
                    duration_s=600.0,
                    **extra,  # type: ignore[arg-type]
                )
            )
    return Corpus(tuple(items))


def test_a_material_gain_at_acceptable_throughput_switches_the_canonical_model() -> None:
    corpus = complete_corpus()
    ids = [i.item_id for i in corpus.items]
    report = run_benchmark(
        corpus,
        [
            ScriptedAdapter(INCUMBENT, dict.fromkeys(ids, "ئەمە زۆر خراپە")),
            ScriptedAdapter(CHALLENGER, dict.fromkeys(ids, PERFECT)),
        ],
        a_session(),
    )
    decision = decide_canonical(report, max_rtf=1.0)
    assert decision.switch, decision.reasons
    assert decision.challenger == CHALLENGER


def test_an_immaterial_gain_keeps_the_incumbent() -> None:
    """§8.1 says *material*. Noise-level wins are how a frozen architecture drifts.

    The gain that matters is relative, so the challenger has to be only slightly better
    than a mediocre incumbent: 20 character errors against 19 is a 5% improvement, half
    the threshold. (A perfect challenger against any flawed incumbent is a 100% gain, no
    matter how small the incumbent's absolute error — which is the right behaviour, and
    the reason this fixture cannot simply transcribe correctly.)
    """
    report = a_run(
        incumbent_text={"hew-1": PERFECT + "x" * 10, "muk-1": PERFECT + "x" * 10},
        challenger_text={"hew-1": PERFECT + "x" * 9, "muk-1": PERFECT + "x" * 10},
    )
    incumbent_cer = report.models[INCUMBENT].normalized_cer
    challenger_cer = report.models[CHALLENGER].normalized_cer
    assert incumbent_cer is not None and challenger_cer is not None
    gain = (incumbent_cer - challenger_cer) / incumbent_cer
    assert 0 < gain < MATERIAL_GAIN_RATIO, f"fixture must give a sub-threshold gain, got {gain}"

    decision = decide_canonical(report, max_rtf=1.0)
    assert not decision.switch
    assert any("material" in r for r in decision.reasons)


def test_a_dialect_regression_blocks_a_switch_that_wins_on_average() -> None:
    """§4.4 is the whole reason per-dialect numbers exist. Winning the mean is not winning."""
    report = a_run(
        incumbent_text={"hew-1": "ئەمە زۆر خراپەxxxxxx", "muk-1": PERFECT},
        challenger_text={"hew-1": PERFECT, "muk-1": "ئەمە زۆر خراپە"},
    )
    decision = decide_canonical(report, max_rtf=1.0)
    assert not decision.switch
    assert any("mukriyan" in r for r in decision.reasons)


def test_unacceptable_throughput_blocks_an_accuracy_win() -> None:
    report = a_run(
        incumbent_text={"hew-1": "ئەمە زۆر خراپە", "muk-1": "ئەمە زۆر خراپە"},
        challenger_text={"hew-1": PERFECT, "muk-1": PERFECT},
        step=600.0,
    )
    decision = decide_canonical(report, max_rtf=1.0)
    assert not decision.switch
    assert any("throughput" in r or "rtf" in r.lower() for r in decision.reasons)


def test_with_no_challenger_the_incumbent_stays() -> None:
    report = a_run({"hew-1": PERFECT, "muk-1": PERFECT})
    decision = decide_canonical(report, max_rtf=1.0)
    assert not decision.switch
    assert decision.challenger is None


def test_a_report_without_the_incumbent_is_an_error_not_a_switch() -> None:
    """Silently promoting the only model present is exactly how a pin gets lost."""
    report = run_benchmark(
        TWO_DIALECT_CORPUS,
        [ScriptedAdapter(CHALLENGER, {"hew-1": PERFECT, "muk-1": PERFECT})],
        a_session(),
    )
    with pytest.raises(LookupError, match=INCUMBENT):
        decide_canonical(report, max_rtf=1.0)


def test_the_decision_always_explains_itself() -> None:
    report = a_run({"hew-1": PERFECT, "muk-1": PERFECT})
    assert decide_canonical(report, max_rtf=1.0).reasons


def test_a_failed_item_does_not_silently_improve_a_score() -> None:
    """Dropping the item a model choked on would reward failure with a better CER."""

    class ChokesOnMukriyan(ScriptedAdapter):
        def transcribe(self, audio_path: Path, duration_s: float) -> ASRResult:
            if audio_path.stem.startswith("muk"):
                raise RuntimeError("decode failed")
            return super().transcribe(audio_path, duration_s)

    report = run_benchmark(
        TWO_DIALECT_CORPUS,
        [ChokesOnMukriyan(INCUMBENT, {"hew-1": PERFECT, "muk-1": PERFECT})],
        a_session(),
    )
    model = report.models[INCUMBENT]
    assert model.failed_items == 1
    assert model.scored_items == 1
    assert Dialect.MUKRIYAN not in model.normalized_cer_by_dialect


# --- interim corpora may exercise the harness but never decide a model (M0.9b) ---------


def an_interim_corpus() -> Corpus:
    """Unlabelled public data: real Kurdish, no §4.4 dialect labels, no §8.1 conditions."""
    return Corpus(
        tuple(
            CorpusItem(
                item_id=f"cv-{i}",
                audio_path=f"cv-{i}.wav",
                reference_ckb=PERFECT,
                dialect=None,
                conditions=frozenset(),
                duration_s=60.0,
            )
            for i in range(2)
        ),
        provenance=Provenance(name="Common Voice ckb", licence="CC0-1.0", interim=True),
    )


def an_interim_run(incumbent_text: dict[str, str], challenger_text: dict[str, str]):  # type: ignore[no-untyped-def]
    corpus = an_interim_corpus()
    return run_benchmark(
        corpus,
        [
            ScriptedAdapter(INCUMBENT, incumbent_text),
            ScriptedAdapter(CHALLENGER, challenger_text),
        ],
        a_session(),
    )


def test_an_interim_corpus_cannot_promote_a_challenger_however_large_the_gain() -> None:
    """§8.1 justifies a swap on measurement on *your* audio. Public stand-in data is not
    that, no matter how clean the win looks."""
    report = an_interim_run(
        incumbent_text={"cv-0": "ئەمە زۆر خراپە", "cv-1": "ئەمە زۆر خراپە"},
        challenger_text={"cv-0": PERFECT, "cv-1": PERFECT},
    )
    decision = decide_canonical(report, max_rtf=1.0)
    assert not decision.switch
    assert any("interim" in r.lower() for r in decision.reasons)


def test_an_interim_run_still_reports_its_numbers() -> None:
    """Refusing to *decide* on interim data is not refusing to measure with it."""
    report = an_interim_run(
        incumbent_text={"cv-0": "ئەمە زۆر خراپە", "cv-1": "ئەمە زۆر خراپە"},
        challenger_text={"cv-0": PERFECT, "cv-1": PERFECT},
    )
    assert report.models[CHALLENGER].normalized_cer == 0.0
    assert report.models[INCUMBENT].normalized_cer is not None


def test_the_report_marks_itself_interim() -> None:
    payload = an_interim_run({"cv-0": PERFECT, "cv-1": PERFECT}, {"cv-0": PERFECT, "cv-1": PERFECT})
    assert payload.provenance.interim
    assert '"interim": true' in payload.to_json()


def test_an_interim_report_carries_no_per_dialect_numbers() -> None:
    """Nothing to break down by: the data has no dialect labels, and inventing them is
    exactly what §4.4 warns the aggregate hides."""
    report = an_interim_run({"cv-0": PERFECT, "cv-1": PERFECT}, {"cv-0": PERFECT, "cv-1": PERFECT})
    assert report.models[INCUMBENT].normalized_cer_by_dialect == {}


# --- D-094: §4.4 was enforced on the property, never on the artifact a reader receives ------


_MODEL_REPORT_KEYS = {
    "model_id",
    "adapter_impls",
    "scored_items",
    "failed_items",
    "normalized_cer",
    "spacing_free_cer",
    "normalized_cer_by_dialect",
    "named_entity_error",
    "code_switch_error",
    "mean_rtf",
    "worst_rtf",
    "long_audio_failure_rate",
    "peak_vram_bytes",
}


def test_the_written_report_never_carries_an_aggregate_without_its_dialect_breakdown() -> None:
    """`normalized_cer_by_dialect`'s docstring says "§4.4: never report the aggregate without
    these", and nothing held it to that. Deleting the field from `ModelReport.to_dict()` left
    all 1,161 tests green, and the emitted report carried `normalized_cer: 0.15` alone while
    the two dialects it came from measured 0.04 and 0.26 — a 6.5x spread the aggregate hides,
    on the number that decides which model becomes canonical.

    The teeth are in the fixture: the two dialects are deliberately far apart, so the aggregate
    genuinely misleads and the breakdown genuinely informs. A run where both dialects score the
    same would pass whether or not the field survived.
    """
    report = a_run({"hew-1": PERFECT, "muk-1": "ئەمە زۆر خراپە"})
    model = json.loads(report.to_json())["models"][INCUMBENT]

    breakdown = model["normalized_cer_by_dialect"]
    assert set(breakdown) == {"hewler", "mukriyan"}
    assert model["normalized_cer"] is not None
    # The aggregate sits between the two, which is exactly why it cannot stand alone.
    assert breakdown["hewler"] < model["normalized_cer"] < breakdown["mukriyan"], (
        f"the fixture no longer spreads the dialects, so this test has stopped measuring "
        f"anything: {breakdown} against {model['normalized_cer']}"
    )


def test_an_unlabelled_run_emits_an_empty_breakdown_rather_than_omitting_the_key() -> None:
    """The control, and the reason the fix is not "emit the key only when it has values".

    An interim corpus has no §4.4 labels, so the breakdown is legitimately empty — that is
    already tested on the property. On the artifact the distinction matters more: an absent key
    reads as *not applicable*, an empty object reads as *we looked and the data carries no
    labels*. Omitting it would satisfy the test above and reintroduce the unqualified aggregate
    for exactly the corpus most likely to be quoted early.
    """
    report = an_interim_run({"cv-0": PERFECT, "cv-1": PERFECT}, {"cv-0": PERFECT, "cv-1": PERFECT})
    model = json.loads(report.to_json())["models"][INCUMBENT]
    assert "normalized_cer_by_dialect" in model, (
        "the key vanished for an unlabelled corpus — absent reads as not-applicable, which is "
        "the unqualified aggregate again"
    )
    assert model["normalized_cer_by_dialect"] == {}
    assert model["normalized_cer"] is not None


def test_the_emitted_report_schema_is_recorded_field_by_field() -> None:
    """A field can vanish from a written §8.1 artifact without a single test noticing.

    That is the class of defect, not one field: `to_dict` is a hand-written key list, and the
    only tests reading it did so through substrings or through the properties behind it. The
    recorded set is a visible line in a diff — adding a field means editing this test, the same
    trade `scripts/test-count.floor` already makes.
    """
    document = json.loads(a_run({"hew-1": PERFECT, "muk-1": PERFECT}).to_json())

    assert set(document) == {"provenance", "hardware", "coverage", "models"}
    assert set(document["provenance"]) == {"name", "licence", "interim", "note"}
    assert set(document["hardware"]) == {"host", "accelerator", "notes"}
    assert set(document["coverage"]) == {
        "total_hours",
        "labelled_hours",
        "unlabelled_hours",
        "hours_by_dialect",
        "missing_cells",
        "meets_minimum_hours",
    }
    for model_id, model in document["models"].items():
        assert set(model) == _MODEL_REPORT_KEYS, (
            f"{model_id}: emitted fields drifted from the recorded schema — "
            f"missing {_MODEL_REPORT_KEYS - set(model)}, extra {set(model) - _MODEL_REPORT_KEYS}"
        )


# --- D-097: the report named a class, which a stub can wear ----------------------------------


class OmniAsrAdapter:
    """A stub wearing the real canonical adapter's class name. No weights, no GPU, no model.

    Deliberately named to collide with `hawedit.asr.OmniAsrAdapter`. `validate_adapter` checks
    the *model id* against §7, which this claims honestly, so the class name was the only signal
    left and it was identical.
    """

    model_id = INCUMBENT

    def transcribe(self, audio_path: Path, duration_s: float) -> ASRResult:
        return ASRResult(text_raw=PERFECT)


def test_a_stub_wearing_the_real_adapters_class_name_is_visible_in_the_report() -> None:
    """Measured before the fix: `adapter_impls: ["OmniAsrAdapter"]`, `normalized_cer: 0.0`,
    `mean_rtf: 0.1`, on `hawapc01` / `2x RTX 3090 Ti` — byte for byte what a real run emits,
    from a class with no model behind it.

    Asserted on the emitted JSON, because the report is what a reader receives.
    """
    report = run_benchmark(TWO_DIALECT_CORPUS, [OmniAsrAdapter()], a_session())
    impls = json.loads(report.to_json())["models"][INCUMBENT]["adapter_impls"]

    assert impls == ["test_bench.OmniAsrAdapter"]
    assert impls != ["OmniAsrAdapter"], "a bare class name is what made the stub invisible"
    assert impls != ["hawedit.asr.OmniAsrAdapter"], (
        "the stub is reported as the real canonical adapter — the §8.1 number claims weights "
        "that never loaded"
    )


def test_the_real_canonical_adapter_reports_its_own_module() -> None:
    """The control, and it is the half that can fail for the plausible wrong reason.

    Qualifying with `__module__` is only worth anything if the real adapter's own qualified name
    is what lands in the report — prefixing everything with a constant would satisfy the test
    above and identify just as little. This measures the genuine `hawedit.asr.OmniAsrAdapter`,
    with a backend that raises, so no weights are needed: "failures are recorded not raised"
    (M0.7) means the measurement is still produced and still carries its adapter.
    """

    class RefusingBackend:
        def transcribe_segment(self, audio_path: Path, duration_s: float) -> SegmentTranscript:
            raise RuntimeError("no weights on this host")

    measurement = a_session().measure(
        OmniAsrAdapterReal(backend=RefusingBackend()), an_item("hew-1", Dialect.HEWLER)
    )
    assert measurement.adapter_impl == "hawedit.asr.OmniAsrAdapter"
    assert measurement.error is not None, "the failure must still be recorded, not raised"
    assert measurement.result is None
