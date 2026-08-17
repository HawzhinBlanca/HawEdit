"""Import a Sorani corpus this project did not label itself.

Two sources, one rule. `import_common_voice` was authorised in `DECISIONS.md` D-012: use
public data to exercise the harness end to end while the real §8.1 set is assembled.
`import_cortex_speech` reads a Cortex Speech Studio export — Hawa's own audio with
human-reviewed transcripts, which is `BLOCKED.md` #1's stated first preference (D-179).

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

The same pessimism governs the Cortex export, where one default would be far worse than any
of the above. Its writer **deliberately includes unverified ASR output** — `transcript_export`
drops only human-rejected clips and placeholders, on the reasoning that the owner wants their
whole working transcript. Read as `reference_ckb`, that scores OmniASR against OmniASR's own
output: the character error rate collapses toward zero and reads as a triumph. So only
human-verified records are imported, and the count that was left behind goes in the manifest
rather than into a log nobody reads.

Reference text is stored exactly as the corpus wrote it. Normalizing on import would destroy
the very thing this data is most useful for right now — real evidence about how often the
§4.1 collisions occur in Kurdish that real people typed. Cortex ships its own
`normalizedTranscript` under its own `normalizerVersion`; importing that would put a foreign
normalization into the artifact every index, embedding and model input reads (invariant #3).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Final

from hawedit.corpus import Corpus, CorpusItem, Provenance

__all__ = [
    "COMMON_VOICE_LICENCE",
    "CorpusImportError",
    "MissingDurations",
    "NoVerifiedTranscripts",
    "WrongLocale",
    "import_common_voice",
    "import_cortex_speech",
]

# Common Voice's published licence. Recorded here rather than assumed at the call site so a
# licence audit has one place to look (D-002's rule: no dependency or data without one).
COMMON_VOICE_LICENCE: Final = "CC0-1.0"

_KURDISH_SORANI_LOCALE: Final = "ckb"


class CorpusImportError(ValueError):
    """Raised when a public corpus cannot be imported without inventing something."""


class MissingDurations(CorpusImportError):
    """Raised when clip durations are unavailable — RTF and hours would be fabricated."""


class NoVerifiedTranscripts(CorpusImportError):
    """Raised when an export carries nothing a human confirmed.

    Distinct from an empty file: this one means records were present and every single
    reference in them is still machine output. Scoring against those measures the model
    against itself, so an empty result is the honest outcome and it is loud rather than
    quiet.
    """


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
    unusable = 0
    with tsv_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if limit is not None and len(items) >= limit:
                break

            row_locale = (row.get("locale") or "").strip()
            # The leading `row_locale and` used to skip this entirely for any row whose locale
            # was absent or blank — so a Kurmanji `validated.tsv` with no `locale` column, or
            # with the cell empty, imported clean and the manifest still declared
            # "Mozilla Common Voice ckb", because the provenance name is built from the
            # *parameter* and never from the data. Measured: two Kurmanji rows imported with
            # `reference_ckb='Ev pir bas e'` under a `ckb` provenance. An unreadable locale is
            # not "no objection" — it is the file failing to confirm the language this importer
            # is about to assert on its behalf. D-103.
            if row_locale != locale:
                raise WrongLocale(
                    f"row for clip {row.get('path')!r} has locale {row_locale!r}, expected "
                    f"{locale!r}. Kurmanji and Farsi sit one directory away in any Common "
                    f"Voice download; importing either would poison every ckb number. A blank "
                    f"or missing locale is refused for the same reason: the manifest asserts "
                    f"{locale!r}, so every row has to say so."
                )

            sentence = (row.get("sentence") or "").strip()
            clip = (row.get("path") or "").strip()
            if not sentence or not clip:
                # A clip with no validated sentence has no reference to score against. Skipped,
                # and **counted** — the count reaches the manifest below, exactly as the Cortex
                # importer's `unconfirmed` does. This module states the rule itself, in the
                # refusal it raises a few lines down for a missing duration: "skipping it
                # silently would quietly shrink the corpus". Measured before this counter
                # existed: a 4-row TSV with two unusable rows imported as 2 items with nothing
                # in the corpus, its provenance or its manifest saying so — and corpus size is
                # what §8.1's hours-of-coverage is computed from. D-188.
                unusable += 1
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
                f"Read speech from volunteer contributors. {unusable} row(s) skipped as "
                f"unusable — no validated sentence, or no clip path — so this corpus is "
                f"{len(items)} of {len(items) + unusable} rows read. Reported even at zero: "
                f"corpus size is what §8.1's hours-of-coverage divides, and a skip nothing "
                f"records shrinks it invisibly (D-188). No §4.4 dialect labels and none of "
                f"§8.1's recording conditions — no podcast, no overlapping speakers, no "
                f"code-switch or named-entity annotation. Exercises the harness on real "
                f"Kurdish; does not discharge M0."
            ),
        ),
    )


# Cortex Speech Studio's export is a JSON array of segment records in camelCase. Only the four
# fields this importer actually reads are named; the export carries ~27, and depending on ones
# it does not need would break on a schema change that costs nothing here.
_CORTEX_ID: Final = "id"
_CORTEX_AUDIO: Final = "audioPath"
_CORTEX_RAW: Final = "rawTranscript"
_CORTEX_DURATION_MS: Final = "durationMs"
# Two independent ways a record can carry a human's confirmation. `isGold` marks reference
# material; `verified` marks a reviewer having passed it. Either is a human; neither is the
# decoder.
_CORTEX_VERIFIED: Final = ("verified", "isGold")


def _is_human_confirmed(record: Any) -> bool:
    return any(bool(record.get(field)) for field in _CORTEX_VERIFIED)


def import_cortex_speech(
    export_path: Path,
    licence: str,
    limit: int | None = None,
) -> Corpus:
    """Import a Cortex Speech Studio export as an unlabelled corpus of real material.

    `BLOCKED.md` #1 asks first for "your own labelled material with reference transcripts".
    This is the first half of that: real Sorani audio whose transcripts a human confirmed.
    The second half — §4.4's dialect and §8.1's recording conditions — Cortex does not
    capture, so every item arrives unlabelled and the coverage check still refuses the set.

    Args:
        export_path: a Cortex export — a JSON array of segment records.
        licence: the licence covering *this material*, recorded in the provenance. No default
            and no guess: Common Voice has a published licence this module can name, a private
            export does not, and "unknown" is not a licence.
        limit: import at most this many confirmed records, for a quick smoke run.

    Returns:
        A `Corpus` of the human-confirmed records only, marked interim, so
        `assert_section_8_1_coverage()` still fails and `bench.decide_canonical` still refuses
        to move the canonical pin.

    Raises:
        CorpusImportError: the export is not a JSON array, a record is missing a field this
            importer reads, or a confirmed record carries no usable duration or transcript.
        NoVerifiedTranscripts: records were present and none of them was human-confirmed.
    """
    if not licence.strip():
        raise CorpusImportError(
            "no licence supplied for the Cortex export. Every corpus entering this system "
            "carries an audited licence, and a private export has none this module could "
            "look up — state it at the call site rather than letting it default."
        )

    raw = json.loads(export_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise CorpusImportError(
            f"{export_path.name} is a {type(raw).__name__}, not the JSON array of segment "
            f"records a Cortex export is. Reading a different shape would import whatever "
            f"happened to parse."
        )

    items: list[CorpusItem] = []
    unconfirmed = 0
    for record in raw:
        if not isinstance(record, dict):
            raise CorpusImportError(
                f"{export_path.name} contains a {type(record).__name__} where a segment "
                f"record was expected."
            )
        if not _is_human_confirmed(record):
            # Skipped, and counted — the count reaches the manifest below. Cortex exports
            # machine output on purpose; scoring against it would measure the decoder against
            # itself.
            unconfirmed += 1
            continue
        if limit is not None and len(items) >= limit:
            break

        identifier = str(record.get(_CORTEX_ID) or "").strip()
        audio = str(record.get(_CORTEX_AUDIO) or "").strip()
        reference = str(record.get(_CORTEX_RAW) or "").strip()
        duration_ms = record.get(_CORTEX_DURATION_MS)
        if not identifier or not audio:
            raise CorpusImportError(
                f"a confirmed record is missing {_CORTEX_ID!r} or {_CORTEX_AUDIO!r}: "
                f"{record.get(_CORTEX_ID)!r} / {record.get(_CORTEX_AUDIO)!r}. Both name the "
                f"thing being scored, so neither can be invented."
            )
        if not reference:
            # A *confirmed* record with no text is a corpus defect rather than a partial
            # review — a reviewer marked something that says nothing. Loud, not skipped.
            raise CorpusImportError(
                f"record {identifier!r} is marked human-confirmed and has an empty "
                f"{_CORTEX_RAW!r}. Character error rate is undefined without a reference; "
                f"fix the export rather than scoring it."
            )
        if not isinstance(duration_ms, int | float) or isinstance(duration_ms, bool):
            raise CorpusImportError(
                f"record {identifier!r} has {_CORTEX_DURATION_MS}={duration_ms!r}, which is "
                f"not a number. Real-time factor and the hours-of-coverage check both divide "
                f"by it, and a default would fabricate both."
            )

        items.append(
            CorpusItem(
                item_id=identifier,
                audio_path=audio,
                # Raw, exactly as the reviewer confirmed it. Cortex's own
                # `normalizedTranscript` is deliberately not read — see the module docstring.
                reference_ckb=reference,
                dialect=None,
                conditions=frozenset(),
                duration_s=duration_ms / 1000,
                # `reference_words` is left empty on purpose. Cortex aligns with
                # OmniASR-CTC-300M through sherpa-onnx; §7 pins the 3B, and invariant #5 says
                # word timings come from CTC Viterbi alignment only. §8.1's alignment metric
                # therefore scores none of these items — None, not 0.0.
            )
        )

    if not items:
        raise NoVerifiedTranscripts(
            f"{export_path.name} carries {unconfirmed} record(s) and not one is human-"
            f"confirmed. Cortex exports unverified decoder output by design, so importing it "
            f"as reference would score the model against its own transcript. Review the "
            f"segments in Cortex first."
        )

    return Corpus(
        tuple(items),
        provenance=Provenance(
            name=f"Cortex Speech Studio export ({export_path.name})",
            licence=licence,
            interim=True,
            note=(
                f"{len(items)} human-confirmed segment(s); {unconfirmed} unconfirmed record(s) "
                f"left behind. Real material, which is BLOCKED.md #1's first preference — but "
                f"Cortex captures no §4.4 dialect and none of §8.1's recording conditions, so "
                f"every item is unlabelled and fills no coverage cell. Interim until those "
                f"four labels are captured at review time: dialect, conditions, named_entities "
                f"and code_switch_spans."
            ),
        ),
    )
