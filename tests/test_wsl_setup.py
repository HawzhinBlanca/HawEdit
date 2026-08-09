from __future__ import annotations

import json
import multiprocessing
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from hawedit.omni_assets import OMNI_ASSETS
from hawedit.wsl_setup import (
    _IDENTITY_PROBE_SCRIPT,
    WslRuntimeError,
    _invalidate_runtime_receipts,
    _publish_source_snapshot,
    _runtime_transaction_lock,
    default_wsl_source,
    load_wsl_runtime_receipt,
    package_digest,
    package_fingerprint,
    provision_wsl_runtime,
    wsl_path,
)


def _candidate_payload() -> dict[str, object]:
    return {
        "schema": 1,
        "distro": "Ubuntu",
        "uid": 1000,
        "home": "/home/ai",
        "python": "/runtime/venv/bin/python",
        "python_version": "3.12.13",
        "packages": {
            "fairseq2": "0.6",
            "fonttools": "4.60.2",
            "klpt": "0.1.7",
            "omnilingual-asr": "0.2.0",
            "qwen-asr": "0.0.6",
            "torch": "2.8.0",
            "torchaudio": "2.8.0",
        },
        "cuda_device_count": 2,
        "asset_cache": "/home/ai/.cache/fairseq2/assets",
        "assets": [
            {
                "name": asset.name,
                "path": f"/cache/{asset.cache_key}/{asset.filename}",
                "size": asset.size,
                "sha256": asset.sha256,
            }
            for asset in OMNI_ASSETS
        ],
    }


def _write_candidate(runtime: Path, package: Path) -> None:
    source = default_wsl_source(package, runtime)
    (source / ".runtime-candidate.json").write_text(
        json.dumps(_candidate_payload()), encoding="utf-8"
    )


def _identity_payload() -> dict[str, object]:
    candidate = _candidate_payload()
    return {
        "uid": candidate["uid"],
        "home": candidate["home"],
        "python": candidate["python"],
        "python_version": candidate["python_version"],
        "packages": candidate["packages"],
    }


def _receipt_snapshot(source: Path) -> Path:
    receipt = json.loads((source / ".ready").read_text(encoding="utf-8"))
    snapshot = receipt["source_snapshot"]
    assert isinstance(snapshot, str)
    return source / "snapshots" / snapshot


def _hold_runtime_lock(runtime: str, entered_event: Any, release_event: Any) -> None:
    with _runtime_transaction_lock(Path(runtime)):
        entered_event.set()
        release_event.wait(10)


def _directory_link_or_reparse_stub(
    monkeypatch: pytest.MonkeyPatch, link: Path, target: Path
) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except OSError:
        link.mkdir()
    real_lstat = os.lstat

    def reparse_lstat(path: str | bytes | os.PathLike[str] | os.PathLike[bytes]) -> Any:
        result = real_lstat(path)
        if Path(os.fsdecode(path)) != link:
            return result

        class ReparseStat:
            st_mode = result.st_mode
            st_nlink = result.st_nlink
            st_dev = result.st_dev
            st_ino = result.st_ino
            st_file_attributes = 0x400

        return ReparseStat()

    monkeypatch.setattr("hawedit.wsl_setup.os.lstat", reparse_lstat)


def test_package_fingerprint_changes_with_worker_source(tmp_path: Path) -> None:
    package = tmp_path / "hawedit"
    package.mkdir()
    module = package / "worker.py"
    module.write_text("value = 1\n", encoding="utf-8")
    before = package_fingerprint(package)
    module.write_text("value = 2\n", encoding="utf-8")
    assert package_fingerprint(package) != before


