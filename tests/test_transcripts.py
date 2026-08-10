"""M0.4 — Kurdish invariants #1 and #3, asserted in code rather than documented.

    #1  transcript.raw.json is never mutated after write. Test this explicitly.
    #3  Indexes, embeddings and model inputs read transcript.norm.json — never raw.

§4.1 puts it plainly: "If you find yourself editing the raw transcript in place, stop —
you've introduced a bug you cannot detect later." So the point of these tests is to make it
detectable: the API refuses, the type system refuses, and a checksum catches whatever gets
past both.
"""

from __future__ import annotations

import json
import stat
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

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
    store.write_norm(other)
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


# --- D-107: the raw file's own write-once layer was never reached by a test ------------------


def test_deleting_the_digest_does_not_open_the_raw_file_to_a_second_write(tmp_path: Path) -> None:
    """`write_raw` refuses twice over, and only the first refusal was tested.

    Found by adversarial pass #7: neutralising `os.link(staging, path)` — the raw file's own
    write-once link — left the whole suite green, because the sidecar's link refuses first in every
    path a test exercised. The second layer is not dead code; it is the layer that matters when the
    sidecar is **gone**, which is the state an attacker hiding a modification would create, since
    `verify_raw_integrity` needs that digest to detect anything.

    Measured: with the sidecar deleted and the raw present, the second write is refused by the
    raw-file layer, the raw bytes are unchanged, no sidecar is resurrected carrying the second
    write's digest, and no staging file is left behind. D-107.
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
    assert sorted(path.name for path in tmp_path.iterdir()) == [raw_path.name], (
        "the refused write left staging files behind"
    )


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


# --- D-109: a per-segment confidence that lies inverts §3's quartile -------------------------


def test_a_positive_log_probability_is_refused() -> None:
    """`SegmentScore` already refuses this, for the reason it names: escalation ranks on log
    probabilities, so a value on the wrong scale silently inverts the bottom quartile — the
    confident segments would be the ones routed to the validator.

    Found unprotected by D-109's own mutation audit: I wrote this guard and no test reached it,
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


# --- D-136: Stage 1 is the expensive stage, and it was re-run every time -------------------


def test_a_transcript_is_reused_when_the_audio_and_producer_both_match(tmp_path: Path) -> None:
    """Measured on the real 38-minute file, Stage 1 costs **1,547 s** for 545 segments, and
    `run_pipeline` called `asr.transcribe` before consulting this store at all."""
    store = TranscriptStore(tmp_path)
    raw = a_raw()
    store.write_raw(raw, audio_sha256="abc123", producer="pkg.RealProducer")

    assert store.reusable_raw("media-001", "abc123", "pkg.RealProducer") == raw


def test_a_changed_audio_digest_is_not_reused(tmp_path: Path) -> None:
    """The control that matters most: same media_id, different recording. Reusing there would
    ship one video's words for another — worse than the 1,547 s it saves."""
    store = TranscriptStore(tmp_path)
    store.write_raw(a_raw(), audio_sha256="abc123", producer="pkg.RealProducer")

    assert store.reusable_raw("media-001", "different", "pkg.RealProducer") is None


def test_a_transcript_from_a_stub_is_not_reused_by_another_producer(tmp_path: Path) -> None:
    """`asr.py`'s own rule: a run driven by a test double "can never be read as a run on real
    weights". Keyed on audio alone, a stub's transcript would be reused by a real --omni-asr run
    and the report would claim OmniASR output."""
    store = TranscriptStore(tmp_path)
    store.write_raw(a_raw(), audio_sha256="abc123", producer="tests.StubProducer")

    assert store.reusable_raw("media-001", "abc123", "hawedit.asr.WslOmniAsrProducer") is None
    # The control: the same stub asking again does get it back, so this measures the producer
    # and not merely that some string mismatches.
    assert store.reusable_raw("media-001", "abc123", "tests.StubProducer") is not None


