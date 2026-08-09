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
import sys
import threading
import wave
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
    QwenSoraniValidator,
    SegmentTranscript,
    WslOmniAsrProducer,
    create_omni_asr_producer,
    long_audio_failure_rate,
    validate_adapter,
)
from hawedit.asr_worker import run_request
from hawedit.corpus import Condition, CorpusItem, Dialect
from hawedit.registry import ModelExcluded, ModelNotInRegistry
from hawedit.transcripts import Word

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
    assert session.measure(StubAdapter(), an_item()).adapter_impl == "StubAdapter"


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
            ctc_text="کوردی.",
            words=(Word(w="کوردی.", start_ms=50, end_ms=500, conf=0.9),),
            mean_logprob=-0.1,
        )

    def align_segment(self, audio_path: Path, duration_s: float, text: str) -> SegmentTranscript:
        assert audio_path.exists()
        return SegmentTranscript(
            text_raw=text,
            ctc_text=text,
            words=(Word(w=text, start_ms=50, end_ms=500, conf=0.9),),
            mean_logprob=-0.1,
        )


def _write_pcm(path: Path, duration_s: float = 1.0) -> None:
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16_000)
        stream.writeframes(b"\0\0" * round(duration_s * 16_000))


def _write_requested_pcm(args: list[str]) -> None:
    duration_s = float(args[args.index("-t") + 1])
    _write_pcm(Path(args[-1]), duration_s)


def test_canonical_omni_adapter_is_runnable_by_the_real_benchmark(tmp_path: Path) -> None:
    audio = tmp_path / "clip.wav"
    _write_pcm(audio)
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

        def _ctc_emissions(self, pipeline: object, audio_path: Path) -> tuple[object, int, str]:
            ctc_started.set()
            assert llm_started.wait(1), "LLM did not start while CTC was running"
            return object(), 10, "کوردی."

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
        _write_requested_pcm(args)
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