def test_identity_probe_is_self_contained_and_executable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    expected_packages = _candidate_payload()["packages"]
    assert isinstance(expected_packages, dict)
    monkeypatch.setattr(os, "getuid", lambda: 1000, raising=False)
    monkeypatch.setattr("importlib.metadata.version", lambda name: expected_packages[name])

    exec(compile(_IDENTITY_PROBE_SCRIPT, "<wsl-identity-probe>", "exec"), {})

    payload = json.loads(capsys.readouterr().out)
    assert payload["uid"] == 1000
    assert payload["home"] == str(Path.home().resolve())
    assert payload["packages"] == expected_packages


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
            _write_candidate(runtime, package)
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr("hawedit.wsl_setup.subprocess.run", fake_run)
    result = provision_wsl_runtime(runtime_root=runtime, package_source=package, platform_name="nt")
    source = default_wsl_source(package, runtime)
    first_snapshot = _receipt_snapshot(source)
    assert (
        provision_wsl_runtime(runtime_root=runtime, package_source=package, platform_name="nt")
        == runtime
    )
    second_snapshot = _receipt_snapshot(source)
    assert result == runtime
    assert first_snapshot != second_snapshot
    assert (first_snapshot / "hawedit" / "asr_worker.py").is_file()
    assert (second_snapshot / "hawedit" / "asr_worker.py").is_file()
    assert not (second_snapshot / "hawedit" / "__pycache__").exists()
    receipt = json.loads((source / ".ready").read_text(encoding="utf-8"))
    assert receipt["schema"] == 2
    assert len(receipt["source_sha256"]) == 64
    assert receipt["runtime"]["distro"] == "Ubuntu"
    setup_calls = [call for call in calls if "bash" in call]
    setup_call = setup_calls[0]
    assert "HAWEDIT_WSL_RUNTIME=/mnt/c/runtime" in setup_call
    assert "HAWEDIT_WSL_SOURCE=/mnt/c/runtime" in setup_call
    assert any(value.startswith("HAWEDIT_WSL_VENV=") for value in setup_call)
    assert "HAWEDIT_WSL_ENV_REUSE=0" in setup_call
    assert "HAWEDIT_WSL_ENV_REUSE=1" in setup_calls[1]
    assert setup_call[-3:] == ["bash", "-l", "-s"]
    setup_script = setup_scripts[0].decode("utf-8")
    assert "'torch==2.8.0' 'torchaudio==2.8.0'" in setup_script
    assert "'qwen-asr==0.0.6'" in setup_script
    assert setup_script.count("'fairseq2==0.6'") == 2
    assert setup_script.count("'fonttools==4.60.2'") == 2
    assert "from qwen_asr import Qwen3ASRModel" in setup_script
    assert 'torchaudio_version = torchaudio.__version__.split("+", 1)[0]' in setup_script
    assert "from hawedit.omni_assets import (" in setup_script
    assert "provision_omni_assets," in setup_script
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
            _write_candidate(runtime, package)
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr("hawedit.wsl_setup.subprocess.run", fake_run)
    assert (
        provision_wsl_runtime(runtime_root=runtime, package_source=package, platform_name="nt")
        == runtime
    )
    assert len(scripts) == 1
    assert b"provision_omni_assets()" in scripts[0]


def test_setup_refuses_unexpected_importable_source_members(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package = tmp_path / "hawedit"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "asr_worker.so").write_bytes(b"unchecked-native-code")
    runtime = tmp_path / "runtime"
    monkeypatch.setattr(
        "hawedit.wsl_setup.subprocess.run",
        lambda *_args, **_kwargs: pytest.fail("WSL must not run for an unsafe source tree"),
    )

    with pytest.raises(RuntimeError, match="unexpected HawEdit worker source member"):
        provision_wsl_runtime(runtime_root=runtime, package_source=package, platform_name="nt")
    assert not list((runtime / "sources").glob("*/.ready"))


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
        _write_candidate(runtime, package)
        return subprocess.CompletedProcess(args, 17, b"", b"failed")

    monkeypatch.setattr("hawedit.wsl_setup.subprocess.run", fake_run)
    with pytest.raises(RuntimeError, match="exit code 17"):
        provision_wsl_runtime(runtime_root=runtime, package_source=package, platform_name="nt")

    assert not ready.exists()
    assert not (source / ".runtime-candidate.json").exists()


