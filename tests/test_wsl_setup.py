from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hawedit.wsl_setup import (
    _prefix,
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

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append(args)
        if "wslpath" in args:
            return subprocess.CompletedProcess(args, 0, b"/mnt/c/runtime\n", b"")
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


def test_a_ready_runtime_is_idempotent_without_another_wsl_call(
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

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("ready setup called WSL again")

    monkeypatch.setattr("hawedit.wsl_setup.subprocess.run", forbidden)
    assert (
        provision_wsl_runtime(runtime_root=runtime, package_source=package, platform_name="nt")
        == runtime
    )


# --- D-102: `--` sends the command through a shell that eats the environment -----------------


def test_every_wsl_invocation_bypasses_the_default_shell() -> None:
    """`--exec`, not `--`. Measured 2026-08-09 on hawapc01, the same probe under both spellings:

        wsl.exe --      env HAWEDIT_WSL_RUNTIME=/tmp/x bash -lc …
            -> RUNTIME=[UNSET]  uv=none  python3.12=none
        wsl.exe --exec  env HAWEDIT_WSL_RUNTIME=/tmp/x bash -lc …
            -> RUNTIME=[/tmp/x]  uv=/home/ai/.local/bin/uv  python3.12=…/python3.12

    `--` only ends option parsing; the command line still goes through the distribution's default
    shell, which expanded the `$VAR` references before the `bash -lc` script saw them and ran
    with a PATH omitting `~/.local/bin`. So the runtime root arrived empty,
    `uv venv --python 3.12 ""` failed with uv's own "a value is required for '[PATH]'", and
    `hawedit-asr-setup` could provision nothing — which is why M1.4 recorded the runtime as
    absent on this machine. With `--exec` it provisions: "OmniASR import OK; CUDA GPUs visible: 2".
    """
    assert _prefix(None) == ["wsl.exe", "--exec"]
    assert _prefix("Ubuntu") == ["wsl.exe", "--distribution", "Ubuntu", "--exec"]
    assert "--" not in _prefix("Ubuntu"), (
        "a bare `--` routes the command through the default shell, which drops every `env VAR=`"
    )


def test_the_asr_producer_uses_the_shared_prefix_rather_than_its_own() -> None:
    """The same bug existed in a second copy, and that is why it is now one function.

    `WslOmniAsrProducer` passes `env PYTHONPATH=<source>` to reach `hawedit.asr_worker` inside
    WSL. With `--`, that assignment was eaten too, so Stage 1 would have died on an unimportable
    worker however well the runtime was provisioned — a separate failure with the same cause,
    which is exactly what duplicated invocation logic buys.
    """
    from hawedit.asr import WslOmniAsrProducer

    producer = WslOmniAsrProducer(distro="Ubuntu")
    assert producer._prefix() == _prefix("Ubuntu", producer.wsl_executable)
    assert "--exec" in producer._prefix()
