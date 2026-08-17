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
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path
from threading import Barrier, Event
from types import SimpleNamespace

import pytest

from hawedit.registry import ModelExcluded, ModelNotInRegistry, WrongRole
from hawedit.transcripts import (
    AsrProvenance,
    NormalizedTranscript,
    RawTranscript,
    RawTranscriptImmutable,
    RawTranscriptTampered,
    RejectedValidatorCorrection,
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
MEDIA_SHA256 = "0" * 64

# The two §7 model ids by role, for D-197's tests. Named apart from `CANONICAL` above, which is a
# whole provenance record rather than a model id.


CANONICAL_ASR_ID = "omniASR_LLM_7B_v2"


VALIDATOR_ID = "rzgar/qwen3-asr-sorani-kurdish-ckb-v1"


def a_raw(text: str = "ئه‌مه‌ زۆر باشه‌") -> RawTranscript:
    surface = "ئه‌مه‌"
    return RawTranscript(
        media_id="media-001",
        text_ckb=text,
        words=(Word(w=surface, start_ms=84600, end_ms=84920, conf=0.97),)
        if surface in text
        else (),
        asr=CANONICAL,
        media_sha256=MEDIA_SHA256,
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
    """A norm derived from a different raw is worse than no norm — it looks right.

    Refused at both ends since D-192. The write refuses because a producer that got the digest
    wrong should hear about it while it still has the right one to hand; the read refuses
    because a norm can reach the directory without going through this store at all.
    """
    store = TranscriptStore(tmp_path)
    store.write_raw(a_raw())
    other = normalize_transcript(a_raw("a completely different transcript"))

    with pytest.raises(StaleNormalizedTranscript):
        store.write_norm(other)
    assert not store.norm_path("media-001").exists(), "the refused norm was stored anyway"

    store.norm_path("media-001").write_text(other.to_json(), encoding="utf-8")
    with pytest.raises(StaleNormalizedTranscript):
        store.read_norm("media-001")


def test_storing_a_norm_stamped_from_the_parsed_object_is_refused(tmp_path: Path) -> None:
    """The producer half of D-192, at the boundary every producer shares.

    `normalize_transcript(store.read_raw(id))` — no digest passed — is the line the pipeline
    used to run and the obvious thing to write. It is right until the raw on disk predates a
    schema field, and then it stamps what this release would have written. Same hand-built
    pre-`adapter` artifact as above; here the norm derived from it must be refused at write.
    """
    import hashlib

    store = TranscriptStore(tmp_path)
    payload = json.loads(a_raw().to_json())
    payload["asr"].pop("adapter")
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    store.raw_path("media-001").write_bytes(body)
    store._digest_path("media-001").write_text(hashlib.sha256(body).hexdigest(), encoding="ascii")

    careless = normalize_transcript(store.read_raw("media-001"))
    with pytest.raises(StaleNormalizedTranscript, match="digest of the file"):
        store.write_norm(careless)

    # The control: the same derivation, given the file's digest, is stored and reads back — so
    # this measures where the value came from and not that `write_norm` refuses everything.
    correct = normalize_transcript(
        store.read_raw("media-001"), source_sha256=store.raw_digest("media-001")
    )
    store.write_norm(correct)
    assert store.read_norm("media-001") == correct


def test_norm_written_from_the_matching_raw_reads_back(tmp_path: Path) -> None:
    store = TranscriptStore(tmp_path)
    store.write_raw(a_raw())
    norm = normalize_transcript(store.read_raw("media-001"))
    store.write_norm(norm)
    assert store.read_norm("media-001") == norm


def test_a_transcript_written_before_a_field_existed_is_not_called_stale(tmp_path: Path) -> None:
    """`read_norm` compared the stored `source_sha256` against a **re-serialised** raw.

    So it answered with today's schema rather than with the bytes on disk, and D-181 adding one
    optional `adapter` field to `AsrProvenance` re-dated every transcript ever written. Measured
    on the real 38-minute run and three other artifacts in `work/`: `verify_raw_integrity`
    passed — the files are byte-identical to what was stored — while `read_norm` refused them as
    *"derived from raw 7912e7bd1d35… but the stored raw is 4748ac2a3e02…"* and told the operator
    to re-normalize. Re-normalizing would have written the same unstable value again.

    The pre-D-181 shape is written by hand here, because `write_raw` necessarily writes today's.
    """
    import hashlib

    store = TranscriptStore(tmp_path)
    payload = json.loads(a_raw().to_json())
    assert payload["asr"].pop("adapter", "absent") is None, (
        "this reproduces a transcript stored before `adapter` existed — the field is now gone "
        "from AsrProvenance, so the artifact being simulated is not the one that broke"
    )
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    store.raw_path("media-001").write_bytes(body)
    store._digest_path("media-001").write_text(hashlib.sha256(body).hexdigest(), encoding="ascii")

    stored = store.read_raw("media-001")
    # The control. If the two digests agreed, this file would not exhibit the drift and every
    # assertion below would hold for a `read_norm` that still re-hashed the parsed object.
    assert stored.sha256() != store.raw_digest("media-001"), (
        "the hand-written artifact serialises identically under today's schema, so it cannot "
        "measure the defect"
    )
    store.verify_raw_integrity("media-001")  # invariant #1: the bytes are what was written

    store.write_norm(normalize_transcript(stored, source_sha256=store.raw_digest("media-001")))
    assert store.read_norm("media-001").text_ckb == "ئەمە زۆر باشە"


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


# --- D-197: the validator's reading is evidence, never a replacement ----------------------
#
# §3 Stage 1 says "route the bottom quartile, and any segment where LLM-7B and CTC-3B disagree
# materially, to the validator" and stops there — it never says what the validator's answer DOES
# to the canonical text. D-197 specifies it, and the rule is one-directional: the validator can
# flag a span, never rewrite it. These pin the place the type already enforces that.


@pytest.mark.parametrize(
    ("label", "kwargs"),
    [
        ("the validator in the canonical slot", {"canonical": VALIDATOR_ID}),
        ("the emissions model in the canonical slot", {"canonical": "omniASR_CTC_3B_v2"}),
        (
            "the canonical model validating itself",
            {"canonical": CANONICAL_ASR_ID, "validated_by": CANONICAL_ASR_ID},
        ),
    ],
)
def test_a_model_cannot_take_the_asr_role_it_is_not_section_7s_model_for(
    label: str, kwargs: dict[str, str]
) -> None:
    """The enforcement point of D-197's merge rule.

    If the validator could occupy `canonical`, "the canonical transcript" would mean whichever
    model happened to be written there, and Kurdish invariant #1 — raw is *exactly as canonical
    ASR emitted*, write-once — would be guarding a field that no longer says what produced it.
    The self-validation case is the same defect turned around: a model that validates its own
    output has validated nothing, and `validated_by` would be a field that always agreed.
    """
    with pytest.raises(WrongRole):
        AsrProvenance(**kwargs)  # type: ignore[arg-type]


def test_the_canonical_and_validator_pairing_section_7_names_is_accepted() -> None:
    """The control. Three refusals above are only meaningful if the legitimate pairing — §7's
    canonical ASR read, §7's validator second-opinion — is the one thing that passes."""
    provenance = AsrProvenance(
        canonical=CANONICAL_ASR_ID, validated_by=VALIDATOR_ID, aligner="ctc_viterbi"
    )
    assert provenance.canonical == CANONICAL_ASR_ID
    assert provenance.validated_by == VALIDATOR_ID


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
    lock_name = ".media-001.transcript.raw.lock"
    assert sorted(path.name for path in tmp_path.iterdir()) == [lock_name, raw_path.name], (
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

    assert store.reusable_raw("media-001", "abc123", "pkg.RealProducer", MEDIA_SHA256) == raw


def test_a_changed_audio_digest_is_not_reused(tmp_path: Path) -> None:
    """The control that matters most: same media_id, different recording. Reusing there would
    ship one video's words for another — worse than the 1,547 s it saves."""
    store = TranscriptStore(tmp_path)
    store.write_raw(a_raw(), audio_sha256="abc123", producer="pkg.RealProducer")

    assert store.reusable_raw("media-001", "different", "pkg.RealProducer", MEDIA_SHA256) is None


def test_matching_audio_and_producer_cannot_reuse_transcript_for_other_media_bytes(
    tmp_path: Path,
) -> None:
    store = TranscriptStore(tmp_path)
    store.write_raw(a_raw(), audio_sha256="abc123", producer="pkg.RealProducer")

    with pytest.raises(RawTranscriptImmutable, match="not bound to source media"):
        store.reusable_raw("media-001", "abc123", "pkg.RealProducer", "1" * 64)


def test_legacy_unbound_transcript_is_not_reused_after_media_binding(tmp_path: Path) -> None:
    store = TranscriptStore(tmp_path)
    legacy = RawTranscript(
        media_id="media-001",
        text_ckb="ئه‌مه‌ زۆر باشه‌",
        words=(Word(w="ئه‌مه‌", start_ms=84_600, end_ms=84_920, conf=0.97),),
        asr=CANONICAL,
    )
    store.write_raw(legacy, audio_sha256="abc123", producer="pkg.RealProducer")

    with pytest.raises(RawTranscriptImmutable, match="new work directory"):
        store.reusable_raw("media-001", "abc123", "pkg.RealProducer", MEDIA_SHA256)


def test_a_transcript_from_a_stub_is_not_reused_by_another_producer(tmp_path: Path) -> None:
    """`asr.py`'s own rule: a run driven by a test double "can never be read as a run on real
    weights". Keyed on audio alone, a stub's transcript would be reused by a real --omni-asr run
    and the report would claim OmniASR output."""
    store = TranscriptStore(tmp_path)
    store.write_raw(a_raw(), audio_sha256="abc123", producer="tests.StubProducer")

    assert (
        store.reusable_raw("media-001", "abc123", "hawedit.asr.WslOmniAsrProducer", MEDIA_SHA256)
        is None
    )
    # The control: the same stub asking again does get it back, so this measures the producer
    # and not merely that some string mismatches.
    assert store.reusable_raw("media-001", "abc123", "tests.StubProducer", MEDIA_SHA256) is not None


def test_a_transcript_written_without_provenance_is_never_reused(tmp_path: Path) -> None:
    """Every transcript written before D-136 is in this state, as is one whose sidecar was
    cleaned up. Absent evidence is not evidence of a match."""
    store = TranscriptStore(tmp_path)
    store.write_raw(a_raw())

    assert store.reusable_raw("media-001", "abc123", "pkg.RealProducer", MEDIA_SHA256) is None
    assert not (tmp_path / "media-001.transcript.raw.provenance.json").is_file()


def test_half_a_provenance_record_is_not_a_match(tmp_path: Path) -> None:
    """Both keys are required. A sidecar naming only the audio would let any producer claim it."""
    store = TranscriptStore(tmp_path)
    store.write_raw(a_raw(), audio_sha256="abc123", producer="pkg.RealProducer")
    sidecar = tmp_path / "media-001.transcript.raw.provenance.json"
    assert sidecar.is_file(), "the sidecar this test overwrites is not where it thinks"
    sidecar.write_text(json.dumps({"audio_sha256": "abc123"}), encoding="utf-8")

    assert store.reusable_raw("media-001", "abc123", "pkg.RealProducer", MEDIA_SHA256) is None


def test_unreadable_provenance_falls_back_to_transcribing(tmp_path: Path) -> None:
    store = TranscriptStore(tmp_path)
    store.write_raw(a_raw(), audio_sha256="abc123", producer="pkg.RealProducer")
    (tmp_path / "media-001.transcript.raw.provenance.json").write_text('{"audio', encoding="utf-8")

    assert store.reusable_raw("media-001", "abc123", "pkg.RealProducer", MEDIA_SHA256) is None


def test_reuse_still_verifies_the_transcript_against_its_digest(tmp_path: Path) -> None:
    """A tampered transcript must not be handed back just because the sidecar matches — the
    reuse path is a *read* of the canonical artifact and invariant #1's tamper evidence applies
    to it exactly as it does to every other read."""
    store = TranscriptStore(tmp_path)
    path = store.write_raw(a_raw(), audio_sha256="abc123", producer="pkg.Real")
    path.chmod(0o644)
    path.write_text(a_raw(text="something else entirely").to_json(), encoding="utf-8")

    with pytest.raises(RawTranscriptTampered):
        store.reusable_raw("media-001", "abc123", "pkg.Real", MEDIA_SHA256)


def test_a_missing_transcript_is_not_reused_even_with_a_sidecar(tmp_path: Path) -> None:
    """The sidecar is written after the transcript, so this state should not arise — which is
    exactly why it must not be trusted if it does."""
    store = TranscriptStore(tmp_path)
    (tmp_path / "media-001.transcript.raw.provenance.json").write_text(
        json.dumps({"audio_sha256": "abc123", "producer": "pkg.Real"}), encoding="utf-8"
    )

    assert store.reusable_raw("media-001", "abc123", "pkg.Real", MEDIA_SHA256) is None


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
            store.reusable_raw("media-001", "abc123", "pkg.Real", MEDIA_SHA256)


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
        store.reusable_raw("media-001", "abc123", "pkg.Real", MEDIA_SHA256)


def test_an_intact_digest_still_verifies_and_still_reuses(tmp_path: Path) -> None:
    """The control, and the table above needs one: a `verify_raw_integrity` that raised
    unconditionally — or a `reusable_raw` that never returned anything — passes every case above.

    So this requires the untouched pair to verify *and* to come back through the reuse door with
    the text that was written.
    """
    store = TranscriptStore(tmp_path)
    store.write_raw(a_raw(), audio_sha256="abc123", producer="pkg.Real")

    store.verify_raw_integrity("media-001")  # must not raise
    reused = store.reusable_raw("media-001", "abc123", "pkg.Real", MEDIA_SHA256)
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


# --- D-167: a surface form must be one line ------------------------------------------------

# Every break `str.splitlines` recognises, plus the position that a length check would miss.
# `Word` is the chokepoint: seven construction sites route through `__post_init__`, two of them
# reading JSON off disk, and one guard here covers all of them.


_NOT_ONE_LINE = (
    "a\nb",
    "a\r\nb",
    "a\rb",
    "a\vb",
    "a\fb",
    "a\x1cb",
    "a\x85b",
    "a\u2028b",
    "a\u2029b",
    "a\n\nb",
    "a\n",  # trailing: `len(splitlines()) == 1` accepts this, and ` `.join still breaks the line
    "\nb",
)


@pytest.mark.parametrize("surface", _NOT_ONE_LINE)
def test_a_surface_form_that_is_not_one_line_is_refused(surface: str) -> None:
    """Measured before this guard, on real ffmpeg 8.1.1 and real libass: a word carrying a
    break burned a frame **byte-identical** to one rendered with the tail deleted — the text
    after the break never reached the pixels — while `parse_dialogue_times` returned exactly
    the times of the intact file and `parse_srt_times` returned the right cue count.

    `evidence/a-word-that-was-not-one-line.md`. D-167.
    """
    with pytest.raises(ValueError, match="one line"):
        Word(w=surface, start_ms=0, end_ms=100, conf=0.9)


@pytest.mark.parametrize("surface", ["a b", "a\tb", " a", "a ", "a\xa0b"])
def test_whitespace_that_does_not_break_a_line_is_still_accepted(surface: str) -> None:
    """The control for the plausible over-broad fix.

    Refusing *all* whitespace would also catch these, and they lose no text: a tab, a space or
    a no-break space inside a surface form renders whole in both formats. That is a different
    complaint — one `Word` covering two spoken words has one timing for both — and refusing it
    here would reject transcripts over a defect this measurement never demonstrated.
    """
    assert Word(w=surface, start_ms=0, end_ms=100, conf=0.9).w == surface


def test_a_supplied_transcript_carrying_a_broken_word_is_refused_at_the_door() -> None:
    """`--transcript FILE` is a documented flag, and `Word(**w)` is how the file becomes words.

    This is the reachable path, so it is not latent: nothing upstream objects. Invariant #5's
    aligner check passes on `ctc_viterbi`, and the aligned-words-appear-in-`text_ckb` cross-check
    passes too as soon as the file is internally consistent — which a file written by a tool that
    wrapped its own output would be.
    """
    surface = "دووەم\nسێیەم"
    payload = json.dumps(
        {
            "media_id": "media-001",
            "text_ckb": f"یەکەم {surface}",
            "words": [
                {"w": "یەکەم", "start_ms": 0, "end_ms": 400, "conf": 0.9},
                {"w": surface, "start_ms": 400, "end_ms": 900, "conf": 0.9},
            ],
            "asr": {"canonical": "omniASR_LLM_7B_v2", "aligner": "ctc_viterbi"},
        },
        ensure_ascii=False,
    )
    with pytest.raises(ValueError, match="one line"):
        RawTranscript.from_json(payload)


# --- the constructor's checks, and the file that reaches them --------------------------------
#
# Measured by neutralising each refusal in a shadow copy of src/hawedit and running this file
# together with the eighteen others that import `hawedit.transcripts`. The wider scope is the
# point: `:259` read unheld against this file alone and is held by another of the eighteen, so
# a narrower run would have reported a gap that is not there. The nine below survived it.
#
# They divide in two, and the division matters more than the count. `from_json` is the trust
# boundary — it reads `transcript.raw.json` off disk and hands `data["media_id"]` straight to
# the constructor — so the first group is reachable by a file. The second is not: `from_json`
# builds `tuple(Word(**w) …)` and `AsrProvenance(**…)`, so those types are already right by the
# time the constructor sees them. That group is the contract with a caller that ignores the
# annotations, which mypy checks statically and nothing checks at runtime.


def _raw_file(**overrides: object) -> str:
    """A valid `transcript.raw.json` with one field replaced.

    Serialised from a real `RawTranscript` rather than hand-written, so a schema change breaks
    this loudly instead of leaving it testing a document the code no longer reads.
    """
    data = json.loads(a_raw().to_json())
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (42, "media_id must be a non-empty string"),
        (None, "media_id must be a non-empty string"),
        ("", "media_id must be a non-empty string"),
        ("   ", "media_id must be a non-empty string"),
    ],
)
def test_a_raw_transcript_file_whose_media_id_is_not_a_name_is_refused(
    value: object, message: str
) -> None:
    """`media_id` is what the artifact is stored and looked up under, so an empty or non-string
    one is not a cosmetic problem: `TranscriptStore` would key a file on it.
    """
    with pytest.raises(ValueError, match=message):
        RawTranscript.from_json(_raw_file(media_id=value))


def test_legacy_raw_transcript_without_media_digest_remains_readable_but_unbound() -> None:
    payload = json.loads(a_raw().to_json())
    payload.pop("media_sha256")
    assert RawTranscript.from_json(json.dumps(payload, ensure_ascii=False)).media_sha256 is None


@pytest.mark.parametrize("value", [True, 7, "A" * 64, "0" * 63, "g" * 64])
def test_raw_transcript_refuses_a_noncanonical_media_digest(value: object) -> None:
    with pytest.raises(ValueError, match="media_sha256"):
        RawTranscript.from_json(_raw_file(media_sha256=value))


def test_raw_transcript_round_trips_an_exact_media_digest() -> None:
    raw = RawTranscript.from_json(_raw_file(media_sha256="0" * 64))
    assert raw.media_sha256 == "0" * 64


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (None, "text_ckb must be a string"),
        (["ئه‌مه‌"], "text_ckb must be a string"),
        (12, "text_ckb must be a string"),
        ("   ", "text_ckb must not contain only whitespace"),
        ("\n\t ", "text_ckb must not contain only whitespace"),
    ],
)
def test_a_raw_transcript_file_whose_text_is_not_text_is_refused(
    value: object, message: str
) -> None:
    """Two different failures, and the second is the quiet one.

    A non-string `text_ckb` is caught the moment anything reads it — but only if something
    does: with no words the surface scan never runs, and `null` would be written straight back
    out by `to_json` as a canonical artifact of nothing. Whitespace-only is worse still,
    because it is a perfectly valid string that says a Kurdish clip contains no speech.
    """
    with pytest.raises(ValueError, match=message):
        RawTranscript.from_json(_raw_file(text_ckb=value))


