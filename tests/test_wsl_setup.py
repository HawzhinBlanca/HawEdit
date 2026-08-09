from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hawedit.wsl_setup import (
    default_wsl_source,
    package_fingerprint,
    provision_wsl_runtime,
    wsl_path,
)


def test_package_fingerprint_changes_with_worker_source(tmp_path: Path) -> None:
    package = tmp_path / "hawedit"
    package.mkdir()
    module = package / "worker.py"
    module.write_text("value = 1\n", encoding="utf-8")
    before = package_fingerprint(package)
    module.write_text("value = 2\n", encoding="utf-8")
    assert package_fingerprint(package) != before


def test_wsl_path_uses_forward_slashes_so_wsl_does_not_drop_separators(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: list[str] = []

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        seen.append(args[-1])
        return subprocess.CompletedProcess(args, 0, b"/mnt/c/runtime\n", b"")

    monkeypatch.setattr("hawedit.wsl_setup.subprocess.run", fake_run)
    assert wsl_path(tmp_path) == "/mnt/c/runtime"
    assert "\\" not in seen[0]


def test_wheel_safe_setup_copies_only_the_package_and_marks_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package = tmp_path / "installed" / "hawedit"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "asr_worker.py").write_text("WORKER = True\n", encoding="utf-8")
    (package / "__pycache__").mkdir()
    (package / "__pycache__" / "worker.pyc").write_bytes(b"cache")
    runtime = tmp_path / "runtime"
    calls: list[list[str]] = []
    setup_scripts: list[bytes] = []

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append(args)
        if "wslpath" in args:
            return subprocess.CompletedProcess(args, 0, b"/mnt/c/runtime\n", b"")
        script = kwargs.get("input")
        if isinstance(script, bytes):
            setup_scripts.append(script)
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr("hawedit.wsl_setup.subprocess.run", fake_run)
    result = provision_wsl_runtime(runtime_root=runtime, package_source=package, platform_name="nt")
    source = default_wsl_source(package, runtime)
    assert result == runtime
    assert (source / "hawedit" / "asr_worker.py").is_file()
    assert not (source / "hawedit" / "__pycache__").exists()
    assert (source / ".ready").read_text(encoding="ascii") == "ready\n"
    setup_call = next(call for call in calls if "bash" in call)
    assert "HAWEDIT_WSL_RUNTIME=/mnt/c/runtime" in setup_call
    assert "HAWEDIT_WSL_SOURCE=/mnt/c/runtime" in setup_call
    assert setup_call[-3:] == ["bash", "-l", "-s"]
    setup_script = setup_scripts[0].decode("utf-8")
    assert "'torch==2.8.0' 'torchaudio==2.8.0'" in setup_script
    assert "'qwen-asr==0.0.6'" in setup_script
    assert setup_script.count("'fairseq2==0.6'") == 2
    assert setup_script.count("'fonttools==4.60.2'") == 2
    assert "from qwen_asr import Qwen3ASRModel" in setup_script
    assert 'torchaudio_version = torchaudio.__version__.split("+", 1)[0]' in setup_script
    assert "from hawedit.omni_assets import provision_omni_assets" in setup_script
    assert setup_script.index("provision_omni_assets()") < setup_script.index("import torch")


def test_a_ready_runtime_revalidates_assets_and_dependencies(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package = tmp_path / "hawedit"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    source = default_wsl_source(package, runtime)
    source.mkdir(parents=True)
    (source / ".ready").write_text("ready\n", encoding="ascii")

    scripts: list[bytes] = []

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        if "wslpath" in args:
            return subprocess.CompletedProcess(args, 0, b"/mnt/c/runtime\n", b"")
        value = kwargs.get("input")
        if isinstance(value, bytes):
            scripts.append(value)
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr("hawedit.wsl_setup.subprocess.run", fake_run)
    assert (
        provision_wsl_runtime(runtime_root=runtime, package_source=package, platform_name="nt")
        == runtime
    )
    assert len(scripts) == 1
    assert b"provision_omni_assets()" in scripts[0]


def test_failed_revalidation_invalidates_an_existing_ready_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package = tmp_path / "hawedit"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    runtime = tmp_path / "runtime"
    source = default_wsl_source(package, runtime)
    source.mkdir(parents=True)
    ready = source / ".ready"
    ready.write_text("ready\n", encoding="ascii")

    def fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        if "wslpath" in args:
            return subprocess.CompletedProcess(args, 0, b"/mnt/c/runtime\n", b"")
        return subprocess.CompletedProcess(args, 17, b"", b"failed")

    monkeypatch.setattr("hawedit.wsl_setup.subprocess.run", fake_run)
    with pytest.raises(RuntimeError, match="exit code 17"):
        provision_wsl_runtime(runtime_root=runtime, package_source=package, platform_name="nt")

    assert not ready.exists()
