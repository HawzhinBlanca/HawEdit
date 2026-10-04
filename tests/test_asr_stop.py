"""Production stop contracts; injected failures are not canonical-model quality evidence."""

from __future__ import annotations

import hashlib
import json
import wave
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import test_pipeline as pipeline_fixtures
from hawedit.asr import (
    VALIDATOR_MODEL_ID,
    OmniAsrProducer,
    SegmentTranscript,
    _assemble_canonical_transcript,
    _PreparedSpeechSegment,
    _validate_hard_segments,
    transcribe_prepared_segments,
)
from hawedit.asr_worker import run_request
from hawedit.captions import find_ffmpeg
from hawedit.checkpoint import load_stage_checkpoint
from hawedit.discovery import Candidate
from hawedit.events import RunEvent, RunState
from hawedit.judge import JudgeRequest, JudgeVerdict
from hawedit.pipeline import PipelineRun, StageSkipped, run_pipeline
from hawedit.transcripts import (
    NormalizedTranscript,
    RawTranscript,
    RejectedValidatorCorrection,
    TranscriptStore,
    UnalignedSpeech,
    Word,
)


class RegionBackend:
    def __init__(self, *, fail_draft: int = -1, fail_alignment: int = -1) -> None:
        self.fail_draft = fail_draft
        self.fail_alignment = fail_alignment
        self.calls: list[Path] = []
        self.align_calls: list[Path] = []
        self.results: list[SegmentTranscript] = []

    def transcribe_segment(self, audio_path: Path, duration_s: float) -> SegmentTranscript:
        self.calls.append(audio_path)
        if len(self.calls) - 1 == self.fail_draft:
            raise RuntimeError("declared draft failure")
        result = SegmentTranscript("کوردی.", "جیاواز.", (Word("کوردی.", 0, 500, 0.8),), -0.5)
        self.results.append(result)
        return result

    def align_segment(self, audio_path: Path, duration_s: float, text: str) -> SegmentTranscript:
        self.align_calls.append(audio_path)
        if len(self.align_calls) - 1 == self.fail_alignment:
            raise RuntimeError("declared correction alignment failure")
        return SegmentTranscript(text, text, (Word(text, 10, 510, 0.8),), -0.2)


class RegionValidator:
    model_id = VALIDATOR_MODEL_ID

    def __init__(self, fail_at: int = -1) -> None:
        self.fail_at = fail_at
        self.calls: list[Path] = []

    def transcribe_segment(self, audio_path: Path, duration_s: float) -> str:
        self.calls.append(audio_path)
        if len(self.calls) - 1 == self.fail_at:
            raise RuntimeError("declared correction transcription failure")
        return "ڕاستکراوە."


def prepared_regions(root: Path) -> tuple[_PreparedSpeechSegment, ...]:
    regions = []
    for index in range(3):
        path = root / f"speech-{index:04d}.wav"
        with wave.open(str(path), "wb") as stream:
            stream.setparams((1, 2, 16_000, 0, "NONE", "not compressed"))
            stream.writeframes(b"\x00\x00" * 16_000)
        regions.append(_PreparedSpeechSegment(path, index * 1_000, (index + 1) * 1_000))
    return tuple(regions)


def worker_request(root: Path) -> Path:
    regions = prepared_regions(root)
    request = root / "request.json"
    request.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "media_id": "episode",
                "validator_model_dir": "unused-with-injected-validator",
                "segments": [
                    {"path": item.path.name, "start_ms": item.start_ms, "end_ms": item.end_ms}
                    for item in regions
                ],
            }
        ),
        encoding="utf-8",
    )
    return request


@pytest.mark.parametrize("failed_index", [0, 1, 2])
def test_native_production_stops_on_first_asr_failure(tmp_path: Path, failed_index: int) -> None:
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    backend = RegionBackend(fail_draft=failed_index)
    validator = RegionValidator()
    with pytest.raises(RuntimeError, match="declared draft failure"):
        OmniAsrProducer(backend, validator).transcribe(
            "episode",
            pipeline_fixtures.FIXTURE,
            tuple(SimpleNamespace(start_ms=i * 1_000, end_ms=(i + 1) * 1_000) for i in range(3)),
            tmp_path / "stage1",
            ffmpeg=ffmpeg,
        )
    assert len(backend.calls) == failed_index + 1
    assert validator.calls == []
    assert backend.align_calls == []