def test_the_empty_transcript_is_still_readable() -> None:
    """The control for the pair above. `text_ckb` is checked with `if self.text_ckb and …`, so
    the empty string is deliberately allowed — a file that transcribed to nothing is a real
    outcome and is not the same as one whose text is whitespace. A refusal that swept both up
    would pass those tests and reject a legitimate artifact.
    """
    empty = RawTranscript.from_json(_raw_file(text_ckb="", words=[]))
    assert empty.text_ckb == ""


def test_an_asr_provenance_whose_adapter_is_named_but_blank_is_refused() -> None:
    """D-181: the adapter field exists because "a transcript decoded by adapted weights and one
    decoded by stock weights are different transcripts, and only this field says which is
    which". `None` says there was no fine-tune. `""` says there was one and it has no name —
    precisely the ambiguity the field was added to remove, and it arrives through the file.
    """
    payload = json.loads(a_raw().to_json())
    payload["asr"]["adapter"] = "   "
    with pytest.raises(ValueError, match="adapter must name the fine-tune or be None"):
        RawTranscript.from_json(json.dumps(payload, ensure_ascii=False))

    # The control: `None` is how the same file says there was no fine-tune, and must still load.
    payload["asr"]["adapter"] = None
    assert RawTranscript.from_json(json.dumps(payload, ensure_ascii=False)).asr.adapter is None


