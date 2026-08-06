"""M0.9 — the benchmark runner, the report, and §8.1's decision rule.

§8.1's decision rule: "LLM-7B stays canonical unless another model shows a material accuracy
gain on *your* audio at acceptable throughput." Three clauses, each of which the code has to
honour — and §4.4 adds a fourth constraint, because a challenger that wins on average while
losing in Mukriyan is not a win, it is an average.

The rule is deliberately hard to satisfy. §1: "No model changes without measurement." §7:
"Every figure above is vendor- or author-reported and not independently replicated."
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hawedit2.asr import ASRResult, Hardware, MeasurementSession
from hawedit2.bench import (
    MATERIAL_GAIN_RATIO,
    BenchmarkReport,
    decide_canonical,
    run_benchmark,
)
from hawedit2.corpus import Condition, Corpus, CorpusItem, Dialect

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
    assert report.models[INCUMBENT].adapter_impls == ("ScriptedAdapter",)


def test_the_report_records_real_time_factor() -> None:
    report = a_run({"hew-1": PERFECT, "muk-1": PERFECT}, step=6.0)
    assert report.models[INCUMBENT].mean_rtf == pytest.approx(0.1)


def test_the_report_serialises_to_json() -> None:
    report = a_run({"hew-1": PERFECT, "muk-1": PERFECT})
    payload = report.to_json()
    assert "hawapc01" in payload
    assert "hewler" in payload
    assert INCUMBENT in payload


def test_the_report_carries_the_corpus_coverage_it_was_run_on() -> None:
    """A headline CER from a corpus missing five of 21 cells must not look unqualified."""
    report = a_run({"hew-1": PERFECT, "muk-1": PERFECT})
    assert report.coverage.missing_cells, "this two-item corpus is deliberately incomplete"
    assert report.coverage.total_hours > 0


# --- §8.1 decision rule ----------------------------------------------------------------


def test_a_material_gain_at_acceptable_throughput_switches_the_canonical_model() -> None:
    report = a_run(
        incumbent_text={"hew-1": "ئەمە زۆر خراپە", "muk-1": "ئەمە زۆر خراپە"},
        challenger_text={"hew-1": PERFECT, "muk-1": PERFECT},
    )
    decision = decide_canonical(report, max_rtf=1.0)
    assert decision.switch
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