def test_receipt_invalidation_refuses_linked_source_without_touching_external_ready(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime = tmp_path / "runtime"
    sources = runtime / "sources"
    sources.mkdir(parents=True)
    external = tmp_path / "external-source"
    external.mkdir()
    victim = external / ".ready"
    victim.write_bytes(b"external-ready-must-survive")
    _directory_link_or_reparse_stub(monkeypatch, sources / "linked", external)

    with pytest.raises(WslRuntimeError, match="source generation.*unlinked regular directory"):
        _invalidate_runtime_receipts(runtime)
    assert victim.read_bytes() == b"external-ready-must-survive"


def test_snapshot_publication_refuses_linked_root_without_touching_external_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package = tmp_path / "hawedit"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    source_root = tmp_path / "runtime" / "sources" / "identity"
    source_root.mkdir(parents=True)
    external = tmp_path / "external-snapshots"
    external.mkdir()
    victim = external / "victim.txt"
    victim.write_bytes(b"external-snapshot-must-survive")
    _directory_link_or_reparse_stub(monkeypatch, source_root / "snapshots", external)

    with pytest.raises(WslRuntimeError, match="snapshots directory.*unlinked regular directory"):
        _publish_source_snapshot(package, source_root)
    assert victim.read_bytes() == b"external-snapshot-must-survive"
    assert tuple(external.iterdir()) == (victim,)


def test_setup_refuses_linked_runtime_root_without_touching_external_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package = tmp_path / "hawedit"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    external = tmp_path / "external-runtime"
    external.mkdir()
    victim = external / "victim.txt"
    victim.write_bytes(b"external-runtime-must-survive")
    runtime = tmp_path / "runtime-link"
    _directory_link_or_reparse_stub(monkeypatch, runtime, external)
    monkeypatch.setattr(
        "hawedit.wsl_setup.subprocess.run",
        lambda *_args, **_kwargs: pytest.fail("WSL must not run through a linked runtime root"),
    )

    with pytest.raises(WslRuntimeError, match="runtime root.*unlinked regular directory"):
        provision_wsl_runtime(runtime_root=runtime, package_source=package, platform_name="nt")
    assert victim.read_bytes() == b"external-runtime-must-survive"


def test_reuse_drift_never_publishes_an_immediately_invalid_receipt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package = tmp_path / "hawedit"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    runtime = tmp_path / "runtime"
    setup_count = 0

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        nonlocal setup_count
        if "wslpath" in args:
            return subprocess.CompletedProcess(args, 0, b"/mnt/c/runtime\n", b"")
        if "bash" in args:
            setup_count += 1
            payload = _candidate_payload()
            if setup_count == 2:
                payload["cuda_device_count"] = 3
            source = default_wsl_source(package, runtime)
            (source / ".runtime-candidate.json").write_text(json.dumps(payload), encoding="utf-8")
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr("hawedit.wsl_setup.subprocess.run", fake_run)
    provision_wsl_runtime(runtime_root=runtime, package_source=package, platform_name="nt")
    source = default_wsl_source(package, runtime)
    assert (source / ".ready").is_file()

    with pytest.raises(WslRuntimeError, match="generation validation changed"):
        provision_wsl_runtime(runtime_root=runtime, package_source=package, platform_name="nt")
    assert not (source / ".ready").exists()
    assert not (source / ".runtime-candidate.json").exists()


def test_setup_transaction_lock_serializes_separate_processes(tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    first_entered = context.Event()
    first_release = context.Event()
    second_entered = context.Event()
    second_release = context.Event()
    first = context.Process(
        target=_hold_runtime_lock, args=(str(tmp_path / "runtime"), first_entered, first_release)
    )
    second = context.Process(
        target=_hold_runtime_lock, args=(str(tmp_path / "runtime"), second_entered, second_release)
    )
    first.start()
    try:
        assert first_entered.wait(10)
        second.start()
        assert not second_entered.wait(0.5), "two processes entered one runtime transaction"
        first_release.set()
        assert second_entered.wait(10)
        second_release.set()
        second.join(10)
        assert second.exitcode == 0
    finally:
        first_release.set()
        second_release.set()
        first.join(10)
        if second.pid is not None:
            second.join(10)
    assert first.exitcode == 0


def test_windows_setup_lock_retries_beyond_msvcrt_short_lock_window(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class ContendedMsvcrt:
        LK_NBLCK = 1
        LK_UNLCK = 2

        def __init__(self) -> None:
            self.attempts = 0
            self.unlocked = False

        def locking(self, _file: int, mode: int, _bytes: int) -> None:
            if mode == self.LK_UNLCK:
                self.unlocked = True
                return
            self.attempts += 1
            if self.attempts <= 11:
                raise OSError(36, "simulated lock contention")

    fake = ContendedMsvcrt()
    monkeypatch.setattr("hawedit.wsl_setup._WINDOWS_HOST", True)
    monkeypatch.setattr("hawedit.wsl_setup.time.sleep", lambda _seconds: None)
    # Patch import resolution last: pytest itself uses importlib to resolve string targets.
    monkeypatch.setattr("hawedit.wsl_setup.importlib.import_module", lambda _name: fake)

    with _runtime_transaction_lock(tmp_path / "runtime"):
        assert fake.attempts == 12
    assert fake.unlocked


def test_windows_setup_lock_normalizes_acquire_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class PermanentlyContendedMsvcrt:
        LK_NBLCK = 1
        LK_UNLCK = 2

        @staticmethod
        def locking(_file: int, _mode: int, _bytes: int) -> None:
            raise OSError(36, "simulated permanent contention")

    monkeypatch.setattr("hawedit.wsl_setup._WINDOWS_HOST", True)
    monkeypatch.setattr("hawedit.wsl_setup._WINDOWS_LOCK_TIMEOUT_SECONDS", 0)
    monkeypatch.setattr(
        "hawedit.wsl_setup.importlib.import_module",
        lambda _name: PermanentlyContendedMsvcrt(),
    )

    with (
        pytest.raises(WslRuntimeError, match="timed out waiting.*setup lock"),
        _runtime_transaction_lock(tmp_path / "runtime"),
    ):
        pytest.fail("a contended lock must not be entered")


def test_windows_unlock_failure_never_masks_body_exception(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class UnlockFailsMsvcrt:
        LK_NBLCK = 1
        LK_UNLCK = 2

        @classmethod
        def locking(cls, _file: int, mode: int, _bytes: int) -> None:
            if mode == cls.LK_UNLCK:
                raise OSError(5, "simulated unlock failure")

    monkeypatch.setattr("hawedit.wsl_setup._WINDOWS_HOST", True)
    monkeypatch.setattr(
        "hawedit.wsl_setup.importlib.import_module", lambda _name: UnlockFailsMsvcrt()
    )

    with (
        pytest.raises(ValueError, match="original setup failure"),
        _runtime_transaction_lock(tmp_path / "runtime"),
    ):
        raise ValueError("original setup failure")
    with (
        pytest.raises(WslRuntimeError, match="cannot release.*setup lock"),
        _runtime_transaction_lock(tmp_path / "runtime"),
    ):
        pass


def test_posix_setup_lock_normalizes_acquire_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class AcquireFailsFcntl:
        LOCK_EX = 1
        LOCK_UN = 2

        @staticmethod
        def flock(_file: int, _operation: int) -> None:
            raise OSError(5, "simulated acquire failure")

    monkeypatch.setattr("hawedit.wsl_setup._WINDOWS_HOST", False)
    monkeypatch.setattr(
        "hawedit.wsl_setup.importlib.import_module", lambda _name: AcquireFailsFcntl()
    )

    with (
        pytest.raises(WslRuntimeError, match="cannot acquire.*setup lock"),
        _runtime_transaction_lock(tmp_path / "runtime"),
    ):
        pytest.fail("a failed POSIX lock must not be entered")


def test_setup_lock_refuses_hardlink_without_touching_target(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    victim = tmp_path / "victim.txt"
    victim.write_bytes(b"do-not-touch")
    os.link(victim, runtime / ".setup.lock")

    with (
        pytest.raises(WslRuntimeError, match="one unlinked regular file"),
        _runtime_transaction_lock(runtime),
    ):
        pytest.fail("hard-linked lock must never be acquired")
    assert victim.read_bytes() == b"do-not-touch"


def test_setup_lock_refuses_symlink_without_touching_target(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    victim = tmp_path / "victim.txt"
    victim.write_bytes(b"do-not-touch")
    try:
        (runtime / ".setup.lock").symlink_to(victim)
    except OSError:
        lock_path = runtime / ".setup.lock"
        lock_path.write_bytes(b"existing-lock")
        real_lstat = os.lstat

        def reparse_lstat(path: str | bytes | os.PathLike[str] | os.PathLike[bytes]) -> Any:
            result = real_lstat(path)
            if Path(os.fsdecode(path)) != lock_path:
                return result

            class ReparseStat:
                st_mode = result.st_mode
                st_nlink = result.st_nlink
                st_dev = result.st_dev
                st_ino = result.st_ino
                st_file_attributes = 0x400

            return ReparseStat()

        monkeypatch.setattr("hawedit.wsl_setup.os.lstat", reparse_lstat)

    with (
        pytest.raises(WslRuntimeError, match="safely open|one unlinked regular file"),
        _runtime_transaction_lock(runtime),
    ):
        pytest.fail("symlinked lock must never be acquired")
    assert victim.read_bytes() == b"do-not-touch"


def test_legacy_ready_flag_is_not_a_runtime_receipt(tmp_path: Path) -> None:
    package = tmp_path / "hawedit"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    runtime = tmp_path / "runtime"
    source = default_wsl_source(package, runtime)
    source.mkdir(parents=True)
    (source / ".ready").write_text("ready\n", encoding="ascii")

    with pytest.raises(WslRuntimeError, match="cannot read.*readiness receipt"):
        load_wsl_runtime_receipt(runtime_root=runtime, package_source=package)


def test_receipt_refuses_a_missing_wsl_interpreter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package = tmp_path / "hawedit"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    runtime = tmp_path / "runtime"

    def fake_setup(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        if "wslpath" in args:
            return subprocess.CompletedProcess(args, 0, b"/mnt/c/runtime\n", b"")
        if "bash" in args:
            _write_candidate(runtime, package)
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr("hawedit.wsl_setup.subprocess.run", fake_setup)
    provision_wsl_runtime(runtime_root=runtime, package_source=package, platform_name="nt")

    def missing_python(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        if "wslpath" in args:
            return subprocess.CompletedProcess(args, 0, b"/mnt/c/generation\n", b"")
        return subprocess.CompletedProcess(args, 1, b"", b"missing")

    monkeypatch.setattr("hawedit.wsl_setup.subprocess.run", missing_python)
    with pytest.raises(WslRuntimeError, match="interpreter is missing"):
        load_wsl_runtime_receipt(runtime_root=runtime, package_source=package)


def test_receipt_refuses_tampered_copied_worker_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package = tmp_path / "hawedit"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    runtime = tmp_path / "runtime"

    def fake_setup(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        if "wslpath" in args:
            return subprocess.CompletedProcess(args, 0, b"/mnt/c/runtime\n", b"")
        if "bash" in args:
            _write_candidate(runtime, package)
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr("hawedit.wsl_setup.subprocess.run", fake_setup)
    provision_wsl_runtime(runtime_root=runtime, package_source=package, platform_name="nt")
    source = default_wsl_source(package, runtime)
    (_receipt_snapshot(source) / "hawedit" / "__init__.py").write_text(
        "TAMPERED = True\n", encoding="utf-8"
    )

    with pytest.raises(WslRuntimeError, match="copied.*source does not match"):
        load_wsl_runtime_receipt(runtime_root=runtime, package_source=package)


@pytest.mark.parametrize("tamper", ["pyc", "extra-directory"])
def test_receipt_refuses_unmanifested_snapshot_members(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tamper: str
) -> None:
    package = tmp_path / "hawedit"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    runtime = tmp_path / "runtime"

    def fake_setup(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        if "wslpath" in args:
            return subprocess.CompletedProcess(args, 0, b"/mnt/c/runtime\n", b"")
        if "bash" in args:
            _write_candidate(runtime, package)
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr("hawedit.wsl_setup.subprocess.run", fake_setup)
    provision_wsl_runtime(runtime_root=runtime, package_source=package, platform_name="nt")
    snapshot_package = _receipt_snapshot(default_wsl_source(package, runtime)) / "hawedit"
    if tamper == "pyc":
        cache = snapshot_package / "__pycache__"
        cache.mkdir()
        (cache / "__init__.cpython-312.pyc").write_bytes(b"malicious")
        with pytest.raises(RuntimeError, match="must not contain bytecode caches"):
            package_digest(snapshot_package, reject_bytecode_cache=True)
    else:
        (snapshot_package / "shadow").mkdir()

    with pytest.raises(WslRuntimeError, match="cannot verify.*worker source"):
        load_wsl_runtime_receipt(runtime_root=runtime, package_source=package)


def test_receipt_runtime_must_match_versioned_generation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package = tmp_path / "hawedit"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    runtime = tmp_path / "runtime"

    def fake_setup(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        if "wslpath" in args:
            return subprocess.CompletedProcess(args, 0, b"/mnt/c/runtime\n", b"")
        if "bash" in args:
            _write_candidate(runtime, package)
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr("hawedit.wsl_setup.subprocess.run", fake_setup)
    provision_wsl_runtime(runtime_root=runtime, package_source=package, platform_name="nt")
    source = default_wsl_source(package, runtime)
    marker = source / ".ready"
    receipt = json.loads(marker.read_text(encoding="utf-8"))
    receipt["runtime"]["home"] = "/home/forged"
    marker.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(WslRuntimeError, match="does not match.*environment generation"):
        load_wsl_runtime_receipt(runtime_root=runtime, package_source=package)


def test_receipt_refuses_live_interpreter_package_drift(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package = tmp_path / "hawedit"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    runtime = tmp_path / "runtime"

    def fake_setup(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        if "wslpath" in args:
            return subprocess.CompletedProcess(args, 0, b"/mnt/c/runtime\n", b"")
        if "bash" in args:
            _write_candidate(runtime, package)
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr("hawedit.wsl_setup.subprocess.run", fake_setup)
    provision_wsl_runtime(runtime_root=runtime, package_source=package, platform_name="nt")

    live_identity = _identity_payload()
    assert isinstance(live_identity["packages"], dict)
    live_identity["packages"] = {**live_identity["packages"], "torch": "0.0.0"}

    def drifted_runtime(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        if "wslpath" in args:
            return subprocess.CompletedProcess(args, 0, b"/mnt/c/runtime\n", b"")
        return subprocess.CompletedProcess(args, 0, json.dumps(live_identity).encode(), b"")

    monkeypatch.setattr("hawedit.wsl_setup.subprocess.run", drifted_runtime)
    with pytest.raises(WslRuntimeError, match="package versions drifted"):
        load_wsl_runtime_receipt(runtime_root=runtime, package_source=package)
