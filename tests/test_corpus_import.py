"""M0.14 — importing a public Sorani corpus as an interim set.

Authorised deviation (D-012): use public data to exercise the harness while the real
labelled set is assembled. The import has to be *pessimistic* about what it does not know —
Common Voice has no dialect labels, no §8.1 condition labels, and no duration in its main
TSV. Filling any of those in with a plausible default is how an interim number turns into a
number somebody quotes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hawedit.corpus_import import (
    CorpusImportError,
    MissingDurations,
    NoVerifiedTranscripts,
    WrongLocale,
    import_common_voice,
    import_cortex_speech,
)

# Real Sorani, written the way Common Voice contributors actually type it — note the
# Arabic yeh/kaf and ZWNJ forms that §4.1 exists to normalize.
ROWS = [
    ("common_voice_ckb_001.mp3", "ئه‌مه‌ زۆر باشه‌", "ckb"),
    ("common_voice_ckb_002.mp3", "كوردستان وڵاتێكی جوانه‌", "ckb"),
    ("common_voice_ckb_003.mp3", "ساڵی ۲۰۲۵ ساڵێكی گرنگ بوو", "ckb"),
]

HEADER = "client_id\tpath\tsentence\tup_votes\tdown_votes\tage\tgender\taccents\tlocale\tsegment"


def write_tsv(path: Path, rows: list[tuple[str, str, str]] = ROWS) -> Path:
    lines = [HEADER]
    for i, (clip, sentence, locale) in enumerate(rows):
        lines.append(f"cid{i}\t{clip}\t{sentence}\t2\t0\t\t\t\t{locale}\t")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_durations(path: Path, rows: list[tuple[str, str, str]] = ROWS) -> Path:
    lines = ["clip\tduration[ms]"]
    for clip, _, _ in rows:
        lines.append(f"{clip}\t5000")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_imported_items_are_unlabelled_not_guessed(tmp_path: Path) -> None:
    """Common Voice carries no dialect. Assigning one would be inventing the evidence
    §4.4 exists to protect."""
    corpus = import_common_voice(
        write_tsv(tmp_path / "validated.tsv"), write_durations(tmp_path / "clip_durations.tsv")
    )
    assert len(corpus.items) == 3
    for item in corpus.items:
        assert item.dialect is None
        assert item.conditions == frozenset()
        assert item.is_labelled is False


def test_the_corpus_is_marked_interim_with_its_licence(tmp_path: Path) -> None:
    corpus = import_common_voice(
        write_tsv(tmp_path / "validated.tsv"), write_durations(tmp_path / "clip_durations.tsv")
    )
    assert corpus.provenance.interim is True
    assert corpus.provenance.licence == "CC0-1.0"
    assert "ckb" in corpus.provenance.name


def test_an_interim_import_cannot_satisfy_section_8_1(tmp_path: Path) -> None:
    """The point of the whole exercise: this set exercises the harness, it does not
    discharge M0."""
    from hawedit.corpus import IncompleteCoverage

    corpus = import_common_voice(
        write_tsv(tmp_path / "validated.tsv"), write_durations(tmp_path / "clip_durations.tsv")
    )
    with pytest.raises(IncompleteCoverage):
        corpus.assert_section_8_1_coverage()
    assert corpus.coverage().labelled_hours == 0.0
    assert corpus.coverage().unlabelled_hours > 0.0


def test_reference_text_is_kept_exactly_as_the_corpus_wrote_it(tmp_path: Path) -> None:
    """Invariant #1's spirit: the reference is raw. Normalization happens at scoring time,
    and normalizing on import would destroy the §4.1 evidence this data carries."""
    corpus = import_common_voice(
        write_tsv(tmp_path / "validated.tsv"), write_durations(tmp_path / "clip_durations.tsv")
    )
    assert corpus.items[0].reference_ckb == "ئه‌مه‌ زۆر باشه‌"
    assert "‌" in corpus.items[0].reference_ckb, "the ZWNJ must survive the import"


def test_durations_are_required_not_assumed(tmp_path: Path) -> None:
    """No duration means no RTF and no hours. A default would be a fabricated measurement."""
    with pytest.raises(MissingDurations, match="clip_durations"):
        import_common_voice(write_tsv(tmp_path / "validated.tsv"), None)


def test_a_clip_with_no_duration_entry_is_refused(tmp_path: Path) -> None:
    partial = tmp_path / "clip_durations.tsv"
    write_durations(partial, ROWS[:2])
    with pytest.raises(MissingDurations, match="common_voice_ckb_003"):
        import_common_voice(write_tsv(tmp_path / "validated.tsv"), partial)


def test_durations_convert_from_milliseconds(tmp_path: Path) -> None:
    corpus = import_common_voice(
        write_tsv(tmp_path / "validated.tsv"), write_durations(tmp_path / "clip_durations.tsv")
    )
    assert corpus.items[0].duration_s == pytest.approx(5.0)


def test_a_non_kurdish_locale_is_refused(tmp_path: Path) -> None:
    """Importing Kurmanji or Farsi by accident would silently poison every ckb number."""
    rows = [("x.mp3", "این فارسی است", "fa")]
    with pytest.raises(WrongLocale, match="fa"):
        import_common_voice(
            write_tsv(tmp_path / "validated.tsv", rows),
            write_durations(tmp_path / "clip_durations.tsv", rows),
        )


def test_rows_without_a_sentence_are_skipped_not_imported_empty(tmp_path: Path) -> None:
    rows = [*ROWS, ("common_voice_ckb_004.mp3", "   ", "ckb")]
    corpus = import_common_voice(
        write_tsv(tmp_path / "validated.tsv", rows),
        write_durations(tmp_path / "clip_durations.tsv", rows),
    )
    assert len(corpus.items) == 3


def test_limit_takes_a_prefix(tmp_path: Path) -> None:
    corpus = import_common_voice(
        write_tsv(tmp_path / "validated.tsv"),
        write_durations(tmp_path / "clip_durations.tsv"),
        limit=2,
    )
    assert len(corpus.items) == 2


def test_audio_paths_point_into_the_clips_directory(tmp_path: Path) -> None:
    corpus = import_common_voice(
        write_tsv(tmp_path / "validated.tsv"), write_durations(tmp_path / "clip_durations.tsv")
    )
    assert corpus.items[0].audio_path == "clips/common_voice_ckb_001.mp3"


def test_the_imported_manifest_round_trips(tmp_path: Path) -> None:
    from hawedit.corpus import Corpus

    corpus = import_common_voice(
        write_tsv(tmp_path / "validated.tsv"), write_durations(tmp_path / "clip_durations.tsv")
    )
    out = tmp_path / "interim.json"
    out.write_text(corpus.to_json(), encoding="utf-8")
    assert Corpus.load(out) == corpus


# --- an unreadable locale is refused, not waved through -----------------------------------
#
# The check was `if row_locale and row_locale != locale:`. The leading truthiness clause skipped
# it for every row whose locale was absent or blank, so a Kurmanji `validated.tsv` with no
# `locale` column — or with the cell empty — imported clean, and the manifest still declared
# "Mozilla Common Voice ckb" because the provenance name is built from the *parameter* and never
# from the data. Measured: two Kurmanji rows imported as `reference_ckb='Ev pir bas e'` under a
# ckb provenance. Found by the fourth adversarial pass. D-103.


def _kurmanji_tsv(path: Path, *, locale_column: bool, blank: bool = False) -> Path:
    """A Kurmanji split whose locale is unreadable in one of the two real ways."""
    rows = [("common_voice_kmr_001.mp3", "Ev pir bas e"), ("common_voice_kmr_002.mp3", "Kurdistan")]
    if locale_column:
        header = (
            "client_id\tpath\tsentence\tup_votes\tdown_votes\tage\tgender\taccents\tlocale\tsegment"
        )
        body = [
            f"cid{i}\t{c}\t{s}\t2\t0\t\t\t\t{'' if blank else 'kmr'}\t"
            for i, (c, s) in enumerate(rows)
        ]
    else:
        header = "client_id\tpath\tsentence\tup_votes\tdown_votes\tage\tgender\taccents\tsegment"
        body = [f"cid{i}\t{c}\t{s}\t2\t0\t\t\t\t" for i, (c, s) in enumerate(rows)]
    path.write_text("\n".join([header, *body]) + "\n", encoding="utf-8")
    durations = path.parent / "clip_durations.tsv"
    durations.write_text(
        "clip\tduration[ms]\n" + "".join(f"{c}\t4000\n" for c, _ in rows), encoding="utf-8"
    )
    return path


def test_a_missing_locale_column_is_refused_not_assumed_kurdish(tmp_path: Path) -> None:
    """A file that never states its language cannot confirm the one the manifest asserts."""
    tsv = _kurmanji_tsv(tmp_path / "validated.tsv", locale_column=False)
    with pytest.raises(WrongLocale, match="blank or missing locale"):
        import_common_voice(tsv, tmp_path / "clip_durations.tsv")


def test_a_blank_locale_cell_is_refused(tmp_path: Path) -> None:
    tsv = _kurmanji_tsv(tmp_path / "validated.tsv", locale_column=True, blank=True)
    with pytest.raises(WrongLocale, match="blank or missing locale"):
        import_common_voice(tsv, tmp_path / "clip_durations.tsv")


def test_an_honest_ckb_split_still_imports(tmp_path: Path) -> None:
    """The control. Refusing every row would pass both tests above and import nothing ever.

    Also asserts the provenance, because the defect was that the manifest asserted a language the
    data never confirmed — so the two have to be checked together.
    """
    corpus = import_common_voice(
        write_tsv(tmp_path / "validated.tsv"),
        write_durations(tmp_path / "clip_durations.tsv"),
    )
    assert len(corpus.items) == len(ROWS)
    assert "ckb" in corpus.provenance.name


# --- D-179: the Cortex Speech Studio export --------------------------------------------------

# Fields named exactly as the real export writes them. Taken from a committed artifact in that
# repository (`manifests/real_audio_tests/…user_dataset_output.json`), not from its type
# declarations, so the shape here is one the tool has actually produced.
CONFIRMED = {
    "id": "9409cc07-f150-42ed-b853-1ffcaf10abee",
    "audioPath": "B7871-esv2-speech-89p.wav",
    "rawTranscript": "ئەمە دەقێکی ڕاستەقینەیە",
    "normalizedTranscript": "SOMETHING CORTEX NORMALIZED",
    "durationMs": 15_000,
    "speakerId": "SPEAKER_00",
    "verified": True,
    "isGold": False,
}
MACHINE_ONLY = {
    "id": "0000-unverified",
    "audioPath": "B7871-esv2-speech-89p.wav",
    "rawTranscript": "ئەمە دەرچووی ئامێرە",
    "durationMs": 4_000,
    "speakerId": "SPEAKER_00",
    "verified": False,
    "isGold": False,
}

A_LICENCE = "proprietary — Hawa's own recordings"


def write_export(path: Path, records: list[dict[str, object]]) -> Path:
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    return path


def test_unverified_records_are_not_imported_as_reference(tmp_path: Path) -> None:
    """The defect this importer exists to prevent.

    Cortex's `transcript_export` drops only human-rejected clips and placeholders — its own
    comment says the owner wants their whole working transcript, so **unverified decoder output
    is included by design**, and the committed sample artifact carries `"verified": false`.
    Imported as `reference_ckb`, that scores OmniASR against OmniASR's own transcript: CER
    collapses toward zero and reads as a triumph, and every §3 Stage 1 escalation threshold and
    M7 quality gate is derived from it. D-179.
    """
    export = write_export(tmp_path / "export.json", [CONFIRMED, MACHINE_ONLY])
    corpus = import_cortex_speech(export, licence=A_LICENCE)

    assert [item.item_id for item in corpus.items] == [CONFIRMED["id"]]
    assert all(item.reference_ckb != MACHINE_ONLY["rawTranscript"] for item in corpus.items)


def test_a_confirmed_record_is_imported(tmp_path: Path) -> None:
    """The control. Without it the test above passes for an importer that imports nothing,
    and "no unverified data got in" would be true by refusing everything."""
    export = write_export(tmp_path / "export.json", [CONFIRMED, MACHINE_ONLY])
    corpus = import_cortex_speech(export, licence=A_LICENCE)

    (item,) = corpus.items
    assert item.reference_ckb == CONFIRMED["rawTranscript"]
    assert item.audio_path == CONFIRMED["audioPath"]
    assert item.duration_s == 15.0, "durationMs must arrive as seconds"


def test_gold_counts_as_human_confirmation(tmp_path: Path) -> None:
    """Two independent doors: a reviewer passing a segment, and it being reference material.

    Checked separately because an importer keyed on `verified` alone would silently drop every
    gold segment — the *most* trustworthy records in the export.
    """
    gold = {**MACHINE_ONLY, "id": "gold-1", "verified": False, "isGold": True}
    corpus = import_cortex_speech(write_export(tmp_path / "e.json", [gold]), licence=A_LICENCE)
    assert [item.item_id for item in corpus.items] == ["gold-1"]


# The two refusals below were held by nothing — measured by neutralising each in a shadow copy of
# src/hawedit and running this file with tests/test_corpus.py and tests/test_review_findings.py.


def test_a_record_that_is_not_an_object_is_refused(tmp_path: Path) -> None:
    """The export is a JSON array whose entries this importer reads with `.get`.

    A bare string or number where a record belongs is a different export format, and `.get` on
    it raises AttributeError several lines later — a stack trace about a missing attribute
    rather than a statement about the file. §8.1's corpus is what every ASR number is scored
    against, so "this is not the export you think it is" has to be said in those words.
    """
    export = write_export(tmp_path / "e.json", [{**MACHINE_ONLY, "verified": True}])
    export.write_text(
        json.dumps([{**MACHINE_ONLY, "verified": True}, "not-a-record"], ensure_ascii=False),
        encoding="utf-8",
    )
    with pytest.raises(CorpusImportError, match="where a segment record was expected"):
        import_cortex_speech(export, licence=A_LICENCE)


def test_a_confirmed_record_missing_its_id_or_audio_is_refused(tmp_path: Path) -> None:
    """ "Both name the thing being scored, so neither can be invented."

    An item with no id cannot be matched against a hypothesis, and one with no audio path names
    no recording to decode. Either would enter the corpus as an item that quietly measures
    nothing, and §8.1's whole point is that the number carries what produced it.
    """
    for field in ("id", "audioPath"):
        record = {**MACHINE_ONLY, "verified": True, field: "   "}
        export = write_export(tmp_path / f"e-{field}.json", [record])
        with pytest.raises(CorpusImportError, match="is missing"):
            import_cortex_speech(export, licence=A_LICENCE)


def test_an_export_with_nothing_confirmed_is_refused_loudly(tmp_path: Path) -> None:
    """An empty corpus would be the quiet version of the same answer.

    `Corpus` is happy to hold nothing, and a caller measuring an empty set gets no items and no
    complaint. The refusal names the count so the operator knows the export was read correctly
    and simply has not been reviewed yet.
    """
    export = write_export(tmp_path / "export.json", [MACHINE_ONLY, {**MACHINE_ONLY, "id": "b"}])
    with pytest.raises(NoVerifiedTranscripts, match="not one is human-confirmed"):
        import_cortex_speech(export, licence=A_LICENCE)


def test_imported_items_are_unlabelled_so_coverage_still_refuses(tmp_path: Path) -> None:
    """Cortex captures no §4.4 dialect and none of §8.1's conditions.

    The importer must not invent them — and the consequence has to stay visible: an unlabelled
    item fills no coverage cell, so the set cannot discharge M0 however many hours it holds.
    """
    corpus = import_cortex_speech(write_export(tmp_path / "e.json", [CONFIRMED]), licence=A_LICENCE)
    (item,) = corpus.items
    assert item.dialect is None
    assert item.conditions == frozenset()
    assert not item.is_labelled
    assert corpus.provenance.interim, "an unlabelled set must not read as evidence for a switch"


def test_cortex_own_normalization_is_not_imported(tmp_path: Path) -> None:
    """Invariant #3: every index, embedding and model input reads *this* project's normalized
    form. Cortex ships its own under its own `normalizerVersion`.

    The fixture makes the two impossible to confuse — importing the wrong field would put
    `SOMETHING CORTEX NORMALIZED` into the reference, which no CER against Kurdish could
    survive quietly.
    """
    corpus = import_cortex_speech(write_export(tmp_path / "e.json", [CONFIRMED]), licence=A_LICENCE)
    (item,) = corpus.items
    assert item.reference_ckb == CONFIRMED["rawTranscript"]
    assert str(CONFIRMED["normalizedTranscript"]) not in item.reference_ckb


def test_reference_word_timings_are_not_imported(tmp_path: Path) -> None:
    """Invariant #5: word timings come from CTC Viterbi alignment only.

    Cortex aligns with OmniASR-CTC-300M through sherpa-onnx and §7 pins the 3B — a different
    model at a different tier. §8.1's alignment metric therefore scores none of these items,
    which is `None` rather than `0.0`, and importing the timings anyway would put a foreign
    aligner's output behind an invariant that names one.
    """
    with_alignment = {**CONFIRMED, "alignmentJson": '{"source_start_ms":0,"source_end_ms":15000}'}
    corpus = import_cortex_speech(
        write_export(tmp_path / "e.json", [with_alignment]), licence=A_LICENCE
    )
    (item,) = corpus.items
    assert item.reference_words == ()


def test_the_manifest_records_what_was_left_behind(tmp_path: Path) -> None:
    """ "Skipped silently" is how a corpus quietly shrinks — D-091's lesson on this same module.

    The unconfirmed count belongs in the artifact a reader opens, not in a log line.
    """
    records = [CONFIRMED] + [{**MACHINE_ONLY, "id": f"m{i}"} for i in range(3)]
    corpus = import_cortex_speech(write_export(tmp_path / "e.json", records), licence=A_LICENCE)
    assert "3 unconfirmed" in corpus.provenance.note
    assert "1 human-confirmed" in corpus.provenance.note


def test_a_licence_must_be_supplied(tmp_path: Path) -> None:
    """Common Voice has a published licence this module can name; a private export does not.

    The hard rule is never to guess one, so there is deliberately no default to fall back on.
    """
    export = write_export(tmp_path / "e.json", [CONFIRMED])
    with pytest.raises(CorpusImportError, match="no licence supplied"):
        import_cortex_speech(export, licence="   ")


def test_a_confirmed_record_without_a_usable_duration_is_refused(tmp_path: Path) -> None:
    """Real-time factor and hours-of-coverage both divide by it."""
    export = write_export(tmp_path / "e.json", [{**CONFIRMED, "durationMs": None}])
    with pytest.raises(CorpusImportError, match="not a number"):
        import_cortex_speech(export, licence=A_LICENCE)


def test_a_confirmed_record_with_no_transcript_is_refused_not_skipped(tmp_path: Path) -> None:
    """A reviewer marked something that says nothing — a defect in the export, not a partial
    review, so it is loud rather than dropped."""
    export = write_export(tmp_path / "e.json", [{**CONFIRMED, "rawTranscript": "  "}])
    with pytest.raises(CorpusImportError, match="empty"):
        import_cortex_speech(export, licence=A_LICENCE)


def test_a_file_that_is_not_an_array_of_records_is_refused(tmp_path: Path) -> None:
    """The control against reading whatever happens to parse."""
    path = tmp_path / "e.json"
    path.write_text(json.dumps({"segments": [CONFIRMED]}), encoding="utf-8")
    with pytest.raises(CorpusImportError, match="not the JSON array"):
        import_cortex_speech(path, licence=A_LICENCE)


# --- D-188: the Common Voice import shrank the corpus without saying so ---------------------


def test_rows_skipped_as_unusable_are_counted_into_the_manifest(tmp_path: Path) -> None:
    """This module states the rule in its own refusal for a missing duration — "skipping it
    silently would quietly shrink the corpus" — and the Cortex importer next door obeys it by
    counting `unconfirmed` into the manifest. This path did not.

    Measured before the counter existed: a 4-row TSV with two unusable rows imported as 2 items
    with nothing in the corpus, its provenance or its manifest saying so. Corpus size is what
    §8.1's hours-of-coverage divides.
    """
    rows = [
        *ROWS,
        ("common_voice_ckb_004.mp3", "", "ckb"),  # validated clip, no sentence
        ("common_voice_ckb_005.mp3", "   ", "ckb"),  # whitespace only
    ]
    corpus = import_common_voice(
        write_tsv(tmp_path / "validated.tsv", rows),
        write_durations(tmp_path / "clip_durations.tsv", rows),
    )

    assert len(corpus.items) == len(ROWS), "the unusable rows must not become items"

    note = " ".join(corpus.provenance.note.split())
    assert "2 row(s) skipped as unusable" in note, note
    assert f"{len(ROWS)} of {len(rows)} rows read" in note, note


def test_a_clean_import_reports_zero_skipped_rather_than_omitting_it(tmp_path: Path) -> None:
    """The control, and D-110's rule: a line that appears only when something was skipped
    cannot be told from an import that does not count skips at all."""
    corpus = import_common_voice(
        write_tsv(tmp_path / "validated.tsv"),
        write_durations(tmp_path / "clip_durations.tsv"),
    )

    note = " ".join(corpus.provenance.note.split())
    assert "0 row(s) skipped as unusable" in note, note
    assert f"{len(ROWS)} of {len(ROWS)} rows read" in note, note
