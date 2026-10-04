"""Native PCM plus synthetic worker faults; no ASR-accuracy claims."""

from __future__ import annotations

import subprocess
import wave
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from hawedit.asr import WslOmniAsrProducer
from hawedit.ingest import SpeechSegment
from hawedit.pipeline import _operational_failure
from hawedit.registry import ModelEntry

_ALIGNMENT_CAUSE = (
    "hawedit.asr.AsrProductionFailure: production ASR halted during draft/alignment "
    "at 905634..917022 ms: AlignmentInfeasible: 569 frames cannot emit 401 tokens: "
    "CTC needs at least 669 frames"
)


def _worker_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    stderr: bytes,
    code: int,
) -> RuntimeError:
    audio = tmp_path / "source.wav"
    with wave.open(str(audio), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16_000)
        stream.writeframes(b"\0" * 32_000)
    validator = tmp_path / "validator"
    validator.mkdir()
    active = False
    calls = 0
    original_run = subprocess.run

    class HostModelStore:
        @staticmethod
        def path_for(_entry: ModelEntry) -> Path:
            return validator

    @contextmanager
    def verified(_model_id: str, selected: Path) -> Iterator[Path]:
        nonlocal active
        assert selected == validator
        active = True
        try:
            yield selected.resolve()
        finally:
            active = False

    def worker_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        nonlocal calls
        if "wslpath" in args:
            return subprocess.CompletedProcess(args, 0, b"/mnt/c/shared\n", b"")
        if "hawedit.asr_worker" in args:
            assert active
            calls += 1
            return subprocess.CompletedProcess(args, code, b"", stderr)
        return original_run(args, **kwargs)

    monkeypatch.setattr("hawedit.asr.ModelStore", HostModelStore)
    monkeypatch.setattr("hawedit.asr.verified_checkpoint_access", verified)
    monkeypatch.setattr("hawedit.asr.subprocess.run", worker_run)
    with pytest.raises(RuntimeError) as failure:
        WslOmniAsrProducer(interpreter="/opt/hawedit/python").transcribe(
            "diagnostic-contract", audio, (SpeechSegment(0, 1_000),), tmp_path / "stage1"
        )
    assert calls == 1
    assert not active
    assert not (tmp_path / "stage1" / "omni-asr-worker-output.json").exists()
    with wave.open(str(tmp_path / "stage1" / "speech-0000.wav"), "rb") as decoded:
        assert (decoded.getnframes(), decoded.getframerate()) == (16_000, 16_000)
    return failure.value


def test_wsl_content_failure_does_not_recommend_reprovisioning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    failure = _worker_error(monkeypatch, tmp_path, _ALIGNMENT_CAUSE.encode(), 1)
    assert "hawedit-asr-setup" not in str(failure)
    assert _ALIGNMENT_CAUSE in str(failure)


def test_wsl_worker_error_tail_survives_pipeline_reason_budget(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stderr = ("Traceback frame\n" * 300 + _ALIGNMENT_CAUSE + "\n").encode()
    failure = _worker_error(monkeypatch, tmp_path, stderr, 1)
    report = _operational_failure("transcript", "canonical ASR runtime", failure)
    assert _ALIGNMENT_CAUSE in report.reason
    assert len(str(failure)) <= 1_024
    assert len(report.reason) <= 1_100
    assert "\n" not in report.reason


def test_wsl_missing_worker_output_remains_a_refusal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    failure = _worker_error(monkeypatch, tmp_path, b"", 0)
    assert "exit 0" in str(failure)
    assert "no transcript was returned" in str(failure)
    assert "hawedit-asr-setup" not in str(failure)


def test_missing_wsl_receipt_still_reports_setup_prerequisite(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setattr("hawedit.asr.configured_wsl_runtime", lambda: runtime)
    with pytest.raises(RuntimeError, match="Run hawedit-asr-setup"):
        WslOmniAsrProducer()._runtime()
