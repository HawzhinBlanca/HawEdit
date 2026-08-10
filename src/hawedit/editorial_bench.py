"""Human-labelled Sorani editorial regression sets and their promotion report."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Final

from hawedit.cli import machine_readable_stdout, program_name, use_utf8_streams
from hawedit.corpus import Dialect
from hawedit.judge import (
    JUDGE_SHADOW,
    KURDISH_EDITORIAL_JUDGE,
    MIN_REGRESSION_ITEMS,
    JudgeDecision,
    JudgeVerdict,
    decide_judge,
)

__all__ = [
    "MIN_ITEMS_PER_DIALECT",
    "EditorialComparison",
    "EditorialRegressionReport",
    "EditorialRegressionSet",
    "Preference",
    "main",
]

MIN_ITEMS_PER_DIALECT: Final = 5


class Preference(Enum):
    INCUMBENT = "incumbent"
    SHADOW = "shadow"
    TIE = "tie"


@dataclass(frozen=True, slots=True)
class EditorialComparison:
    """One blind human comparison of two verdicts for the exact same Sorani footage."""

    item_id: str
    media_path: str
    dialect: Dialect
    incumbent: JudgeVerdict
    shadow: JudgeVerdict
    preference: Preference
    reviewers: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.item_id.strip() or not self.media_path.strip():
            raise ValueError("editorial comparison needs an item_id and media_path")
        if self.incumbent.judge != KURDISH_EDITORIAL_JUDGE:
            raise ValueError(
                f"{self.item_id}: incumbent verdict came from {self.incumbent.judge!r}, not "
                f"{KURDISH_EDITORIAL_JUDGE!r}"
            )
        if self.shadow.judge != JUDGE_SHADOW:
            raise ValueError(
                f"{self.item_id}: shadow verdict came from {self.shadow.judge!r}, not "
                f"{JUDGE_SHADOW!r}"
            )
        incumbent_span = (
            self.incumbent.candidate_id,
            self.incumbent.clip_in_ms,
            self.incumbent.clip_out_ms,
        )
        shadow_span = (
            self.shadow.candidate_id,
            self.shadow.clip_in_ms,
            self.shadow.clip_out_ms,
        )
        if incumbent_span != shadow_span:
            raise ValueError(
                f"{self.item_id}: judges evaluated different candidates/spans: "
                f"{incumbent_span!r} vs {shadow_span!r}"
            )
        named = tuple(name.strip() for name in self.reviewers if name.strip())
        if len(set(named)) < 2:
            raise ValueError(
                f"{self.item_id}: a real editorial comparison needs at least two named "
                "human reviewers"
            )

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> EditorialComparison:
        return EditorialComparison(
            item_id=str(data["item_id"]),
            media_path=str(data["media_path"]),
            dialect=Dialect(str(data["dialect"])),
            incumbent=JudgeVerdict.from_dict(dict(data["incumbent"])),
            shadow=JudgeVerdict.from_dict(dict(data["shadow"])),
            preference=Preference(str(data["preference"])),
            reviewers=tuple(str(value) for value in data["reviewers"]),
        )


@dataclass(frozen=True, slots=True)
class EditorialRegressionReport:
    set_name: str
    total_items: int
    preferences: Mapping[Preference, int]
    items_by_dialect: Mapping[Dialect, int]
    decision: JudgeDecision

    def to_dict(self) -> dict[str, object]:
        return {
            "set_name": self.set_name,
            "total_items": self.total_items,
            "preferences": {key.value: value for key, value in self.preferences.items()},
            "items_by_dialect": {key.value: value for key, value in self.items_by_dialect.items()},
            "decision": {
                "incumbent": self.decision.incumbent,
                "challenger": self.decision.challenger,
                "switch": self.decision.switch,
                "reasons": list(self.decision.reasons),
            },
        }


@dataclass(frozen=True, slots=True)
class EditorialRegressionSet:
    name: str
    authorized_by: str
    interim: bool
    items: tuple[EditorialComparison, ...]

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.authorized_by.strip():
            raise ValueError("editorial set needs a name and a recorded media authorization")
        ids = [item.item_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("editorial set contains duplicate item ids")

    def assert_real(self, media_root: Path) -> None:
        if self.interim:
            raise ValueError("an interim editorial set cannot be reported as production evidence")
        if len(self.items) < MIN_REGRESSION_ITEMS:
            raise ValueError(
                f"editorial set has {len(self.items)} items; the promotion floor is "
                f"{MIN_REGRESSION_ITEMS}"
            )
        counts = Counter(item.dialect for item in self.items)
        thin = [dialect.value for dialect in Dialect if counts[dialect] < MIN_ITEMS_PER_DIALECT]
        if thin:
            raise ValueError(
                f"editorial set has fewer than {MIN_ITEMS_PER_DIALECT} items for "
                f"dialect(s): {', '.join(thin)}"
            )
        missing = [
            item.item_id for item in self.items if not (media_root / item.media_path).is_file()
        ]
        if missing:
            raise FileNotFoundError(f"editorial source media is missing for item(s): {missing}")

    def evaluate(self, media_root: Path) -> EditorialRegressionReport:
        self.assert_real(media_root)
        preferences = Counter(item.preference for item in self.items)
        dialects = Counter(item.dialect for item in self.items)
        decision = decide_judge(
            incumbent_wins=preferences[Preference.INCUMBENT],
            shadow_wins=preferences[Preference.SHADOW],
            ties=preferences[Preference.TIE],
        )
        return EditorialRegressionReport(
            set_name=self.name,
            total_items=len(self.items),
            preferences=dict(preferences),
            items_by_dialect=dict(dialects),
            decision=decision,
        )

    @staticmethod
    def load(path: Path) -> EditorialRegressionSet:
        data: Mapping[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return EditorialRegressionSet(
            name=str(data["name"]),
            authorized_by=str(data["authorized_by"]),
            interim=bool(data.get("interim", False)),
            items=tuple(EditorialComparison.from_dict(item) for item in data["items"]),
        )


def main(argv: Sequence[str] | None = None) -> int:
    use_utf8_streams()
    parser = argparse.ArgumentParser(
        prog=program_name("hawedit.editorial_bench"),
        description="Validate and score a real human-labelled Sorani editorial regression set",
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--media-root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        # The same exposure `--json` had: this prints a document to a stream every library
        # it loads can also print to, and one of them does (D-119). The report owns stdout;
        # the rest goes to stderr, whether or not a dependency is noisy today.
        with machine_readable_stdout() as report_stream:
            report = EditorialRegressionSet.load(args.manifest).evaluate(args.media_root)
            payload = json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
            if args.output:
                if args.output.exists():
                    raise FileExistsError(f"refusing to overwrite benchmark report {args.output}")
                args.output.write_text(payload + "\n", encoding="utf-8")
            else:
                print(payload, file=report_stream)
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
