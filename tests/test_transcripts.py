"""M0.4 — Kurdish invariants #1 and #3, asserted in code rather than documented.

    #1  transcript.raw.json is never mutated after write. Test this explicitly.
    #3  Indexes, embeddings and model inputs read transcript.norm.json — never raw.

§4.1 puts it plainly: "If you find yourself editing the raw transcript in place, stop —
you've introduced a bug you cannot detect later." So the point of these tests is to make it
detectable: the API refuses, the type system refuses, and a checksum catches whatever gets
past both.
"""

from __future__ import annotations

import importlib
import json
import os
import stat
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path
from threading import Barrier, Event
from types import SimpleNamespace

import pytest

from hawedit.registry import ModelExcluded, ModelNotInRegistry
from hawedit.transcripts import (
    AsrProvenance,
    NormalizedTranscript,
    RawTranscript,
    RawTranscriptImmutable,
    RawTranscriptTampered,
    SegmentConfidence,
    StaleNormalizedTranscript,
    TranscriptStore,
    UnalignedSpeech,
    Word,
    assert_model_input,
    normalize_transcript,
    validate_media_id,
)

CANONICAL = AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi")


def a_raw(text: str = "ئه‌مه‌ زۆر باشه‌") -> RawTranscript:
    surface = "ئه‌مه‌"
    return RawTranscript(
        media_id="media-001",
        text_ckb=text,
        words=(Word(w=surface, start_ms=84600, end_ms=84920, conf=0.97),)
        if surface in text
        else (),
        asr=CANONICAL,
    )


@pytest.mark.parametrize(
    "unsafe",
    [
        "",
        "../escape",
        "a/b",
        "a\\b",
        "clip:one",
        "NUL",
        "COM1.json",
        " trailing",
        ".hidden",
        "a" * 181,
    ],
)
def test_media_ids_are_refused_before_they_can_become_paths(unsafe: str) -> None:
    with pytest.raises(ValueError, match="media_id"):
        validate_media_id(unsafe)


def test_sorani_and_spaces_inside_a_media_id_remain_legal() -> None:
    assert validate_media_id("هەوا episode-12") == "هەوا episode-12"


