"""Measure how often §4.1's encoding collisions occur in real Kurdish text.

§0 puts normalization first among the three things that decide whether this system works:
"Skip normalization and your search index silently fails to match text that looks identical
on screen." That is an assertion in a document. This module turns it into a number measured
on real Sorani, so §4.1's MANDATORY is backed by evidence from this project's own data
rather than by the blueprint's say-so.

The headline metric is `index_collision_rate`: the share of distinct raw forms that collapse
onto a form some *other* raw spelling also produces. That is the quantity §0 is describing —
each collapse is a pair of index entries that would never have matched each other, with
nothing visible on screen to explain why.

Occurrence counts are per item, not per character: an item containing four Arabic yehs is one
affected item. What matters is how many documents are wrong, not how many characters are.

Conjunctive `و` is deliberately absent from `COLLISIONS`. §4.1 lists it, KLPT does not
implement separation for it, and D-003 records that as a known gap — counting it here would
imply a measurement of something this system does not yet do.

The reverse also happened: measuring the real lexicon surfaced a collision §4.1 does **not**
list — U+06BE HEH DOACHASHMEE against U+0647 HEH — which KLPT does resolve, and which was
responsible for every merge found in a curated dictionary. See D-013.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Final

from hawedit.normalize import normalize_sorani

__all__ = ["COLLISIONS", "CollisionReport", "measure_collisions"]

_FARSI_DIGITS: Final = "۰۱۲۳۴۵۶۷۸۹"
_EASTERN_ARABIC_DIGITS: Final = "٠١٢٣٤٥٦٧٨٩"

# The §4.1 collisions KLPT's normalize() actually resolves (measured in D-003).
COLLISIONS: Final[Mapping[str, Callable[[str], bool]]] = {
    # AsoSoft replaces every "ه" + ZWNJ with Kurdish "ە". Both are everywhere in real text.
    "he_plus_zwnj": lambda t: "ه‌" in t,
    # Kurdish uses the Farsi forms; Arabic keyboards emit ي and ك.
    "arabic_yeh": lambda t: "ي" in t,
    "arabic_kaf": lambda t: "ك" in t,
    "farsi_numerals": lambda t: any(d in t for d in _FARSI_DIGITS),
    "eastern_arabic_numerals": lambda t: any(d in t for d in _EASTERN_ARABIC_DIGITS),
    # NOT in §4.1's table — found by measuring the real Sorani lexicon (D-013). U+06BE
    # HEH DOACHASHMEE against U+0647 HEH. KLPT resolves it, but only in word context: an
    # isolated "ھ" is left alone, so the detector counts the character wherever it appears
    # while the merge only happens where normalization actually fires.
    "heh_doachashmee": lambda t: "ھ" in t,
}


@dataclass(frozen=True, slots=True)
class CollisionReport:
    """What §4.1's collisions cost on a given body of Kurdish text."""

    total_items: int
    items_changed_by_normalization: int
    counts_by_collision: Mapping[str, int]
    distinct_raw: int
    distinct_normalized: int
    merged_groups: tuple[tuple[str, ...], ...]

    @property
    def changed_rate(self) -> float | None:
        """Share of items whose text is altered by normalization.

        `None` for an empty corpus — a rate over nothing is not zero.
        """
        if not self.total_items:
            return None
        return self.items_changed_by_normalization / self.total_items

    @property
    def index_collision_rate(self) -> float | None:
        """Share of distinct raw forms that normalization merges with another form.

        This is §0's failure mode as a number: without §4.1 these are pairs of index
        entries that look identical on screen and never match each other.
        """
        if not self.distinct_raw:
            return None
        return (self.distinct_raw - self.distinct_normalized) / self.distinct_raw

    def summary(self) -> str:
        if self.changed_rate is None or self.index_collision_rate is None:
            return "no items measured"
        parts = ", ".join(
            f"{name}={self.counts_by_collision[name]}" for name in sorted(self.counts_by_collision)
        )
        return (
            f"{self.total_items} items, {self.changed_rate:.2%} altered by normalization; "
            f"{self.distinct_raw} distinct raw forms -> {self.distinct_normalized} normalized "
            f"({self.index_collision_rate:.2%} would have failed to match); {parts}"
        )


def measure_collisions(texts: Iterable[str], sample_groups: int = 10) -> CollisionReport:
    """Measure §4.1 collision incidence across `texts`.

    Args:
        texts: raw Kurdish strings, exactly as written. Do not pre-normalize — that is the
            thing being measured.
        sample_groups: how many merged groups to keep as concrete examples for the report.
    """
    counts = dict.fromkeys(COLLISIONS, 0)
    total = 0
    changed = 0
    by_normalized: dict[str, set[str]] = {}

    for text in texts:
        total += 1
        for name, detector in COLLISIONS.items():
            if detector(text):
                counts[name] += 1
        normalized = normalize_sorani(text)
        if normalized != text:
            changed += 1
        by_normalized.setdefault(normalized, set()).add(text)

    merged = tuple(tuple(sorted(forms)) for forms in by_normalized.values() if len(forms) > 1)[
        :sample_groups
    ]

    return CollisionReport(
        total_items=total,
        items_changed_by_normalization=changed,
        counts_by_collision=counts,
        distinct_raw=len({t for forms in by_normalized.values() for t in forms}),
        distinct_normalized=len(by_normalized),
        merged_groups=merged,
    )
