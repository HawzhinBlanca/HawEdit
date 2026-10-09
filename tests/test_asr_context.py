"""Input-policy contracts; synthetic backend output is not native ASR evidence."""

from __future__ import annotations

import subprocess
import wave
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import hawedit.asr as asr
import test_asr as asr_fixtures
import test_transcripts as transcript_fixtures
from hawedit.asr_completion import COMPLETION_POLICY_ID
from hawedit.captions import find_ffmpeg
from hawedit.transcripts import RawTranscriptImmutable, TranscriptStore


def regions(*intervals: tuple[int, int]) -> tuple[SimpleNamespace, ...]:
    return tuple(SimpleNamespace(start_ms=start, end_ms=end) for start, end in intervals)


def bounds(items: Any) -> list[tuple[int, int]]:
    return [(item.start_ms, item.end_ms) for item in items]


def test_context_grouping_preserves_complete_intervals_and_respects_limits() -> None:
    original = regions((0, 8_000), (9_000, 14_000), (15_001, 17_000), (18_000, 33_002))
    grouped = asr._contextual_speech_regions(original)
    assert bounds(grouped) == [(0, 14_000), (15_001, 17_000), (18_000, 33_002)]
    for interval in original:
        assert (
            sum(
                window.start_ms <= interval.start_ms and interval.end_ms <= window.end_ms
                for window in grouped
            )
            == 1
        )
    assert bounds(original) == [(0, 8_000), (9_000, 14_000), (15_001, 17_000), (18_000, 33_002)]
    assert bounds(asr._contextual_speech_regions(regions((0, 17_000), (17_500, 18_000)))) == [
        (0, 18_000)
    ]
    assert bounds(asr._contextual_speech_regions(regions((0, 17_000), (17_500, 18_001)))) == [
        (0, 17_000),
        (17_500, 18_001),
    ]


@pytest.mark.parametrize("duration_ms", [18_001, 19_000, 38_000, 40_000])
def test_context_grouping_keeps_supported_long_single_region_intact(duration_ms: int) -> None:
    original = regions((0, duration_ms), (duration_ms + 100, duration_ms + 1_000))
    assert bounds(asr._contextual_speech_regions(original)) == [
        (0, duration_ms),
        (duration_ms + 100, duration_ms + 1_000),
    ]
    assert asr._contextual_speech_regions(()) == ()


@pytest.mark.parametrize(
    "items",
    [
        regions((-1, 10)),
        regions((10, 10)),
        regions((10, 9)),
        regions((0, 40_001)),
        regions((0, 100), (99, 200)),
        regions((100, 200), (0, 50)),
        (SimpleNamespace(start_ms=True, end_ms=100),),
        (SimpleNamespace(start_ms=0.5, end_ms=100),),
        (SimpleNamespace(start_ms=0, end_ms="100"),),
    ],
)
def test_context_grouping_refuses_invalid_input(items: tuple[SimpleNamespace, ...]) -> None:
    with pytest.raises(ValueError, match="speech|region|interval"):
        asr._contextual_speech_regions(items)


def test_factory_native_and_wsl_share_context_and_completion_policy() -> None:
    native = asr.create_omni_asr_producer("local")
    wsl = asr.create_omni_asr_producer("wsl")
    assert isinstance(native, asr.OmniAsrProducer)
    assert isinstance(wsl, asr.WslOmniAsrProducer)
    assert native.context_grouping is True
    assert wsl.context_grouping is True
    assert native.admission_policy == wsl.admission_policy
    assert asr.CONTEXT_GROUPING_POLICY_ID == "vad-context-v1-gap1000-span18000"
    assert (
        native.admission_policy
        == asr.ASR_COMPLETION_POLICY_ID + "+" + asr.CONTEXT_GROUPING_POLICY_ID
    )


def test_direct_producer_context_grouping_remains_explicit() -> None:
    native, wsl = asr.OmniAsrProducer(), asr.WslOmniAsrProducer()
    assert native.context_grouping is False
    assert wsl.context_grouping is False
    assert native.admission_policy == wsl.admission_policy == asr.ASR_COMPLETION_POLICY_ID
    assert asr.OmniAsrProducer(asr_fixtures.FakeOmniBackend()).admission_policy is None
    grouped_stub = asr.OmniAsrProducer(asr_fixtures.FakeOmniBackend(), context_grouping=True)
    assert grouped_stub.admission_policy == asr.CONTEXT_GROUPING_POLICY_ID


@pytest.mark.parametrize("bad", [1, "true", None])
@pytest.mark.parametrize("producer", [asr.OmniAsrProducer, asr.WslOmniAsrProducer])
def test_context_configuration_requires_an_actual_boolean(bad: object, producer: Any) -> None:
    with pytest.raises(ValueError, match="context.*boolean"):
        producer(context_grouping=bad)


