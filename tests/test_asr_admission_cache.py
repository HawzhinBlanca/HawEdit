"""Cache plumbing tests; policy labels do not certify native speech fidelity."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

import test_pipeline as pipeline_fixtures
import test_transcripts as transcript_fixtures
from hawedit.pipeline import run_pipeline
from hawedit.transcripts import RawTranscript, RawTranscriptImmutable, TranscriptStore

POLICY = "natural-eos-test-policy-v1"


def snapshot(root: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in root.glob("*.transcript.raw.*")}


def test_qwen_policy_refuses_legacy_canonical_cache(tmp_path: Path) -> None:
    from hawedit.asr import ASR_COMPLETION_POLICY_ID, CONTEXT_GROUPING_POLICY_ID
    from hawedit.asr_completion import COMPLETION_POLICY_ID
    from hawedit.transcripts import normalize_transcript

    store = TranscriptStore(tmp_path)
    raw = transcript_fixtures.a_raw()
    store.write_raw(
        raw,
        audio_sha256="audio",
        producer="producer",
        admission_policy=COMPLETION_POLICY_ID + "+" + CONTEXT_GROUPING_POLICY_ID,
    )
    store.write_norm(normalize_transcript(raw, store.raw_digest(raw.media_id)))
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    with pytest.raises(RawTranscriptImmutable, match="admission.*new work directory"):
        store.reusable_raw(
            raw.media_id,
            "audio",
            "producer",
            transcript_fixtures.MEDIA_SHA256,
            admission_policy=ASR_COMPLETION_POLICY_ID + "+" + CONTEXT_GROUPING_POLICY_ID,
        )
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before
    assert store.read_raw(raw.media_id) == raw
    assert store.read_norm(raw.media_id).source_sha256 == store.raw_digest(raw.media_id)


@pytest.mark.parametrize(
    "provenance", ["legacy", "absent", "malformed", "invalid-utf8", "wrong-policy"]
)
def test_required_admission_policy_refuses_legacy_cache(tmp_path: Path, provenance: str) -> None:
    store = TranscriptStore(tmp_path)
    store.write_raw(transcript_fixtures.a_raw(), audio_sha256="audio", producer="producer")
    sidecar = tmp_path / "media-001.transcript.raw.provenance.json"
    if provenance == "absent":
        sidecar.unlink()
    elif provenance == "malformed":
        sidecar.write_text('{"broken', encoding="utf-8")
    elif provenance == "invalid-utf8":
        sidecar.write_bytes(b"\xff\xfe")
    elif provenance == "wrong-policy":
        record = json.loads(sidecar.read_text(encoding="utf-8"))
        record["admission_policy"] = "different"
        sidecar.write_text(json.dumps(record), encoding="utf-8")
    before = snapshot(tmp_path)
    with pytest.raises(RawTranscriptImmutable, match="admission.*new work directory"):
        store.reusable_raw(
            "media-001",
            "audio",
            "producer",
            transcript_fixtures.MEDIA_SHA256,
            admission_policy=POLICY,
        )
    assert snapshot(tmp_path) == before


def test_matching_admission_policy_reuses_verified_cache(tmp_path: Path) -> None:
    store = TranscriptStore(tmp_path)
    raw = transcript_fixtures.a_raw()
    store.write_raw(raw, audio_sha256="audio", producer="producer", admission_policy=POLICY)
    before = snapshot(tmp_path)
    assert (
        store.reusable_raw(
            "media-001",
            "audio",
            "producer",
            transcript_fixtures.MEDIA_SHA256,
            admission_policy=POLICY,
        )
        == raw
    )
    assert snapshot(tmp_path) == before


def test_admission_validation_uses_one_provenance_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = TranscriptStore(tmp_path)
    raw = transcript_fixtures.a_raw()
    store.write_raw(raw, audio_sha256="audio", producer="producer", admission_policy=POLICY)
    sidecar = tmp_path / "media-001.transcript.raw.provenance.json"
    original = Path.read_text
    reads: list[Path] = []

    def counted(path: Path, encoding: str | None = None, errors: str | None = None) -> str:
        if path == sidecar:
            reads.append(path)
        return original(path, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", counted)
    assert (
        store.reusable_raw(
            "media-001",
            "audio",
            "producer",
            transcript_fixtures.MEDIA_SHA256,
            admission_policy=POLICY,
        )
        == raw
    )
    assert reads == [sidecar]


@pytest.mark.parametrize("changed", ["audio", "producer", "media", "policy"])
def test_required_admission_policy_refuses_changed_cache_identity(
    tmp_path: Path, changed: str
) -> None:
    store = TranscriptStore(tmp_path)
    store.write_raw(
        transcript_fixtures.a_raw(),
        audio_sha256="audio",
        producer="producer",
        admission_policy=POLICY,
    )
    before = snapshot(tmp_path)
    with pytest.raises(RawTranscriptImmutable):
        store.reusable_raw(
            "media-001",
            "changed" if changed == "audio" else "audio",
            "changed" if changed == "producer" else "producer",
            "1" * 64 if changed == "media" else transcript_fixtures.MEDIA_SHA256,
            admission_policy="changed" if changed == "policy" else POLICY,
        )
    assert snapshot(tmp_path) == before


def test_admission_record_cannot_relabel_existing_raw(tmp_path: Path) -> None:
    store = TranscriptStore(tmp_path)
    raw = transcript_fixtures.a_raw()
    store.write_raw(raw, audio_sha256="audio", producer="producer")
    before = snapshot(tmp_path)
    with pytest.raises(RawTranscriptImmutable):
        store.write_raw(raw, audio_sha256="audio", producer="producer", admission_policy=POLICY)
    assert snapshot(tmp_path) == before


def test_required_admission_policy_refuses_orphaned_publication(tmp_path: Path) -> None:
    store = TranscriptStore(tmp_path)
    (tmp_path / "media-001.transcript.raw.sha256").write_text("0" * 64, encoding="ascii")
    before = snapshot(tmp_path)
    with pytest.raises(RawTranscriptImmutable, match="admission"):
        store.reusable_raw(
            "media-001",
            "audio",
            "producer",
            transcript_fixtures.MEDIA_SHA256,
            admission_policy=POLICY,
        )
    assert snapshot(tmp_path) == before


def test_admission_policy_requires_complete_producer_provenance(tmp_path: Path) -> None:
    store = TranscriptStore(tmp_path)
    with pytest.raises(ValueError, match="audio.*producer"):
        store.write_raw(transcript_fixtures.a_raw(), admission_policy=POLICY)
    assert snapshot(tmp_path) == {}


class CountingProducer:
    def __init__(self, policy: str | None) -> None:
        self.admission_policy = policy
        self.calls = 0

    def transcribe(
        self,
        media_id: str,
        audio_path: Path,
        speech_segments: object,
        work_dir: Path,
        ffmpeg: Path | None = None,
    ) -> RawTranscript:
        self.calls += 1
        return replace(pipeline_fixtures.a_transcript(media_id), media_id=media_id)


def test_pipeline_refuses_legacy_admission_before_inference(tmp_path: Path) -> None:
    work = tmp_path / "work"
    producer = CountingProducer(None)
    run_pipeline(pipeline_fixtures.FIXTURE, work, media_id="probe", asr=producer)
    before = snapshot(work / "transcripts")
    producer.admission_policy = POLICY
    with pytest.raises(RawTranscriptImmutable, match="admission"):
        run_pipeline(pipeline_fixtures.FIXTURE, work, media_id="probe", asr=producer)
    assert producer.calls == 1
    assert snapshot(work / "transcripts") == before


def test_pipeline_reuses_matching_admission_policy(tmp_path: Path) -> None:
    work = tmp_path / "work"
    producer = CountingProducer(POLICY)
    run_pipeline(pipeline_fixtures.FIXTURE, work, media_id="probe", asr=producer)
    sidecar = work / "transcripts/probe.transcript.raw.provenance.json"
    assert json.loads(sidecar.read_text(encoding="utf-8"))["admission_policy"] == POLICY
    before = snapshot(work / "transcripts")
    run_pipeline(pipeline_fixtures.FIXTURE, work, media_id="probe", asr=producer)
    assert producer.calls == 1
    assert snapshot(work / "transcripts") == before


def test_qwen_v2_policy_preserves_and_refuses_v1_canonical_cache(tmp_path: Path) -> None:
    from hawedit.asr import ASR_COMPLETION_POLICY_ID, CONTEXT_GROUPING_POLICY_ID
    from hawedit.asr_completion import COMPLETION_POLICY_ID
    from hawedit.qwen_completion import QWEN_COMPLETION_POLICY_ID
    from hawedit.transcripts import normalize_transcript

    assert QWEN_COMPLETION_POLICY_ID.startswith("qwen-natural-eos-greedy-before512-v2:")
    previous = "qwen-natural-eos-greedy-before512-v1:" + QWEN_COMPLETION_POLICY_ID.split(":")[1]
    store = TranscriptStore(tmp_path)
    raw = transcript_fixtures.a_raw()
    store.write_raw(
        raw,
        audio_sha256="audio",
        producer="producer",
        admission_policy=COMPLETION_POLICY_ID + "+" + previous + "+" + CONTEXT_GROUPING_POLICY_ID,
    )
    store.write_norm(normalize_transcript(raw, store.raw_digest(raw.media_id)))
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    with pytest.raises(RawTranscriptImmutable, match="admission.*new work directory"):
        store.reusable_raw(
            raw.media_id,
            "audio",
            "producer",
            transcript_fixtures.MEDIA_SHA256,
            admission_policy=ASR_COMPLETION_POLICY_ID + "+" + CONTEXT_GROUPING_POLICY_ID,
        )
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before
    assert store.read_raw(raw.media_id) == raw
    assert store.read_norm(raw.media_id).source_sha256 == store.raw_digest(raw.media_id)
