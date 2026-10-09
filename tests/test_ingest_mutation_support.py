"""Actual filesystem mutation controls; Windows lease evidence is host-specific."""

from __future__ import annotations

import hashlib
import os
import threading
import time
from pathlib import Path
from typing import BinaryIO

import pytest

from hawedit.native_process import NativeProcessError, _libraries, _open_image, _path
from ingest_mutation_support import replace_test_executable


def _files(tmp_path: Path) -> tuple[Path, Path]:
    binary = tmp_path / "copied.exe"
    replacement = tmp_path / "replacement.exe"
    binary.write_bytes(b"original copied image")
    replacement.write_bytes(b"changed copied image")
    return binary, replacement


def _lease(binary: Path) -> BinaryIO:
    return _open_image(
        _libraries(),
        _path(binary, directory=False),
        hashlib.sha256(binary.read_bytes()).hexdigest(),
    )


def test_executable_mutation_changes_real_bytes(tmp_path: Path) -> None:
    binary, replacement = _files(tmp_path)
    expected = replacement.read_bytes()
    replace_test_executable(replacement, binary)
    assert binary.read_bytes() == expected
    assert not replacement.exists()


def test_executable_mutation_waits_for_released_windows_lease(tmp_path: Path) -> None:
    binary, replacement = _files(tmp_path)
    expected = replacement.read_bytes()
    if os.name != "nt":
        with pytest.raises(NativeProcessError, match="Windows"):
            _lease(binary)
        replace_test_executable(replacement, binary)
        assert binary.read_bytes() == expected
        return
    with _lease(binary) as lease:
        with pytest.raises(PermissionError):
            replacement.replace(binary)
        release = threading.Timer(0.15, lease.close)
        release.start()
        try:
            replace_test_executable(replacement, binary, timeout_s=2.0)
        finally:
            release.join(3.0)
            assert not release.is_alive(), "Original lease-release thread did not exit"
    assert binary.read_bytes() == expected
    assert not replacement.exists()


def test_executable_mutation_refuses_retained_windows_lease(tmp_path: Path) -> None:
    binary, replacement = _files(tmp_path)
    before = binary.read_bytes(), replacement.read_bytes()
    if os.name != "nt":
        with pytest.raises(NativeProcessError, match="Windows"):
            _lease(binary)
        assert before == (binary.read_bytes(), replacement.read_bytes())
        return
    with _lease(binary):
        with pytest.raises(PermissionError):
            replacement.replace(binary)
        started = time.monotonic()
        with pytest.raises(PermissionError) as refusal:
            replace_test_executable(replacement, binary, timeout_s=0.12)
        elapsed = time.monotonic() - started
        assert refusal.value.winerror in (5, 32)
        assert 0.12 <= elapsed < 2.0
        assert before == (binary.read_bytes(), replacement.read_bytes())
    assert before == (binary.read_bytes(), replacement.read_bytes())


def test_executable_mutation_missing_input_is_not_retried(tmp_path: Path) -> None:
    binary, replacement = _files(tmp_path)
    before = binary.read_bytes(), replacement.read_bytes()
    started = time.monotonic()
    with pytest.raises(FileNotFoundError):
        replace_test_executable(tmp_path / "missing.exe", binary, timeout_s=10.0)
    assert time.monotonic() - started < 2.0
    assert before == (binary.read_bytes(), replacement.read_bytes())


@pytest.mark.parametrize("timeout_s", [0.0, -1.0, float("nan"), float("inf"), -float("inf")])
def test_executable_mutation_rejects_invalid_budget(tmp_path: Path, timeout_s: float) -> None:
    binary, replacement = _files(tmp_path)
    before = binary.read_bytes(), replacement.read_bytes()
    with pytest.raises(ValueError, match="finite positive"):
        replace_test_executable(replacement, binary, timeout_s=timeout_s)
    assert before == (binary.read_bytes(), replacement.read_bytes())