def test_the_constructor_refuses_the_element_types_its_annotations_promise() -> None:
    """Not reachable through `from_json`; every ignore below marks a state mypy already forbids.

    They are checked at runtime anyway because `RawTranscript` is frozen, hashed, and declared
    "never modified after write" by Kurdish invariant #1. A list where a tuple belongs is a
    mutable field inside that artifact, and `sha256()` would go on answering for it while it
    changed — a mutation invariant #1 exists to make detectable, made undetectable.
    """
    with pytest.raises(ValueError, match="words must be a tuple"):
        RawTranscript(media_id="m", text_ckb="ئه‌مه‌", words=[], asr=CANONICAL)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="asr must be AsrProvenance"):
        RawTranscript(
            media_id="m",
            text_ckb="ئه‌مه‌",
            words=(),
            asr={"canonical": CANONICAL_ASR_ID},  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match=r"word 0 is not a Word"):
        RawTranscript(
            media_id="m",
            text_ckb="ئه‌مه‌",
            words=("ئه‌مه‌",),  # type: ignore[arg-type]
            asr=CANONICAL,
        )

    with pytest.raises(ValueError, match=r"unaligned\[0\] is not an UnalignedSpeech"):
        RawTranscript(
            media_id="m",
            text_ckb="ئه‌مه‌",
            words=(),
            asr=CANONICAL,
            unaligned=({"start_ms": 0, "end_ms": 1, "reason": "x"},),  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match=r"segment_confidence\[0\] is not a SegmentConfidence"):
        RawTranscript(
            media_id="m",
            text_ckb="ئه‌مه‌",
            words=(),
            asr=CANONICAL,
            segment_confidence=(-0.5,),  # type: ignore[arg-type]
        )


