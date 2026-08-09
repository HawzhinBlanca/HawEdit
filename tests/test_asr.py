"""M0.7 — the ASR adapter boundary and the throughput half of §8.1.

    real-time factor measured on hawapc01 · VRAM · long-audio failure rate

§3 Stage 1 is emphatic about the trap here: Meta's published RTF (0.003 for CTC-3B, 0.092
for LLM-7B) is "batch=1, 30 s audio, BF16, on an A100. Do not derive wall-clock promises for
hawapc01 from them." A throughput number without the hardware it was measured on is not a
weaker number, it is a wrong one — so `Hardware` is required, not optional, and comparing
measurements across hardware is refused.

The real adapters need GPUs this container does not have (M0.11, BLOCKED.md #2). What is
built and tested here is the boundary they plug into, and every measurement records the
adapter class that produced it so a run driven by a test double can never be mistaken for a
run on real weights.
"""

from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from hawedit.asr import (
    LONG_AUDIO_THRESHOLD_S,
    ASRResult,
    Hardware,
    IncomparableHardware,
    MeasurementSession,
    OmniAsrAdapter,
    OmniAsrBackend,
    OmniAsrProducer,
    SegmentTranscript,
    WslOmniAsrProducer,
    _assemble_canonical_transcript,
    _PreparedSpeechSegment,
    create_omni_asr_producer,
    long_audio_failure_rate,
    transcribe_prepared_segments,
    validate_adapter,
)
from hawedit.asr_worker import run_request
from hawedit.corpus import Condition, CorpusItem, Dialect
from hawedit.forced_alignment import AlignmentInfeasible
from hawedit.registry import ModelExcluded, ModelNotInRegistry
from hawedit.transcripts import RawTranscript, Word

HAWAPC01 = Hardware(host="hawapc01", accelerator="2x RTX 3090 Ti", notes="Threadripper 3990X")
AN_A100 = Hardware(host="a100-box", accelerator="A100")


class StubAdapter:
    """A test double. Named so it is obvious in any report it appears in."""

    def __init__(self, model_id: str = "omniASR_LLM_7B_v2", text: str = "ئەمە") -> None:
        self.model_id = model_id
        self._text = text

    def transcribe(self, audio_path: Path, duration_s: float) -> ASRResult:
        return ASRResult(text_raw=self._text)


class FailingAdapter(StubAdapter):
    def transcribe(self, audio_path: Path, duration_s: float) -> ASRResult:
        raise RuntimeError("model refused a 62 s input")


def an_item(item_id: str = "itm-001", duration_s: float = 30.0) -> CorpusItem:
    return CorpusItem(
        item_id=item_id,
        audio_path=f"audio/{item_id}.wav",
        reference_ckb="ئەمە زۆر باشە",
        dialect=Dialect.HEWLER,
        conditions=frozenset({Condition.FORMAL_NEWS}),
        duration_s=duration_s,
    )


class FakeClock:
    def __init__(self, step: float) -> None:
        self._now = 0.0
        self._step = step

    def __call__(self) -> float:
        now = self._now
        self._now += self._step
        return now


# --- the adapter boundary is the §7 boundary ------------------------------------------


def test_an_adapter_for_an_unregistered_model_is_refused() -> None:
    with pytest.raises(ModelNotInRegistry):
        validate_adapter(StubAdapter(model_id="openai/whisper-large-v3"))


def test_an_adapter_for_an_excluded_model_is_refused() -> None:
    with pytest.raises(ModelExcluded):
        validate_adapter(StubAdapter(model_id="RevgeAI/vekol-stt-ckb-small"))


def test_an_adapter_for_a_registered_model_is_accepted() -> None:
    assert validate_adapter(StubAdapter()).role == "canonical_asr"


# --- measurement ----------------------------------------------------------------------


def test_a_measurement_records_wall_clock_and_real_time_factor() -> None:
    session = MeasurementSession(hardware=HAWAPC01, clock=FakeClock(step=3.0))
    measurement = session.measure(StubAdapter(), an_item(duration_s=30.0))
    assert measurement.wall_clock_s == pytest.approx(3.0)
    assert measurement.rtf == pytest.approx(0.1)


def test_a_measurement_names_the_adapter_that_produced_it() -> None:
    """A run driven by a test double must be self-evident in the report."""
    session = MeasurementSession(hardware=HAWAPC01, clock=FakeClock(step=1.0))
    assert session.measure(StubAdapter(), an_item()).adapter_impl == "test_asr.StubAdapter", (
        "the adapter must be identified by module too — a bare class name is forgeable"
    )


