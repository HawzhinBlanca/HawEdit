"""Actual native lifetimes on Windows; unsupported hosts prove refusal only."""

from __future__ import annotations

import ctypes
import hashlib
import io
import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from ctypes import wintypes as w
from pathlib import Path
from typing import Any

import pytest

from hawedit.native_process import NativeJob, NativeProcessError
from hawedit.studio_private import PrivateDirectory


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _environment() -> dict[str, str]:
    return {"SystemRoot": os.environ.get("SYSTEMROOT", "C:/Windows")}


def _available() -> bool:
    if os.name == "nt":
        return True
    with (
        open(os.devnull, "rb") as stdin,
        open(os.devnull, "wb") as out,
        pytest.raises(NativeProcessError, match="Windows"),
    ):
        NativeJob.create(
            (sys.executable, "-c", "raise RuntimeError('must not run')"),
            cwd=Path.cwd(),
            environment=_environment(),
            expected_executable_sha256=_hash(Path(sys.executable)),
            stdin=stdin,
            stdout=out,
            stderr=out,
        )
    return False


@contextmanager
def _inputs(tmp_path: Path, code: str = "print('owned')") -> Iterator[dict[str, Any]]:
    directory = PrivateDirectory(tmp_path / "stdio", exclusive=True)
    with (
        open(os.devnull, "rb") as stdin,
        directory.open_new_file("stdout.log") as stdout,
        directory.open_new_file("stderr.log") as stderr,
    ):
        yield dict(
            argv=(str(Path(sys.executable).resolve()), "-I", "-B", "-c", code),
            cwd=directory.path,
            environment=_environment(),
            expected_executable_sha256=_hash(Path(sys.executable)),
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
        )


def _kernel() -> Any:
    loader = getattr(ctypes, "WinDLL", None)
    assert callable(loader)
    k = loader("kernel32", use_last_error=True)
    signatures = {
        "OpenProcess": ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
        "WaitForSingleObject": ([w.HANDLE, w.DWORD], w.DWORD),
        "CloseHandle": ([w.HANDLE], w.BOOL),
        "GetProcessId": ([w.HANDLE], w.DWORD),
        "GetProcessTimes": (
            [w.HANDLE, *([ctypes.POINTER(w.FILETIME)] * 4)],
            w.BOOL,
        ),
        "IsProcessInJob": ([w.HANDLE, w.HANDLE, ctypes.POINTER(w.BOOL)], w.BOOL),
        "QueryFullProcessImageNameW": (
            [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)],
            w.BOOL,
        ),
        "CreateEventW": ([ctypes.c_void_p, w.BOOL, w.BOOL, w.LPCWSTR], w.HANDLE),
        "SetHandleInformation": ([w.HANDLE, w.DWORD, w.DWORD], w.BOOL),
    }
    for name, (args, result) in signatures.items():
        fn = getattr(k, name)
        fn.argtypes = args
        fn.restype = result
    return k


def _observe(k: Any, pid: int, job: NativeJob | None = None) -> int:
    assert pid != os.getpid()
    handle = k.OpenProcess(0x00100000 | 0x1000, False, pid)
    assert handle
    try:
        assert k.GetProcessId(handle) == pid
        assert k.WaitForSingleObject(handle, 0) == 258
        creation, exited, kernel, user = (w.FILETIME() for _ in range(4))
        assert k.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exited),
            ctypes.byref(kernel),
            ctypes.byref(user),
        )
        assert (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        image = ctypes.create_unicode_buffer(32768)
        length = w.DWORD(len(image))
        assert k.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(length))
        assert Path(image.value).is_file()
        if job is not None:
            inside = w.BOOL()
            assert k.IsProcessInJob(handle, job._job, ctypes.byref(inside))
            assert inside.value
        return int(handle)
    except BaseException:
        k.CloseHandle(handle)
        raise


def _ready(path: Path, timeout: float = 10) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
            else:
                assert isinstance(value, dict)
                return value
        time.sleep(0.01)
    raise AssertionError("Actual harmless child did not reach its live barrier")


def test_native_owner_unsupported_platform_refuses(tmp_path: Path) -> None:
    if not _available():
        return
    with _inputs(tmp_path) as kwargs, NativeJob.create(**kwargs) as job:
        job.resume()
        assert job.wait(10) == 0