# --- audit finding #9: the path invariant #1 guards is derived from a media_id ----------------
#
# Both refusals in `_safe` are held — `test_audit_regressions.py` reaches each with one input,
# `raw_path("a/b")` and `raw_path("")`. What is *not* held is most of what they say, and the
# reason is worth recording because it bounds the instrument rather than this module: the
# guard-revert matrix neutralises a whole `if` line, so a compound condition reports HELD as
# soon as any one disjunct is covered. These two lines carry six between them:
#
#     if not media_id or media_id in {".", ".."}:                       # 1 of 2 covered
#     if any(sep in media_id for sep in ("/", "\\", "\x00")) or ".." in media_id:   # 1 of 4
#
# So this block adds no new refusal. It covers the five disjuncts that were reachable and
# untested, on a path-traversal guard, which is not somewhere to accept a one-input sample.


@pytest.mark.parametrize("media_id", [".", ".."])
def test_a_media_id_that_is_only_a_path_component_is_refused(tmp_path: Path, media_id: str) -> None:
    """The second disjunct of the first refusal; `""` is the one already covered elsewhere.

    Neither escapes the store, which is why they are stated apart from the separator check
    below — `"."` contains no separator and no parent reference, so that check would pass it
    through, and it becomes `..transcript.raw.json` in the root. Every media_id of that shape
    collides there, and invariant #1 refuses a *second* write to a path: the collision does not
    surface as a naming bug but as the next clip being rejected for tampering with the first.
    """
    store = TranscriptStore(tmp_path)
    with pytest.raises(ValueError, match="would create a hidden delivery"):
        store.raw_path(media_id)


