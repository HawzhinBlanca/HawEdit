"""Bounded native bytes, not producer/model/Linux/billing/publication admission."""

from __future__ import annotations

import ctypes
import math
import os
import threading
import time
import uuid
from collections.abc import Sequence
from ctypes import wintypes as w
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, BinaryIO, ClassVar

from hawedit.native_process import NativeJob, NativeProcessError
from hawedit.windows_security import (
    _AccessAllowedAce,
    _AclSizeInformation,
    _current_user_sid,
    _SecurityAttributes,
    _sid_string,
)

__all__ = ["NativeIOError", "NativeIOResult", "run_native"]

_CHUNK = 4096
_MAX_BYTES = 16 * 1024**2
_EXECUTION_LOCK = threading.Lock()
_QUARANTINE: list[object] = []


class NativeIOError(NativeProcessError):
    """Refused or uncertain native IO; never release a durable attempt on faith."""


@dataclass(frozen=True)
class NativeIOResult:
    exit_code: int
    stdout: bytes
    stderr: bytes


class _Overlap(ctypes.Structure):
    _fields_: ClassVar[Sequence[tuple[str, type[Any]]]] = [
        ("Internal", ctypes.c_size_t),
        ("InternalHigh", ctypes.c_size_t),
        ("Offset", w.DWORD),
        ("OffsetHigh", w.DWORD),
        ("hEvent", w.HANDLE),
    ]


def _error(operation: str, code: int | None = None) -> NativeIOError:
    reader = getattr(ctypes, "get_last_error", None)
    selected = code if code is not None else int(reader()) if callable(reader) else -1
    return NativeIOError(f"{operation}: Win32 error {selected}")


def _check(value: object, operation: str) -> None:
    if not value:
        raise _error(operation)


