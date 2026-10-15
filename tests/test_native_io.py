"""Actual pending IO tests prepared before product implementation; no mocks."""

from __future__ import annotations

import ctypes
import hashlib
import importlib
import json
import os
import sys
import time
from ctypes import wintypes as w
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from hawedit.native_process import NativeJob
from hawedit.studio_private import PrivateDirectory


def module() -> ModuleType:
    return importlib.import_module("hawedit.native_io")


def available() -> bool:
    api = module()
    if os.name == "nt":
        return True
    with pytest.raises(api.NativeIOError, match="Windows"):
        api._NativePipe(reading=True)
    return False


def run(tmp_path: Path, code: str, **options: Any) -> Any:
    api = module()
    private = PrivateDirectory(tmp_path / "execution", exclusive=True)
    executable = Path(getattr(sys, "_base_executable", sys.executable)).resolve()
    defaults = dict(input_bytes=b"", timeout_seconds=4, output_limit_bytes=131072)
    defaults.update(options)
    return api.run_native(
        (str(executable), "-I", "-B", "-c", code),
        cwd=private.path,
        environment={"SystemRoot": os.environ.get("SYSTEMROOT", "C:/Windows")},
        expected_executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
        **defaults,
    )


@pytest.mark.parametrize("reading", [False, True])
def test_native_io_pending_cancel_keeps_original_memory_until_completion(reading: bool) -> None:
    if not available():
        return
    pipe = module()._NativePipe(reading=reading)
    try:
        original = (pipe.buffer, pipe.overlap, pipe.event, pipe.handle)
        result = pipe.read() if reading else pipe.write(b"A" * 4096)
        if not reading:
            for _ in range(16):
                if result is None:
                    break
                result = pipe.write(b"A" * 4096)
        assert result is None and pipe.pending
        assert (pipe.buffer, pipe.overlap, pipe.event, pipe.handle) == original
        pipe.close()
        assert not pipe.pending and pipe.handle == 0 and pipe.event == 0
        pipe.close()
    finally:
        pipe.close()


def test_native_io_binary_input_and_independent_streams(tmp_path: Path) -> None:
    if not available():
        return
    payload = bytes(range(256)) * 256
    result = run(
        tmp_path,
        "import sys; b=sys.stdin.buffer.read(); "
        "sys.stdout.buffer.write(b); sys.stderr.buffer.write(b[::-1])",
        input_bytes=payload,
    )
    assert result.exit_code == 0
    assert result.stdout == payload and result.stderr == payload[::-1]


@pytest.mark.parametrize("stream", [1, 2])
def test_native_io_output_overflow_refuses_original_scope(tmp_path: Path, stream: int) -> None:
    if not available():
        return
    with pytest.raises(module().NativeIOError, match="output limit"):
        run(
            tmp_path,
            f"import os,time; os.write({stream},b'X'*1048576); time.sleep(20)",
            output_limit_bytes=4096,
        )


def test_native_io_two_streams_share_one_limit(tmp_path: Path) -> None:
    if not available():
        return
    with pytest.raises(module().NativeIOError, match="output limit"):
        run(
            tmp_path,
            "import os; os.write(1,b'A'*4096); os.write(2,b'B'*4096)",
            output_limit_bytes=8191,
        )


def test_native_io_exact_combined_bound_passes(tmp_path: Path) -> None:
    if not available():
        return
    result = run(
        tmp_path, "import os; os.write(1,b'A'*4096); os.write(2,b'B'*4096)", output_limit_bytes=8192
    )
    assert result.exit_code == 0 and result.stdout == b"A" * 4096 and result.stderr == b"B" * 4096


def test_native_io_empty_output_and_nonzero_exit_are_not_completion(tmp_path: Path) -> None:
    if not available():
        return
    result = run(tmp_path, "raise SystemExit(7)")
    assert result.exit_code == 7 and result.stdout == result.stderr == b""
    assert not hasattr(result, "completed") and not hasattr(result, "ready")