@pytest.mark.parametrize(
    "media_id",
    [
        "../../etc/passwd",
        "a\\b",  # the separator that matters on the box §6 names, and `/` is the covered one
        "a\x00b",
        "clip..1",  # no separator at all — the `".." in media_id` clause, on its own
    ],
)
def test_a_media_id_that_would_escape_the_store_is_refused(tmp_path: Path, media_id: str) -> None:
    """ "`media_id` reaches here from filenames and job payloads." That is the whole argument:
    the value is not the program's own, and the path is interpolated from it.

    Invariant #1's write-once guarantee is a promise about a path, so a caller who chooses the
    path has the guarantee for nothing. `a/b` is the case already covered; these are the other
    three, and `clip..1` is the one furthest from it — it is caught by a different clause of
    the same line, so no amount of separator testing would have reached it.
    """
    store = TranscriptStore(tmp_path)
    with pytest.raises(
        ValueError,
        match=r"contains a (control, path separator, or reserved filename character|"
        r"parent reference)",
    ):
        store.raw_path(media_id)


def test_an_ordinary_media_id_still_resolves_inside_the_store(tmp_path: Path) -> None:
    """The control. A refusal that rejected every media_id would satisfy both tests above and
    leave the store unable to hold a transcript; `norm_path` is checked too because it derives
    its path from the same helper and would be the way around it.
    """
    store = TranscriptStore(tmp_path)
    for path in (store.raw_path("media-001"), store.norm_path("media-001")):
        assert path.parent == tmp_path
        assert path.name.startswith("media-001.")