@pytest.mark.parametrize(
    "change",
    [
        {"argv": ()},
        {"argv": "not-an-argv"},
        {"argv": ("relative.exe",)},
        {"argv": ("C:/hawedit-deliberately-absent.exe",)},
        {"argv": (sys.executable, "bad\0argument")},
        {"cwd": Path("relative")},
        {"expected_executable_sha256": "x" * 64},
        {"expected_executable_sha256": "0" * 63},
        {"expected_executable_sha256": False},
        {"environment": {}},
        {"environment": {"SystemRoot": "C:/Windows", "BAD=KEY": "value"}},
        {"environment": {"SystemRoot": "C:/Windows", "BAD": "bad\0value"}},
        {"environment": {"SystemRoot": "C:/Windows", "PATH": "x", "Path": "y"}},
        {"environment": {"SystemRoot": "C:/Windows", "BAD": 1}},
    ],
)
def test_native_owner_rejects_invalid_launch_inputs(
    tmp_path: Path, change: dict[str, object]
) -> None:
    if not _available():
        return
    job = None
    with _inputs(tmp_path) as kwargs:
        kwargs.update(change)
        try:
            with pytest.raises(NativeProcessError):
                job = NativeJob.create(**kwargs)
        finally:
            if job is not None:
                job.close()


def test_native_owner_wrong_image_hash_refuses(tmp_path: Path) -> None:
    if not _available():
        return
    with _inputs(tmp_path) as kwargs:
        kwargs["expected_executable_sha256"] = "0" * 64
        with pytest.raises(NativeProcessError, match="hash"):
            NativeJob.create(**kwargs)


def test_native_owner_refuses_invalid_stdio(tmp_path: Path) -> None:
    if not _available():
        return
    with _inputs(tmp_path) as kwargs:
        kwargs["stdout"] = io.BytesIO()
        with pytest.raises(NativeProcessError, match="stdio"):
            NativeJob.create(**kwargs)


def test_native_owner_never_runs_code_before_job_assignment(tmp_path: Path) -> None:
    if not _available():
        return
    marker = tmp_path / "ran.txt"
    code = f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')"
    k = _kernel()
    with _inputs(tmp_path, code) as kwargs, NativeJob.create(**kwargs) as job:
        held = _observe(k, job.process_id, job)
        try:
            assert job.members() == (job.process_id,)
            time.sleep(0.05)
            assert not marker.exists()
            job.resume()
            assert job.wait(10) == 0
            assert k.WaitForSingleObject(held, 0) == 0
            assert job.members() == ()
            assert marker.read_text() == "ran"
        finally:
            k.CloseHandle(held)


def test_native_owner_runs_actual_child(tmp_path: Path) -> None:
    if not _available():
        return
    code = "import sys; print('owned'); print('diagnostic',file=sys.stderr); sys.exit(3)"
    with _inputs(tmp_path, code) as kwargs, NativeJob.create(**kwargs) as job:
        job.resume()
        assert job.wait(10) == 3
        assert job.members() == ()
    assert (tmp_path / "stdio/stdout.log").read_bytes().strip() == b"owned"
    assert (tmp_path / "stdio/stderr.log").read_bytes().strip() == b"diagnostic"


def test_native_owner_resume_is_single_use(tmp_path: Path) -> None:
    if not _available():
        return
    with _inputs(tmp_path) as kwargs, NativeJob.create(**kwargs) as job:
        job.resume()
        with pytest.raises(NativeProcessError, match="resume"):
            job.resume()
        assert job.wait(10) == 0
    with pytest.raises(NativeProcessError, match="closed"):
        job.resume()


def test_native_owner_stdio_handle_list(tmp_path: Path) -> None:
    if not _available():
        return
    k = _kernel()
    sentinel = k.CreateEventW(None, True, False, None)
    assert sentinel
    assert k.SetHandleInformation(sentinel, 1, 1)
    try:
        code = (
            "import ctypes; k=ctypes.WinDLL('kernel32'); "
            "k.SetEvent.argtypes=[ctypes.c_void_p]; k.SetEvent.restype=ctypes.c_int; "
            f"k.SetEvent({int(sentinel)}); print('probed')"
        )
        with _inputs(tmp_path, code) as kwargs, NativeJob.create(**kwargs) as job:
            job.resume()
            assert job.wait(10) == 0
        assert (tmp_path / "stdio/stdout.log").read_bytes().strip() == b"probed"
        assert k.WaitForSingleObject(sentinel, 0) == 258
    finally:
        k.CloseHandle(sentinel)


