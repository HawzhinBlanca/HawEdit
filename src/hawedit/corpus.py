"""The labelled Sorani audio set (§8.1) — its manifest, and the coverage it must satisfy.

§8.1 is titled "blocks everything", and what it asks for is not "several hours of Kurdish"
but several hours across a specific grid: three dialects (§4.4) crossed with seven recording
conditions. §4.4 explains why the grid cannot be collapsed — "A single aggregate CER hides
the dialect where the product is actually used" — and names heavy regional dialect and fast
conversational speech as the known weak spot of existing Sorani models. Averaging that away
is how a benchmark reports a good number for a product that fails in Slemani.

So this module treats coverage as a validated property, not a hope:

* item-level consistency is checked at construction — an item labelled ckb–English without
  annotated spans has an unmeasurable code-switch error, and D-008 forbids unmeasured
  reading as zero;
* `coverage()` reports duration **per dialect** and lists the missing (dialect, condition)
  cells by name;
* `assert_section_8_1_coverage()` refuses a corpus that leaves a cell empty or falls short
  on hours, and says which.

Reference transcripts are stored exactly as labelled. They are raw text (invariant #1);
normalization happens at scoring time, in `metrics`.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Final

from hawedit.transcripts import Word

__all__ = [
    "MINIMUM_HOURS",
    "Condition",
    "Corpus",
    "CorpusItem",
    "Coverage",
    "Dialect",
    "IncompleteCoverage",
    "InvalidCorpusItem",
    "Provenance",
]


class Dialect(Enum):
    """The three dialects §4.4 requires to be evaluated separately."""

    HEWLER = "hewler"
    SLEMANI = "slemani"
    MUKRIYAN = "mukriyan"


class Condition(Enum):
    """The recording conditions §8.1 enumerates."""

    FORMAL_NEWS = "formal_news"
    CASUAL_PODCAST = "casual_podcast"
    CODE_SWITCH_EN = "code_switch_en"
    CODE_SWITCH_AR = "code_switch_ar"
    NOISY = "noisy"
    OVERLAPPING_SPEAKERS = "overlapping_speakers"
    NAMED_ENTITIES = "named_entities"


# §8.1 asks for "several hours". Three is the smallest number "several" honestly describes,
# and it is a floor rather than a target — see DECISIONS.md D-009.
MINIMUM_HOURS: Final = 3.0

_CODE_SWITCH_CONDITIONS: Final = frozenset({Condition.CODE_SWITCH_EN, Condition.CODE_SWITCH_AR})


class InvalidCorpusItem(ValueError):
    """Raised when a labelled item is internally inconsistent — a corpus bug, not a result."""


class IncompleteCoverage(RuntimeError):
    """Raised when the labelled set does not cover what §8.1 requires."""


@dataclass(frozen=True, slots=True)
class CorpusItem:
    """One labelled audio item and everything needed to score it."""

    item_id: str
    audio_path: str
    reference_ckb: str
    # None means "not labelled for dialect". A public corpus does not carry §4.4's
    # Hewlêr/Slemani/Mukriyan split, and inventing one would be fabricated evidence — so
    # unlabelled items contribute hours and nothing else. See Provenance and D-012.
    dialect: Dialect | None
    conditions: frozenset[Condition]
    duration_s: float
    named_entities: tuple[str, ...] = ()
    code_switch_spans: tuple[str, ...] = ()
    speaker_count: int = 1
    # Optional: §8.1's alignment-accuracy metric needs reference word timings. Expensive to
    # annotate, so items without them simply do not contribute to that metric (None, not 0).
    reference_words: tuple[Word, ...] = ()

    def __post_init__(self) -> None:
        if not self.reference_ckb.strip():
            raise InvalidCorpusItem(
                f"{self.item_id}: empty reference transcript. Character error rate is "
                f"undefined without one — this item cannot be scored."
            )
        if self.duration_s <= 0:
            raise InvalidCorpusItem(
                f"{self.item_id}: duration_s must be positive; real-time factor and the "
                f"hours-of-coverage check both divide by it."
            )
        if self.dialect is not None and not self.conditions:
            raise InvalidCorpusItem(
                f"{self.item_id}: has a dialect but no condition. Half-labelled items fill "
                f"a coverage cell they cannot support — label both, or neither."
            )
        if self.dialect is None and self.conditions:
            raise InvalidCorpusItem(
                f"{self.item_id}: has conditions but no dialect. §4.4 scores per dialect, so "
                f"a condition with no dialect cannot be placed in the coverage grid — label "
                f"both, or neither."
            )
        if self.conditions & _CODE_SWITCH_CONDITIONS and not self.code_switch_spans:
            raise InvalidCorpusItem(
                f"{self.item_id}: labelled as code-switching but has no code_switch_spans. "
                f"§8.1 scores the switched spans specifically; without them the item's "
                f"code-switch error is unmeasurable, and unmeasured must not read as zero."
            )
        if Condition.NAMED_ENTITIES in self.conditions and not self.named_entities:
            raise InvalidCorpusItem(
                f"{self.item_id}: labelled for named entities but has no named_entities "
                f"annotated. §8.1 measures whether the names survived; nothing to check."
            )
        if Condition.OVERLAPPING_SPEAKERS in self.conditions and self.speaker_count < 2:
            raise InvalidCorpusItem(
                f"{self.item_id}: labelled overlapping_speakers with speaker_count="
                f"{self.speaker_count}. Overlap needs at least two speakers."
            )

    @property
    def is_labelled(self) -> bool:
        """True when this item can occupy a §8.1 coverage cell."""
        return self.dialect is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "audio_path": self.audio_path,
            "reference_ckb": self.reference_ckb,
            "dialect": self.dialect.value if self.dialect else None,
            "conditions": sorted(c.value for c in self.conditions),
            "duration_s": self.duration_s,
            "named_entities": list(self.named_entities),
            "code_switch_spans": list(self.code_switch_spans),
            "speaker_count": self.speaker_count,
            # §8.1's alignment metric depends on these. Omitting them from serialization
            # silently discarded the ground truth on every save/load round trip — audit #6.
            "reference_words": [
                {"w": w.w, "start_ms": w.start_ms, "end_ms": w.end_ms, "conf": w.conf}
                for w in self.reference_words
            ],
        }

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> CorpusItem:
        item_id = data.get("item_id", "<unnamed>")
        raw_dialect = data.get("dialect")
        try:
            dialect = Dialect(raw_dialect) if raw_dialect is not None else None
        except ValueError as exc:
            raise InvalidCorpusItem(
                f"{item_id}: unknown dialect {data['dialect']!r}. §4.4 evaluates Hewlêr, "
                f"Slemani and Mukriyan; a fourth needs a blueprint amendment, not a "
                f"manifest entry."
            ) from exc
        try:
            conditions = frozenset(Condition(c) for c in data["conditions"])
        except ValueError as exc:
            raise InvalidCorpusItem(
                f"{item_id}: unknown condition in {data['conditions']!r}"
            ) from exc
        return CorpusItem(
            item_id=item_id,
            audio_path=data["audio_path"],
            reference_ckb=data["reference_ckb"],
            dialect=dialect,
            conditions=conditions,
            duration_s=float(data["duration_s"]),
            named_entities=tuple(data.get("named_entities", ())),
            code_switch_spans=tuple(data.get("code_switch_spans", ())),
            speaker_count=int(data.get("speaker_count", 1)),
            reference_words=tuple(Word(**w) for w in data.get("reference_words", ())),
        )


@dataclass(frozen=True, slots=True)
class Provenance:
    """Where a corpus came from, and whether it may be treated as evidence.

    `interim=True` marks a stand-in — public data used to exercise the harness while the
    real labelled set is assembled. An interim corpus can prove the pipeline runs; it
    cannot justify a model change (§1: "No model changes without measurement", §8.1: on
    *your* audio), and `bench.decide_canonical` refuses to switch on one.
    """

    name: str
    licence: str
    interim: bool = False
    note: str = ""

    def __post_init__(self) -> None:
        if not self.licence.strip():
            raise ValueError(
                f"corpus {self.name!r} has no recorded licence. Every corpus entering this "
                f"system carries an audited licence — NonCommercial is a hard reject, and "
                f"'unknown' is not a licence."
            )


@dataclass(frozen=True, slots=True)
class Coverage:
    """What the labelled set actually covers, per dialect and per cell."""

    hours_by_dialect: Mapping[Dialect, float]
    items_by_dialect: Mapping[Dialect, int]
    missing_cells: tuple[tuple[Dialect, Condition], ...]
    labelled_hours: float
    unlabelled_hours: float
    meets_minimum_hours: bool

    @property
    def total_hours(self) -> float:
        return self.labelled_hours + self.unlabelled_hours

    def is_complete(self) -> bool:
        return not self.missing_cells and self.meets_minimum_hours

    def summary(self) -> str:
        per_dialect = ", ".join(f"{d.value}={self.hours_by_dialect[d]:.2f}h" for d in Dialect)
        unlabelled = (
            f", {self.unlabelled_hours:.2f}h unlabelled (counts toward nothing)"
            if self.unlabelled_hours
            else ""
        )
        return (
            f"{self.labelled_hours:.2f}h labelled ({per_dialect}){unlabelled}; "
            f"{len(self.missing_cells)} of {len(Dialect) * len(Condition)} cells empty"
        )


@dataclass(frozen=True, slots=True)
class Corpus:
    """The labelled Sorani set §8.1 calls for."""

    items: tuple[CorpusItem, ...] = field(default=())
    provenance: Provenance = field(
        default=Provenance(name="unnamed", licence="unrecorded — see DECISIONS.md")
    )

    def coverage(self) -> Coverage:
        hours: dict[Dialect, float] = {d: 0.0 for d in Dialect}
        counts: dict[Dialect, int] = {d: 0 for d in Dialect}
        populated: set[tuple[Dialect, Condition]] = set()
        unlabelled_hours = 0.0
        for item in self.items:
            if item.dialect is None:
                # Hours with no dialect cannot fill a §4.4 cell and must not count toward
                # the §8.1 minimum: five hours of unlabelled read speech is not five hours
                # of coverage. Tracked separately so it is visible, not discarded.
                unlabelled_hours += item.duration_s / 3600.0
                continue
            hours[item.dialect] += item.duration_s / 3600.0
            counts[item.dialect] += 1
            for condition in item.conditions:
                populated.add((item.dialect, condition))

        missing = tuple(
            (dialect, condition)
            for dialect in Dialect
            for condition in Condition
            if (dialect, condition) not in populated
        )
        labelled = sum(hours.values())
        return Coverage(
            hours_by_dialect=hours,
            items_by_dialect=counts,
            missing_cells=missing,
            labelled_hours=labelled,
            unlabelled_hours=unlabelled_hours,
            meets_minimum_hours=labelled >= MINIMUM_HOURS,
        )

    def assert_section_8_1_coverage(self) -> None:
        """Refuse a labelled set that cannot produce the numbers §8.1 asks for.

        Raises:
            IncompleteCoverage: a (dialect, condition) cell is empty, or the set is
                shorter than `MINIMUM_HOURS`. The message names what is missing —
                "incomplete" without the specifics is not actionable.
        """
        coverage = self.coverage()
        problems: list[str] = []
        if coverage.missing_cells:
            named = ", ".join(f"{d.value}/{c.value}" for d, c in coverage.missing_cells)
            problems.append(f"uncovered cells: {named}")
        if not coverage.meets_minimum_hours:
            problems.append(
                f"only {coverage.labelled_hours:.2f} hours labelled; §8.1 asks for several "
                f"(floor {MINIMUM_HOURS:.1f}h)"
            )
        if problems:
            raise IncompleteCoverage(
                "labelled set does not satisfy §8.1 — "
                + "; ".join(problems)
                + ". §4.4: a single aggregate hides the dialect the product is used in."
            )

    def by_dialect(self, dialect: Dialect) -> tuple[CorpusItem, ...]:
        return tuple(i for i in self.items if i.dialect is dialect)

    def missing_audio(self, root: Path) -> tuple[CorpusItem, ...]:
        """Items whose audio file is not on disk under `root`.

        Kept separate from schema validation on purpose: the manifest is authored before
        the audio is delivered, which is exactly the state M0.12 is blocked in.
        """
        return tuple(i for i in self.items if not (root / i.audio_path).exists())

    def to_json(self) -> str:
        return json.dumps(
            {
                "provenance": {
                    "name": self.provenance.name,
                    "licence": self.provenance.licence,
                    "interim": self.provenance.interim,
                    "note": self.provenance.note,
                },
                "items": [i.to_dict() for i in self.items],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )

    @staticmethod
    def from_items(items: Iterable[CorpusItem]) -> Corpus:
        return Corpus(tuple(items))

    @staticmethod
    def load(path: Path) -> Corpus:
        data: Mapping[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        raw_items: Sequence[Mapping[str, Any]] = data["items"]
        raw_provenance = data.get("provenance")
        provenance = (
            Provenance(
                name=raw_provenance["name"],
                licence=raw_provenance["licence"],
                interim=bool(raw_provenance.get("interim", False)),
                note=raw_provenance.get("note", ""),
            )
            if raw_provenance
            else Provenance(name="unnamed", licence="unrecorded — see DECISIONS.md")
        )
        return Corpus(tuple(CorpusItem.from_dict(i) for i in raw_items), provenance=provenance)