@pytest.mark.parametrize("failed_index", [0, 1, 2])
def test_worker_production_stops_on_first_asr_failure(tmp_path: Path, failed_index: int) -> None:
    backend = RegionBackend(fail_draft=failed_index)
    validator = RegionValidator()
    output = tmp_path / "output.json"
    with pytest.raises(RuntimeError, match="declared draft failure"):
        run_request(worker_request(tmp_path), output, backend, validator)
    assert len(backend.calls) == failed_index + 1
    assert validator.calls == []
    assert backend.align_calls == []
    assert not output.exists()


@pytest.mark.parametrize("failure_kind", ["transcription", "alignment"])
def test_native_production_stops_on_first_validator_failure(
    tmp_path: Path, failure_kind: str
) -> None:
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    backend = RegionBackend(fail_alignment=1 if failure_kind == "alignment" else -1)
    validator = RegionValidator(fail_at=1 if failure_kind == "transcription" else -1)
    with pytest.raises(RuntimeError, match=f"declared correction {failure_kind} failure"):
        OmniAsrProducer(backend, validator).transcribe(
            "episode",
            pipeline_fixtures.FIXTURE,
            tuple(SimpleNamespace(start_ms=i * 1_000, end_ms=(i + 1) * 1_000) for i in range(3)),
            tmp_path / "stage1",
            ffmpeg=ffmpeg,
        )
    assert len(backend.calls) == 3
    assert len(validator.calls) == 2
    assert len(backend.align_calls) == (2 if failure_kind == "alignment" else 1)


@pytest.mark.parametrize("failure_kind", ["transcription", "alignment"])
def test_worker_production_stops_on_first_validator_failure(
    tmp_path: Path, failure_kind: str
) -> None:
    backend = RegionBackend(fail_alignment=1 if failure_kind == "alignment" else -1)
    validator = RegionValidator(fail_at=1 if failure_kind == "transcription" else -1)
    output = tmp_path / "output.json"
    with pytest.raises(RuntimeError, match=f"declared correction {failure_kind} failure"):
        run_request(worker_request(tmp_path), output, backend, validator)
    assert len(backend.calls) == 3
    assert len(validator.calls) == 2
    assert len(backend.align_calls) == (2 if failure_kind == "alignment" else 1)
    assert not output.exists()


@pytest.mark.parametrize("failure_kind", ["draft", "correction"])
def test_strict_helpers_preserve_diagnostic_inputs_and_failure_kind(
    tmp_path: Path, failure_kind: str
) -> None:
    prepared = prepared_regions(tmp_path)
    backend = RegionBackend(fail_draft=1 if failure_kind == "draft" else -1)
    with pytest.raises(RuntimeError) as caught:
        initial, _ = transcribe_prepared_segments(backend, prepared, stop_on_failure=True)
        _validate_hard_segments(
            initial, backend, lambda: RegionValidator(fail_at=1), stop_on_failure=True
        )
    results = getattr(caught.value, "diagnostic_results", None)
    gaps = getattr(caught.value, "unaligned", None)
    corrections = getattr(caught.value, "rejected_validator_corrections", None)
    assert isinstance(results, tuple)
    assert isinstance(gaps, tuple)
    assert isinstance(corrections, tuple)
    assert [item for _, item in results] == backend.results
    assert (len(gaps), len(corrections)) == ((1, 0) if failure_kind == "draft" else (0, 1))
    diagnostic = _assemble_canonical_transcript(
        "episode", results, gaps, rejected_validator_corrections=corrections
    )
    assert diagnostic.words[0].w == "کوردی."
    assert diagnostic.words[0].start_ms == 0
    assert diagnostic.asr.validated_by is None
    assert isinstance(caught.value.__cause__, RuntimeError)


def damaged_transcript(kind: str) -> RawTranscript:
    raw = pipeline_fixtures.a_transcript("episode")
    return replace(
        raw,
        unaligned=(UnalignedSpeech(1_750, 1_900, "declared alignment failure"),)
        if kind in {"gap", "both"}
        else (),
        rejected_validator_corrections=(
            RejectedValidatorCorrection(
                100, 1_700, VALIDATOR_MODEL_ID, "declared correction failure"
            ),
        )
        if kind in {"correction", "both"}
        else (),
    )


