"""Import a public Sorani corpus as an **interim** labelled set.

Authorised in `DECISIONS.md` D-012: use public data to exercise the harness end to end while
the real §8.1 set is assembled. That authorisation is narrow, and this module is written to
keep it narrow.

The governing rule is that the importer must be pessimistic about everything the source does
not actually state. Common Voice is read speech collected from volunteers: it has no §4.4
dialect label, no §8.1 recording-condition label, and no duration in its main TSV. Every one
of those has an obvious plausible default, and every one of those defaults would convert an
interim stand-in into a number somebody quotes six months from now:

* **Dialect stays `None`.** Not "hewler because most contributors are from Hewlêr".
* **Conditions stay empty.** Read speech is not "formal news", and labelling it so would fill
  a coverage cell that the audio cannot support.
* **Duration is required**, from `clip_durations.tsv` or not at all. A default clip length
  would fabricate both the real-time factor and the hours-of-coverage figure.
* **Locale is checked.** Kurmanji (`kmr`) and Farsi (`fa`) are one directory away in any
  Common Voice download, and importing either would silently poison every `ckb` number.

Reference text is stored exactly as the corpus wrote it. Normalizing on import would destroy
the very thing this data is most useful for right now — real evidence about how often the
§4.1 collisions occur in Kurdish that real people typed.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Final

from hawedit.corpus import Corpus, CorpusItem, Provenance

__all__ = [
    "COMMON_VOICE_LICENCE",
    "CorpusImportError",
    "MissingDurations",
    "WrongLocale",
    "import_common_voice",
]

# Common Voice's published licence. Recorded here rather than assumed at the call site so a
# licence audit has one place to look (D-002's rule: no dependency or data without one).
COMMON_VOICE_LICENCE: Final = "CC0-1.0"

_KURDISH_SORANI_LOCALE: Final = "ckb"


class CorpusImportError(ValueError):
    """Raised when a public corpus cannot be imported without inventing something."""


class MissingDurations(CorpusImportError):
    """Raised when clip durations are unavailable — RTF and hours would be fabricated."""


class WrongLocale(CorpusImportError):
    """Raised when the source data is not Central Kurdish."""


def _read_durations(path: Path) -> dict[str, float]:
    """Read Common Voice's `clip_durations.tsv` into seconds keyed by clip filename."""
    durations: dict[str, float] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            clip = (row.get("clip") or "").strip()
            raw = (row.get("duration[ms]") or "").strip()
            if not clip or not raw:
                continue
            durations[clip] = float(raw) / 1000.0
    return durations


def import_common_voice(
    tsv_path: Path,
    durations_path: Path | None,
    locale: str = _KURDISH_SORANI_LOCALE,
    limit: int | None = None,
    licence: str = COMMON_VOICE_LICENCE,
) -> Corpus:
    """Import a Common Voice split as an interim, unlabelled corpus.

    Args:
        tsv_path: a Common Voice split TSV (`validated.tsv`, `train.tsv`, …).
        durations_path: `clip_durations.tsv`. Required — see `MissingDurations`.
        locale: the expected locale. Rows with any other locale are refused.
        limit: import at most this many rows, for a quick smoke run.
        licence: the source's licence, recorded in the corpus provenance.

    Returns:
        A `Corpus` whose items are all unlabelled and whose provenance is marked interim,
        so `assert_section_8_1_coverage()` still fails and `bench.decide_canonical` still
        refuses to move the canonical pin.

    Raises:
        MissingDurations: no durations file, or a clip missing from it.
        WrongLocale: a row is not in the expected locale.
    """
    if durations_path is None:
        raise MissingDurations(
            "no clip_durations.tsv supplied. Common Voice's split TSVs carry no clip length, "
            "and inventing one would fabricate both the real-time factor and the "
            "hours-of-coverage figure. Supply the durations file from the same release."
        )
    durations = _read_durations(durations_path)

    items: list[CorpusItem] = []
    with tsv_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if limit is not None and len(items) >= limit:
                break

            row_locale = (row.get("locale") or "").strip()
            if row_locale and row_locale != locale:
                raise WrongLocale(
                    f"row for clip {row.get('path')!r} has locale {row_locale!r}, expected "
                    f"{locale!r}. Kurmanji and Farsi sit one directory away in any Common "
                    f"Voice download; importing either would poison every ckb number."
                )

            sentence = (row.get("sentence") or "").strip()
            clip = (row.get("path") or "").strip()
            if not sentence or not clip:
                # A clip with no validated sentence has no reference to score against.
                continue

            if clip not in durations:
                raise MissingDurations(
                    f"clip {clip!r} has no entry in {durations_path.name}. Every item needs a "
                    f"real duration; skipping it silently would quietly shrink the corpus, and "
                    f"defaulting it would fabricate a measurement."
                )

            items.append(
                CorpusItem(
                    item_id=Path(clip).stem,
                    audio_path=f"clips/{clip}",
                    # Raw, exactly as the contributor typed it (invariant #1's spirit).
                    reference_ckb=sentence,
                    dialect=None,
                    conditions=frozenset(),
                    duration_s=durations[clip],
                )
            )

    return Corpus(
        tuple(items),
        provenance=Provenance(
            name=f"Mozilla Common Voice {locale} ({tsv_path.name})",
            licence=licence,
            interim=True,
            note=(
                "Read speech from volunteer contributors. No §4.4 dialect labels and none of "
                "§8.1's recording conditions — no podcast, no overlapping speakers, no "
                "code-switch or named-entity annotation. Exercises the harness on real "
                "Kurdish; does not discharge M0."
            ),
        ),
    )