def test_native_owner_holds_actual_image_lease(tmp_path: Path) -> None:
    if not _available():
        return
    copied = tmp_path / "copied-launcher.exe"
    copied.write_bytes(Path(sys.executable).read_bytes())
    with _inputs(tmp_path) as kwargs:
        kwargs["argv"] = (str(copied), "-c", "print('must remain suspended')")
        kwargs["expected_executable_sha256"] = _hash(copied)
        with NativeJob.create(**kwargs), pytest.raises(PermissionError), copied.open("wb"):
            pass
    assert _hash(copied) == kwargs["expected_executable_sha256"]
    copied.write_bytes(b"now-released")
    assert copied.read_bytes() == b"now-released"


def _descendants_code(path: Path, *, exit_root: bool = False) -> str:
    return (
        "import json,os,pathlib,subprocess,sys,time; "
        "child=subprocess.Popen([sys._base_executable,'-I','-B','-c',"
        "'import time; time.sleep(20)'],stdin=subprocess.DEVNULL,"
        "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,"
        "creationflags=subprocess.CREATE_NO_WINDOW); "
        f"pathlib.Path({str(path)!r}).write_text(json.dumps({{'root':os.getpid(),"
        "'child':child.pid})); " + ("sys.exit(0)" if exit_root else "time.sleep(20)")
    )


@pytest.mark.parametrize("action", ["stop", "timeout"])
def test_native_owner_stop_terminates_actual_descendants(tmp_path: Path, action: str) -> None:
    if not _available():
        return
    barrier = tmp_path / "ready.json"
    k = _kernel()
    held: list[int] = []
    with _inputs(tmp_path, _descendants_code(barrier)) as kwargs, NativeJob.create(**kwargs) as job:
        job.resume()
        ready = _ready(barrier)
        members = job.members()
        assert {job.process_id, ready["root"], ready["child"]}.issubset(members)
        try:
            for pid in members:
                held.append(_observe(k, pid, job))
            if action == "stop":
                job.stop()
                with pytest.raises(NativeProcessError, match="stopped"):
                    job.wait(1)
            else:
                with pytest.raises(NativeProcessError, match="deadline"):
                    job.wait(0.05)
            assert job.members() == ()
            assert all(k.WaitForSingleObject(handle, 0) == 0 for handle in held)
        finally:
            for handle in held:
                k.CloseHandle(handle)


def test_native_owner_launcher_exit_not_completion(tmp_path: Path) -> None:
    if not _available():
        return
    barrier = tmp_path / "ready.json"
    k = _kernel()
    with (
        _inputs(tmp_path, _descendants_code(barrier, exit_root=True)) as kwargs,
        NativeJob.create(**kwargs) as job,
    ):
        job.resume()
        ready = _ready(barrier)
        child = _observe(k, ready["child"], job)
        try:
            with pytest.raises(NativeProcessError, match="deadline"):
                job.wait(0.1)
            assert job.members() == ()
            assert k.WaitForSingleObject(child, 0) == 0
        finally:
            k.CloseHandle(child)