# --- what clause-level revert found that line-level could not ---------------------------------
#
# `guardsweep` neutralises a whole `if` line, so a compound condition reads HELD as soon as any
# one clause is covered. Replacing one operand at a time instead — `or` operands with False,
# `and` operands with True, so the rest of the expression still decides — reopened two guards in
# this module that the line-level run had already passed.


@pytest.mark.parametrize("surface", [42, None, ["word"], b"word"])
def test_a_word_whose_surface_is_not_a_string_is_refused_by_type(surface: object) -> None:
    """`not isinstance(self.w, str)` in `if not isinstance(self.w, str) or not self.w.strip():`.

    `bytes` is the case that shows why the clause is there rather than merely tidy: `b"word"`
    has a `.strip()`, it is truthy, and `b"word".splitlines() == [b"word"]`, so without the
    isinstance check it passes every remaining guard and becomes a `Word`. `to_json` then fails
    on it much later, in a different module, about a type nobody chose. The numeric and `None`
    cases fail earlier but no better — `.strip()` on them is an AttributeError from inside the
    constructor rather than a sentence about the word.

    `RawTranscript.from_json` builds `Word(**w)` straight from `transcript.raw.json`, so none of
    these values has to be the program's own.
    """
    with pytest.raises(ValueError, match="surface form must be a non-empty string"):
        Word(w=surface, start_ms=0, end_ms=1, conf=0.5)  # type: ignore[arg-type]


