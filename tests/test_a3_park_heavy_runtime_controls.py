"""Tests for A3 (D-337): heavy runtime controls parked behind explicit strict flags."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_desktop_default_bypasses_heavy_runtime_controls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Plain desktop ASR producer resolves WSL Python without requiring a .ready receipt."""
    from hawedit.asr import (
        STRICT_RUNTIME_ENV,
        WslOmniAsrProducer,
        create_omni_asr_producer,
        strict_runtime_enabled,
    )

    monkeypatch.delenv(STRICT_RUNTIME_ENV, raising=False)
    monkeypatch.delenv("HAWEDIT_WSL_PYTHON", raising=False)
    assert not strict_runtime_enabled(env={})

    def fail_receipt(**_kwargs: object) -> object:
        raise AssertionError("receipt gate must not block default desktop runs")

    monkeypatch.setattr("hawedit.asr.load_wsl_runtime_receipt", fail_receipt)
    monkeypatch.setattr(
        "hawedit.asr._discover_plain_wsl_python", lambda **_kw: "/opt/wsl/bin/python"
    )
    producer = create_omni_asr_producer("wsl", distro="Ubuntu")
    assert isinstance(producer, WslOmniAsrProducer)
    monkeypatch.setattr(producer, "_wsl_path", lambda path: f"/wsl/{Path(path).name}")

    interpreter, wsl_src = producer._runtime()
    assert interpreter == "/opt/wsl/bin/python"
    assert wsl_src == "/wsl/src"


def test_strict_runtime_flag_enforces_full_receipt_and_admission(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Setting HAWEDIT_STRICT_RUNTIME=1 or strict_runtime=True restores receipt gating."""
    from hawedit.asr import (
        STRICT_RUNTIME_ENV,
        WslOmniAsrProducer,
        create_omni_asr_producer,
        strict_runtime_enabled,
    )

    monkeypatch.setenv(STRICT_RUNTIME_ENV, "1")
    monkeypatch.setattr("hawedit.asr.configured_wsl_runtime", lambda: tmp_path / "absent")
    assert strict_runtime_enabled()

    producer = create_omni_asr_producer("wsl")
    assert isinstance(producer, WslOmniAsrProducer)
    with pytest.raises(RuntimeError, match="runtime receipt is invalid"):
        producer._runtime()

    monkeypatch.delenv(STRICT_RUNTIME_ENV, raising=False)
    explicit = create_omni_asr_producer("wsl", strict_runtime=True)
    assert isinstance(explicit, WslOmniAsrProducer)
    with pytest.raises(RuntimeError, match="runtime receipt is invalid"):
        explicit._runtime()


def test_gpu_runtime_strict_audit_still_rejects_visibility_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Existing strict GPU audit continues refusing CUDA_VISIBLE_DEVICES overrides."""
    from hawedit.gpu_runtime import GpuRuntimeError, audit_gpu_runtime

    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    with pytest.raises(GpuRuntimeError, match="CUDA_VISIBLE_DEVICES"):
        audit_gpu_runtime()


def test_studio_protected_mode_is_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    """Protected Studio 503 admission stays off on desktop unless opted in via env or flag."""
    from hawedit.web import PROTECTED_STUDIO_ENV, protected_studio_enabled

    monkeypatch.delenv(PROTECTED_STUDIO_ENV, raising=False)
    assert not protected_studio_enabled(env={})
    assert protected_studio_enabled(env={PROTECTED_STUDIO_ENV: "1"})
    assert protected_studio_enabled(env={}, protected=True)