def test_a_failing_adapter_is_recorded_not_raised() -> None:
    """§8.1 measures a long-audio *failure rate*, so failure is data, not an abort."""
    session = MeasurementSession(hardware=HAWAPC01, clock=FakeClock(step=1.0))
    measurement = session.measure(FailingAdapter(), an_item(duration_s=62.0))
    assert measurement.failed
    assert measurement.result is None
    assert "62 s" in (measurement.error or "")


def test_vram_is_none_without_a_probe_never_zero() -> None:
    """Zero VRAM would read as a measured result. This ran on a box with no GPU."""
    session = MeasurementSession(hardware=HAWAPC01, clock=FakeClock(step=1.0))
    assert session.measure(StubAdapter(), an_item()).peak_vram_bytes is None


def test_vram_comes_from_the_probe_when_one_is_supplied() -> None:
    session = MeasurementSession(
        hardware=HAWAPC01, clock=FakeClock(step=1.0), vram_probe=lambda: 17 * 1024**3
    )
    assert session.measure(StubAdapter(), an_item()).peak_vram_bytes == 17 * 1024**3


# --- hardware provenance --------------------------------------------------------------


def test_hardware_must_be_named() -> None:
    with pytest.raises(ValueError, match="host"):
        Hardware(host="  ", accelerator="2x RTX 3090 Ti")


def test_measurements_from_different_hardware_refuse_to_be_compared() -> None:
    """§3 Stage 1: an A100 RTF is not a 3090 Ti RTF, and averaging them invents a number."""
    on_hawapc01 = MeasurementSession(hardware=HAWAPC01, clock=FakeClock(step=3.0)).measure(
        StubAdapter(), an_item()
    )
    on_a100 = MeasurementSession(hardware=AN_A100, clock=FakeClock(step=1.0)).measure(
        StubAdapter(), an_item()
    )
    with pytest.raises(IncomparableHardware, match="hawapc01"):
        long_audio_failure_rate([on_hawapc01, on_a100])


# --- long-audio failure rate ----------------------------------------------------------


def test_long_audio_threshold_is_the_omniasr_interface_limit() -> None:
    """§3 Stage 1: the 40 s ceiling is what VAD's 38 s max_speech_duration_s stays under."""
    assert LONG_AUDIO_THRESHOLD_S == 40.0


def test_long_audio_failure_rate_counts_only_long_items() -> None:
    session = MeasurementSession(hardware=HAWAPC01, clock=FakeClock(step=1.0))
    measurements = [
        session.measure(FailingAdapter(), an_item("short-fail", duration_s=10.0)),
        session.measure(FailingAdapter(), an_item("long-fail", duration_s=62.0)),
        session.measure(StubAdapter(), an_item("long-ok", duration_s=55.0)),
    ]
    assert long_audio_failure_rate(measurements) == pytest.approx(0.5)


def test_long_audio_failure_rate_is_none_when_nothing_was_long() -> None:
    """Unmeasured is not 0.0 — a corpus of 30 s clips says nothing about long-audio."""
    session = MeasurementSession(hardware=HAWAPC01, clock=FakeClock(step=1.0))
    measurements = [session.measure(StubAdapter(), an_item(duration_s=30.0))]
    assert long_audio_failure_rate(measurements) is None


def test_long_audio_failure_rate_of_an_empty_run_is_none() -> None:
    assert long_audio_failure_rate([]) is None


class FakeOmniBackend:
    def transcribe_segment(self, audio_path: Path, duration_s: float) -> SegmentTranscript:
        assert audio_path.exists()
        return SegmentTranscript(
            text_raw="کوردی.",
            words=(Word(w="کوردی.", start_ms=50, end_ms=500, conf=0.9),),
            mean_logprob=-0.1,
        )


def test_canonical_omni_adapter_is_runnable_by_the_real_benchmark(tmp_path: Path) -> None:
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"wav")
    result = OmniAsrAdapter(FakeOmniBackend()).transcribe(audio, 1.0)
    assert result.text_raw == "کوردی."
    assert result.words[0].w == "کوردی."