def test_a_transcript_decoded_with_a_fine_tune_is_not_the_same_transcript() -> None:
    """`not self.adapter.strip()` in `if self.adapter is not None and not self.adapter.strip():`.

    The clause was uncovered because nothing here had ever built a provenance with a *real*
    adapter — only a blank one and `None`. Neutralised, the guard fires for every non-None
    adapter, so a mis-written check would reject every fine-tuned transcript in the system and
    the suite would stay green.

    Asserted on the digests rather than on the field, because that is the claim D-181 actually
    makes: the adapter lives in the artifact and not in a log precisely so that "a transcript
    decoded by adapted weights and one decoded by stock weights are different transcripts". If
    the two hash alike, the field is decoration.
    """
    adapter = "lora:3f5a1c9d2e7b4068"
    adapted = AsrProvenance(canonical=CANONICAL_ASR_ID, aligner="ctc_viterbi", adapter=adapter)
    with_lora = RawTranscript(media_id="m", text_ckb="ئه‌مه‌", words=(), asr=adapted)
    stock = RawTranscript(media_id="m", text_ckb="ئه‌مه‌", words=(), asr=CANONICAL)

    assert with_lora.asr.adapter == adapter
    assert RawTranscript.from_json(with_lora.to_json()).asr.adapter == adapter
    assert with_lora.sha256() != stock.sha256(), (
        "a transcript decoded with a fine-tune hashes identically to one decoded with stock "
        "weights — D-181 put the adapter in the artifact so that cannot be true"
    )


CANONICAL = AsrProvenance(canonical="omniASR_LLM_7B_v2", aligner="ctc_viterbi")


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


def _delete_sidecar(path: Path) -> None:
    path.unlink()


def _empty_sidecar(path: Path) -> None:
    path.write_text("", encoding="ascii")


