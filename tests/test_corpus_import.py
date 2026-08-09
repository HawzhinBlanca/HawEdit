"""M0.14 — importing a public Sorani corpus as an interim set.

Authorised deviation (D-012): use public data to exercise the harness while the real
labelled set is assembled. The import has to be *pessimistic* about what it does not know —
Common Voice has no dialect labels, no §8.1 condition labels, and no duration in its main
TSV. Filling any of those in with a plausible default is how an interim number turns into a
number somebody quotes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hawedit.corpus_import import MissingDurations, WrongLocale, import_common_voice

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
# ckb provenance. Found by the fourth adversarial pass. D-091.


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