@pytest.mark.parametrize(
    "legacy_policy",
    [COMPLETION_POLICY_ID, COMPLETION_POLICY_ID + "+vad-context-v1-gap1000-span38000"],
)
def test_context_policy_cannot_reuse_legacy_raw_binding(tmp_path: Path, legacy_policy: str) -> None:
    grouped = asr.create_omni_asr_producer("local")
    assert isinstance(grouped, asr.OmniAsrProducer)
    store = TranscriptStore(tmp_path)
    raw = transcript_fixtures.a_raw()
    store.write_raw(raw, audio_sha256="audio", producer="producer", admission_policy=legacy_policy)
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    with pytest.raises(RawTranscriptImmutable, match="admission"):
        store.reusable_raw(
            "media-001",
            "audio",
            "producer",
            transcript_fixtures.MEDIA_SHA256,
            admission_policy=grouped.admission_policy,
        )
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before


def source_pcm(path: Path) -> bytes:
    pcm = b"\x11\x00" * 16_000 + b"\x22\x00" * 16_000
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16_000)
        stream.writeframes(pcm)
    return pcm


def read_pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as stream:
        assert (stream.getnchannels(), stream.getsampwidth(), stream.getframerate()) == (
            1,
            2,
            16_000,
        )
        return stream.readframes(stream.getnframes())


def test_native_context_grouping_cuts_real_pcm_without_dropping_regions(tmp_path: Path) -> None:
    audio = tmp_path / "source.wav"
    pcm = source_pcm(audio)
    seen: list[tuple[float, bytes]] = []

    class RecordingBackend(asr_fixtures.FakeOmniBackend):
        def transcribe_segment(self, audio_path: Path, duration_s: float) -> asr.SegmentTranscript:
            seen.append((duration_s, read_pcm(audio_path)))
            return super().transcribe_segment(audio_path, duration_s)

    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None, "The required real media runtime must be available"
    producer = asr.OmniAsrProducer(RecordingBackend(), context_grouping=True)
    transcript = producer.transcribe(
        "context-test", audio, regions((100, 1_100), (1_200, 1_700)), tmp_path / "stage1", ffmpeg
    )
    assert seen == [(1.6, pcm[100 * 32 : 1_700 * 32])]
    assert [(word.start_ms, word.end_ms) for word in transcript.words] == [(150, 600)]
    assert len(list((tmp_path / "stage1").glob("speech-*.wav"))) == 1


def test_native_context_policy_drift_refuses_result(tmp_path: Path) -> None:
    audio = tmp_path / "source.wav"
    source_pcm(audio)

    class DriftingBackend(asr_fixtures.FakeOmniBackend):
        def transcribe_segment(self, audio_path: Path, duration_s: float) -> asr.SegmentTranscript:
            producer.context_grouping = False
            return super().transcribe_segment(audio_path, duration_s)

    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    producer = asr.OmniAsrProducer(DriftingBackend(), context_grouping=True)
    with pytest.raises(RuntimeError, match="context policy changed"):
        producer.transcribe(
            "context-test",
            audio,
            regions((100, 1_100), (1_200, 1_700)),
            tmp_path / "stage1",
            ffmpeg,
        )


@pytest.mark.parametrize("drift", [False, True])
def test_wsl_context_grouping_preserves_real_pcm_and_refuses_policy_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, drift: bool
) -> None:
    audio = tmp_path / "source.wav"
    pcm = source_pcm(audio)
    validator = tmp_path / "validator"
    validator.mkdir()
    stage1 = tmp_path / "stage1"
    process_run = subprocess.run
    seen: list[dict[str, Any]] = []
    fixture = transcript_fixtures.a_raw()
    expected = replace(fixture, words=(replace(fixture.words[0], start_ms=150, end_ms=600),))

    class TransportProducer(asr.WslOmniAsrProducer):
        def _runtime(self) -> tuple[str, str]:
            return "/test/python", "/test/source"

        def _prefix(self) -> list[str]:
            return ["owned-wsl-test"]

        def _wsl_path(self, path: Path) -> str:
            return str(path)

    @contextmanager
    def verified(model_id: str, path: Path) -> Iterator[Path]:
        assert model_id == asr.VALIDATOR_MODEL_ID
        assert path == validator
        yield path

    def transport(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        if args[0] != "owned-wsl-test":
            return process_run(args, **kwargs)
        import json

        request = json.loads((stage1 / "omni-asr-request.json").read_text(encoding="utf-8"))
        seen.append(request)
        assert [(r["start_ms"], r["end_ms"]) for r in request["segments"]] == [(100, 1_700)]
        assert read_pcm(stage1 / request["segments"][0]["path"]) == pcm[100 * 32 : 1_700 * 32]
        if drift:
            producer.context_grouping = False
        (stage1 / "omni-asr-worker-output.json").write_text(expected.to_json(), encoding="utf-8")
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(asr, "verified_checkpoint_access", verified)
    monkeypatch.setattr(subprocess, "run", transport)
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    producer = TransportProducer(
        interpreter="/test/python", validator_model_dir=validator, context_grouping=True
    )
    if drift:
        with pytest.raises(RuntimeError, match="context policy changed"):
            producer.transcribe(
                "media-001", audio, regions((100, 1_100), (1_200, 1_700)), stage1, ffmpeg
            )
    else:
        assert (
            producer.transcribe(
                "media-001", audio, regions((100, 1_100), (1_200, 1_700)), stage1, ffmpeg
            )
            == expected
        )
    assert len(seen) == 1