def test_native_io_nonreader_deadline_drains_pending_input(tmp_path: Path) -> None:
    if not available():
        return
    with pytest.raises(module().NativeIOError, match="deadline"):
        run(tmp_path, "import time; time.sleep(20)", input_bytes=b"X" * 65536, timeout_seconds=0.3)


def test_native_io_output_flood_refuses_while_input_blocked(tmp_path: Path) -> None:
    if not available():
        return
    with pytest.raises(module().NativeIOError, match="output limit"):
        run(
            tmp_path,
            "import os,time; os.write(1,b'X'*1048576); time.sleep(20)",
            input_bytes=b"X" * 65536,
            output_limit_bytes=4096,
        )


def test_native_io_true_eof_does_not_complete_live_original(tmp_path: Path) -> None:
    if not available():
        return
    with pytest.raises(module().NativeIOError, match="deadline"):
        run(
            tmp_path,
            "import os,time; os.close(1); os.close(2); time.sleep(20)",
            timeout_seconds=0.3,
        )


def test_native_io_root_exit_does_not_complete_live_native_writer(tmp_path: Path) -> None:
    if not available():
        return
    with pytest.raises(module().NativeIOError, match="deadline"):
        run(
            tmp_path,
            "import subprocess,sys; subprocess.Popen([sys.executable,'-I','-B','-c',"
            "'import time; time.sleep(20)'])",
            timeout_seconds=0.4,
        )


@pytest.mark.parametrize("timeout", [0, -1, True, float("inf"), float("nan"), 43201])
def test_native_io_invalid_deadline_refuses_before_launch(tmp_path: Path, timeout: Any) -> None:
    with pytest.raises(module().NativeIOError, match="deadline"):
        run(tmp_path, "raise RuntimeError('must not run')", timeout_seconds=timeout)


@pytest.mark.parametrize("limit", [0, -1, True, 1.5, 16777217])
def test_native_io_invalid_output_bound_refuses_before_launch(tmp_path: Path, limit: Any) -> None:
    with pytest.raises(module().NativeIOError, match="output limit"):
        run(tmp_path, "raise RuntimeError('must not run')", output_limit_bytes=limit)


@pytest.mark.parametrize("payload", ["text", bytearray(b"mutable"), memoryview(b"mutable")])
def test_native_io_nonimmutable_input_refuses_before_launch(tmp_path: Path, payload: Any) -> None:
    with pytest.raises(module().NativeIOError, match="input"):
        run(tmp_path, "raise RuntimeError('must not run')", input_bytes=payload)


def test_native_io_oversized_input_refuses_before_launch(tmp_path: Path) -> None:
    with pytest.raises(module().NativeIOError, match="input"):
        run(tmp_path, "raise RuntimeError('must not run')", input_bytes=b"X" * 16777217)


def test_native_io_closed_child_input_is_refusal(tmp_path: Path) -> None:
    if not available():
        return
    with pytest.raises(module().NativeIOError, match="input reader closed"):
        run(tmp_path, "import os,time; os.close(0); time.sleep(20)", input_bytes=b"X" * 65536)


@pytest.mark.parametrize("broad", [False, True])
def test_native_io_acl_policy_reads_actual_descriptor(broad: bool) -> None:
    if not available():
        return
    import uuid

    from hawedit.windows_security import _current_user_sid, _SecurityAttributes

    api = module()
    k, a = api._libraries()
    sid = _current_user_sid()
    descriptor = w.LPVOID()
    sddl = f"O:{sid}D:P(A;;GA;;;SY)(A;;GA;;;{sid})"
    if broad:
        sddl += "(A;;GR;;;WD)"
    assert a.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        sddl, 1, ctypes.byref(descriptor), None
    )
    handle = 0
    try:
        attrs = _SecurityAttributes(ctypes.sizeof(_SecurityAttributes), descriptor, False)
        handle = int(
            k.CreateNamedPipeW(
                "\\\\.\\pipe\\HawEdit-test-" + uuid.uuid4().hex,
                1 | 0x40000000 | 0x80000,
                8,
                1,
                4096,
                4096,
                0,
                ctypes.byref(attrs),
            )
            or 0
        )
        assert handle and handle != ctypes.c_void_p(-1).value
        if broad:
            with pytest.raises(api.NativeIOError, match="ACL"):
                api._inspect_private_pipe(handle, sid)
        else:
            api._inspect_private_pipe(handle, sid)
    finally:
        assert not k.LocalFree(descriptor)
        if handle:
            assert k.CloseHandle(handle)