@lru_cache(maxsize=1)
def _libraries() -> tuple[Any, Any]:
    if os.name != "nt" or ctypes.sizeof(ctypes.c_void_p) != 8:
        raise NativeIOError("Native IO requires Windows64")
    loader = getattr(ctypes, "WinDLL", None)
    if not callable(loader):
        raise NativeIOError("Windows native IO loader unavailable")
    k, a = loader("kernel32", use_last_error=True), loader("advapi32", use_last_error=True)
    signatures = {
        "CreateNamedPipeW": (
            [w.LPCWSTR, *([w.DWORD] * 6), ctypes.POINTER(_SecurityAttributes)],
            w.HANDLE,
        ),
        "CreateFileW": (
            [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE],
            w.HANDLE,
        ),
        "ConnectNamedPipe": ([w.HANDLE, ctypes.POINTER(_Overlap)], w.BOOL),
        "GetNamedPipeClientProcessId": ([w.HANDLE, ctypes.POINTER(w.ULONG)], w.BOOL),
        "CreateEventW": ([ctypes.c_void_p, w.BOOL, w.BOOL, w.LPCWSTR], w.HANDLE),
        "ResetEvent": ([w.HANDLE], w.BOOL),
        "ReadFile": (
            [w.HANDLE, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD), ctypes.POINTER(_Overlap)],
            w.BOOL,
        ),
        "WriteFile": (
            [w.HANDLE, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD), ctypes.POINTER(_Overlap)],
            w.BOOL,
        ),
        "GetOverlappedResult": (
            [w.HANDLE, ctypes.POINTER(_Overlap), ctypes.POINTER(w.DWORD), w.BOOL],
            w.BOOL,
        ),
        "CancelIoEx": ([w.HANDLE, ctypes.POINTER(_Overlap)], w.BOOL),
        "WaitForSingleObject": ([w.HANDLE, w.DWORD], w.DWORD),
        "GetHandleInformation": ([w.HANDLE, ctypes.POINTER(w.DWORD)], w.BOOL),
        "CloseHandle": ([w.HANDLE], w.BOOL),
        "LocalFree": ([w.LPVOID], w.LPVOID),
        "VirtualAlloc": ([w.LPVOID, ctypes.c_size_t, w.DWORD, w.DWORD], w.LPVOID),
        "VirtualFree": ([w.LPVOID, ctypes.c_size_t, w.DWORD], w.BOOL),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(k, name)
        function.argtypes, function.restype = arguments, result
    signatures = {
        "ConvertStringSecurityDescriptorToSecurityDescriptorW": (
            [w.LPCWSTR, w.DWORD, ctypes.POINTER(w.LPVOID), ctypes.POINTER(w.DWORD)],
            w.BOOL,
        ),
        "GetSecurityInfo": (
            [w.HANDLE, w.DWORD, w.DWORD, *([ctypes.POINTER(w.LPVOID)] * 5)],
            w.DWORD,
        ),
        "GetSecurityDescriptorControl": (
            [w.LPVOID, ctypes.POINTER(w.WORD), ctypes.POINTER(w.DWORD)],
            w.BOOL,
        ),
        "GetAclInformation": ([w.LPVOID, w.LPVOID, w.DWORD, w.DWORD], w.BOOL),
        "GetAce": ([w.LPVOID, w.DWORD, ctypes.POINTER(w.LPVOID)], w.BOOL),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(a, name)
        function.argtypes, function.restype = arguments, result
    return k, a


def _inspect_private_pipe(handle: int, sid: str) -> None:
    k, a = _libraries()
    owner, dacl, descriptor = w.LPVOID(), w.LPVOID(), w.LPVOID()
    code = int(
        a.GetSecurityInfo(
            handle,
            1,
            1 | 4,
            ctypes.byref(owner),
            None,
            ctypes.byref(dacl),
            None,
            ctypes.byref(descriptor),
        )
    )
    if code:
        raise _error("Private pipe ACL readback", code)
    try:
        control, revision = w.WORD(), w.DWORD()
        _check(
            a.GetSecurityDescriptorControl(
                descriptor, ctypes.byref(control), ctypes.byref(revision)
            ),
            "Private pipe ACL control",
        )
        if not dacl or _sid_string(owner) != sid or not control.value & 0x1000:
            raise NativeIOError("Private pipe ACL owner/protection refused")
        info = _AclSizeInformation()
        _check(
            a.GetAclInformation(dacl, ctypes.byref(info), ctypes.sizeof(info), 2),
            "Private pipe ACL size",
        )
        if info.AceCount != 2:
            raise NativeIOError("Private pipe ACL principal count refused")
        principals: set[str] = set()
        for index in range(info.AceCount):
            pointer = w.LPVOID()
            _check(a.GetAce(dacl, index, ctypes.byref(pointer)), "Private pipe ACL entry")
            if pointer.value is None:
                raise NativeIOError("Private pipe ACL entry absent")
            ace = ctypes.cast(pointer, ctypes.POINTER(_AccessAllowedAce)).contents
            if (
                ace.Header.AceSize < ctypes.sizeof(_AccessAllowedAce)
                or ace.Header.AceType != 0
                or ace.Header.AceFlags != 0
                or ace.Mask != 0x001F01FF
            ):
                raise NativeIOError("Private pipe ACL access refused")
            principals.add(_sid_string(w.LPVOID(pointer.value + _AccessAllowedAce.SidStart.offset)))
        if principals != {sid, "S-1-5-18"}:
            raise NativeIOError("Private pipe ACL principals refused")
    finally:
        _check(not k.LocalFree(descriptor), "Private pipe ACL descriptor release")


def _retain(resource: object) -> None:
    if not any(item is resource for item in _QUARANTINE):
        _QUARANTINE.append(resource)


class _NativePipe:
    def __init__(self, *, reading: bool) -> None:
        if _QUARANTINE:
            raise NativeIOError("Uncertain native IO retained; restart/reconcile before launching")
        self.k, self.a = _libraries()
        self.owner = os.getpid()
        self.reading = reading
        self.handle = self.event = 0
        self.allocation = 0
        self.child: BinaryIO | None = None
        self.pending = self.eof = False
        self.submitted = 0
        sid = _current_user_sid()
        descriptor = w.LPVOID()
        _check(
            self.a.ConvertStringSecurityDescriptorToSecurityDescriptorW(
                f"O:{sid}D:P(A;;GA;;;SY)(A;;GA;;;{sid})", 1, ctypes.byref(descriptor), None
            ),
            "Private pipe descriptor",
        )
        try:
            # Python view collection must not free memory used by uncertain native IO.
            self.allocation = int(self.k.VirtualAlloc(None, 2 * _CHUNK, 0x3000, 4) or 0)
            _check(self.allocation, "Native IO arena allocation")
            self.buffer = (ctypes.c_char * _CHUNK).from_address(self.allocation)
            self.overlap = _Overlap.from_address(self.allocation + _CHUNK)
            attributes = _SecurityAttributes(ctypes.sizeof(_SecurityAttributes), descriptor, False)
            name = "\\\\.\\pipe\\HawEdit-IO-" + uuid.uuid4().hex
            handle = self.k.CreateNamedPipeW(
                name,
                (1 if reading else 2) | 0x40000000 | 0x80000,
                8,
                1,
                _CHUNK,
                _CHUNK,
                0,
                ctypes.byref(attributes),
            )
            if not handle or handle == ctypes.c_void_p(-1).value:
                raise _error("Private pipe creation")
            self.handle = int(handle)
            _inspect_private_pipe(self.handle, sid)
            self.event = int(self.k.CreateEventW(None, True, False, None) or 0)
            _check(self.event, "Private pipe event")
            self.overlap.hEvent = self.event
            client = self.k.CreateFileW(
                name, 0x40000000 if reading else 0x80000000, 0, None, 3, 0, None
            )
            if not client or client == ctypes.c_void_p(-1).value:
                raise _error("Private pipe client creation")
            try:
                _inspect_private_pipe(int(client), sid)
                import msvcrt

                fd = msvcrt.open_osfhandle(
                    int(client), (os.O_WRONLY if reading else os.O_RDONLY) | os.O_BINARY
                )
            except BaseException:
                self.k.CloseHandle(client)
                raise
            try:
                self.child = os.fdopen(fd, "wb" if reading else "rb", buffering=0)
            except BaseException:
                os.close(fd)
                raise
            connected = self.k.ConnectNamedPipe(self.handle, ctypes.byref(self.overlap))
            code = 0 if connected else int(ctypes.get_last_error())
            if code == 997:
                self.pending = True
                raise NativeIOError("Private pipe connection unexpectedly pending")
            if code not in (0, 535):
                raise _error("Private pipe connection", code)
            client_pid = w.ULONG()
            _check(
                self.k.GetNamedPipeClientProcessId(self.handle, ctypes.byref(client_pid)),
                "Private pipe client identity",
            )
            if client_pid.value != self.owner:
                raise NativeIOError("Private pipe client belongs to another process")
            _inspect_private_pipe(self.handle, sid)
            for owned in (self.handle, self.event):
                flags = w.DWORD()
                _check(
                    self.k.GetHandleInformation(owned, ctypes.byref(flags)),
                    "Private pipe inheritance",
                )
                if flags.value & 1:
                    raise NativeIOError("Private pipe/event must not be inherited")
        except BaseException:
            self.close()
            raise
        finally:
            if self.k.LocalFree(descriptor):
                _retain(self)
                raise _error("Private pipe descriptor release")

    def _owned(self) -> None:
        if self.owner != os.getpid():
            raise NativeIOError("Native IO belongs to another owner process")

    def _finish(self) -> tuple[int, int] | None:
        status = int(self.k.WaitForSingleObject(self.event, 0))
        if status == 258:
            return None
        if status != 0:
            raise _error("Pending native IO event")
        count = w.DWORD()
        result = self.k.GetOverlappedResult(
            self.handle, ctypes.byref(self.overlap), ctypes.byref(count), False
        )
        code = 0 if result else int(ctypes.get_last_error())
        if code == 996:
            return None
        if code not in (0, 995, 109, 232):
            raise _error("Pending native IO completion uncertain", code)
        self.pending = False
        return int(count.value), code

    def _transfer(self, data: bytes | None) -> tuple[int, int] | None:
        self._owned()
        if not self.handle:
            raise NativeIOError("Native IO pipe is closed")
        if self.pending:
            return self._finish()
        _check(self.k.ResetEvent(self.event), "Native IO event reset")
        count = w.DWORD()
        if data is None:
            self.submitted = _CHUNK
            result = self.k.ReadFile(
                self.handle, self.buffer, _CHUNK, ctypes.byref(count), ctypes.byref(self.overlap)
            )
        else:
            if type(data) is not bytes or not 0 < len(data) <= _CHUNK:
                raise NativeIOError("Native IO input chunk refused")
            ctypes.memmove(self.buffer, data, len(data))
            self.submitted = len(data)
            result = self.k.WriteFile(
                self.handle, self.buffer, len(data), ctypes.byref(count), ctypes.byref(self.overlap)
            )
        code = 0 if result else int(ctypes.get_last_error())
        if code == 997:
            self.pending = True
            return None
        return int(count.value), code

    def read(self) -> bytes | None:
        self._owned()
        if not self.reading:
            raise NativeIOError("Native IO pipe is not an output reader")
        if self.eof:
            return b""
        result = self._transfer(None)
        if result is None:
            return None
        count, code = result
        if code == 109 or (code == 0 and count == 0):
            self.eof = True
            return b""
        if code:
            raise _error("Native IO read", code)
        if not 0 < count <= _CHUNK:
            raise NativeIOError("Native IO read count refused")
        return self.buffer.raw[:count]

    def write(self, data: bytes) -> int | None:
        self._owned()
        if self.reading:
            raise NativeIOError("Native IO pipe is not an input writer")
        result = self._transfer(data)
        if result is None:
            return None
        count, code = result
        if code in (109, 232):
            raise NativeIOError("Native IO input reader closed before complete delivery")
        if code:
            raise _error("Native IO write", code)
        if not 0 < count <= self.submitted:
            raise NativeIOError("Native IO write count refused")
        return count

    def close_child(self) -> None:
        self._owned()
        if self.child is not None:
            self.child.close()
            self.child = None

    def close(self) -> None:
        self._owned()
        try:
            self.close_child()
            if self.pending:
                result = self.k.CancelIoEx(self.handle, ctypes.byref(self.overlap))
                code = 0 if result else int(ctypes.get_last_error())
                if code not in (0, 1168):
                    raise _error("Native IO cancellation request", code)
                deadline = time.monotonic() + 5
                while self.pending:
                    completed = self._finish()
                    if completed is not None and completed[1] not in (0, 995, 109, 232):
                        raise _error("Native IO cancelled completion", completed[1])
                    if self.pending:
                        if time.monotonic() >= deadline:
                            raise NativeIOError("Native IO cancellation completion uncertain")
                        time.sleep(0.001)
            for name in ("handle", "event"):
                handle = getattr(self, name)
                if handle:
                    _check(self.k.CloseHandle(handle), "Native IO original handle release")
                    setattr(self, name, 0)
            if self.allocation:
                _check(self.k.VirtualFree(self.allocation, 0, 0x8000), "Native IO arena release")
                self.allocation = 0
        except BaseException:
            _retain(self)
            raise


def run_native(
    argv: Sequence[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    expected_executable_sha256: str,
    input_bytes: bytes,
    timeout_seconds: float,
    output_limit_bytes: int,
) -> NativeIOResult:
    """Run one owned native scope; raw output does not certify a producer result."""
    if (
        type(timeout_seconds) not in (int, float)
        or not math.isfinite(timeout_seconds)
        or not 0 < timeout_seconds <= 43200
    ):
        raise NativeIOError("Native IO deadline must be finite, positive and bounded")
    if type(output_limit_bytes) is not int or not 0 < output_limit_bytes <= _MAX_BYTES:
        raise NativeIOError("Native IO output limit must be positive and at most16MiB")
    if type(input_bytes) is not bytes or len(input_bytes) > _MAX_BYTES:
        raise NativeIOError("Native IO input must be immutable bytes and at most16MiB")
    if not _EXECUTION_LOCK.acquire(blocking=False):
        raise NativeIOError("Native IO executor already owns an active scope")
    pipes: list[_NativePipe] = []
    job: NativeJob | None = None
    normal = False
    try:
        if _QUARANTINE:
            raise NativeIOError("Uncertain native IO retained; restart/reconcile before launching")
        deadline = time.monotonic() + timeout_seconds
        for reading in (False, True, True):
            pipes.append(_NativePipe(reading=reading))
        incoming, out, err = pipes
        assert incoming.child is not None and out.child is not None and err.child is not None
        job = NativeJob.create(
            argv,
            cwd=cwd,
            environment=environment,
            expected_executable_sha256=expected_executable_sha256,
            stdin=incoming.child,
            stdout=out.child,
            stderr=err.child,
        )
        for pipe in pipes:
            pipe.close_child()
        job.resume()
        sent = 0
        captured = [bytearray(), bytearray()]
        if not input_bytes:
            incoming.close()
        while True:
            if time.monotonic() >= deadline:
                raise NativeIOError("Native IO deadline expired")
            if sent < len(input_bytes):
                count = incoming.write(input_bytes[sent : sent + _CHUNK])
                if count is not None:
                    sent += count
                    if sent == len(input_bytes):
                        incoming.close()
            for index, pipe in enumerate((out, err)):
                chunk = pipe.read()
                if chunk:
                    if sum(len(data) for data in captured) + len(chunk) > output_limit_bytes:
                        raise NativeIOError("Native IO combined output limit exceeded")
                    captured[index].extend(chunk)
            if sent == len(input_bytes) and out.eof and err.eof:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise NativeIOError("Native IO deadline expired")
                code = job.wait(remaining)
                normal = True
                return NativeIOResult(code, bytes(captured[0]), bytes(captured[1]))
            time.sleep(0.001)
    except NativeProcessError as exc:
        if isinstance(exc, NativeIOError):
            raise
        raise NativeIOError(str(exc)) from exc
    finally:
        failures: list[BaseException] = []
        if job is not None:
            stopped = normal
            if not normal:
                try:
                    job.stop()
                    stopped = True
                except BaseException as exc:
                    failures.append(exc)
                    _retain(job)
            if stopped:
                try:
                    job.close()
                except BaseException as exc:
                    failures.append(exc)
                    _retain(job)
        for pipe in pipes:
            try:
                pipe.close()
            except BaseException as exc:
                failures.append(exc)
        _EXECUTION_LOCK.release()
        if failures:
            raise NativeIOError(
                "Native IO cleanup uncertain; retained resources prohibit launches"
            ) from failures[0]
