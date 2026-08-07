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
from pathlib import Path

import pytest

from hawedit.registry import ModelExcluded, ModelNotInRegistry
from hawedit.transcripts import (
    AsrProvenance,
    NormalizedTranscript,
    RawTranscript,
    RawTranscriptImmutable,
    RawTranscriptTampered,
    StaleNormalizedTranscript,
    TranscriptStore,
    Word,
    assert_model_input,
    normalize_transcript,
)

CANONICAL = AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi")


def a_raw(text: str = "ئه‌مه‌ زۆر باشه‌") -> RawTranscript:
    return RawTranscript(
        media_id="media-001",
        text_ckb=text,
        words=(Word(w="ئه‌مه‌", start_ms=84600, end_ms=84920, conf=0.97),),
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