@pytest.mark.parametrize("reading", [False, True])
def test_native_io_actual_cancel_request_does_not_release_pending_memory(reading: bool) -> None:
    if not available():
        return
    pipe = module()._NativePipe(reading=reading)
    try:
        result = pipe.read() if reading else pipe.write(b"X" * 4096)
        if not reading:
            for _ in range(16):
                if result is None:
                    break
                result = pipe.write(b"X" * 4096)
        assert result is None and pipe.pending
        original = (pipe.buffer, pipe.overlap, pipe.event, pipe.handle)
        assert pipe.k.CancelIoEx(pipe.handle, ctypes.byref(pipe.overlap))
        assert pipe.pending
        assert (pipe.buffer, pipe.overlap, pipe.event, pipe.handle) == original
        deadline = time.monotonic() + 5
        completed = pipe._finish()
        while completed is None and time.monotonic() < deadline:
            time.sleep(0.001)
            completed = pipe._finish()
        assert completed == (0, 995) and not pipe.pending
        pipe.close()
        assert pipe.handle == pipe.event == 0
    finally:
        pipe.close()


def test_native_io_uncertain_original_handle_retains_memory_and_refuses_launch(
    tmp_path: Path,
) -> None:
    if not available():
        return
    source = str(Path(__file__).resolve().parents[1] / "src")
    code = (
        "import sys; "
        f"sys.path.insert(0,{source!r}); "
        "import hawedit.native_io as n; p=n._NativePipe(reading=True); "
        "assert p.read() is None and p.pending; "
        "held=(p.buffer,p.overlap,p.event,p.handle); assert p.k.CloseHandle(p.handle)\n"
        "try: p.close()\n"
        "except n.NativeIOError: pass\n"
        "else: raise AssertionError('uncertain original handle accepted')\n"
        "assert p.pending and n._QUARANTINE==[p]; "
        "assert (p.buffer,p.overlap,p.event,p.handle)==held\n"
        "try: n.run_native((),cwd=None,environment={},expected_executable_sha256='',"
        "input_bytes=b'',timeout_seconds=1,output_limit_bytes=1)\n"
        "except n.NativeIOError as e: assert 'retained' in str(e)\n"
        "else: raise AssertionError('quarantined process launched')\n"
        "print('refused')"
    )
    result = run(tmp_path, code)
    assert result.exit_code == 0 and result.stdout.strip() == b"refused" and not result.stderr
    assert module()._QUARANTINE == []