def test_a_transcript_written_without_provenance_is_never_reused(tmp_path: Path) -> None:
    """Every transcript written before D-136 is in this state, as is one whose sidecar was
    cleaned up. Absent evidence is not evidence of a match."""
    store = TranscriptStore(tmp_path)
    store.write_raw(a_raw())

    assert store.reusable_raw("media-001", "abc123", "pkg.RealProducer") is None
    assert not (tmp_path / "media-001.transcript.raw.provenance.json").is_file()


def test_half_a_provenance_record_is_not_a_match(tmp_path: Path) -> None:
    """Both keys are required. A sidecar naming only the audio would let any producer claim it."""
    store = TranscriptStore(tmp_path)
    store.write_raw(a_raw(), audio_sha256="abc123", producer="pkg.RealProducer")
    sidecar = tmp_path / "media-001.transcript.raw.provenance.json"
    assert sidecar.is_file(), "the sidecar this test overwrites is not where it thinks"
    sidecar.write_text(json.dumps({"audio_sha256": "abc123"}), encoding="utf-8")

    assert store.reusable_raw("media-001", "abc123", "pkg.RealProducer") is None


def test_unreadable_provenance_falls_back_to_transcribing(tmp_path: Path) -> None:
    store = TranscriptStore(tmp_path)
    store.write_raw(a_raw(), audio_sha256="abc123", producer="pkg.RealProducer")
    (tmp_path / "media-001.transcript.raw.provenance.json").write_text('{"audio', encoding="utf-8")

    assert store.reusable_raw("media-001", "abc123", "pkg.RealProducer") is None


def test_reuse_still_verifies_the_transcript_against_its_digest(tmp_path: Path) -> None:
    """A tampered transcript must not be handed back just because the sidecar matches — the
    reuse path is a *read* of the canonical artifact and invariant #1's tamper evidence applies
    to it exactly as it does to every other read."""
    store = TranscriptStore(tmp_path)
    path = store.write_raw(a_raw(), audio_sha256="abc123", producer="pkg.Real")
    path.chmod(0o644)
    path.write_text(a_raw(text="something else entirely").to_json(), encoding="utf-8")

    with pytest.raises(RawTranscriptTampered):
        store.reusable_raw("media-001", "abc123", "pkg.Real")


def test_a_missing_transcript_is_not_reused_even_with_a_sidecar(tmp_path: Path) -> None:
    """The sidecar is written after the transcript, so this state should not arise — which is
    exactly why it must not be trusted if it does."""
    store = TranscriptStore(tmp_path)
    (tmp_path / "media-001.transcript.raw.provenance.json").write_text(
        json.dumps({"audio_sha256": "abc123", "producer": "pkg.Real"}), encoding="utf-8"
    )

    assert store.reusable_raw("media-001", "abc123", "pkg.Real") is None


# --- D-151: invariant #1's tamper evidence, held in the state that removes it -----------------
#
# `verify_raw_integrity` has two refusals. The mismatch half — the file no longer hashes to the
# recorded digest — has three tests. The *missing digest* half had none: every one of those tests
# reaches the check by editing the transcript, never by touching the sidecar. Measured, with that
# branch neutered: delete the sidecar, rewrite the canonical transcript, and
# `verify_raw_integrity` returns cleanly while `read_raw` hands back
# `'ئەمە دەقێکی جیاوازە — TAMPERED'` — with all 1,471 tests green.
# `evidence/invariant-1-had-no-digest-no-problem.md`.
# =========================================================================================


def _delete(sidecar: Path) -> None:
    sidecar.unlink()


def _empty(sidecar: Path) -> None:
    sidecar.write_text("", encoding="ascii")


def _whitespace(sidecar: Path) -> None:
    sidecar.write_text("   \n", encoding="ascii")


def _not_ascii(sidecar: Path) -> None:
    sidecar.write_bytes(b"\xff\xfe not a digest")


def _a_directory(sidecar: Path) -> None:
    sidecar.unlink()
    sidecar.mkdir()


# Every way the recorded digest can stop being a readable digest. *Which* states belong here is a
# judgment — nothing can derive it — so it is written once and the parametrisation is derived from
# it, because the failure a test cannot catch is the two drifting apart. Found by mutation: with
# the state list spelled out separately, dropping "deleted" from it left the suite green while the
# code that produces that state sat there unused.
_SIDECAR_BREAKERS: dict[str, Callable[[Path], None]] = {
    "deleted": _delete,
    "empty": _empty,
    "whitespace only": _whitespace,
    "not ASCII": _not_ascii,
    "a directory": _a_directory,
}
_SIDECAR_STATES = tuple(_SIDECAR_BREAKERS)


