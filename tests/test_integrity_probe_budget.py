"""Deadline contracts against actual probe implementation; adapter bytes are not asset evidence."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from hawedit import wsl_setup as setup


def install_boundary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, payload: dict[str, object] | None = None
) -> list[dict[str, Any]]:
    receipt = SimpleNamespace(
        generation_root=tmp_path / "environment",
        source_root=tmp_path / "source",
        distro="Ubuntu",
        asset_bytes=43_546_500_168,
    )
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(setup, "load_wsl_runtime_receipt", lambda **_kwargs: receipt)
    monkeypatch.setattr(setup, "wsl_path", lambda path, *_args: "/mapped/" + Path(path).name)

    def process(command: list[str], **options: Any) -> subprocess.CompletedProcess[bytes]:
        seen.append({"command": command, **options})
        output = (
            payload
            if payload is not None
            else {"files_verified": 3, "size_bytes": receipt.asset_bytes, "cuda_device_count": 2}
        )
        return subprocess.CompletedProcess(command, 0, json.dumps(output).encode(), b"")

    monkeypatch.setattr("hawedit.wsl_setup.subprocess.run", process)
    return seen


@pytest.mark.parametrize(
    "budget", [None, True, False, 0, -1, 1801, 1.5, "300", float("nan"), float("inf")]
)
def test_integrity_probe_invalid_budget_refuses_before_receipt(
    monkeypatch: pytest.MonkeyPatch, budget: Any
) -> None:
    def no_receipt(**_kwargs: object) -> None:
        pytest.fail("Invalid integrity budget reached receipt or child work")

    monkeypatch.setattr(setup, "load_wsl_runtime_receipt", no_receipt)
    with pytest.raises(setup.WslRuntimeError, match="timeout_seconds.*1.*1800"):
        setup.probe_wsl_runtime(timeout_seconds=budget)


def test_integrity_probe_default_budget_is_bounded_and_keeps_all_hashes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen = install_boundary(monkeypatch, tmp_path)
    result = setup.probe_wsl_runtime(distro="Ubuntu")
    assert result.files_verified == 3
    assert seen[0]["timeout"] == 300
    assert seen[0]["command"][-1] == setup._PROBE_SCRIPT
    assert "assert_omni_card_integrity()" in seen[0]["command"][-1]
    assert "assert_omni_asset_integrity()" in seen[0]["command"][-1]


@pytest.mark.parametrize("budget", [1, 120, 300, 900, 1800])
def test_integrity_probe_selected_budget_retains_full_hash_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, budget: int
) -> None:
    seen = install_boundary(monkeypatch, tmp_path)
    result = setup.probe_wsl_runtime(distro="Ubuntu", timeout_seconds=budget)
    assert result.size_bytes == 43_546_500_168
    assert seen == [
        {
            "command": [
                "wsl.exe",
                "--distribution",
                "Ubuntu",
                "--exec",
                "env",
                "PYTHONDONTWRITEBYTECODE=1",
                "PYTHONPATH=/mapped/source",
                "/mapped/environment/bin/python",
                "-c",
                setup._PROBE_SCRIPT,
            ],
            "capture_output": True,
            "check": False,
            "timeout": budget,
        }
    ]


@pytest.mark.parametrize("failure", ["timeout", "os"])
def test_integrity_probe_process_failure_is_actionable_refusal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: str
) -> None:
    install_boundary(monkeypatch, tmp_path)

    def process(command: list[str], **options: Any) -> subprocess.CompletedProcess[bytes]:
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, options["timeout"])
        raise OSError("WSL bridge unavailable")

    monkeypatch.setattr("hawedit.wsl_setup.subprocess.run", process)
    with pytest.raises(setup.WslRuntimeError, match="integrity.*(900|unavailable)") as caught:
        setup.probe_wsl_runtime(timeout_seconds=900)
    assert "verified readiness" in str(caught.value)
    assert isinstance(
        caught.value.__cause__, subprocess.TimeoutExpired if failure == "timeout" else OSError
    )


@pytest.mark.parametrize(
    "field,value", [("files_verified", 2), ("size_bytes", 43_546_500_167), ("cuda_device_count", 1)]
)
def test_integrity_probe_drift_still_refuses_with_larger_budget(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, field: str, value: int
) -> None:
    payload: dict[str, object] = {
        "files_verified": 3,
        "size_bytes": 43_546_500_168,
        "cuda_device_count": 2,
    }
    payload[field] = value
    seen = install_boundary(monkeypatch, tmp_path, payload)
    with pytest.raises(setup.WslRuntimeError, match="drifted"):
        setup.probe_wsl_runtime(timeout_seconds=900)
    assert seen[0]["timeout"] == 900


def test_integrity_probe_malformed_output_still_refuses_with_larger_budget(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    install_boundary(monkeypatch, tmp_path)

    def process(command: list[str], **_options: Any) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(command, 0, b"{bad-json", b"")

    monkeypatch.setattr("hawedit.wsl_setup.subprocess.run", process)
    with pytest.raises(setup.WslRuntimeError, match="invalid.*probe output"):
        setup.probe_wsl_runtime(timeout_seconds=900)
