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
from hawedit.asr_completion import COMPLETION_POLICY_ID, DecodeIncomplete, DecoderContractError
from hawedit.captions import find_ffmpeg
from hawedit.transcripts import RawTranscriptImmutable, TranscriptStore, Word


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
    native_off = asr.create_omni_asr_producer("local")
    wsl_off = asr.create_omni_asr_producer("wsl")
    assert isinstance(native_off, asr.OmniAsrProducer)
    assert isinstance(wsl_off, asr.WslOmniAsrProducer)
    assert native_off.context_grouping is True
    assert wsl_off.context_grouping is True
    assert native_off.admission_policy == wsl_off.admission_policy
    assert asr.CONTEXT_GROUPING_POLICY_ID == "vad-context-v1-gap1000-span18000"
    assert (
        native_off.admission_policy
        == COMPLETION_POLICY_ID + "+" + asr.CONTEXT_GROUPING_POLICY_ID + "+validator-off"
    )

    native_on = asr.create_omni_asr_producer("local", validate_hard_segments=True)
    wsl_on = asr.create_omni_asr_producer("wsl", validate_hard_segments=True)
    assert isinstance(native_on, asr.OmniAsrProducer)
    assert isinstance(wsl_on, asr.WslOmniAsrProducer)
    assert native_on.admission_policy == wsl_on.admission_policy
    assert (
        native_on.admission_policy
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
    grouped = asr.create_omni_asr_producer("local", validate_hard_segments=True)
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


def source_pcm(path: Path, duration_s: float = 2.0) -> bytes:
    if duration_s == 2.0:
        pcm = b"\x11\x00" * 16_000 + b"\x22\x00" * 16_000
    else:
        total_samples = round(duration_s * 16_000)
        pcm = b"".join(
            ((idx * 37) % 30_000).to_bytes(2, "little", signed=True) for idx in range(total_samples)
        )
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


def test_grouped_region_splits_into_constituent_raw_vad_segments_on_decode_incomplete(
    tmp_path: Path,
) -> None:
    audio = tmp_path / "source.wav"
    pcm = source_pcm(audio, duration_s=5.0)
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    sub_intervals = ((100, 1_500), (1_800, 3_600))
    calls: list[tuple[str, bytes, float]] = []

    class SplitRetryBackend:
        def transcribe_segment(self, audio_path: Path, duration_s: float) -> asr.SegmentTranscript:
            frames = read_pcm(audio_path)
            calls.append((audio_path.name, frames, duration_s))
            if round(duration_s * 1_000) == 3_500:
                raise DecodeIncomplete(
                    f"segment {audio_path.name}: greedy attempt: loop; beam-5 retry: loop"
                )
            if frames == pcm[100 * 32 : 1_500 * 32]:
                return asr.SegmentTranscript(
                    "سڵاو کورد.",
                    "سڵاو کورد",
                    (
                        Word("سڵاو", 50, 500, 0.9),
                        Word("کورد.", 600, 1_300, 0.92),
                    ),
                    -0.2,
                )
            assert frames == pcm[1_800 * 32 : 3_600 * 32]
            return asr.SegmentTranscript(
                "بەشی دووەم.",
                "بەشی دووەم",
                (
                    Word("بەشی", 50, 700, 0.91),
                    Word("دووەم.", 800, 1_700, 0.93),
                ),
                -0.15,
            )

        def align_segment(
            self, audio_path: Path, duration_s: float, text: str
        ) -> asr.SegmentTranscript:
            raise AssertionError("validator should not run")

    producer = asr.OmniAsrProducer(
        SplitRetryBackend(),
        context_grouping=True,
        validate_hard_segments=False,
    )
    raw = producer.transcribe("ep-split", audio, regions(*sub_intervals), tmp_path / "work", ffmpeg)
    assert len(calls) == 3
    assert [round(c[2] * 1_000) for c in calls] == [3_500, 1_400, 1_800]
    assert [w.w for w in raw.words] == ["سڵاو", "کورد.", "بەشی", "دووەم."]
    assert [(w.start_ms, w.end_ms) for w in raw.words] == [
        (150, 600),
        (700, 1_400),
        (1_850, 2_500),
        (2_600, 3_500),
    ]
    assert raw.unaligned == ()
    assert [c.end_ms - c.start_ms for c in raw.segment_confidence] == [1_400, 1_800]


def test_grouped_region_split_keeps_strict_fail_stop_when_constituent_also_fails(
    tmp_path: Path,
) -> None:
    audio = tmp_path / "source.wav"
    source_pcm(audio, duration_s=5.0)
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    sub_intervals = ((100, 1_500), (1_800, 3_600))
    calls: list[int] = []

    class SecondSubFailsBackend:
        def transcribe_segment(self, audio_path: Path, duration_s: float) -> asr.SegmentTranscript:
            dur_ms = round(duration_s * 1_000)
            calls.append(dur_ms)
            if dur_ms == 3_500:
                raise DecodeIncomplete(
                    f"segment {audio_path.name}: greedy attempt: loop; beam-5 retry: loop"
                )
            if dur_ms == 1_400:
                return asr.SegmentTranscript(
                    "سڵاو.", "سڵاو", (Word("سڵاو.", 50, 1_200, 0.9),), -0.2
                )
            raise DecodeIncomplete(
                f"segment {audio_path.name}: greedy attempt: loop; beam-5 retry: still looping"
            )

        def align_segment(
            self, audio_path: Path, duration_s: float, text: str
        ) -> asr.SegmentTranscript:
            raise AssertionError("validator should not run")

    producer = asr.OmniAsrProducer(
        SecondSubFailsBackend(),
        context_grouping=True,
        validate_hard_segments=False,
    )
    with pytest.raises(asr.AsrProductionFailure) as exc_info:
        producer.transcribe("ep-fail", audio, regions(*sub_intervals), tmp_path / "work", ffmpeg)
    assert calls == [3_500, 1_400, 1_800]
    assert exc_info.value.unaligned[0].start_ms == 1_800
    assert exc_info.value.unaligned[0].end_ms == 3_600


def test_decoder_contract_error_never_triggers_constituent_split(tmp_path: Path) -> None:
    audio = tmp_path / "source.wav"
    source_pcm(audio, duration_s=5.0)
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    calls: list[int] = []

    class ContractFailBackend:
        def transcribe_segment(self, audio_path: Path, duration_s: float) -> asr.SegmentTranscript:
            calls.append(round(duration_s * 1_000))
            raise DecoderContractError(
                "Installed decoder differs from the validated completion contract"
            )

        def align_segment(
            self, audio_path: Path, duration_s: float, text: str
        ) -> asr.SegmentTranscript:
            raise AssertionError("validator should not run")

    producer = asr.OmniAsrProducer(
        ContractFailBackend(),
        context_grouping=True,
        validate_hard_segments=False,
    )
    with pytest.raises(asr.AsrProductionFailure, match="Installed decoder differs"):
        producer.transcribe(
            "ep-contract", audio, regions((100, 1_500), (1_800, 3_600)), tmp_path / "work", ffmpeg
        )
    assert calls == [3_500]


def test_wsl_worker_and_journal_support_constituent_split_with_crash_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib.metadata
    import json

    import hawedit.asr_resume as resume_mod
    from hawedit.asr_worker import run_request
    from test_asr_resume import private

    audio = tmp_path / "source.wav"
    pcm = source_pcm(audio, duration_s=7.0)
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    # Two windows: first merges two sub-segments (100..1500, 1800..3600);
    # second is a singleton (5000..6200).
    input_regions = regions((100, 1_500), (1_800, 3_600), (5_000, 6_200))
    stage1 = tmp_path / "stage1"
    process_run = subprocess.run
    captured_req: dict[str, Any] = {}

    class CaptureProducer(asr.WslOmniAsrProducer):
        def _runtime(self) -> tuple[str, str]:
            return "/test/python", "/test/source"

        def _prefix(self) -> list[str]:
            return ["owned-wsl-split-test"]

        def _wsl_path(self, path: Path) -> str:
            return str(path)

    def capture_transport(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        if args[0] != "owned-wsl-split-test":
            return process_run(args, **kwargs)
        req_path = stage1 / "omni-asr-request.json"
        captured_req.update(json.loads(req_path.read_text(encoding="utf-8")))
        (stage1 / "omni-asr-worker-output.json").write_text(
            transcript_fixtures.a_raw().to_json(), encoding="utf-8"
        )
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", capture_transport)
    producer = CaptureProducer(
        interpreter="/test/python",
        context_grouping=True,
        validate_hard_segments=False,
    )
    producer.transcribe("media-001", audio, input_regions, stage1, ffmpeg)
    segs = captured_req["segments"]
    assert len(segs) == 2
    assert segs[0]["sub_segments"] == [
        {"start_ms": 100, "end_ms": 1_500},
        {"start_ms": 1_800, "end_ms": 3_600},
    ]
    assert "sub_segments" not in segs[1]

    req_path = stage1 / "omni-asr-request.json"
    monkeypatch.setattr(resume_mod, "freeze_fairseq2_asset_overrides", lambda: None)
    monkeypatch.setattr(resume_mod, "assert_omni_card_integrity", lambda: req_path)
    monkeypatch.setattr(resume_mod, "assert_omni_asset_integrity", lambda: ())
    monkeypatch.setattr(
        importlib.metadata,
        "distribution",
        lambda _name: SimpleNamespace(locate_file=lambda _p: req_path),
    )
    monkeypatch.setattr(importlib.metadata, "version", lambda _name: "0.0.0")

    ckpt = private(tmp_path)
    call_durations: list[int] = []

    class CrashOnSecondSubBackend:
        def __init__(self, fail_second_sub: bool) -> None:
            self.fail_second_sub = fail_second_sub

        def transcribe_segment(self, audio_path: Path, duration_s: float) -> asr.SegmentTranscript:
            dur_ms = round(duration_s * 1_000)
            call_durations.append(dur_ms)
            if dur_ms == 3_500:
                raise DecodeIncomplete(
                    f"segment {audio_path.name}: greedy attempt: loop; beam-5 retry: loop"
                )
            if dur_ms == 1_400:
                assert read_pcm(audio_path) == pcm[100 * 32 : 1_500 * 32]
                return asr.SegmentTranscript(
                    "سڵاو.", "سڵاو", (Word("سڵاو.", 20, 1_100, 0.9),), -0.2
                )
            if dur_ms == 1_800:
                if self.fail_second_sub:
                    raise RuntimeError("simulated worker crash before constituent 1")
                assert read_pcm(audio_path) == pcm[1_800 * 32 : 3_600 * 32]
                return asr.SegmentTranscript(
                    "کورد.", "کورد", (Word("کورد.", 20, 1_500, 0.9),), -0.2
                )
            assert dur_ms == 1_200
            return asr.SegmentTranscript("باشە.", "باشە", (Word("باشە.", 20, 1_000, 0.9),), -0.2)

        def align_segment(
            self, audio_path: Path, duration_s: float, text: str
        ) -> asr.SegmentTranscript:
            raise AssertionError("validator should not run")

    with pytest.raises(asr.AsrProductionFailure, match="simulated worker crash"):
        run_request(
            req_path,
            tmp_path / "out_crash.json",
            CrashOnSecondSubBackend(fail_second_sub=True),
            checkpoint_root=ckpt,
        )
    # Grouped failed, sub 0 succeeded and saved to journal, sub 1 crashed
    assert call_durations == [3_500, 1_400, 1_800]

    call_durations.clear()
    raw = run_request(
        req_path,
        tmp_path / "out_resume.json",
        CrashOnSecondSubBackend(fail_second_sub=False),
        checkpoint_root=ckpt,
    )
    # Rerun retries grouped (which wasn't cached since it failed), hits journal cache for sub 0,
    # then runs ONLY sub 1 (1_800) and singleton (1_200)!
    assert call_durations == [3_500, 1_800, 1_200]
    assert [w.w for w in raw.words] == ["سڵاو.", "کورد.", "باشە."]
    assert [(w.start_ms, w.end_ms) for w in raw.words] == [
        (120, 1_200),
        (1_820, 3_300),
        (5_020, 6_000),
    ]


def _pcm_with_quiet_spans(
    path: Path,
    duration_ms: int,
    *,
    loud_amp: int = 12_000,
    quiet_spans: tuple[tuple[int, int, int], ...] = (),
) -> bytes:
    """Build deterministic 16 kHz mono PCM16 WAV with optional quiet spans (start, end, amp)."""
    total_samples = round(duration_ms * 16)
    amps = [loud_amp] * total_samples
    for q_start, q_end, q_amp in quiet_spans:
        lo = max(0, round(q_start * 16))
        hi = min(total_samples, round(q_end * 16))
        for idx in range(lo, hi):
            amps[idx] = q_amp
    pcm = b"".join(
        (amp if idx % 2 == 0 else -amp).to_bytes(2, "little", signed=True)
        for idx, amp in enumerate(amps)
    )
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16_000)
        stream.writeframes(pcm)
    return pcm


def test_singleton_splits_once_at_silence_dip_and_decodes_both_halves(tmp_path: Path) -> None:
    audio = tmp_path / "source.wav"
    # 12_000 ms singleton with unique 200 ms silent dip at 6_100..6_300 ms -> center 6_200 ms.
    pcm = _pcm_with_quiet_spans(audio, 12_000, quiet_spans=((6_100, 6_300, 0),))
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    calls: list[tuple[str, bytes, int]] = []

    class DipSplitBackend:
        def transcribe_segment(self, audio_path: Path, duration_s: float) -> asr.SegmentTranscript:
            frames = read_pcm(audio_path)
            dur_ms = round(duration_s * 1_000)
            calls.append((audio_path.name, frames, dur_ms))
            if dur_ms == 12_000:
                raise DecodeIncomplete(
                    f"segment {audio_path.name}: greedy attempt: no natural EOS; beam-5 retry: loop"
                )
            if audio_path.name == "speech-0000-dip-00.wav":
                assert dur_ms == 6_200
                assert frames == pcm[: 6_200 * 32]
                return asr.SegmentTranscript(
                    "بەشی یەکەم.",
                    "بەشی یەکەم",
                    (
                        Word("بەشی", 100, 1_500, 0.91),
                        Word("یەکەم.", 2_000, 5_800, 0.92),
                    ),
                    -0.25,
                )
            assert audio_path.name == "speech-0000-dip-01.wav"
            assert dur_ms == 5_800
            assert frames == pcm[6_200 * 32 :]
            return asr.SegmentTranscript(
                "بەشی دووەم.",
                "بەشی دووەم",
                (
                    Word("بەشی", 100, 1_200, 0.93),
                    Word("دووەم.", 1_500, 5_200, 0.94),
                ),
                -0.20,
            )

        def align_segment(
            self, audio_path: Path, duration_s: float, text: str
        ) -> asr.SegmentTranscript:
            raise AssertionError("validator should not run")

    producer = asr.OmniAsrProducer(
        DipSplitBackend(),
        context_grouping=True,
        validate_hard_segments=False,
    )
    raw = producer.transcribe("ep-dip", audio, regions((0, 12_000)), tmp_path / "work", ffmpeg)
    assert len(calls) == 3
    assert [c[2] for c in calls] == [12_000, 6_200, 5_800]
    assert [w.w for w in raw.words] == ["بەشی", "یەکەم.", "بەشی", "دووەم."]
    assert [(w.start_ms, w.end_ms) for w in raw.words] == [
        (100, 1_500),
        (2_000, 5_800),
        (6_300, 7_400),
        (7_700, 11_400),
    ]
    assert raw.unaligned == ()
    assert [(c.start_ms, c.end_ms) for c in raw.segment_confidence] == [
        (0, 6_200),
        (6_200, 12_000),
    ]


def test_singleton_never_splits_when_duration_below_minimum_or_no_silence_dip(
    tmp_path: Path,
) -> None:
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None

    class AlwaysIncompleteBackend:
        def __init__(self, *, contract_error: bool = False) -> None:
            self.calls: list[int] = []
            self.contract_error = contract_error

        def transcribe_segment(self, audio_path: Path, duration_s: float) -> asr.SegmentTranscript:
            self.calls.append(round(duration_s * 1_000))
            if self.contract_error:
                raise DecoderContractError("Installed decoder differs")
            raise DecodeIncomplete(f"segment {audio_path.name}: loop")

        def align_segment(
            self, audio_path: Path, duration_s: float, text: str
        ) -> asr.SegmentTranscript:
            raise AssertionError("validator should not run")

    # (a) 12_000 ms with shallow dip (4_000 > 0.15 * 11_866): no silence-dip split.
    continuous = tmp_path / "continuous.wav"
    _pcm_with_quiet_spans(continuous, 12_000, quiet_spans=((6_100, 6_300, 4_000),))
    work_a = tmp_path / "work_a"
    backend_a = AlwaysIncompleteBackend()
    producer_a = asr.OmniAsrProducer(backend_a, context_grouping=True, validate_hard_segments=False)
    with pytest.raises(asr.AsrProductionFailure):
        producer_a.transcribe("ep-cont", continuous, regions((0, 12_000)), work_a, ffmpeg)
    assert backend_a.calls == [12_000]
    assert not list(work_a.glob("*-dip-*.wav"))

    # (b) 7_500 ms (< 8_000 ms) even with a 200 ms silent dip at 3_650..3_850: no dip split.
    short = tmp_path / "short.wav"
    _pcm_with_quiet_spans(short, 7_500, quiet_spans=((3_650, 3_850, 0),))
    work_b = tmp_path / "work_b"
    backend_b = AlwaysIncompleteBackend()
    producer_b = asr.OmniAsrProducer(backend_b, context_grouping=True, validate_hard_segments=False)
    with pytest.raises(asr.AsrProductionFailure):
        producer_b.transcribe("ep-short", short, regions((0, 7_500)), work_b, ffmpeg)
    assert backend_b.calls == [7_500]
    assert not list(work_b.glob("*-dip-*.wav"))

    # (c) All-zero (overall_rms == 0) 12_000 ms audio: never triggers dip split.
    silent = tmp_path / "silent.wav"
    _pcm_with_quiet_spans(silent, 12_000, loud_amp=0)
    work_c = tmp_path / "work_c"
    backend_c = AlwaysIncompleteBackend()
    producer_c = asr.OmniAsrProducer(backend_c, context_grouping=True, validate_hard_segments=False)
    with pytest.raises(asr.AsrProductionFailure):
        producer_c.transcribe("ep-zero", silent, regions((0, 12_000)), work_c, ffmpeg)
    assert backend_c.calls == [12_000]
    assert not list(work_c.glob("*-dip-*.wav"))

    # (d) DecoderContractError on 12_000 ms singleton with deep dip: never triggers dip split.
    with_dip = tmp_path / "with_dip.wav"
    _pcm_with_quiet_spans(with_dip, 12_000, quiet_spans=((6_100, 6_300, 0),))
    work_d = tmp_path / "work_d"
    backend_d = AlwaysIncompleteBackend(contract_error=True)
    producer_d = asr.OmniAsrProducer(backend_d, context_grouping=True, validate_hard_segments=False)
    with pytest.raises(asr.AsrProductionFailure, match="Installed decoder differs"):
        producer_d.transcribe("ep-contract", with_dip, regions((0, 12_000)), work_d, ffmpeg)
    assert backend_d.calls == [12_000]
    assert not list(work_d.glob("*-dip-*.wav"))


def test_singleton_dip_split_never_recurses_and_fails_stop_if_either_half_fails(
    tmp_path: Path,
) -> None:
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    # 20_000 ms with center dip at 10_100..10_300 (center 10_200 ms -> half0=10_200, half1=9_800),
    # plus secondary dips at 4_900..5_100 and 14_900..15_100 to verify no recursion happens.
    audio = tmp_path / "source.wav"
    _pcm_with_quiet_spans(
        audio,
        20_000,
        quiet_spans=((4_900, 5_100, 0), (10_100, 10_300, 0), (14_900, 15_100, 0)),
    )

    class FailHalfBackend:
        def __init__(self, fail_half0: bool) -> None:
            self.fail_half0 = fail_half0
            self.calls: list[tuple[str, int]] = []

        def transcribe_segment(self, audio_path: Path, duration_s: float) -> asr.SegmentTranscript:
            dur_ms = round(duration_s * 1_000)
            self.calls.append((audio_path.name, dur_ms))
            if dur_ms == 20_000:
                raise DecodeIncomplete("parent loop")
            if audio_path.name == "speech-0000-dip-00.wav":
                if self.fail_half0:
                    raise DecodeIncomplete("half0 still loops")
                return asr.SegmentTranscript(
                    "بەشی یەکەم.", "بەشی یەکەم", (Word("بەشی", 100, 900, 0.9),), -0.2
                )
            raise DecodeIncomplete("half1 still loops")

        def align_segment(
            self, audio_path: Path, duration_s: float, text: str
        ) -> asr.SegmentTranscript:
            raise AssertionError("validator should not run")

    # Notice sliding search on [3_000, 17_000] hits 4_900..5_100 first (all three windows are 0),
    # giving center 5_000 ms -> half0 = 5_000 ms, half1 = 15_000 ms (still >= 8_000 with 2 dips!).
    b0 = FailHalfBackend(fail_half0=True)
    p0 = asr.OmniAsrProducer(b0, context_grouping=True, validate_hard_segments=False)
    with pytest.raises(asr.AsrProductionFailure) as exc0:
        p0.transcribe("ep-fail0", audio, regions((0, 20_000)), tmp_path / "w0", ffmpeg)
    assert b0.calls == [("speech-0000.wav", 20_000), ("speech-0000-dip-00.wav", 5_000)]
    assert (exc0.value.unaligned[0].start_ms, exc0.value.unaligned[0].end_ms) == (0, 5_000)

    b1 = FailHalfBackend(fail_half0=False)
    p1 = asr.OmniAsrProducer(b1, context_grouping=True, validate_hard_segments=False)
    with pytest.raises(asr.AsrProductionFailure) as exc1:
        p1.transcribe("ep-fail1", audio, regions((0, 20_000)), tmp_path / "w1", ffmpeg)
    assert b1.calls == [
        ("speech-0000.wav", 20_000),
        ("speech-0000-dip-00.wav", 5_000),
        ("speech-0000-dip-01.wav", 15_000),
    ]
    assert (exc1.value.unaligned[0].start_ms, exc1.value.unaligned[0].end_ms) == (5_000, 20_000)
    assert not list((tmp_path / "w1").glob("*dip-*-dip-*.wav"))


def test_wsl_worker_journal_supports_singleton_dip_split_with_crash_recovery_and_tamper_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib.metadata
    import json

    import hawedit.asr_resume as resume_mod
    from hawedit.asr_worker import run_request
    from test_asr_resume import private

    audio = tmp_path / "source.wav"
    pcm = _pcm_with_quiet_spans(audio, 12_000, quiet_spans=((6_100, 6_300, 0),))
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    stage1 = tmp_path / "stage1"
    process_run = subprocess.run
    captured_req: dict[str, Any] = {}

    class CaptureProducer(asr.WslOmniAsrProducer):
        def _runtime(self) -> tuple[str, str]:
            return "/test/python", "/test/source"

        def _prefix(self) -> list[str]:
            return ["owned-wsl-dip-test"]

        def _wsl_path(self, path: Path) -> str:
            return str(path)

    def capture_transport(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        if args[0] != "owned-wsl-dip-test":
            return process_run(args, **kwargs)
        req_path = stage1 / "omni-asr-request.json"
        captured_req.update(json.loads(req_path.read_text(encoding="utf-8")))
        (stage1 / "omni-asr-worker-output.json").write_text(
            transcript_fixtures.a_raw().to_json(), encoding="utf-8"
        )
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", capture_transport)
    producer = CaptureProducer(
        interpreter="/test/python",
        context_grouping=True,
        validate_hard_segments=False,
    )
    producer.transcribe("media-001", audio, regions((0, 12_000)), stage1, ffmpeg)
    assert set(captured_req) == {"schema_version", "media_id", "segments", "validate_hard_segments"}
    assert len(captured_req["segments"]) == 1
    assert "sub_segments" not in captured_req["segments"][0]

    req_path = stage1 / "omni-asr-request.json"
    monkeypatch.setattr(resume_mod, "freeze_fairseq2_asset_overrides", lambda: None)
    monkeypatch.setattr(resume_mod, "assert_omni_card_integrity", lambda: req_path)
    monkeypatch.setattr(resume_mod, "assert_omni_asset_integrity", lambda: ())
    monkeypatch.setattr(
        importlib.metadata,
        "distribution",
        lambda _name: SimpleNamespace(locate_file=lambda _p: req_path),
    )
    monkeypatch.setattr(importlib.metadata, "version", lambda _name: "0.0.0")

    ckpt = private(tmp_path)
    call_durations: list[int] = []

    class CrashOnSecondDipHalfBackend:
        def __init__(self, fail_second_half: bool) -> None:
            self.fail_second_half = fail_second_half

        def transcribe_segment(self, audio_path: Path, duration_s: float) -> asr.SegmentTranscript:
            dur_ms = round(duration_s * 1_000)
            call_durations.append(dur_ms)
            if dur_ms == 12_000:
                raise DecodeIncomplete("singleton loop")
            if audio_path.name == "speech-0000-dip-00.wav":
                assert read_pcm(audio_path) == pcm[: 6_200 * 32]
                return asr.SegmentTranscript(
                    "سڵاو.", "سڵاو", (Word("سڵاو.", 50, 1_500, 0.9),), -0.2
                )
            assert audio_path.name == "speech-0000-dip-01.wav"
            if self.fail_second_half:
                raise RuntimeError("simulated worker crash before dip-01")
            assert read_pcm(audio_path) == pcm[6_200 * 32 :]
            return asr.SegmentTranscript("کورد.", "کورد", (Word("کورد.", 50, 2_000, 0.9),), -0.2)

        def align_segment(
            self, audio_path: Path, duration_s: float, text: str
        ) -> asr.SegmentTranscript:
            raise AssertionError("validator should not run")

    with pytest.raises(asr.AsrProductionFailure, match="simulated worker crash"):
        run_request(
            req_path,
            tmp_path / "out_crash.json",
            CrashOnSecondDipHalfBackend(fail_second_half=True),
            checkpoint_root=ckpt,
        )
    assert call_durations == [12_000, 6_200, 5_800]

    call_durations.clear()
    raw = run_request(
        req_path,
        tmp_path / "out_resume.json",
        CrashOnSecondDipHalfBackend(fail_second_half=False),
        checkpoint_root=ckpt,
    )
    # Resuming hits journal cache for dip-00 and runs ONLY dip-01.
    assert call_durations == [12_000, 5_800]
    assert [w.w for w in raw.words] == ["سڵاو.", "کورد."]
    assert [(w.start_ms, w.end_ms) for w in raw.words] == [(50, 1_500), (6_250, 8_200)]

    # Tampering with dip-00 WAV bytes must be rejected by OperationJournal._assert_bound_subsegment.
    tampered_dip = stage1 / "speech-0000-dip-00.wav"
    original_bytes = tampered_dip.read_bytes()
    tampered_dip.write_bytes(original_bytes[:-2] + b"\x7f\x7f")
    prepared = [
        asr._PreparedSpeechSegment(path=stage1 / "speech-0000.wav", start_ms=0, end_ms=12_000)
    ]
    with (
        resume_mod.worker_journal(ckpt, req_path, prepared, None, None) as journal,
        pytest.raises(RuntimeError, match="bound audio changed"),
    ):
        journal.operation("draft", tampered_dip, 6.2)