def test_transcript_store_refuses_a_symlink_root_before_any_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_lstat = os.lstat

    def symlink_root(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
    ) -> os.stat_result:
        result = real_lstat(path)
        if Path(os.fsdecode(path)) == tmp_path:
            values = list(result)
            values[0] = stat.S_IFLNK | 0o777
            return os.stat_result(values)
        return result

    monkeypatch.setattr(os, "lstat", symlink_root)
    with pytest.raises(RuntimeError, match="root must be.*symlink"):
        TranscriptStore(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_transcript_store_refuses_a_windows_reparse_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_lstat = os.lstat

    def reparse_root(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
    ) -> object:
        result = real_lstat(path)
        if Path(os.fsdecode(path)) != tmp_path:
            return result
        return SimpleNamespace(
            st_mode=result.st_mode,
            st_dev=result.st_dev,
            st_ino=result.st_ino,
            st_file_attributes=0x400,
        )

    monkeypatch.setattr(os, "lstat", reparse_root)
    with pytest.raises(RuntimeError, match="root must be.*reparse"):
        TranscriptStore(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_transcript_store_refuses_a_replaced_root_before_publication(tmp_path: Path) -> None:
    root = tmp_path / "store"
    store = TranscriptStore(root)
    displaced = tmp_path / "displaced"
    root.rename(displaced)
    root.mkdir()

    with pytest.raises(RuntimeError, match="root changed identity"):
        store.write_raw(a_raw())

    assert list(root.iterdir()) == []
    assert list(displaced.iterdir()) == []


# --- invariant #1: raw is written once and never mutated ------------------------------


def test_writing_raw_twice_is_refused(tmp_path: Path) -> None:
    store = TranscriptStore(tmp_path)
    store.write_raw(a_raw())
    with pytest.raises(RawTranscriptImmutable):
        store.write_raw(a_raw("something else entirely"))


def test_rewriting_raw_with_identical_content_is_still_refused(tmp_path: Path) -> None:
    """ "Never modified" is about the write path, not about whether the bytes differ.

    Allowing an idempotent-looking rewrite is how in-place editing sneaks in later.
    """
    store = TranscriptStore(tmp_path)
    store.write_raw(a_raw())
    with pytest.raises(RawTranscriptImmutable):
        store.write_raw(a_raw())


def test_refused_rewrite_does_not_replace_the_existing_digest(tmp_path: Path) -> None:
    """The immutable raw and its tamper-evidence sidecar are one write-once artifact."""
    store = TranscriptStore(tmp_path)
    store.write_raw(a_raw())
    sidecar = tmp_path / "media-001.transcript.raw.sha256"
    recorded = sidecar.read_bytes()

    with pytest.raises(RawTranscriptImmutable):
        store.write_raw(a_raw("different ASR output"))

    assert sidecar.read_bytes() == recorded
    assert store.read_raw("media-001") == a_raw()
    store.verify_raw_integrity("media-001")


def test_competing_writers_publish_one_matching_raw_and_digest(tmp_path: Path) -> None:
    store = TranscriptStore(tmp_path)
    contenders = (
        RawTranscript(media_id="race", text_ckb="first", words=(), asr=CANONICAL),
        RawTranscript(media_id="race", text_ckb="second", words=(), asr=CANONICAL),
    )
    barrier = Barrier(len(contenders))

    def attempt(raw: RawTranscript) -> str | None:
        barrier.wait()
        try:
            store.write_raw(raw)
        except RawTranscriptImmutable:
            return None
        return raw.text_ckb

    with ThreadPoolExecutor(max_workers=len(contenders)) as pool:
        results = tuple(pool.map(attempt, contenders))

    winners = tuple(result for result in results if result is not None)
    assert len(winners) == 1
    assert store.read_raw("race").text_ckb == winners[0]
    store.verify_raw_integrity("race")


def test_losing_writer_cannot_observe_digest_before_raw_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pipeline loser reads immediately after RawTranscriptImmutable; that must be safe."""
    store = TranscriptStore(tmp_path)
    winner = RawTranscript(media_id="race", text_ckb="first", words=(), asr=CANONICAL)
    loser = RawTranscript(media_id="race", text_ckb="second", words=(), asr=CANONICAL)
    digest_path = tmp_path / "race.transcript.raw.sha256"
    digest_published = Event()
    permit_raw_publication = Event()
    real_link = os.link

    def gated_link(source: Path, destination: Path) -> None:
        real_link(source, destination)
        if Path(destination) == digest_path and not digest_published.is_set():
            digest_published.set()
            assert permit_raw_publication.wait(timeout=5)

    monkeypatch.setattr(os, "link", gated_link)
    with ThreadPoolExecutor(max_workers=2) as pool:
        winning_write = pool.submit(store.write_raw, winner)
        assert digest_published.wait(timeout=5)
        losing_write = pool.submit(store.write_raw, loser)
        try:
            with pytest.raises(FutureTimeoutError):
                losing_write.result(timeout=0.05)
        finally:
            permit_raw_publication.set()

        assert winning_write.result(timeout=5) == store.raw_path("race")
        with pytest.raises(RawTranscriptImmutable):
            losing_write.result(timeout=5)

    assert store.read_raw("race") == winner
    store.verify_raw_integrity("race")


def test_an_orphan_digest_is_reported_as_interrupted_publication(tmp_path: Path) -> None:
    store = TranscriptStore(tmp_path)
    (tmp_path / "media-001.transcript.raw.sha256").write_text("0" * 64, encoding="ascii")

    with pytest.raises(RawTranscriptTampered, match="publication was interrupted"):
        store.read_raw("media-001")
    with pytest.raises(RawTranscriptTampered, match="missing while its write-once digest"):
        store.verify_raw_integrity("media-001")


def test_windows_lock_retries_contention_instead_of_using_crt_short_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hawedit.transcripts as transcript_module

    class FakeMsvcrt:
        LK_NBLCK = 1
        LK_UNLCK = 2

        def __init__(self) -> None:
            self.attempts = 0
            self.unlocked = False

        def locking(self, _fd: int, mode: int, _count: int) -> None:
            if mode == self.LK_UNLCK:
                self.unlocked = True
                return
            self.attempts += 1
            if self.attempts < 3:
                raise OSError("lock held")

    fake = FakeMsvcrt()
    real_import = importlib.import_module
    monkeypatch.setattr("hawedit.transcripts._WINDOWS_HOST", True)
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda name: fake if name == "msvcrt" else real_import(name),
    )

    with transcript_module._exclusive_file_lock(tmp_path / "retry.lock"):
        assert fake.attempts == 3
    assert fake.unlocked


@pytest.mark.parametrize("body_fails", (False, True))
def test_transcript_unlock_failure_is_normalized_without_masking_the_body(
    body_fails: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hawedit.transcripts as transcript_module

    class FailingUnlock:
        LK_NBLCK = 1
        LK_UNLCK = 2

        def locking(self, _fd: int, mode: int, _count: int) -> None:
            if mode == self.LK_UNLCK:
                raise OSError("unlock failed")

    fake = FailingUnlock()
    real_import = importlib.import_module
    monkeypatch.setattr("hawedit.transcripts._WINDOWS_HOST", True)
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda name: fake if name == "msvcrt" else real_import(name),
    )

    expected = LookupError if body_fails else RuntimeError
    message = "body failed" if body_fails else "cannot release transcript"
    with (
        pytest.raises(expected, match=message),
        transcript_module._exclusive_file_lock(tmp_path / f"unlock-{body_fails}.lock"),
    ):
        if body_fails:
            raise LookupError("body failed")


def test_a_hardlinked_transcript_lock_cannot_modify_its_other_name(tmp_path: Path) -> None:
    store = TranscriptStore(tmp_path)
    victim = tmp_path / "victim"
    victim.write_bytes(b"")
    os.link(victim, tmp_path / ".media-001.transcript.raw.lock")

    with pytest.raises(RuntimeError, match="one regular link"):
        store.write_raw(a_raw())
    assert victim.read_bytes() == b""


def test_a_symlinked_transcript_lock_is_refused_before_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = TranscriptStore(tmp_path)
    lock = tmp_path / ".media-001.transcript.raw.lock"
    real_lstat = os.lstat

    def fake_lstat(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
    ) -> os.stat_result:
        result = real_lstat(tmp_path)
        if Path(os.fsdecode(path)) == lock:
            values = list(result)
            values[0] = stat.S_IFLNK | 0o777
            return os.stat_result(values)
        return result

    monkeypatch.setattr(os, "lstat", fake_lstat)
    with pytest.raises(RuntimeError, match="symlink"):
        store.write_raw(a_raw())


def test_a_reparse_transcript_lock_is_refused_before_modification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = TranscriptStore(tmp_path)
    lock = tmp_path / ".media-001.transcript.raw.lock"
    lock.write_bytes(b"do-not-touch")
    real_lstat = os.lstat

    def fake_lstat(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
    ) -> object:
        result = real_lstat(path)
        if Path(os.fsdecode(path)) != lock:
            return result
        return SimpleNamespace(
            st_mode=result.st_mode,
            st_nlink=result.st_nlink,
            st_dev=result.st_dev,
            st_ino=result.st_ino,
            st_file_attributes=0x400,
        )

    monkeypatch.setattr(os, "lstat", fake_lstat)
    with pytest.raises(RuntimeError, match="reparse"):
        store.write_raw(a_raw())
    assert lock.read_bytes() == b"do-not-touch"


def test_raw_file_is_marked_read_only(tmp_path: Path) -> None:
    """Defence in depth, not a guarantee: root ignores the mode bits (see the module docs)."""
    store = TranscriptStore(tmp_path)
    path = store.write_raw(a_raw())
    assert stat.S_IMODE(path.stat().st_mode) == 0o444


def test_tampering_with_raw_on_disk_is_detected(tmp_path: Path) -> None:
    """The honest boundary: permissions can be bypassed, so integrity is checksum-based."""
    store = TranscriptStore(tmp_path)
    path = store.write_raw(a_raw())
    store.verify_raw_integrity("media-001")  # clean

    path.chmod(0o644)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["text_ckb"] = "quietly edited"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RawTranscriptTampered):
        store.verify_raw_integrity("media-001")


def test_byte_only_tampering_with_raw_is_detected(tmp_path: Path) -> None:
    """Equivalent parsed JSON is still a mutation of the canonical file's exact bytes."""
    store = TranscriptStore(tmp_path)
    path = store.write_raw(a_raw())
    path.chmod(0o644)
    path.write_bytes(path.read_bytes() + b"\n")

    # Parsing and canonical re-serialization would erase this edit and miss the mutation.
    assert store.read_raw("media-001") == a_raw()
    with pytest.raises(RawTranscriptTampered):
        store.verify_raw_integrity("media-001")


@pytest.mark.parametrize(
    ("w", "start_ms", "end_ms", "conf", "message"),
    [
        ("", 0, 1, 0.5, "surface form"),
        ("   ", 0, 1, 0.5, "surface form"),
        ("word", -1, 1, 0.5, "non-negative"),
        ("word", 1, 1, 0.5, "after start"),
        ("word", 2, 1, 0.5, "after start"),
        ("word", 0, 1, -0.01, "probability"),
        ("word", 0, 1, 1.01, "probability"),
        ("word", 0, 1, float("nan"), "probability"),
    ],
)
def test_invalid_word_data_is_refused(
    w: str, start_ms: int, end_ms: int, conf: float, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        Word(w=w, start_ms=start_ms, end_ms=end_ms, conf=conf)


def test_non_integer_word_timing_is_refused() -> None:
    with pytest.raises(ValueError, match="integer milliseconds"):
        Word(w="word", start_ms=0.5, end_ms=1, conf=0.5)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "words",
    [
        (
            Word(w="first", start_ms=100, end_ms=300, conf=0.9),
            Word(w="second", start_ms=250, end_ms=400, conf=0.9),
        ),
        (
            Word(w="first", start_ms=500, end_ms=600, conf=0.9),
            Word(w="second", start_ms=100, end_ms=200, conf=0.9),
        ),
    ],
)
def test_raw_transcript_refuses_overlapping_or_out_of_order_words(
    words: tuple[Word, ...],
) -> None:
    with pytest.raises(ValueError, match="chronological and non-overlapping"):
        RawTranscript(
            media_id="invalid-order",
            text_ckb="first second",
            words=words,
            asr=CANONICAL,
        )


def test_raw_transcript_refuses_a_word_absent_from_the_asr_text() -> None:
    with pytest.raises(ValueError, match="does not appear"):
        RawTranscript(
            media_id="mismatch",
            text_ckb="the ASR emitted this",
            words=(Word(w="invented", start_ms=0, end_ms=100, conf=0.9),),
            asr=CANONICAL,
        )


def test_raw_transcript_allows_partial_but_ordered_alignment() -> None:
    raw = RawTranscript(
        media_id="partial",
        text_ckb="one unaligned two trailing",
        words=(
            Word(w="one", start_ms=0, end_ms=100, conf=0.9),
            Word(w="two", start_ms=200, end_ms=300, conf=0.8),
        ),
        asr=CANONICAL,
    )
    assert tuple(word.w for word in raw.words) == ("one", "two")


def test_raw_transcript_allows_ctc_and_asr_punctuation_to_differ() -> None:
    raw = RawTranscript(
        media_id="punctuation",
        text_ckb="first second continues",
        words=(
            Word(w="first", start_ms=0, end_ms=100, conf=0.9),
            Word(w="second.", start_ms=100, end_ms=200, conf=0.8),
        ),
        asr=CANONICAL,
    )
    assert raw.words[-1].w == "second."


def test_raw_transcript_is_immutable_in_memory(tmp_path: Path) -> None:
    raw = a_raw()
    with pytest.raises(Exception):  # noqa: B017 — frozen dataclass raises FrozenInstanceError
        raw.text_ckb = "mutated"  # type: ignore[misc]
    assert isinstance(raw.words, tuple), "words must not be a mutable list"


def test_normalizing_does_not_touch_raw_on_disk(tmp_path: Path) -> None:
    """The whole point of invariant #1: deriving must be read-only on the source."""
    store = TranscriptStore(tmp_path)
    store.write_raw(a_raw())
    before = store.raw_digest("media-001")

    norm = normalize_transcript(store.read_raw("media-001"))
    store.write_norm(norm)

    assert store.raw_digest("media-001") == before
    store.verify_raw_integrity("media-001")


def test_raw_round_trips_unchanged(tmp_path: Path) -> None:
    store = TranscriptStore(tmp_path)
    original = a_raw()
    store.write_raw(original)
    assert store.read_raw("media-001") == original


def test_raw_keeps_the_asr_text_byte_for_byte(tmp_path: Path) -> None:
    """§4.1: raw is "EXACTLY as ASR emitted" and ships to the client. No normalization."""
    as_emitted = "ئه‌مه‌ كوردي ۲۰۲۵"
    store = TranscriptStore(tmp_path)
    store.write_raw(a_raw(as_emitted))
    assert store.read_raw("media-001").text_ckb == as_emitted


# --- invariant #3: models read norm, never raw ----------------------------------------


def test_model_input_rejects_raw() -> None:
    with pytest.raises(TypeError, match="raw"):
        assert_model_input(a_raw())


def test_model_input_accepts_normalized() -> None:
    assert_model_input(normalize_transcript(a_raw()))  # must not raise


def test_normalized_is_derived_and_records_its_source() -> None:
    raw = a_raw()
    norm = normalize_transcript(raw)
    assert isinstance(norm, NormalizedTranscript)
    assert norm.media_id == raw.media_id
    assert norm.text_ckb == "ئەمە زۆر باشە"
    assert norm.source_sha256 == raw.sha256()


def test_a_stale_normalized_transcript_is_detected(tmp_path: Path) -> None:
    """A norm derived from a different raw is worse than no norm — it looks right."""
    store = TranscriptStore(tmp_path)
    store.write_raw(a_raw())
    other = normalize_transcript(a_raw("a completely different transcript"))
    # The publisher refuses this, and the reader retains its own guard for artifacts planted by
    # an older build or an out-of-band writer.
    with pytest.raises(StaleNormalizedTranscript, match="refusing to publish"):
        store.write_norm(other)
    assert not store.norm_path("media-001").exists()
    store.norm_path("media-001").write_text(other.to_json(), encoding="utf-8")
    with pytest.raises(StaleNormalizedTranscript):
        store.read_norm("media-001")


def test_norm_written_from_the_matching_raw_reads_back(tmp_path: Path) -> None:
    store = TranscriptStore(tmp_path)
    store.write_raw(a_raw())
    norm = normalize_transcript(store.read_raw("media-001"))
    store.write_norm(norm)
    assert store.read_norm("media-001") == norm


def test_norm_may_be_rewritten_because_it_is_derived(tmp_path: Path) -> None:
    """Only raw is write-once. Re-normalizing after a KLPT upgrade must be possible."""
    store = TranscriptStore(tmp_path)
    store.write_raw(a_raw())
    norm = normalize_transcript(store.read_raw("media-001"))
    store.write_norm(norm)
    store.write_norm(norm)  # must not raise


def test_norm_publication_replaces_a_hardlink_without_touching_its_victim(tmp_path: Path) -> None:
    store = TranscriptStore(tmp_path / "store")
    raw = a_raw()
    store.write_raw(raw)
    victim = tmp_path / "victim.txt"
    victim.write_text("ORIGINAL", encoding="utf-8")
    os.link(victim, store.norm_path(raw.media_id))

    norm = normalize_transcript(raw)
    store.write_norm(norm)

    assert victim.read_text(encoding="utf-8") == "ORIGINAL"
    assert store.read_norm(raw.media_id) == norm
    assert not store.norm_path(raw.media_id).samefile(victim)


def test_failed_norm_publication_preserves_the_previous_complete_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = TranscriptStore(tmp_path)
    raw = a_raw()
    store.write_raw(raw)
    norm = normalize_transcript(raw)
    store.write_norm(norm)
    before = store.norm_path(raw.media_id).read_bytes()

    def refuse_replace(_source: Path, _destination: Path) -> None:
        raise PermissionError("simulated publication refusal")

    monkeypatch.setattr(os, "replace", refuse_replace)
    with pytest.raises(PermissionError, match="publication refusal"):
        store.write_norm(norm)

    assert store.norm_path(raw.media_id).read_bytes() == before
    assert list(tmp_path.glob("*.tmp")) == []


def test_norm_staging_cleanup_failure_does_not_mask_the_publication_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = TranscriptStore(tmp_path)
    raw = a_raw()
    store.write_raw(raw)
    norm = normalize_transcript(raw)
    original_unlink = Path.unlink

    def refuse_replace(_source: Path, _destination: Path) -> None:
        raise PermissionError("PRIMARY publication refusal")

    def refuse_staging_unlink(path: Path, missing_ok: bool = False) -> None:
        if path.name.endswith(".tmp"):
            raise OSError("SECONDARY cleanup refusal")
        original_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(os, "replace", refuse_replace)
    monkeypatch.setattr(Path, "unlink", refuse_staging_unlink)
    with pytest.raises(PermissionError, match="PRIMARY") as caught:
        store.write_norm(norm)

    notes = getattr(caught.value, "__notes__", ())
    assert any("SECONDARY cleanup refusal" in note for note in notes)


# --- provenance must name a model §7 permits ------------------------------------------


def test_transcript_from_an_unregistered_model_is_refused() -> None:
    with pytest.raises(ModelNotInRegistry):
        RawTranscript(
            media_id="m",
            text_ckb="x",
            words=(),
            asr=AsrProvenance(canonical="openai/whisper-large-v3"),
        )


def test_transcript_from_an_excluded_model_is_refused() -> None:
    with pytest.raises(ModelExcluded):
        RawTranscript(
            media_id="m",
            text_ckb="x",
            words=(),
            asr=AsrProvenance(canonical="RevgeAI/vekol-stt-ckb-small"),
        )


def test_validator_model_must_also_be_registered() -> None:
    with pytest.raises(ModelNotInRegistry):
        RawTranscript(
            media_id="m",
            text_ckb="x",
            words=(),
            asr=AsrProvenance(canonical="omniASR_LLM_7B_v2", validated_by="some-other-asr"),
        )


# --- D-103: a gap in a client-facing transcript must say why ---------------------------------


def test_an_unaligned_gap_must_carry_a_reason() -> None:
    """An unexplained gap is indistinguishable from silence that was never there.

    §5 already states this shape for `RejectedCandidate` — "a blank reason measures nothing" —
    and a transcript that ships to a client has the stronger version of the problem: the reader
    cannot tell speech the model refused from speech that did not happen.
    """
    with pytest.raises(ValueError, match="needs a reason"):
        UnalignedSpeech(start_ms=1_000, end_ms=1_316, reason="   ")


def test_an_unaligned_gap_must_have_length() -> None:
    with pytest.raises(ValueError, match="no length"):
        UnalignedSpeech(start_ms=1_316, end_ms=1_316, reason="AlignmentInfeasible: 15 frames")


def test_a_real_reason_and_span_are_accepted() -> None:
    """The control: the two refusals above must not amount to refusing every gap."""
    gap = UnalignedSpeech(
        start_ms=1_000, end_ms=1_316, reason="AlignmentInfeasible: 15 frames cannot emit 15 tokens"
    )
    assert gap.end_ms - gap.start_ms == 316
    assert "15 tokens" in gap.reason


# --- D-139: the raw file's own write-once layer was never reached by a test ------------------


def test_deleting_the_digest_does_not_open_the_raw_file_to_a_second_write(tmp_path: Path) -> None:
    """`write_raw` refuses twice over, and only the first refusal was tested.

    Found by adversarial pass #7: neutralising `os.link(staging, path)` — the raw file's own
    write-once link — left the whole suite green, because the sidecar's link refuses first in every
    path a test exercised. The second layer is not dead code; it is the layer that matters when the
    sidecar is **gone**, which is the state an attacker hiding a modification would create, since
    `verify_raw_integrity` needs that digest to detect anything.

    Measured: with the sidecar deleted and the raw present, the second write is refused by the
    raw-file layer, the raw bytes are unchanged, no sidecar is resurrected carrying the second
    write's digest, and no staging file is left behind. D-139.
    """
    store = TranscriptStore(tmp_path)
    store.write_raw(a_raw())
    raw_path = tmp_path / "media-001.transcript.raw.json"
    sidecar = tmp_path / "media-001.transcript.raw.sha256"
    original = raw_path.read_bytes()

    sidecar.chmod(stat.S_IWRITE)
    sidecar.unlink()

    with pytest.raises(RawTranscriptImmutable, match="already exists"):
        store.write_raw(a_raw("a second, different ASR output"))

    assert raw_path.read_bytes() == original, (
        "the canonical transcript was replaced once its digest was removed — invariant #1"
    )
    assert not sidecar.exists(), (
        "a refused write published a digest for content it did not write, which would "
        "authenticate the wrong bytes"
    )
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        ".media-001.transcript.raw.lock",
        raw_path.name,
    ], "the refused write left staging files behind (the persistent lock is expected)"


def test_the_first_layer_still_refuses_while_the_digest_is_present(tmp_path: Path) -> None:
    """The control. The test above must not be satisfiable by breaking the sidecar's own link.

    With both artifacts present the refusal has to come from the *first* layer — its message says
    "already exists or is being written", the raw-file layer's says "already exists." — so the two
    are distinguishable and each is now pinned to its own state.
    """
    store = TranscriptStore(tmp_path)
    store.write_raw(a_raw())

    with pytest.raises(RawTranscriptImmutable, match="already exists or is being written"):
        store.write_raw(a_raw("a second, different ASR output"))

    store.verify_raw_integrity("media-001")


# --- D-144: a per-segment confidence that lies inverts §3's quartile -------------------------


def test_a_positive_log_probability_is_refused() -> None:
    """`SegmentScore` already refuses this, for the reason it names: escalation ranks on log
    probabilities, so a value on the wrong scale silently inverts the bottom quartile — the
    confident segments would be the ones routed to the validator.

    Found unprotected by D-144's own mutation audit: I wrote this guard and no test reached it,
    which is the third iteration running where the audit's real catch was my own new guard.
    """
    with pytest.raises(ValueError, match="inverts the bottom quartile"):
        SegmentConfidence(start_ms=0, end_ms=1_000, mean_logprob=0.5)


def test_a_zero_length_segment_confidence_is_refused() -> None:
    with pytest.raises(ValueError, match="no length"):
        SegmentConfidence(start_ms=1_000, end_ms=1_000, mean_logprob=-1.0)


def test_a_real_segment_confidence_is_accepted() -> None:
    """The control: the two refusals above must not amount to refusing every measurement.

    Zero is a legitimate log-probability — certainty — and must not be confused with the positive
    values that indicate a wrong scale.
    """
    scored = SegmentConfidence(start_ms=1_000, end_ms=1_316, mean_logprob=-6.523425833753913)
    assert scored.end_ms - scored.start_ms == 316
    assert SegmentConfidence(start_ms=0, end_ms=1, mean_logprob=0.0).mean_logprob == 0.0