def _break_the_sidecar(sidecar: Path, how: str) -> None:
    _SIDECAR_BREAKERS[how](sidecar)


@pytest.mark.parametrize("how", _SIDECAR_STATES)
@pytest.mark.parametrize("entry_point", ["verify_raw_integrity", "reusable_raw"])
def test_a_transcript_whose_digest_is_gone_cannot_be_verified(
    tmp_path: Path, how: str, entry_point: str
) -> None:
    """Both paths that claim to check invariant #1, in every state that removes the evidence.

    Asserted on both because they are different doors: the pipeline calls
    `verify_raw_integrity` directly, and Stage 1 reuse goes through `reusable_raw`. A guard
    correct only on the door its one caller happens to use is one the next caller walks past.
    """
    store = TranscriptStore(tmp_path)
    store.write_raw(a_raw(), audio_sha256="abc123", producer="pkg.Real")
    _break_the_sidecar(store._digest_path("media-001"), how)

    with pytest.raises(RawTranscriptTampered):
        if entry_point == "verify_raw_integrity":
            store.verify_raw_integrity("media-001")
        else:
            store.reusable_raw("media-001", "abc123", "pkg.Real")


@pytest.mark.parametrize("how", _SIDECAR_STATES)
def test_a_tampered_transcript_is_still_refused_once_its_digest_is_gone(
    tmp_path: Path, how: str
) -> None:
    """The state this actually protects against, asserted on the text that would ship.

    Deleting the sidecar is the cheapest way to erase tamper evidence — the file it would have
    contradicted is right there. Measured with the refusal removed: the edited Sorani comes back
    from `read_raw` as the canonical transcript.
    """
    store = TranscriptStore(tmp_path)
    path = store.write_raw(a_raw(), audio_sha256="abc123", producer="pkg.Real")
    path.chmod(0o644)
    path.write_text(a_raw(text="ئەمە دەقێکی جیاوازە — TAMPERED").to_json(), encoding="utf-8")
    _break_the_sidecar(store._digest_path("media-001"), how)

    with pytest.raises(RawTranscriptTampered):
        store.verify_raw_integrity("media-001")
    # The door a real Stage 1 run takes. It must refuse rather than hand the edited text back.
    with pytest.raises(RawTranscriptTampered):
        store.reusable_raw("media-001", "abc123", "pkg.Real")


def test_an_intact_digest_still_verifies_and_still_reuses(tmp_path: Path) -> None:
    """The control, and the table above needs one: a `verify_raw_integrity` that raised
    unconditionally — or a `reusable_raw` that never returned anything — passes every case above.

    So this requires the untouched pair to verify *and* to come back through the reuse door with
    the text that was written.
    """
    store = TranscriptStore(tmp_path)
    store.write_raw(a_raw(), audio_sha256="abc123", producer="pkg.Real")

    store.verify_raw_integrity("media-001")  # must not raise
    reused = store.reusable_raw("media-001", "abc123", "pkg.Real")
    assert reused is not None, "an intact transcript was not offered for reuse"
    assert reused.text_ckb == a_raw().text_ckb


def test_every_way_of_breaking_the_sidecar_is_actually_exercised() -> None:
    """The parametrisation is derived from the breakers; this pins that it still is.

    It cannot check the *judgment* — nothing can derive which states belong in the table — but it
    can check that the two halves have not drifted, which is the failure mutation found: a state
    list edited down while the code producing that state stays behind, unused and unrun.
    """
    assert set(_SIDECAR_STATES) == set(_SIDECAR_BREAKERS), (
        f"the parametrisation no longer covers every sidecar state: "
        f"{sorted(set(_SIDECAR_BREAKERS) - set(_SIDECAR_STATES))} produced but never exercised; "
        f"{sorted(set(_SIDECAR_STATES) - set(_SIDECAR_BREAKERS))} named but not producible"
    )
