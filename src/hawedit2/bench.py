"""§8.1's ASR benchmark: run the labelled set through each candidate, report comparably,
and apply the decision rule.

§8.1 is explicit about what this exists for: "Published CERs across different models are
computed on different datasets with different normalization — they are not comparable. Only
this harness produces comparable numbers." And the rule it feeds:

    "LLM-7B stays canonical unless another model shows a material accuracy gain on *your*
    audio at acceptable throughput."

Four conditions have to hold before the canonical model changes, and the fourth is not in
that sentence — it comes from §4.4:

1. the challenger's normalized CER is materially lower (`MATERIAL_GAIN_RATIO`),
2. its throughput is acceptable on the hardware that was actually measured,
3. it does not regress in **any** dialect — winning the mean while losing Mukriyan is an
   average, not a win,
4. the incumbent was in the run at all; promoting the only model present is how a pin
   silently disappears.

Aggregates are micro-averaged (total edits over total reference characters), so a corpus of
mixed-length items is not dominated by its shortest ones. Per-dialect figures are always
present alongside the aggregate, never instead of it. Items a model failed on are counted as
failures and excluded from its accuracy — dropping them silently would reward a model for
choking on the audio it finds hardest.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from hawedit2.alignment import AlignmentAccuracy, score_alignment
from hawedit2.asr import (
    ASRAdapter,
    Hardware,
    Measurement,
    MeasurementSession,
    long_audio_failure_rate,
    validate_adapter,
)
from hawedit2.corpus import Corpus, CorpusItem, Coverage, Dialect, Provenance
from hawedit2.metrics import (
    code_switch_error_rate,
    named_entity_error_rate,
    normalized_cer,
    spacing_free_cer,
)
from hawedit2.normalize import normalize_sorani
from hawedit2.transcripts import AsrProvenance

__all__ = [
    "CANONICAL_ASR",
    "MATERIAL_GAIN_RATIO",
    "BenchmarkReport",
    "CanonicalDecision",
    "ItemScore",
    "ModelReport",
    "decide_canonical",
    "run_benchmark",
]

# §3 Stage 1 / §7: the pinned canonical ASR. Provisional pending this benchmark, which is
# the only thing §8.1 accepts as grounds for changing it.
CANONICAL_ASR: Final = "omniASR_LLM_7B_v2"

# What "material" means. §8.1 does not put a number on it — see DECISIONS.md D-010. A 10%
# relative reduction in normalized CER is well clear of run-to-run noise while still
# admitting a genuine improvement. It is a floor for *considering* a switch, not a
# sufficient condition: conditions 2-4 above still apply.
MATERIAL_GAIN_RATIO: Final = 0.10


@dataclass(frozen=True, slots=True)
class ItemScore:
    """Every §8.1 accuracy metric for one (model, item), plus what it cost to produce."""

    item_id: str
    # None for an unlabelled item (an interim corpus has no §4.4 dialect). Such an item
    # still scores; it simply contributes to no per-dialect breakdown.
    dialect: Dialect | None
    reference_chars: int
    normalized_cer: float
    spacing_free_cer: float
    named_entity_error: float | None
    code_switch_error: float | None
    alignment: AlignmentAccuracy | None
    rtf: float


@dataclass(frozen=True, slots=True)
class ModelReport:
    """One candidate's results across the labelled set."""

    model_id: str
    adapter_impls: tuple[str, ...]
    scores: tuple[ItemScore, ...]
    failed_items: int
    long_audio_failure_rate: float | None
    peak_vram_bytes: int | None

    @property
    def scored_items(self) -> int:
        return len(self.scores)

    @staticmethod
    def _micro_cer(scores: Sequence[ItemScore], attr: str) -> float | None:
        """Total edits over total reference characters, not a mean of per-item rates.

        A macro-average lets a five-character item weigh as much as a five-hundred
        character one, which for a corpus of mixed-length news and podcast material
        quietly reports a different number than the one anybody means by "CER".
        """
        chars = sum(s.reference_chars for s in scores)
        if not chars:
            return None
        edits: float = sum(float(getattr(s, attr)) * s.reference_chars for s in scores)
        return edits / chars

    @property
    def normalized_cer(self) -> float | None:
        return self._micro_cer(self.scores, "normalized_cer")

    @property
    def spacing_free_cer(self) -> float | None:
        return self._micro_cer(self.scores, "spacing_free_cer")

    @property
    def normalized_cer_by_dialect(self) -> Mapping[Dialect, float]:
        """§4.4: never report the aggregate without these."""
        by_dialect: dict[Dialect, float] = {}
        for dialect in Dialect:
            subset = [s for s in self.scores if s.dialect is dialect]
            value = self._micro_cer(subset, "normalized_cer") if subset else None
            if value is not None:
                by_dialect[dialect] = value
        return by_dialect

    @property
    def named_entity_error(self) -> float | None:
        measured = [s.named_entity_error for s in self.scores if s.named_entity_error is not None]
        return sum(measured) / len(measured) if measured else None

    @property
    def code_switch_error(self) -> float | None:
        measured = [s.code_switch_error for s in self.scores if s.code_switch_error is not None]
        return sum(measured) / len(measured) if measured else None

    @property
    def mean_rtf(self) -> float | None:
        return sum(s.rtf for s in self.scores) / len(self.scores) if self.scores else None

    @property
    def worst_rtf(self) -> float | None:
        return max((s.rtf for s in self.scores), default=None)

    def to_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "adapter_impls": list(self.adapter_impls),
            "scored_items": self.scored_items,
            "failed_items": self.failed_items,
            "normalized_cer": self.normalized_cer,
            "spacing_free_cer": self.spacing_free_cer,
            "normalized_cer_by_dialect": {
                d.value: v for d, v in self.normalized_cer_by_dialect.items()
            },
            "named_entity_error": self.named_entity_error,
            "code_switch_error": self.code_switch_error,
            "mean_rtf": self.mean_rtf,
            "worst_rtf": self.worst_rtf,
            "long_audio_failure_rate": self.long_audio_failure_rate,
            "peak_vram_bytes": self.peak_vram_bytes,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    """The §8.1 run: every candidate, on one named machine, over one labelled set."""

    hardware: Hardware
    coverage: Coverage
    models: Mapping[str, ModelReport]
    provenance: Provenance

    def to_dict(self) -> dict[str, object]:
        return {
            "provenance": {
                "name": self.provenance.name,
                "licence": self.provenance.licence,
                "interim": self.provenance.interim,
                "note": self.provenance.note,
            },
            "hardware": {
                "host": self.hardware.host,
                "accelerator": self.hardware.accelerator,
                "notes": self.hardware.notes,
            },
            "coverage": {
                "total_hours": self.coverage.total_hours,
                "labelled_hours": self.coverage.labelled_hours,
                "unlabelled_hours": self.coverage.unlabelled_hours,
                "hours_by_dialect": {d.value: h for d, h in self.coverage.hours_by_dialect.items()},
                "missing_cells": [f"{d.value}/{c.value}" for d, c in self.coverage.missing_cells],
                "meets_minimum_hours": self.coverage.meets_minimum_hours,
            },
            "models": {mid: m.to_dict() for mid, m in self.models.items()},
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def _score_item(item: CorpusItem, measurement: Measurement) -> ItemScore | None:
    """Score one successful measurement against the item's reference labels."""
    if measurement.result is None:
        return None
    hypothesis = measurement.result.text_raw

    alignment: AlignmentAccuracy | None = None
    if item.reference_words and measurement.result.words:
        alignment = score_alignment(
            item.reference_words,
            measurement.result.words,
            AsrProvenance(canonical=measurement.model_id, aligner="ctc_viterbi"),
        )

    return ItemScore(
        item_id=item.item_id,
        dialect=item.dialect,
        # Weighting is by *normalized* reference length, matching what the CER divides by.
        reference_chars=len(normalize_sorani(item.reference_ckb)),
        normalized_cer=normalized_cer(item.reference_ckb, hypothesis),
        spacing_free_cer=spacing_free_cer(item.reference_ckb, hypothesis),
        named_entity_error=named_entity_error_rate(hypothesis, item.named_entities),
        code_switch_error=code_switch_error_rate(hypothesis, item.code_switch_spans),
        alignment=alignment,
        rtf=measurement.rtf,
    )


def run_benchmark(
    corpus: Corpus,
    adapters: Sequence[ASRAdapter],
    session: MeasurementSession,
) -> BenchmarkReport:
    """Run every candidate over the labelled set and report comparably.

    Every adapter is resolved against §7 before anything runs, so an excluded model cannot
    reach the report and be argued about afterwards.
    """
    for adapter in adapters:
        validate_adapter(adapter)

    models: dict[str, ModelReport] = {}
    for adapter in adapters:
        measurements: list[Measurement] = []
        scores: list[ItemScore] = []
        for item in corpus.items:
            measurement = session.measure(adapter, item)
            measurements.append(measurement)
            score = _score_item(item, measurement)
            if score is not None:
                scores.append(score)

        vram = [m.peak_vram_bytes for m in measurements if m.peak_vram_bytes is not None]
        models[adapter.model_id] = ModelReport(
            model_id=adapter.model_id,
            adapter_impls=tuple(sorted({m.adapter_impl for m in measurements})),
            scores=tuple(scores),
            failed_items=sum(1 for m in measurements if m.failed),
            long_audio_failure_rate=long_audio_failure_rate(measurements),
            peak_vram_bytes=max(vram) if vram else None,
        )

    return BenchmarkReport(
        hardware=session.hardware,
        coverage=corpus.coverage(),
        models=models,
        provenance=corpus.provenance,
    )


@dataclass(frozen=True, slots=True)
class CanonicalDecision:
    """What §8.1's rule concluded, and why. The reasons are the point."""

    incumbent: str
    challenger: str | None
    switch: bool
    reasons: tuple[str, ...]


def decide_canonical(
    report: BenchmarkReport,
    max_rtf: float,
    incumbent: str = CANONICAL_ASR,
) -> CanonicalDecision:
    """Apply §8.1's decision rule to a benchmark report.

    `max_rtf` has no default on purpose: "acceptable throughput" is a capacity decision
    about a specific box and workload, and §3 Stage 1 warns against deriving it from
    published figures. Making the caller state it keeps that choice visible.

    Raises:
        LookupError: the incumbent was not part of the run. Promoting whichever model
            happens to be present is exactly how a pinned choice disappears.
    """
    if incumbent not in report.models:
        raise LookupError(
            f"{incumbent!r} was not in this run, so there is nothing to compare against. "
            f"§8.1 keeps it canonical until a challenger beats it — a run without the "
            f"incumbent cannot promote anything."
        )

    baseline = report.models[incumbent]
    baseline_cer = baseline.normalized_cer
    if baseline_cer is None:
        raise LookupError(
            f"{incumbent!r} produced no scored items in this run — every item failed, or "
            f"the corpus was empty. There is no baseline to beat."
        )

    reasons: list[str] = [
        f"incumbent {incumbent} normalized CER {baseline_cer:.4f} on "
        f"{baseline.scored_items} items ({report.hardware.host})"
    ]
    if report.provenance.interim:
        reasons.append(
            f"corpus {report.provenance.name!r} is INTERIM — a public stand-in, not your "
            f"audio. §8.1 justifies a swap on measurement on your own material, and §1 "
            f"forbids model changes without it. This run can show the harness works and "
            f"can surface a candidate worth testing properly; it cannot promote one."
        )
    # An incomplete corpus BLOCKS a switch rather than merely annotating one. §8.1's rule is
    # "a material accuracy gain on *your* audio", and a set missing dialects or hours is not
    # that audio. Previously this only appended a sentence and the promotion went ahead —
    # audit finding #2.
    coverage_blocks = not report.coverage.is_complete()
    if coverage_blocks:
        reasons.append(
            f"corpus does not satisfy §8.1 ({report.coverage.summary()}) — no model change "
            f"may rest on an incomplete labelled set"
        )

    best: tuple[str, float] | None = None
    for model_id, model in report.models.items():
        if model_id == incumbent:
            continue
        challenger_cer = model.normalized_cer
        if challenger_cer is None:
            reasons.append(f"{model_id}: no scored items, not considered")
            continue

        gain = (baseline_cer - challenger_cer) / baseline_cer if baseline_cer else 0.0
        if gain < MATERIAL_GAIN_RATIO:
            reasons.append(
                f"{model_id}: CER {challenger_cer:.4f} is a {gain:.1%} change against the "
                f"incumbent — not a material gain (threshold {MATERIAL_GAIN_RATIO:.0%})"
            )
            continue

        baseline_by_dialect = baseline.normalized_cer_by_dialect
        challenger_by_dialect = model.normalized_cer_by_dialect
        regressions = [
            f"{dialect.value} ({value:.4f} vs {baseline_by_dialect[dialect]:.4f})"
            for dialect, value in challenger_by_dialect.items()
            if dialect in baseline_by_dialect and value > baseline_by_dialect[dialect]
        ]
        # A dialect the incumbent scored and the challenger did NOT is the worst case, not
        # an absent one: the challenger failed every item in it. Skipping it let a model
        # that choked on all of Mukriyan be promoted on one Hewlêr item. Audit finding #2.
        regressions += [
            f"{dialect.value} (no score at all — failed every item)"
            for dialect in baseline_by_dialect
            if dialect not in challenger_by_dialect
        ]
        if regressions:
            reasons.append(
                f"{model_id}: gains {gain:.1%} overall but regresses in "
                f"{', '.join(regressions)} — §4.4 forbids trading a dialect for an average"
            )
            continue

        worst_rtf = model.worst_rtf
        if worst_rtf is not None and worst_rtf > max_rtf:
            reasons.append(
                f"{model_id}: gains {gain:.1%} but worst-case RTF {worst_rtf:.3f} exceeds "
                f"the acceptable throughput budget {max_rtf:.3f} on {report.hardware.host}"
            )
            continue

        reasons.append(
            f"{model_id}: CER {challenger_cer:.4f}, a {gain:.1%} gain, no dialect "
            f"regression, worst-case RTF {worst_rtf:.3f} within budget"
            if worst_rtf is not None
            else f"{model_id}: CER {challenger_cer:.4f}, a {gain:.1%} gain, no regression"
        )
        if best is None or challenger_cer < best[1]:
            best = (model_id, challenger_cer)

    if best is not None and coverage_blocks:
        reasons.append(
            f"{best[0]} outscores {incumbent} here, but the corpus is incomplete — "
            f"re-run on a §8.1-complete set before moving the pin."
        )
        return CanonicalDecision(incumbent, best[0], switch=False, reasons=tuple(reasons))

    if best is None:
        reasons.append(f"{incumbent} stays canonical")
        return CanonicalDecision(incumbent, None, switch=False, reasons=tuple(reasons))

    if report.provenance.interim:
        reasons.append(
            f"{best[0]} beats {incumbent} on this interim corpus and is worth benchmarking "
            f"on the real labelled set — but the pin does NOT move on interim evidence."
        )
        return CanonicalDecision(incumbent, best[0], switch=False, reasons=tuple(reasons))

    reasons.append(
        f"{best[0]} meets every clause of §8.1's rule — recommend replacing {incumbent}. "
        f"Record the numbers in DECISIONS.md before changing the pin."
    )
    return CanonicalDecision(incumbent, best[0], switch=True, reasons=tuple(reasons))