class NeverJudge:
    model_id = "gemini-2.5-pro"

    def judge(self, request: JudgeRequest) -> JudgeVerdict:
        raise AssertionError("damaged transcript reached paid judging")


def never_discover(transcript: NormalizedTranscript) -> tuple[Candidate, ...]:
    raise AssertionError("damaged transcript reached discovery")


def assert_refused(run: PipelineRun, raw: RawTranscript, events: list[RunEvent]) -> None:
    assert isinstance(run.transcript, StageSkipped)
    assert not run.complete
    assert run.transcript_gaps == raw.unaligned
    assert run.rejected_validator_corrections == raw.rejected_validator_corrections
    assert run.clip is None
    assert isinstance(run.index, StageSkipped)
    assert isinstance(run.render, StageSkipped)
    assert isinstance(run.delivery, StageSkipped)
    assert run.billed_calls == ()
    assert [(item.stage, item.state) for item in events if item.stage == "transcript"] == [
        ("transcript", RunState.STARTED),
        ("transcript", RunState.SKIPPED),
    ]
    assert not any(
        item.stage
        in {"visual_windows", "sentences", "index", "discovery", "editorial", "render", "delivery"}
        for item in events
    )


@pytest.mark.parametrize("kind", ["gap", "correction", "both"])
def test_pipeline_refuses_unresolved_transcript_evidence(tmp_path: Path, kind: str) -> None:
    raw = damaged_transcript(kind)
    events: list[RunEvent] = []
    work = tmp_path / "work"
    run = run_pipeline(
        pipeline_fixtures.FIXTURE,
        work,
        media_id="episode",
        transcript=raw,
        discover=never_discover,
        judge=NeverJudge(),
        on_event=events.append,
    )
    assert_refused(run, raw, events)
    store = TranscriptStore(work / "transcripts")
    assert store.read_raw("episode") == raw
    assert not store.norm_path("episode").exists()
    assert load_stage_checkpoint(work, "stage1_transcript") is None


class NeverAsr:
    def __init__(self) -> None:
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
        raise AssertionError(
            "a matching damaged historical raw must be refused without rerunning ASR"
        )


@pytest.mark.parametrize("kind", ["gap", "correction", "both"])
def test_pipeline_refuses_reused_unresolved_transcript_without_rewriting(
    tmp_path: Path, kind: str
) -> None:
    work = tmp_path / "work"
    ingested = run_pipeline(pipeline_fixtures.FIXTURE, work, media_id="episode").ingest
    assert ingested is not None
    assert not isinstance(ingested, StageSkipped)
    raw = damaged_transcript(kind)
    asr = NeverAsr()
    store = TranscriptStore(work / "transcripts")
    store.write_raw(
        raw,
        audio_sha256=hashlib.sha256(Path(ingested.audio_path).read_bytes()).hexdigest(),
        producer=f"{type(asr).__module__}.{type(asr).__qualname__}",
    )
    before = {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in store.root.iterdir()
        if path.is_file()
    }
    events: list[RunEvent] = []
    run = run_pipeline(
        pipeline_fixtures.FIXTURE,
        work,
        media_id="episode",
        asr=asr,
        discover=never_discover,
        judge=NeverJudge(),
        on_event=events.append,
    )
    assert_refused(run, raw, events)
    assert asr.calls == 0
    assert before == {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in store.root.iterdir()
        if path.is_file()
    }
    assert not store.norm_path("episode").exists()
    assert load_stage_checkpoint(work, "stage1_transcript") is None


def test_pipeline_stops_before_visual_work_after_asr_failure(tmp_path: Path) -> None:
    class FailingAsr(NeverAsr):
        def transcribe(
            self,
            media_id: str,
            audio_path: Path,
            speech_segments: object,
            work_dir: Path,
            ffmpeg: Path | None = None,
        ) -> RawTranscript:
            self.calls += 1
            raise RuntimeError("declared production failure")

    events: list[RunEvent] = []
    producer = FailingAsr()
    run = run_pipeline(
        pipeline_fixtures.FIXTURE,
        tmp_path / "work",
        media_id="episode",
        asr=producer,
        discover=never_discover,
        judge=NeverJudge(),
        on_event=events.append,
    )
    assert_refused(run, pipeline_fixtures.a_transcript("episode"), events)
    assert producer.calls == 1
    assert isinstance(run.transcript, StageSkipped)
    assert "declared production failure" in run.transcript.reason
