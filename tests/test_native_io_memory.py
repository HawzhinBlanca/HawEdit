"""Independent native-page observations; no simulated cancellation or allocator."""

from __future__ import annotations

import ctypes
import gc
import hashlib
import importlib
import os
import sys
import time
from collections.abc import Sequence
from ctypes import wintypes as w
from pathlib import Path
from types import ModuleType
from typing import Any, ClassVar

import pytest


class _MemoryInfo(ctypes.Structure):
    _fields_: ClassVar[Sequence[tuple[str, type[Any]]]] = [
        ("BaseAddress", w.LPVOID),
        ("AllocationBase", w.LPVOID),
        ("AllocationProtect", w.DWORD),
        ("PartitionId", w.WORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", w.DWORD),
        ("Protect", w.DWORD),
        ("Type", w.DWORD),
    ]


def _api() -> ModuleType:
    return importlib.import_module("hawedit.native_io")


def _available() -> bool:
    if os.name == "nt":
        return True
    with pytest.raises(_api().NativeIOError, match="Windows"):
        _api()._NativePipe(reading=True)
    return False


def _query(address: int) -> _MemoryInfo:
    loader = ctypes.WinDLL
    k = loader("kernel32", use_last_error=True)
    k.VirtualQuery.argtypes = [w.LPVOID, ctypes.POINTER(_MemoryInfo), ctypes.c_size_t]
    k.VirtualQuery.restype = ctypes.c_size_t
    info = _MemoryInfo()
    assert ctypes.sizeof(info) == 48
    assert k.VirtualQuery(address, ctypes.byref(info), ctypes.sizeof(info)) == ctypes.sizeof(info)
    return info


def _committed(base: int) -> None:
    info = _query(base)
    assert info.AllocationBase == base and info.BaseAddress == base
    assert info.State == 0x1000 and info.Type == 0x20000
    assert info.AllocationProtect == info.Protect == 4
    assert info.RegionSize == 8192
    overlap = _query(base + 4096)
    assert overlap.AllocationBase == base and overlap.State == 0x1000


@pytest.mark.parametrize("reading", [False, True])
def test_native_io_arena_is_native_and_released_after_drain(reading: bool) -> None:
    if not _available():
        return
    pipe = _api()._NativePipe(reading=reading)
    try:
        base = pipe.allocation
        assert base and ctypes.addressof(pipe.buffer) == base
        assert ctypes.addressof(pipe.overlap) == base + 4096
        assert pipe.buffer._b_needsfree_ == pipe.overlap._b_needsfree_ == 0
        _committed(base)
        pipe.close()
        assert pipe.allocation == pipe.handle == pipe.event == 0
        assert _query(base).State == 0x10000
        pipe.close()
        with pytest.raises(_api().NativeIOError, match="closed"):
            pipe._transfer(None)
    finally:
        pipe.close()


@pytest.mark.parametrize("reading", [False, True])
def test_native_io_native_arena_survives_cancel_request(reading: bool) -> None:
    if not _available():
        return
    pipe = _api()._NativePipe(reading=reading)
    try:
        base = pipe.allocation
        result = pipe.read() if reading else pipe.write(b"X" * 4096)
        if not reading:
            for _ in range(16):
                if result is None:
                    break
                result = pipe.write(b"X" * 4096)
        assert result is None and pipe.pending
        assert pipe.k.CancelIoEx(pipe.handle, ctypes.byref(pipe.overlap))
        assert pipe.pending and pipe.allocation == base
        _committed(base)
        deadline = time.monotonic() + 5
        completed = pipe._finish()
        while completed is None and time.monotonic() < deadline:
            time.sleep(0.001)
            completed = pipe._finish()
        assert completed == (0, 995) and not pipe.pending
        _committed(base)
        pipe.close()
        assert pipe.allocation == 0 and _query(base).State == 0x10000
    finally:
        pipe.close()


def test_native_io_pending_arena_survives_python_owner_collection() -> None:
    if not _available():
        return
    api = _api()
    pipe = api._NativePipe(reading=True)
    try:
        base = pipe.allocation
        assert pipe.read() is None and pipe.pending
        _committed(base)
    except BaseException:
        pipe.close()
        raise
    k, handle, event, client = pipe.k, pipe.handle, pipe.event, pipe.child
    assert client is not None
    del pipe
    gc.collect()
    _committed(base)
    overlap = api._Overlap.from_address(base + 4096)
    assert k.CancelIoEx(handle, ctypes.byref(overlap))
    count = w.DWORD()
    deadline = time.monotonic() + 5
    code = 996
    while code == 996 and time.monotonic() < deadline:
        result = k.GetOverlappedResult(handle, ctypes.byref(overlap), ctypes.byref(count), False)
        code = 0 if result else int(ctypes.get_last_error())
        if code == 996:
            time.sleep(0.001)
    assert code == 995 and count.value == 0
    _committed(base)
    client.close()
    assert k.CloseHandle(handle) and k.CloseHandle(event)
    assert k.VirtualFree(base, 0, 0x8000)
    assert _query(base).State == 0x10000


def test_native_io_uncertainty_keeps_native_arena(tmp_path: Path) -> None:
    if not _available():
        return
    from hawedit.studio_private import PrivateDirectory

    source = str(Path(__file__).resolve().parents[1] / "src")
    code = (
        "import ctypes,gc,sys; from ctypes import wintypes as w\n"
        "class M(ctypes.Structure):\n"
        " _fields_=[('BaseAddress',w.LPVOID),('AllocationBase',w.LPVOID),"
        "('AllocationProtect',w.DWORD),('PartitionId',w.WORD),"
        "('RegionSize',ctypes.c_size_t),('State',w.DWORD),"
        "('Protect',w.DWORD),('Type',w.DWORD)]\n"
        "k=ctypes.WinDLL('kernel32',use_last_error=True); "
        "k.VirtualQuery.argtypes=[w.LPVOID,ctypes.POINTER(M),ctypes.c_size_t]; "
        "k.VirtualQuery.restype=ctypes.c_size_t\n"
        "def _committed(base):\n"
        " m=M(); assert k.VirtualQuery(base,ctypes.byref(m),ctypes.sizeof(m))==48; "
        "assert m.AllocationBase==base and m.State==0x1000 and m.RegionSize==8192; "
        "assert m.Protect==4 and m.Type==0x20000\n"
        f"sys.path.insert(0,{source!r}); "
        "import hawedit.native_io as n; "
        "p=n._NativePipe(reading=True); base=p.allocation; "
        "assert p.read() is None and p.pending; assert p.k.CloseHandle(p.handle)\n"
        "try: p.close()\n"
        "except n.NativeIOError: pass\n"
        "else: raise AssertionError('uncertainty accepted')\n"
        "assert p.pending and p.allocation==base and n._QUARANTINE==[p]; "
        "_committed(base); del p; gc.collect(); _committed(base)\n"
        "try: n.run_native((),cwd=None,environment={},expected_executable_sha256='',"
        "input_bytes=b'',timeout_seconds=1,output_limit_bytes=1)\n"
        "except n.NativeIOError as e: assert 'retained' in str(e)\n"
        "else: raise AssertionError('retained process launched')\n"
        "_committed(base); print('native arena retained')"
    )
    executable = Path(getattr(sys, "_base_executable", sys.executable)).resolve()
    private = PrivateDirectory(tmp_path / "uncertain", exclusive=True)
    result = _api().run_native(
        (str(executable), "-I", "-B", "-c", code),
        cwd=private.path,
        environment={"SystemRoot": os.environ.get("SYSTEMROOT", "C:/Windows")},
        expected_executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
        input_bytes=b"",
        timeout_seconds=4,
        output_limit_bytes=131072,
    )
    assert result.exit_code == 0 and result.stdout.strip() == b"native arena retained"
    assert not result.stderr and _api()._QUARANTINE == []