def test_native_owner_abrupt_parent_death(tmp_path: Path) -> None:
    if not _available():
        return
    barrier = tmp_path / "owner-ready.json"
    release = tmp_path / "release.txt"
    code = (
        "import hashlib,json,os,pathlib,sys,time; "
        "from hawedit.native_process import NativeJob; "
        "exe=pathlib.Path(sys.executable).resolve(); "
        "i=open(os.devnull,'rb'); o=open(os.devnull,'wb'); "
        "j=NativeJob.create((str(exe),'-I','-B','-c','import time; time.sleep(20)'),"
        "cwd=exe.parent,environment={'SystemRoot':os.environ['SystemRoot']},"
        "expected_executable_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(),"
        "stdin=i,stdout=o,stderr=o); j.resume(); time.sleep(.1); "
        f"pathlib.Path({str(barrier)!r}).write_text(json.dumps({{'members':j.members()}})); "
        "deadline=time.monotonic()+10\n"
        f"while not pathlib.Path({str(release)!r}).exists() and time.monotonic()<deadline: "
        "time.sleep(.01)\n"
        f"if pathlib.Path({str(release)!r}).exists(): os._exit(87)\n"
        "j.close(); sys.exit(1)"
    )
    k = _kernel()
    held: list[int] = []
    owner = subprocess.Popen(
        [sys.executable, "-I", "-B", "-c", code],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        ready = _ready(barrier)
        assert ready["members"]
        for pid in ready["members"]:
            held.append(_observe(k, pid))
        release.write_text("release")
        assert owner.wait(timeout=10) == 87
        assert all(k.WaitForSingleObject(handle, 5000) == 0 for handle in held)
    finally:
        if owner.poll() is None:
            owner.kill()
            owner.wait(timeout=5)
        for handle in held:
            k.CloseHandle(handle)


@pytest.mark.parametrize("timeout", [False, 0, -1, float("nan"), float("inf"), 43201, "1", None])
def test_native_owner_refuses_invalid_wait_deadline(tmp_path: Path, timeout: Any) -> None:
    if not _available():
        return
    with _inputs(tmp_path) as kwargs, NativeJob.create(**kwargs) as job:
        with pytest.raises(NativeProcessError, match="deadline"):
            job.wait(timeout)
        job.resume()
        assert job.wait(10) == 0


@pytest.mark.parametrize("systemroot", ["", "   "])
def test_native_owner_refuses_blank_systemroot(tmp_path: Path, systemroot: str) -> None:
    if not _available():
        return
    with _inputs(tmp_path) as kwargs:
        kwargs["environment"] = {"SystemRoot": systemroot}
        with pytest.raises(NativeProcessError, match="SystemRoot"):
            NativeJob.create(**kwargs)


def test_native_owner_wait_before_resume_refuses(tmp_path: Path) -> None:
    if not _available():
        return
    marker = tmp_path / "ran.txt"
    code = f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')"
    k = _kernel()
    with _inputs(tmp_path, code) as kwargs, NativeJob.create(**kwargs) as job:
        held = _observe(k, job.process_id, job)
        try:
            with pytest.raises(NativeProcessError, match="resume"):
                job.wait(0.1)
            assert not marker.exists()
            assert k.WaitForSingleObject(held, 0) == 258
            job.close()
            assert k.WaitForSingleObject(held, 0) == 0
            assert not marker.exists()
        finally:
            k.CloseHandle(held)


def test_native_owner_context_exit_drains_actual_running_descendants(tmp_path: Path) -> None:
    if not _available():
        return
    barrier = tmp_path / "ready.json"
    k = _kernel()
    held: list[int] = []
    try:
        with (
            _inputs(tmp_path, _descendants_code(barrier)) as kwargs,
            NativeJob.create(**kwargs) as job,
        ):
            job.resume()
            ready = _ready(barrier)
            members = job.members()
            assert {ready["root"], ready["child"]}.issubset(members)
            for pid in members:
                held.append(_observe(k, pid, job))
        assert held
        assert all(k.WaitForSingleObject(handle, 0) == 0 for handle in held)
        job.close()
        with pytest.raises(NativeProcessError, match="closed"):
            job.members()
    finally:
        for handle in held:
            k.CloseHandle(handle)


def test_native_owner_waits_for_actual_natural_descendant_exit(tmp_path: Path) -> None:
    if not _available():
        return
    barrier = tmp_path / "ready.json"
    release = tmp_path / "release.txt"
    code = (
        "import json,os,pathlib,subprocess,sys,time; "
        "child=subprocess.Popen([sys._base_executable,'-I','-B','-c',"
        "'import time; time.sleep(.5)'],stdin=subprocess.DEVNULL,"
        "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,"
        "creationflags=subprocess.CREATE_NO_WINDOW); "
        f"pathlib.Path({str(barrier)!r}).write_text(json.dumps({{'child':child.pid}})); "
        "deadline=time.monotonic()+10\n"
        f"while not pathlib.Path({str(release)!r}).exists() and time.monotonic()<deadline: "
        "time.sleep(.01)\n"
        f"sys.exit(0 if pathlib.Path({str(release)!r}).exists() else 1)"
    )
    k = _kernel()
    with _inputs(tmp_path, code) as kwargs, NativeJob.create(**kwargs) as job:
        job.resume()
        ready = _ready(barrier)
        child = _observe(k, ready["child"], job)
        try:
            release.write_text("release")
            assert job.wait(10) == 0
            assert k.WaitForSingleObject(child, 0) == 0
            assert job.members() == ()
            assert not job._observed
        finally:
            k.CloseHandle(child)
