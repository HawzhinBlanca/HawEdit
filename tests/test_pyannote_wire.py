"""Pinned upstream result-shape controls, not inference, model-load or DER evidence."""

from __future__ import annotations

import sys
import wave
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from hawedit.diarization import Segment
from hawedit.ingest import DiarizationInvalidOutput, IngestResult, attach_diarization
from hawedit.pyannote_adapter import PyannoteDiarizer, create_diarizer


@dataclass(frozen=True)
class _Track:
    start: float
    end: float


class _Annotation:
    def __init__(self, turns: list[tuple[float, float, str]]) -> None:
        self.turns = turns

    def itertracks(self, *, yield_label: bool) -> list[tuple[_Track, str, str]]:
        assert yield_label is True
        return [
            (_Track(start, end), f"track-{i}", label)
            for i, (start, end, label) in enumerate(self.turns)
        ]


@dataclass(frozen=True)
class _Output:
    exclusive_speaker_diarization: object

    @property
    def speaker_diarization(self) -> object:
        raise AssertionError("ordinary output must not be selected")


@dataclass
class _Calls:
    checkpoints: list[Path | str] = field(default_factory=list)
    audio: list[str] = field(default_factory=list)
    devices: list[str] = field(default_factory=list)


def _wire(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, output: object, *, device: str = "cpu"
) -> tuple[PyannoteDiarizer, Path, _Calls]:
    audio = tmp_path / "silence.wav"
    with wave.open(str(audio), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(b"\0" * (16000 * 5 * 2))
    checkpoint = tmp_path / "wire-only-checkpoint"
    checkpoint.mkdir()
    calls = _Calls()

    class _Pipeline:
        @classmethod
        def from_pretrained(cls, selected: Path | str) -> _Pipeline:
            calls.checkpoints.append(selected)
            return cls()

        def to(self, selected: object) -> None:
            calls.devices.append(str(selected))

        def __call__(self, selected: str) -> object:
            calls.audio.append(selected)
            return output

    dependency = ModuleType("pyannote.audio")
    dependency.Pipeline = _Pipeline  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pyannote.audio", dependency)
    return create_diarizer(model_dir=checkpoint, device=device), audio, calls


def _base(audio: Path) -> IngestResult:
    return IngestResult(
        media_id="wire-only",
        source="wire-only.mp4",
        source_sha256="0" * 64,
        duration_ms=5000,
        audio_path=str(audio),
        proxy_path="unused.mp4",
        shot_cuts_ms=(),
        speech=(),
    )


def test_wrapped_result_selects_only_explicit_exclusive_turns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = _Output(_Annotation([(0.0004, 1.2344, "SPEAKER_00"), (1.5006, 3.7896, "SPEAKER_01")]))
    adapter, audio, _calls = _wire(tmp_path, monkeypatch, output)
    expected = (
        Segment(0, 1234, "SPEAKER_00"),
        Segment(1501, 3790, "SPEAKER_01"),
    )
    assert adapter.diarize(audio) == expected
    base = _base(audio)
    assert attach_diarization(base, adapter).diarization == expected
    assert base.diarization is None


@pytest.mark.parametrize(
    "output",
    [
        _Annotation([(0.0, 1.0, "LEGACY")]),
        SimpleNamespace(speaker_diarization=_Annotation([(0.0, 1.0, "ORDINARY")])),
        SimpleNamespace(exclusive_speaker_diarization=None),
        _Output(object()),
        _Output(SimpleNamespace(itertracks=None)),
    ],
    ids=["legacy", "ordinary-only", "null", "malformed", "noncallable"],
)
def test_missing_or_malformed_exclusive_output_never_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, output: object
) -> None:
    adapter, audio, _calls = _wire(tmp_path, monkeypatch, output)
    with pytest.raises(DiarizationInvalidOutput, match="exclusive"):
        adapter.diarize(audio)


def test_empty_exclusive_output_does_not_invent_ordinary_turns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter, audio, _calls = _wire(tmp_path, monkeypatch, _Output(_Annotation([])))
    assert adapter.diarize(audio) == ()
    assert attach_diarization(_base(audio), adapter).diarization == ()


def test_configured_model_audio_and_device_reach_the_producer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter, audio, calls = _wire(
        tmp_path, monkeypatch, _Output(_Annotation([(0.0, 1.0, "SPEAKER_00")])), device="cuda:1"
    )
    assert adapter.diarize(audio) == (Segment(0, 1000, "SPEAKER_00"),)
    assert calls.checkpoints == [tmp_path / "wire-only-checkpoint"]
    assert calls.audio == [str(audio)]
    assert calls.devices == ["cuda:1"]
    assert adapter.model_id == "pyannote/speaker-diarization-community-1"


@pytest.mark.parametrize(
    ("turns", "message"),
    [
        ([(1.0001, 1.0003, "SPEAKER_00")], "non-positive duration"),
        ([(0.0, 2.0, "SPEAKER_00"), (1.5, 3.5, "SPEAKER_01")], "turns overlap"),
    ],
    ids=["zero-after-rounding", "overlap"],
)
def test_wrapped_turns_keep_rounding_and_overlap_refusals(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    turns: list[tuple[float, float, str]],
    message: str,
) -> None:
    adapter, audio, _calls = _wire(tmp_path, monkeypatch, _Output(_Annotation(turns)))
    with pytest.raises(DiarizationInvalidOutput, match=message):
        attach_diarization(_base(audio), adapter)


def test_wrapped_turns_outside_media_clock_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter, audio, _calls = _wire(
        tmp_path, monkeypatch, _Output(_Annotation([(0.0, 5.5, "SPEAKER_00")]))
    )
    with pytest.raises(DiarizationInvalidOutput, match="outside media duration"):
        attach_diarization(_base(audio), adapter)