def test_canonical_producer_scales_alignment_to_the_emitted_pcm_not_vad_overshoot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    observed_durations: list[float] = []

    class DurationBackend(FakeOmniBackend):
        def transcribe_segment(self, audio_path: Path, duration_s: float) -> SegmentTranscript:
            observed_durations.append(duration_s)
            end_ms = round(duration_s * 1_000)
            return SegmentTranscript(
                text_raw="کوردی.",
                ctc_text="کوردی.",
                words=(Word("کوردی.", 0, end_ms, 0.9),),
                mean_logprob=-0.1,
            )

    def shortened_cut(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        _write_pcm(Path(args[-1]), 0.982)
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr("hawedit.asr.subprocess.run", shortened_cut)
    transcript = OmniAsrProducer(DurationBackend()).transcribe(
        "media",
        tmp_path / "audio.wav",
        (SimpleNamespace(start_ms=1_000, end_ms=2_000),),
        tmp_path / "stage1",
        ffmpeg=tmp_path / "ffmpeg",
    )
    assert observed_durations == [pytest.approx(0.982)]
    assert transcript.words[-1].end_ms == 1_982


def test_canonical_producer_refuses_an_empty_vad_result(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="no Stage 0 speech"):
        OmniAsrProducer(FakeOmniBackend()).transcribe(
            "media", tmp_path / "audio.wav", (), tmp_path / "stage1", ffmpeg=tmp_path / "ffmpeg"
        )


def test_wsl_worker_loads_one_backend_and_publishes_canonical_transcript(tmp_path: Path) -> None:
    segment = tmp_path / "speech-0000.wav"
    _write_pcm(segment)
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "media_id": "episode",
                "validator_model_dir": "unused-in-agreeing-control",
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
    _write_pcm(outside)
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "media_id": "episode",
                "validator_model_dir": "unused-in-agreeing-control",
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
    validator_dir = tmp_path / "validator"
    validator_dir.mkdir()

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
        _write_requested_pcm(args)
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr("hawedit.asr.subprocess.run", fake_run)
    transcript = WslOmniAsrProducer(
        interpreter="/opt/hawedit/python", validator_model_dir=validator_dir
    ).transcribe(
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


class FakeValidator:
    model_id = "rzgar/qwen3-asr-sorani-kurdish-ckb-v1"

    def __init__(self, text: str = "ڕاستکراوە.") -> None:
        self.text = text
        self.calls: list[Path] = []

    def transcribe_segment(self, audio_path: Path, duration_s: float) -> str:
        self.calls.append(audio_path)
        return self.text


class RoutingBackend:
    def __init__(self, scores: tuple[float, ...], *, disagree_at: int | None = None) -> None:
        self.scores = scores
        self.disagree_at = disagree_at
        self.align_calls: list[tuple[Path, str]] = []

    @staticmethod
    def _index(audio_path: Path) -> int:
        return int(audio_path.stem.rsplit("-", 1)[1])

    def transcribe_segment(self, audio_path: Path, duration_s: float) -> SegmentTranscript:
        index = self._index(audio_path)
        text = f"دەقی{index}."
        ctc_text = "جیاواز." if index == self.disagree_at else text
        return SegmentTranscript(
            text_raw=text,
            ctc_text=ctc_text,
            words=(Word(text, 0, 500, 0.9),),
            mean_logprob=self.scores[index],
        )

    def align_segment(self, audio_path: Path, duration_s: float, text: str) -> SegmentTranscript:
        self.align_calls.append((audio_path, text))
        return SegmentTranscript(
            text_raw=text,
            ctc_text="جیاواز.",
            words=(Word(text, 10, 510, 0.8),),
            mean_logprob=-0.2,
        )


def _fake_ffmpeg(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
    _write_requested_pcm(args)
    return subprocess.CompletedProcess(args, 0, b"", b"")


def test_stage1_routes_the_bottom_quartile_to_the_real_validator_seam(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("hawedit.asr.subprocess.run", _fake_ffmpeg)
    backend = RoutingBackend((-0.1, -2.0, -0.2, -0.3))
    validator = FakeValidator()
    transcript = OmniAsrProducer(backend, validator).transcribe(
        "episode",
        tmp_path / "audio.wav",
        tuple(SimpleNamespace(start_ms=i * 1_000, end_ms=(i + 1) * 1_000) for i in range(4)),
        tmp_path / "stage1",
        ffmpeg=tmp_path / "ffmpeg",
    )
    assert transcript.text_ckb.splitlines() == ["دەقی0.", "ڕاستکراوە.", "دەقی2.", "دەقی3."]
    assert [path.name for path in validator.calls] == ["speech-0001.wav"]
    assert [(path.name, text) for path, text in backend.align_calls] == [
        ("speech-0001.wav", "ڕاستکراوە.")
    ]
    assert transcript.words[1].w == "ڕاستکراوە."
    assert transcript.words[1].start_ms == 1_010
    assert transcript.asr.validated_by == validator.model_id


def test_stage1_routes_material_disagreement_even_without_a_confidence_quartile(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("hawedit.asr.subprocess.run", _fake_ffmpeg)
    backend = RoutingBackend((-0.1,), disagree_at=0)
    validator = FakeValidator()
    transcript = OmniAsrProducer(backend, validator).transcribe(
        "episode",
        tmp_path / "audio.wav",
        (SimpleNamespace(start_ms=0, end_ms=1_000),),
        tmp_path / "stage1",
        ffmpeg=tmp_path / "ffmpeg",
    )
    assert transcript.text_ckb == "ڕاستکراوە."
    assert len(validator.calls) == 1


def test_wsl_worker_applies_the_same_validator_routing_contract(tmp_path: Path) -> None:
    segment = tmp_path / "speech-0000.wav"
    _write_pcm(segment)
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "media_id": "episode",
                "validator_model_dir": "unused-with-injected-validator",
                "segments": [{"path": segment.name, "start_ms": 2_000, "end_ms": 3_000}],
            }
        ),
        encoding="utf-8",
    )
    backend = RoutingBackend((-0.1,), disagree_at=0)
    validator = FakeValidator()
    transcript = run_request(request, tmp_path / "output.json", backend, validator)
    assert transcript.text_ckb == "ڕاستکراوە."
    assert transcript.words[0].start_ms == 2_010
    assert transcript.asr.validated_by == validator.model_id


def test_stage1_does_not_load_validator_weights_when_no_segment_is_selected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("hawedit.asr.subprocess.run", _fake_ffmpeg)
    backend = RoutingBackend((-0.1, -0.2, -0.3))
    transcript = OmniAsrProducer(backend).transcribe(
        "episode",
        tmp_path / "audio.wav",
        tuple(SimpleNamespace(start_ms=i * 1_000, end_ms=(i + 1) * 1_000) for i in range(3)),
        tmp_path / "stage1",
        ffmpeg=tmp_path / "ffmpeg",
    )
    assert transcript.asr.validated_by is None
    assert backend.align_calls == []


def test_qwen_validator_uses_the_official_loader_and_model_card_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    model_dir = tmp_path / "validator"
    model_dir.mkdir()
    (model_dir / "config.json").write_text(
        json.dumps({"model_type": "qwen3_asr"}), encoding="utf-8"
    )
    audio = tmp_path / "segment.wav"
    _write_pcm(audio)
    loaded: dict[str, object] = {}

    class Model:
        def transcribe(self, **kwargs: object) -> list[SimpleNamespace]:
            loaded["transcribe"] = kwargs
            return [SimpleNamespace(text="سۆرانی.")]

    class Loader:
        @staticmethod
        def from_pretrained(path: str, **kwargs: object) -> Model:
            loaded["path"] = path
            loaded["kwargs"] = kwargs
            return Model()

    torch = SimpleNamespace(bfloat16="bf16", cuda=SimpleNamespace(is_available=lambda: True))
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "qwen_asr", SimpleNamespace(Qwen3ASRModel=Loader))
    integrity_calls: list[tuple[str, Path]] = []
    monkeypatch.setattr(
        "hawedit.asr.assert_checkpoint_integrity",
        lambda model_id, path: integrity_calls.append((model_id, path)),
    )
    validator = QwenSoraniValidator(model_dir)
    assert validator.transcribe_segment(audio, 1.0) == "سۆرانی."
    assert loaded["path"] == str(model_dir)
    assert loaded["kwargs"] == {
        "dtype": "bf16",
        "device_map": "cuda:1",
        "max_inference_batch_size": 1,
    }
    assert loaded["transcribe"] == {"audio": str(audio)}
    assert integrity_calls == [(validator.model_id, model_dir)]


def test_qwen_validator_refuses_a_code_loading_config_before_imports(tmp_path: Path) -> None:
    from hawedit.models import UnsafeModelConfig

    model_dir = tmp_path / "validator"
    model_dir.mkdir()
    (model_dir / "config.json").write_text(
        json.dumps(
            {
                "model_type": "qwen3_asr",
                "_attn_implementation_internal": "attacker/kernel",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(UnsafeModelConfig, match="CVE-2026-4372"):
        QwenSoraniValidator(model_dir)._load()


def test_qwen_validator_uses_the_asr_model_type_allowlist(tmp_path: Path) -> None:
    model_dir = tmp_path / "validator"
    model_dir.mkdir()
    (model_dir / "config.json").write_text(json.dumps({"model_type": "xclip"}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="unapproved"):
        QwenSoraniValidator(model_dir)._load()


def test_omni_runtime_selection_is_explicit() -> None:
    assert isinstance(create_omni_asr_producer("local"), OmniAsrProducer)
    assert isinstance(create_omni_asr_producer("wsl"), WslOmniAsrProducer)
    with pytest.raises(ValueError, match="auto, local, wsl"):
        create_omni_asr_producer("remote")
