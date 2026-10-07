"""Real local import/PCM controls; vendor model inference is an explicit double."""

from __future__ import annotations

import hashlib
import importlib
import os
import struct
import sys
import wave
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
import torch

from hawedit.ingest import DiarizationUnavailable
from hawedit.pyannote_adapter import PyannoteDiarizer
from test_pyannote_checkpoint import provision_checkpoint

SAMPLES = [-32768, -16384, 0, 16384, 32767] * 3200


@dataclass
class _Observed:
    stages: list[str] = field(default_factory=list)
    selected: Any = None
    metrics_at_load: str | None = None


def _input(
    root: Path, monkeypatch: pytest.MonkeyPatch, action: Callable[[str], None] | None = None
) -> tuple[PyannoteDiarizer, Path, _Observed]:
    checkpoint = provision_checkpoint(root, monkeypatch)
    audio = root / "actual-test-pcm.wav"
    with wave.open(str(audio), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(struct.pack("<" + "h" * len(SAMPLES), *SAMPLES))
    observed = _Observed()

    def stage(name: str) -> None:
        observed.stages.append(name)
        if action is not None:
            action(name)

    class Annotation:
        def itertracks(self, *, yield_label: bool) -> list[tuple[object, str, str]]:
            stage("conversion")
            assert yield_label
            return [(SimpleNamespace(start=0.0, end=1.0), "track", "SPEAKER_00")]

    class Pipeline:
        @classmethod
        def from_pretrained(cls, selected: Path) -> Pipeline:
            stage("load")
            assert selected == checkpoint
            observed.metrics_at_load = os.environ.get("PYANNOTE_METRICS_ENABLED")
            return cls()

        def to(self, selected: object) -> None:
            stage("device")
            assert str(selected) == "cuda:1"

        def __call__(self, selected: object) -> object:
            stage("inference")
            observed.selected = selected
            return SimpleNamespace(exclusive_speaker_diarization=Annotation())

    dependency = ModuleType("pyannote.audio")
    dependency.Pipeline = Pipeline  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pyannote.audio", dependency)
    return PyannoteDiarizer(model_dir=checkpoint, device="cuda:1"), audio, observed


def test_metrics_disabled_before_vendor_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PYANNOTE_METRICS_ENABLED", "true")
    adapter, audio, observed = _input(tmp_path, monkeypatch)
    adapter.diarize(audio)
    assert observed.metrics_at_load == "false"


def test_diarizer_passes_exact_pcm_waveform(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter, audio, observed = _input(tmp_path, monkeypatch)
    before = hashlib.sha256(audio.read_bytes()).hexdigest()
    adapter.diarize(audio)
    selected = observed.selected
    assert isinstance(selected, dict), "filename decoder is still required"
    assert selected["sample_rate"] == 16000
    assert selected["waveform"].dtype == torch.float32
    assert selected["waveform"].shape == (1, 16000)
    expected = torch.tensor(SAMPLES, dtype=torch.float32).div(32768).unsqueeze(0)
    assert torch.equal(selected["waveform"], expected)
    assert hashlib.sha256(audio.read_bytes()).hexdigest() == before


@pytest.mark.parametrize("attempt_stage", ["load", "device", "inference", "conversion"])
def test_local_diarizer_refuses_sdk_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, attempt_stage: str
) -> None:
    marker = tmp_path / "sdk-executed.txt"
    sdk = tmp_path / "pyannoteai"
    sdk.mkdir()
    (sdk / "__init__.py").write_text(
        "from pathlib import Path\nPath(" + repr(str(marker)) + ").write_text('executed')\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    assert sys.modules.get("pyannoteai") is None

    def action(stage: str) -> None:
        if stage == attempt_stage:
            importlib.import_module("pyannoteai")

    adapter, audio, _observed = _input(tmp_path, monkeypatch, action)
    error = None
    try:
        try:
            adapter.diarize(audio)
        except DiarizationUnavailable as exc:
            error = exc
        assert not marker.exists(), "SDK module actually executed"
        assert error is not None
    finally:
        loaded = sys.modules.get("pyannoteai")
        if loaded is not None and getattr(loaded, "__file__", None) == str(sdk / "__init__.py"):
            del sys.modules["pyannoteai"]


@pytest.mark.parametrize("name", ["pyannoteai", "pyannoteai.sdk", "pyannoteai.client"])
def test_local_diarizer_refuses_preloaded_sdk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    preloaded = ModuleType(name)
    monkeypatch.setitem(sys.modules, name, preloaded)
    adapter, audio, observed = _input(tmp_path, monkeypatch)
    with pytest.raises(DiarizationUnavailable, match="SDK"):
        adapter.diarize(audio)
    assert observed.stages == []
    assert sys.modules[name] is preloaded


def test_swallowed_sdk_import_still_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def action(stage: str) -> None:
        if stage == "load":
            with suppress(Exception):
                importlib.import_module("pyannoteai")

    adapter, audio, _observed = _input(tmp_path, monkeypatch, action)
    with pytest.raises(DiarizationUnavailable, match="SDK"):
        adapter.diarize(audio)


@pytest.mark.parametrize("failure_stage", ["load", "device", "inference", "conversion"])
def test_import_guard_is_removed_after_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_stage: str
) -> None:
    before = tuple(sys.meta_path)

    def action(stage: str) -> None:
        if stage == failure_stage:
            raise RuntimeError("intentional consumer failure")

    adapter, audio, _observed = _input(tmp_path, monkeypatch, action)
    with pytest.raises(DiarizationUnavailable, match="intentional consumer failure"):
        adapter.diarize(audio)
    assert tuple(sys.meta_path) == before


def test_sdk_inserted_after_load_refuses_before_inference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def action(stage: str) -> None:
        if stage == "load":
            monkeypatch.setitem(sys.modules, "pyannoteai", ModuleType("pyannoteai"))

    adapter, audio, observed = _input(tmp_path, monkeypatch, action)
    with pytest.raises(DiarizationUnavailable, match="SDK"):
        adapter.diarize(audio)
    assert observed.stages == ["load"]


@pytest.mark.parametrize(
    "kind", ["garbage", "empty", "rate", "channels", "width", "truncated", "partial-frame"]
)
def test_invalid_pcm_refuses_before_model_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    adapter, audio, observed = _input(tmp_path, monkeypatch)
    if kind in {"garbage", "truncated"}:
        audio.write_bytes(b"not a WAV" if kind == "garbage" else audio.read_bytes()[:-5])
    else:
        with wave.open(str(audio), "wb") as stream:
            stream.setnchannels(2 if kind == "channels" else 1)
            stream.setsampwidth(1 if kind == "width" else 2)
            stream.setframerate(8000 if kind == "rate" else 16000)
            stream.writeframes(
                b""
                if kind == "empty"
                else b"\0" * 32000 + (b"\x01" if kind == "partial-frame" else b"")
            )
    before = hashlib.sha256(audio.read_bytes()).hexdigest()
    with pytest.raises(DiarizationUnavailable, match="PCM|WAV|audio"):
        adapter.diarize(audio)
    assert observed.stages == []
    assert hashlib.sha256(audio.read_bytes()).hexdigest() == before