def _whitespace_sidecar(path: Path) -> None:
    path.write_text("   \n", encoding="ascii")


def _non_ascii_sidecar(path: Path) -> None:
    path.write_bytes(b"\xff\xfe not a digest")


def _directory_sidecar(path: Path) -> None:
    path.unlink()
    path.mkdir()


_DIGEST_EVIDENCE_BREAKERS: dict[str, Callable[[Path], None]] = {
    "deleted": _delete_sidecar,
    "empty": _empty_sidecar,
    "whitespace": _whitespace_sidecar,
    "non-ASCII": _non_ascii_sidecar,
    "directory": _directory_sidecar,
}


_DIGEST_EVIDENCE_STATES = tuple(_DIGEST_EVIDENCE_BREAKERS)


_UNREADABLE_DIGEST_EVIDENCE = frozenset({"deleted", "non-ASCII", "directory"})


@pytest.mark.parametrize("state", _DIGEST_EVIDENCE_STATES)
@pytest.mark.parametrize("entry_point", ("verify", "write_norm"))
def test_missing_or_invalid_digest_evidence_refuses_both_verification_doors(
    tmp_path: Path, state: str, entry_point: str
) -> None:
    """Invariant #1 cannot become green by deleting the file that would contradict it."""
    store = TranscriptStore(tmp_path)
    raw = a_raw()
    store.write_raw(raw)
    _DIGEST_EVIDENCE_BREAKERS[state](store._digest_path("media-001"))

    expected_reason = (
        "no readable digest"
        if state in _UNREADABLE_DIGEST_EVIDENCE
        else "no longer matches the digest"
    )
    with pytest.raises(RawTranscriptTampered, match=expected_reason):
        if entry_point == "verify":
            store.verify_raw_integrity("media-001")
        else:
            store.write_norm(normalize_transcript(raw))


@pytest.mark.parametrize("state", _DIGEST_EVIDENCE_STATES)
def test_tampered_raw_stays_refused_after_its_digest_evidence_is_destroyed(
    tmp_path: Path, state: str
) -> None:
    store = TranscriptStore(tmp_path)
    original = a_raw()
    normalized = normalize_transcript(original)
    path = store.write_raw(original)
    path.chmod(0o644)
    path.write_text(a_raw("TAMPERED canonical transcript").to_json(), encoding="utf-8")
    _DIGEST_EVIDENCE_BREAKERS[state](store._digest_path("media-001"))

    expected_reason = (
        "no readable digest"
        if state in _UNREADABLE_DIGEST_EVIDENCE
        else "no longer matches the digest"
    )
    with pytest.raises(RawTranscriptTampered, match=expected_reason):
        store.verify_raw_integrity("media-001")
    with pytest.raises(RawTranscriptTampered, match=expected_reason):
        store.write_norm(normalized)


def test_intact_digest_evidence_still_verifies_and_reuses(tmp_path: Path) -> None:
    store = TranscriptStore(tmp_path)
    expected = a_raw()
    normalized = normalize_transcript(expected)
    store.write_raw(expected)

    store.verify_raw_integrity("media-001")
    store.write_norm(normalized)
    assert store.read_norm("media-001") == normalized


def test_every_declared_digest_evidence_breaker_is_parametrized() -> None:
    assert set(_DIGEST_EVIDENCE_STATES) == set(_DIGEST_EVIDENCE_BREAKERS)
    assert set(_DIGEST_EVIDENCE_BREAKERS) > _UNREADABLE_DIGEST_EVIDENCE


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


def test_rejected_validator_correction_round_trips_without_becoming_a_gap() -> None:
    rejected = RejectedValidatorCorrection(
        start_ms=1_000,
        end_ms=1_316,
        validator="rzgar/qwen3-asr-sorani-kurdish-ckb-v1",
        reason="AlignmentInfeasible: 15 frames cannot emit 21 validator tokens",
    )
    raw = RawTranscript(
        media_id="validator-fallback",
        text_ckb="canonical words remain",
        words=(),
        asr=CANONICAL,
        rejected_validator_corrections=(rejected,),
    )

    restored = RawTranscript.from_json(raw.to_json())

    assert restored == raw
    assert restored.unaligned == ()
    assert restored.rejected_validator_corrections == (rejected,)


# --- D-139: the raw file's own write-once layer was never reached by a test ------------------
