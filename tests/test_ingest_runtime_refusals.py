"""Physical process-launch and deadline refusals, without replacing the runner."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from hawedit.ingest import IngestError, _extract_once, _run


def _marker_command(marker: Path) -> list[str]:
    return [
        sys.executable,
        "-I",
        "-B",
        "-c",
        f"from pathlib import Path; Path({str(marker)!r}).write_text('launched')",
    ]


@pytest.mark.parametrize("setting", ["no-deadline", "nan", "inf", "-inf", "0", "-1", "43201"])
def test_ingest_invalid_timeout_setting_refuses_before_real_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, setting: str
) -> None:
    monkeypatch.setenv("HAWEDIT_INGEST_TIMEOUT_S", setting)
    marker = tmp_path / "child-launched"
    with pytest.raises(IngestError, match="HAWEDIT_INGEST_TIMEOUT_S"):
        _run(_marker_command(marker))
    assert not marker.exists()


@pytest.mark.parametrize("timeout", [True, None, "1", float("nan"), float("inf"), 0, -1, 43201])
def test_ingest_invalid_default_timeout_refuses_before_real_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, timeout: Any
) -> None:
    monkeypatch.delenv("HAWEDIT_INGEST_TIMEOUT_S", raising=False)
    marker = tmp_path / "child-launched"
    with pytest.raises(IngestError, match="timeout"):
        _run(_marker_command(marker), timeout=timeout)
    assert not marker.exists()


def test_ingest_missing_executable_has_contextual_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HAWEDIT_INGEST_TIMEOUT_S", raising=False)
    executable = tmp_path / "absent-decoder"
    with pytest.raises(IngestError, match="absent-decoder.*launch") as raised:
        _run([str(executable)])
    assert isinstance(raised.value.__cause__, OSError)
    assert not list(tmp_path.iterdir())


def test_ingest_launch_refusal_preserves_atomic_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HAWEDIT_INGEST_TIMEOUT_S", raising=False)
    source = tmp_path / "source.bin"
    source.write_bytes(b"original source bytes")
    dest = tmp_path / "output" / "audio.wav"
    executable = tmp_path / "absent-decoder"
    with pytest.raises(IngestError, match="absent-decoder.*launch"):
        _extract_once(source, dest, [str(executable), str(dest)])
    assert source.read_bytes() == b"original source bytes"
    assert not dest.exists()
    assert not dest.with_suffix(".wav.provenance.json").exists()
    assert [path.name for path in dest.parent.iterdir()] == ["audio.wav.lock"]


@pytest.mark.parametrize("setting", [None, "", "5.5"])
def test_ingest_valid_timeout_retains_actual_child_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, setting: str | None
) -> None:
    if setting is None:
        monkeypatch.delenv("HAWEDIT_INGEST_TIMEOUT_S", raising=False)
    else:
        monkeypatch.setenv("HAWEDIT_INGEST_TIMEOUT_S", setting)
    marker = tmp_path / "child-launched"
    result = _run(_marker_command(marker))
    assert result.returncode == 0 and result.stdout == result.stderr == b""
    assert marker.read_text() == "launched"
