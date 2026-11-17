"""D-303 real PCM adaptation and permanent Windows lock refusal."""

from __future__ import annotations

import errno
import wave
from pathlib import Path

import numpy as np
import pytest

from hawedit.asr import _qwen_audio_input
from hawedit.wsl_setup import WslRuntimeError, _runtime_transaction_lock


@pytest.mark.parametrize("error_number", [errno.EINVAL, errno.EBADF, errno.EIO, None])
def test_setup_noncontention_lock_error_refuses_without_sleep(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, error_number: int | None
) -> None:
    calls: list[int] = []
    failure = OSError(error_number, "permanent lock failure")

    class LockDependency:
        LK_NBLCK = 1
        LK_UNLCK = 2

        @staticmethod
        def locking(_file: int, mode: int, _bytes: int) -> None:
            calls.append(mode)
            raise failure

    def refuse_sleep(_seconds: float) -> None:
        pytest.fail("permanent lock failure must not enter the contention retry")

    monkeypatch.setattr("hawedit.wsl_setup._WINDOWS_HOST", True)
    monkeypatch.setattr("hawedit.wsl_setup.time.sleep", refuse_sleep)
    monkeypatch.setattr("hawedit.wsl_setup.importlib.import_module", lambda _name: LockDependency)
    with (
        pytest.raises(WslRuntimeError, match="cannot acquire.*setup lock") as caught,
        _runtime_transaction_lock(tmp_path / "runtime"),
    ):
        pytest.fail("unowned lock must not enter the transaction")
    assert caught.value.__cause__ is failure
    assert calls == [LockDependency.LK_NBLCK]


@pytest.mark.parametrize("error_number", [errno.EACCES, 36])
def test_setup_contention_retries_and_releases(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, error_number: int
) -> None:
    calls: list[int] = []
    sleeps: list[float] = []

    class LockDependency:
        LK_NBLCK = 1
        LK_UNLCK = 2

        @staticmethod
        def locking(_file: int, mode: int, _bytes: int) -> None:
            calls.append(mode)
            if len(calls) <= 2:
                raise OSError(error_number, "contention")

    monkeypatch.setattr("hawedit.wsl_setup._WINDOWS_HOST", True)
    monkeypatch.setattr("hawedit.wsl_setup.time.sleep", sleeps.append)
    monkeypatch.setattr("hawedit.wsl_setup.importlib.import_module", lambda _name: LockDependency)
    with _runtime_transaction_lock(tmp_path / "runtime"):
        assert calls == [1, 1, 1]
    assert calls == [1, 1, 1, 2]
    assert sleeps == [0.25, 0.25]


def _write_wave(
    path: Path, samples: bytes, *, channels: int = 1, width: int = 2, rate: int = 16_000
) -> None:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(channels)
        audio.setsampwidth(width)
        audio.setframerate(rate)
        audio.writeframes(samples)


@pytest.mark.parametrize("frames", [16_000, 40 * 16_000])
def test_validator_canonical_pcm_uses_exact_predecoded_samples(tmp_path: Path, frames: int) -> None:
    original = np.resize(np.array([-32768, -16384, -1, 0, 1, 16384, 32767], dtype="<i2"), frames)
    path = tmp_path / "speech.wav"
    raw = original.tobytes()
    _write_wave(path, raw)
    unchanged = path.read_bytes()
    adapted = _qwen_audio_input(path)
    assert isinstance(adapted, tuple)
    waveform, rate = adapted
    assert rate == 16_000
    assert waveform.dtype == np.float32
    assert waveform.shape == (frames,)
    np.testing.assert_array_equal(waveform, original.astype(np.float32) / 32768.0)
    assert path.read_bytes() == unchanged


@pytest.mark.parametrize(
    "channels,width,rate,frames",
    [
        (2, 2, 16_000, 16_000),
        (1, 2, 8_000, 8_000),
        (1, 3, 16_000, 16_000),
        (1, 2, 16_000, 40 * 16_000 + 1),
        (1, 2, 16_000, 0),
    ],
)
def test_validator_noncanonical_audio_keeps_original_route(
    tmp_path: Path, channels: int, width: int, rate: int, frames: int
) -> None:
    path = tmp_path / "other.wav"
    _write_wave(
        path, b"\0" * (frames * channels * width), channels=channels, width=width, rate=rate
    )
    assert _qwen_audio_input(path) == str(path)


def test_validator_truncated_pcm_keeps_original_route(tmp_path: Path) -> None:
    path = tmp_path / "truncated.wav"
    _write_wave(path, b"\0\0" * 16_000)
    with path.open("r+b") as stream:
        stream.truncate(path.stat().st_size - 2)
    assert _qwen_audio_input(path) == str(path)


def test_validator_unreadable_header_keeps_original_route(tmp_path: Path) -> None:
    path = tmp_path / "other.mp3"
    path.write_bytes(b"unrecognized-header")
    assert _qwen_audio_input(path) == str(path)