def test_llm_and_ctc_forwards_start_in_parallel() -> None:
    llm_started = threading.Event()
    ctc_started = threading.Event()

    class Llm:
        def transcribe(self, *_args: object, **_kwargs: object) -> list[str]:
            llm_started.set()
            assert ctc_started.wait(1), "CTC did not start while LLM was running"
            return ["کوردی."]

    class Backend(OmniAsrBackend):
        def _load(self) -> tuple[object, object]:
            return Llm(), object()

        def _ctc_emissions(self, pipeline: object, audio_path: Path) -> tuple[object, int]:
            ctc_started.set()
            assert llm_started.wait(1), "LLM did not start while CTC was running"
            return object(), 10

        def _align_emissions(
            self,
            pipeline: object,
            log_probs: object,
            frame_count: int,
            text: str,
            duration_s: float,
        ) -> tuple[Word, ...]:
            return (Word(text, 0, round(duration_s * 1_000), 0.9),)

    result = Backend().transcribe_segment(Path("segment.wav"), 1.0)
    assert result.text_raw == "کوردی."


def test_canonical_producer_runs_vad_segments_and_shifts_ctc_words(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        Path(args[-1]).write_bytes(b"wav")
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr("hawedit.asr.subprocess.run", fake_run)
    producer = OmniAsrProducer(FakeOmniBackend())
    transcript = producer.transcribe(
        "media",
        tmp_path / "audio.wav",
        (
            SimpleNamespace(start_ms=1_000, end_ms=2_000),
            SimpleNamespace(start_ms=3_000, end_ms=4_000),
        ),
        tmp_path / "stage1",
        ffmpeg=tmp_path / "ffmpeg",
    )
    assert transcript.text_ckb == "کوردی.\nکوردی."
    assert [(word.start_ms, word.end_ms) for word in transcript.words] == [
        (1_050, 1_500),
        (3_050, 3_500),
    ]
    assert transcript.asr.canonical == "omniASR_LLM_7B_v2"
    assert transcript.asr.aligner == "ctc_viterbi"


def test_canonical_producer_refuses_an_empty_vad_result(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="no Stage 0 speech"):
        OmniAsrProducer(FakeOmniBackend()).transcribe(
            "media", tmp_path / "audio.wav", (), tmp_path / "stage1", ffmpeg=tmp_path / "ffmpeg"
        )


def test_wsl_worker_loads_one_backend_and_publishes_canonical_transcript(tmp_path: Path) -> None:
    segment = tmp_path / "speech-0000.wav"
    segment.write_bytes(b"wav")
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "media_id": "episode",
                "segments": [{"path": segment.name, "start_ms": 1_000, "end_ms": 2_000}],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "output.json"
    transcript = run_request(request, output, FakeOmniBackend())
    assert transcript.text_ckb == "کوردی."
    assert [(word.start_ms, word.end_ms) for word in transcript.words] == [(1_050, 1_500)]
    assert output.is_file()
    assert output.read_text(encoding="utf-8").endswith("\n")


def test_wsl_worker_rejects_a_segment_outside_the_shared_directory(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.wav"
    outside.write_bytes(b"wav")
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "media_id": "episode",
                "segments": [{"path": "../outside.wav", "start_ms": 1_000, "end_ms": 2_000}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="escapes"):
        run_request(request, tmp_path / "output.json", FakeOmniBackend())


def test_windows_wsl_producer_cuts_locally_then_invokes_one_worker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worker_calls: list[list[str]] = []
    stage1 = tmp_path / "stage1"

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        if "wslpath" in args:
            return subprocess.CompletedProcess(args, 0, b"/mnt/c/shared\n", b"")
        if "hawedit.asr_worker" in args:
            worker_calls.append(args)
            transcript = run_request(
                stage1 / "omni-asr-request.json",
                stage1 / "omni-asr-worker-output.json",
                FakeOmniBackend(),
            )
            assert transcript.media_id == "episode"
            return subprocess.CompletedProcess(args, 0, b"", b"")
        Path(args[-1]).write_bytes(b"wav")
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr("hawedit.asr.subprocess.run", fake_run)
    transcript = WslOmniAsrProducer(interpreter="/opt/hawedit/python").transcribe(
        "episode",
        tmp_path / "audio.wav",
        (SimpleNamespace(start_ms=1_000, end_ms=2_000),),
        stage1,
        ffmpeg=tmp_path / "ffmpeg",
    )
    assert transcript.words[0].start_ms == 1_050
    assert len(worker_calls) == 1
    assert worker_calls[0][0] == "wsl.exe"
    assert "/opt/hawedit/python" in worker_calls[0]


def test_omni_runtime_selection_is_explicit() -> None:
    assert isinstance(create_omni_asr_producer("local"), OmniAsrProducer)
    assert isinstance(create_omni_asr_producer("wsl"), WslOmniAsrProducer)
    with pytest.raises(ValueError, match="auto, local, wsl"):
        create_omni_asr_producer("remote")


# --- D-103: one unalignable region used to discard a whole 38-minute run ---------------------


class _RefusingOnOneSegment:
    """Transcribes every region except the one whose audio is too short for its tokens.

    Mirrors what the real stack did on `ZAR38MinTest.mp4`: 547 regions cut, one 316 ms region
    produced 15 CTC frames for 15 tokens, and `AlignmentInfeasible` refused.
    """

    def __init__(self, failing_stem: str) -> None:
        self.failing_stem = failing_stem
        self.seen: list[str] = []

    def transcribe_segment(self, audio_path: Path, duration_s: float) -> SegmentTranscript:
        self.seen.append(audio_path.stem)
        if audio_path.stem == self.failing_stem:
            raise AlignmentInfeasible(
                "15 frames cannot emit 15 tokens: CTC needs at least 17 frames"
            )
        return SegmentTranscript(
            text_raw="کوردی.",
            words=(Word(w="کوردی.", start_ms=50, end_ms=500, conf=0.9),),
            mean_logprob=-0.1,
        )


def _regions(tmp_path: Path, count: int) -> tuple[_PreparedSpeechSegment, ...]:
    prepared = []
    for index in range(count):
        path = tmp_path / f"speech-{index:04d}.wav"
        path.write_bytes(b"wav")
        prepared.append(_PreparedSpeechSegment(path, index * 1_000, index * 1_000 + 600))
    return tuple(prepared)


def test_one_unalignable_region_does_not_discard_the_others(tmp_path: Path) -> None:
    """Measured before the fix: the run raised and 38 minutes of Kurdish produced nothing.

    `AlignmentInfeasible` is correct — inventing a word boundary is what invariant #5 forbids —
    so the refusal stays and the blast radius shrinks to the one region. D-103.
    """
    prepared = _regions(tmp_path, 5)
    backend = _RefusingOnOneSegment("speech-0002")

    results, unaligned = transcribe_prepared_segments(backend, prepared)

    assert len(results) == 4, "the other four regions must still be transcribed"
    assert len(backend.seen) == 5, "the failure must not stop the loop"
    assert [gap.start_ms for gap in unaligned] == [2_000]
    assert "AlignmentInfeasible" in unaligned[0].reason
    assert "17 frames" in unaligned[0].reason, "the reason must survive into the record"


def test_the_written_transcript_says_which_speech_it_does_not_contain(tmp_path: Path) -> None:
    """Asserted on the artifact. A short transcript with no record of the gap is worse than the
    refusal it replaced: the client cannot tell missing speech from silence that was never there.
    """
    prepared = _regions(tmp_path, 3)
    results, unaligned = transcribe_prepared_segments(
        _RefusingOnOneSegment("speech-0001"), prepared
    )
    transcript = _assemble_canonical_transcript("zar38", results, unaligned)

    document = json.loads(transcript.to_json())
    assert document["unaligned"] == [
        {
            "start_ms": 1_000,
            "end_ms": 1_600,
            "reason": document["unaligned"][0]["reason"],
        }
    ]
    assert "AlignmentInfeasible" in document["unaligned"][0]["reason"]
    assert RawTranscript.from_json(transcript.to_json()) == transcript


def test_a_run_where_nothing_aligned_is_refused_rather_than_written_empty(tmp_path: Path) -> None:
    """The control on the other side. "Record failures and continue" must not become "write an
    empty transcript": a file with no words and no text is not a transcript, and it would sail
    past every downstream stage as though the media had no speech.
    """
    prepared = _regions(tmp_path, 2)

    class RefusingAlways:
        def transcribe_segment(self, audio_path: Path, duration_s: float) -> SegmentTranscript:
            raise AlignmentInfeasible("no frames at all")

    results, unaligned = transcribe_prepared_segments(RefusingAlways(), prepared)
    assert results == ()
    with pytest.raises(RuntimeError, match="aligned none of 2 speech regions"):
        _assemble_canonical_transcript("zar38", results, unaligned)


def test_a_clean_run_records_no_gaps_at_all(tmp_path: Path) -> None:
    """The control. A helper that reported every region as unaligned would satisfy the tests
    above and quietly empty every transcript this project has ever produced.
    """
    prepared = _regions(tmp_path, 4)
    results, unaligned = transcribe_prepared_segments(FakeOmniBackend(), prepared)

    assert len(results) == 4
    assert unaligned == ()
    transcript = _assemble_canonical_transcript("zar38", results, unaligned)
    assert transcript.unaligned == ()
    assert json.loads(transcript.to_json())["unaligned"] == []