def test_native_io_pending_reads_owner_death_signals_original_native_member(tmp_path: Path) -> None:
    if not available():
        return
    if sys.platform != "win32":  # unreachable: available() is True only on Windows
        return
    private = PrivateDirectory(tmp_path / "owner", exclusive=True)
    barrier, release = private.path / "ready.json", private.path / "release.txt"
    code = (
        "import hashlib,json,os,pathlib,sys,time; "
        "from hawedit.native_process import NativeJob; "
        "from hawedit.native_io import _NativePipe; "
        "a=_NativePipe(reading=True); b=_NativePipe(reading=True); "
        "exe=pathlib.Path(sys._base_executable).resolve(); i=open(os.devnull,'rb'); "
        "j=NativeJob.create((str(exe),'-I','-B','-c','import time; time.sleep(20)'),"
        f"cwd=pathlib.Path({str(private.path)!r}),environment={{'SystemRoot':os.environ['SystemRoot']}},"
        "expected_executable_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(),"
        "stdin=i,stdout=a.child,stderr=b.child); a.close_child(); b.close_child(); "
        "j.resume(); assert a.read() is None and b.read() is None; "
        "assert a.pending and b.pending; "
        f"pathlib.Path({str(barrier)!r}).write_text("
        "json.dumps({'members':j.members(),'pending':2})); "
        "deadline=time.monotonic()+10\n"
        f"while not pathlib.Path({str(release)!r}).exists() and time.monotonic()<deadline: "
        "time.sleep(.01)\n"
        f"if pathlib.Path({str(release)!r}).exists(): os._exit(87)\n"
        "j.close(); a.close(); b.close(); sys.exit(1)"
    )
    loader = ctypes.WinDLL
    k = loader("kernel32", use_last_error=True)
    k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    k.OpenProcess.restype = w.HANDLE
    k.IsProcessInJob.argtypes = [w.HANDLE, w.HANDLE, ctypes.POINTER(w.BOOL)]
    k.IsProcessInJob.restype = w.BOOL
    k.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
    k.WaitForSingleObject.restype = w.DWORD
    k.CloseHandle.argtypes = [w.HANDLE]
    k.CloseHandle.restype = w.BOOL
    executable = Path(sys.executable).resolve()
    held: list[int] = []
    with (
        open(os.devnull, "rb") as stdin,
        private.open_new_file("stdout.log") as stdout,
        private.open_new_file("stderr.log") as stderr,
        NativeJob.create(
            (str(executable), "-I", "-B", "-c", code),
            cwd=private.path,
            environment={"SystemRoot": os.environ["SYSTEMROOT"]},
            expected_executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
        ) as outer,
    ):
        try:
            outer.resume()
            deadline = time.monotonic() + 10
            while not barrier.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert barrier.exists(), private.path.joinpath("stderr.log").read_text()
            ready = json.loads(barrier.read_text())
            assert ready["pending"] == 2 and ready["members"]
            for pid in ready["members"]:
                assert pid != os.getpid() and pid in outer.members()
                handle = int(k.OpenProcess(0x100000 | 0x1000, False, pid) or 0)
                assert handle
                held.append(handle)
                inside = w.BOOL()
                assert k.IsProcessInJob(handle, outer._job, ctypes.byref(inside)) and inside.value
                assert k.WaitForSingleObject(handle, 0) == 258
            release.write_text("release")
            assert outer.wait(10) == 87
            assert all(k.WaitForSingleObject(handle, 0) == 0 for handle in held)
            assert outer.members() == ()
        finally:
            for handle in held:
                assert k.CloseHandle(handle)


def test_native_io_concurrent_scope_refuses_without_waiting_for_active_worker(
    tmp_path: Path,
) -> None:
    if not available():
        return
    import threading

    marker = tmp_path / "active.txt"
    errors: list[BaseException] = []

    def execute() -> None:
        try:
            run(
                tmp_path,
                f"import pathlib,time; pathlib.Path({str(marker)!r}).write_text('active'); "
                "time.sleep(20)",
                timeout_seconds=2,
            )
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=execute)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not marker.exists() and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.read_text() == "active" and thread.is_alive()
        with pytest.raises(module().NativeIOError, match="already owns"):
            module().run_native(
                (),
                cwd=None,
                environment={},
                expected_executable_sha256="",
                input_bytes=b"",
                timeout_seconds=1,
                output_limit_bytes=1,
            )
    finally:
        thread.join(timeout=10)
    assert not thread.is_alive() and len(errors) == 1
    assert isinstance(errors[0], module().NativeIOError) and "deadline" in str(errors[0])
    assert module()._QUARANTINE == []
