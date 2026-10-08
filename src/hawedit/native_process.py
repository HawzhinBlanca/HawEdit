"""Held Windows native lifetime, not producer/model/billing/publication authority.

The host must separately admit code/resources, bound IO and own Linux execution.
Only ordinary native descendants inherit this job; it is not a hostile-code sandbox.
Use the context manager: wait observes the original root, retained members and
empty job, not just a PID or report. An admission handshake must retain every
producer resource: ephemeral unobserved descendants are not a complete drain proof.
Abandoned scopes have best-effort finalization.
"""

from __future__ import annotations

import ctypes
import hashlib
import math
import os
import re
import stat
import subprocess
import threading
import time
import weakref
from collections.abc import Sequence
from ctypes import wintypes as w
from functools import lru_cache
from pathlib import Path
from types import TracebackType
from typing import Any, BinaryIO, ClassVar

__all__ = ["NativeJob", "NativeProcessError"]

_MAX_MEMBERS = 64
_CLEANUP_SECONDS = 5.0
_UNCERTAIN_SCOPES: list[object] = []


class NativeProcessError(RuntimeError):
    """Native execution refused or uncertain; never release durable work on faith."""


class _Basic(ctypes.Structure):
    _fields_: ClassVar[Sequence[tuple[str, type[Any]]]] = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", w.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", w.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", w.DWORD),
        ("SchedulingClass", w.DWORD),
    ]


class _IO(ctypes.Structure):
    _fields_: ClassVar[Sequence[tuple[str, type[Any]]]] = [
        (name, ctypes.c_ulonglong)
        for name in (
            "ReadOperationCount",
            "WriteOperationCount",
            "OtherOperationCount",
            "ReadTransferCount",
            "WriteTransferCount",
            "OtherTransferCount",
        )
    ]


class _Extended(ctypes.Structure):
    _fields_: ClassVar[Sequence[tuple[str, type[Any]]]] = [
        ("BasicLimitInformation", _Basic),
        ("IoInfo", _IO),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _Accounting(ctypes.Structure):
    _fields_: ClassVar[Sequence[tuple[str, type[Any]]]] = [
        (name, ctypes.c_longlong)
        for name in (
            "TotalUserTime",
            "TotalKernelTime",
            "ThisPeriodTotalUserTime",
            "ThisPeriodTotalKernelTime",
        )
    ] + [
        (name, w.DWORD)
        for name in (
            "TotalPageFaultCount",
            "TotalProcesses",
            "ActiveProcesses",
            "TotalTerminatedProcesses",
        )
    ]


class _ProcessList(ctypes.Structure):
    _fields_: ClassVar[Sequence[tuple[str, type[Any]]]] = [
        ("NumberOfAssignedProcesses", w.DWORD),
        ("NumberOfProcessIdsInList", w.DWORD),
        ("ProcessIdList", ctypes.c_size_t * _MAX_MEMBERS),
    ]


class _Startup(ctypes.Structure):
    _fields_: ClassVar[Sequence[tuple[str, type[Any]]]] = [
        ("cb", w.DWORD),
        ("lpReserved", w.LPWSTR),
        ("lpDesktop", w.LPWSTR),
        ("lpTitle", w.LPWSTR),
        *[
            (name, w.DWORD)
            for name in (
                "dwX",
                "dwY",
                "dwXSize",
                "dwYSize",
                "dwXCountChars",
                "dwYCountChars",
                "dwFillAttribute",
                "dwFlags",
            )
        ],
        ("wShowWindow", w.WORD),
        ("cbReserved2", w.WORD),
        ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
        ("hStdInput", w.HANDLE),
        ("hStdOutput", w.HANDLE),
        ("hStdError", w.HANDLE),
    ]


class _StartupEx(ctypes.Structure):
    _fields_: ClassVar[Sequence[tuple[str, type[Any]]]] = [
        ("StartupInfo", _Startup),
        ("lpAttributeList", ctypes.c_void_p),
    ]


class _Information(ctypes.Structure):
    _fields_: ClassVar[Sequence[tuple[str, type[Any]]]] = [
        ("hProcess", w.HANDLE),
        ("hThread", w.HANDLE),
        ("dwProcessId", w.DWORD),
        ("dwThreadId", w.DWORD),
    ]


def _error(operation: str) -> NativeProcessError:
    reader = getattr(ctypes, "get_last_error", None)
    code = int(reader()) if callable(reader) else -1
    return NativeProcessError(f"{operation} failed with Win32 error {code}")


def _check(value: object, operation: str) -> None:
    if not value:
        raise _error(operation)


@lru_cache(maxsize=1)
def _libraries() -> Any:
    if os.name != "nt" or ctypes.sizeof(ctypes.c_void_p) != 8:
        raise NativeProcessError("Native job ownership requires Windows64")
    loader = getattr(ctypes, "WinDLL", None)
    if not callable(loader):
        raise NativeProcessError("Windows native loader unavailable")
    k = loader("kernel32", use_last_error=True)
    signatures = {
        "CreateJobObjectW": ([ctypes.c_void_p, w.LPCWSTR], w.HANDLE),
        "SetInformationJobObject": ([w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD], w.BOOL),
        "QueryInformationJobObject": (
            [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p],
            w.BOOL,
        ),
        "AssignProcessToJobObject": ([w.HANDLE, w.HANDLE], w.BOOL),
        "IsProcessInJob": ([w.HANDLE, w.HANDLE, ctypes.POINTER(w.BOOL)], w.BOOL),
        "CreateProcessW": (
            [
                w.LPCWSTR,
                w.LPWSTR,
                ctypes.c_void_p,
                ctypes.c_void_p,
                w.BOOL,
                w.DWORD,
                ctypes.c_void_p,
                w.LPCWSTR,
                ctypes.POINTER(_Startup),
                ctypes.POINTER(_Information),
            ],
            w.BOOL,
        ),
        "ResumeThread": ([w.HANDLE], w.DWORD),
        "WaitForSingleObject": ([w.HANDLE, w.DWORD], w.DWORD),
        "GetExitCodeProcess": ([w.HANDLE, ctypes.POINTER(w.DWORD)], w.BOOL),
        "TerminateJobObject": ([w.HANDLE, w.UINT], w.BOOL),
        "TerminateProcess": ([w.HANDLE, w.UINT], w.BOOL),
        "CloseHandle": ([w.HANDLE], w.BOOL),
        "GetHandleInformation": ([w.HANDLE, ctypes.POINTER(w.DWORD)], w.BOOL),
        "GetCurrentProcess": ([], w.HANDLE),
        "OpenProcess": ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
        "GetProcessId": ([w.HANDLE], w.DWORD),
        "DuplicateHandle": (
            [w.HANDLE, w.HANDLE, w.HANDLE, ctypes.POINTER(w.HANDLE), w.DWORD, w.BOOL, w.DWORD],
            w.BOOL,
        ),
        "GetFileType": ([w.HANDLE], w.DWORD),
        "GetConsoleMode": ([w.HANDLE, ctypes.POINTER(w.DWORD)], w.BOOL),
        "CreateFileW": (
            [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE],
            w.HANDLE,
        ),
        "GetFinalPathNameByHandleW": ([w.HANDLE, w.LPWSTR, w.DWORD, w.DWORD], w.DWORD),
        "QueryFullProcessImageNameW": (
            [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)],
            w.BOOL,
        ),
        "InitializeProcThreadAttributeList": (
            [ctypes.c_void_p, w.DWORD, w.DWORD, ctypes.POINTER(ctypes.c_size_t)],
            w.BOOL,
        ),
        "UpdateProcThreadAttribute": (
            [
                ctypes.c_void_p,
                w.DWORD,
                ctypes.c_size_t,
                ctypes.c_void_p,
                ctypes.c_size_t,
                ctypes.c_void_p,
                ctypes.c_void_p,
            ],
            w.BOOL,
        ),
        "DeleteProcThreadAttributeList": ([ctypes.c_void_p], None),
    }
    try:
        for name, (args, result) in signatures.items():
            function = getattr(k, name)
            function.argtypes = args
            function.restype = result
    except (AttributeError, OSError) as exc:
        raise NativeProcessError("Required Windows native API unavailable") from exc
    return k


def _path(value: Path, *, directory: bool) -> Path:
    if not isinstance(value, Path) or not value.is_absolute() or value.drive.startswith("\\\\"):
        raise NativeProcessError("Native launch requires an explicit absolute local path")
    if any(part.endswith((".", " ")) or ":" in part for part in value.parts[1:]):
        raise NativeProcessError("Native launch refuses ambiguous paths")
    resolved = value.resolve(strict=True)
    info = resolved.lstat()
    if bool(getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
        raise NativeProcessError("Native launch refuses reparse resources")
    if not (
        stat.S_ISDIR(info.st_mode)
        if directory
        else stat.S_ISREG(info.st_mode) and info.st_nlink == 1
    ):
        raise NativeProcessError("Native launch resource is not a plain local member")
    return resolved


def _environment(values: dict[str, str]) -> str:
    if type(values) is not dict or not 1 <= len(values) <= 128:
        raise NativeProcessError("Native launch requires an explicit bounded environment")
    names: set[str] = set()
    for name, value in values.items():
        if not isinstance(name, str) or not isinstance(value, str) or not name or "=" in name:
            raise NativeProcessError("Invalid native environment field")
        if name.casefold() in names or any(ord(c) < 32 or ord(c) == 127 for c in name + value):
            raise NativeProcessError("Duplicate or unsafe native environment field")
        names.add(name.casefold())
    if (
        "systemroot" not in names
        or not next(
            value for name, value in values.items() if name.casefold() == "systemroot"
        ).strip()
    ):
        raise NativeProcessError("Explicit native environment requires SystemRoot")
    block = (
        "\0".join(f"{name}={values[name]}" for name in sorted(values, key=str.casefold)) + "\0\0"
    )
    if len(block.encode("utf-16-le")) > 65534:
        raise NativeProcessError("Native environment exceeds its bound")
    return block


def _held_path(k: Any, handle: int) -> Path:
    buffer = ctypes.create_unicode_buffer(32768)
    count = int(k.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0))
    if not 0 < count < len(buffer):
        raise _error("Held image path")
    name = buffer.value
    return Path(name[4:] if name.startswith("\\\\?\\") else name)


def _open_image(k: Any, path: Path, expected: str) -> BinaryIO:
    import msvcrt

    handle = k.CreateFileW(str(path), 0x80000000, 1, None, 3, 0x00200000, None)
    if handle is None or handle == ctypes.c_void_p(-1).value:
        raise _error("Native executable lease")
    descriptor = -1
    stream = None
    try:
        if _held_path(k, int(handle)) != path:
            raise NativeProcessError("Native executable lease path changed")
        descriptor = msvcrt.open_osfhandle(int(handle), os.O_RDONLY | os.O_BINARY)
        handle = None
        stream = os.fdopen(descriptor, "rb")
        descriptor = -1
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or not 0 < info.st_size <= 256 * 1024**2
        ):
            raise NativeProcessError("Native executable lease is invalid or oversized")
        if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
            raise NativeProcessError("Native executable hash differs from admitted binding")
        return stream
    except BaseException:
        if stream is not None:
            stream.close()
        elif descriptor >= 0:
            os.close(descriptor)
        elif handle is not None:
            k.CloseHandle(handle)
        raise


def _discard(
    k: Any, job: int, process: int, thread: int, image: BinaryIO, observed: dict[int, int]
) -> None:
    # Finalization is owned-only best effort, never a durable completion observation.
    k.CloseHandle(job)
    k.WaitForSingleObject(process, 5000)
    k.CloseHandle(thread)
    k.CloseHandle(process)
    for handle in observed.values():
        k.CloseHandle(handle)
    observed.clear()
    image.close()


class NativeJob:
    """A non-transferable original native scope; caller must also own IO and Linux."""

    def __init__(self) -> None:
        self._owner_pid = os.getpid()
        self._lock = threading.RLock()
        self._k = _libraries()
        self._job = 0
        self._process = 0
        self._thread = 0
        self._pid = 0
        self._image: BinaryIO | None = None
        self._image_path = Path()
        self._state = "new"
        self._assigned = False
        self._observed: dict[int, int] = {}
        self._finalizer: (
            weakref.finalize[[Any, int, int, int, BinaryIO, dict[int, int]], NativeJob] | None
        ) = None

    @classmethod
    def create(
        cls,
        argv: Sequence[str],
        *,
        cwd: Path,
        environment: dict[str, str],
        expected_executable_sha256: str,
        stdin: BinaryIO,
        stdout: BinaryIO,
        stderr: BinaryIO,
    ) -> NativeJob:
        """Create assigned and suspended; no child code runs before explicit resume."""
        if _UNCERTAIN_SCOPES:
            raise NativeProcessError("Uncertain native scope retained; reconcile before launching")
        scope = cls()
        duplicates: list[int] = []
        attributes: Any = None
        initialized = False
        try:
            if (
                not isinstance(argv, tuple | list)
                or not 1 <= len(argv) <= 256
                or any(not isinstance(a, str) or "\0" in a for a in argv)
            ):
                raise NativeProcessError("Invalid bounded native argv")
            if (
                not isinstance(expected_executable_sha256, str)
                or re.fullmatch("[a-f0-9]{64}", expected_executable_sha256) is None
            ):
                raise NativeProcessError("Invalid native executable hash")
            executable = _path(Path(argv[0]), directory=False)
            directory = _path(cwd, directory=True)
            command = subprocess.list2cmdline([str(executable), *argv[1:]])
            if len(command.encode("utf-16-le")) > 65532:
                raise NativeProcessError("Native command exceeds its bound")
            env = ctypes.create_unicode_buffer(_environment(environment))
            scope._image = _open_image(scope._k, executable, expected_executable_sha256)
            scope._image_path = executable
            scope._job = int(scope._k.CreateJobObjectW(None, None) or 0)
            _check(scope._job, "Private native job creation")
            flags = w.DWORD()
            _check(
                scope._k.GetHandleInformation(scope._job, ctypes.byref(flags)),
                "Native job handle policy",
            )
            if flags.value & 1:
                raise NativeProcessError("Native job handle must not be inherited")
            limits = _Extended()
            limits.BasicLimitInformation.LimitFlags = 0x2000 | 0x8
            limits.BasicLimitInformation.ActiveProcessLimit = _MAX_MEMBERS
            _check(
                scope._k.SetInformationJobObject(
                    scope._job, 9, ctypes.byref(limits), ctypes.sizeof(limits)
                ),
                "Native job limits",
            )
            import msvcrt

            current = scope._k.GetCurrentProcess()
            for index, stream in enumerate((stdin, stdout, stderr)):
                try:
                    if not (stream.readable() if index == 0 else stream.writable()):
                        raise ValueError("wrong access")
                    original = msvcrt.get_osfhandle(stream.fileno())
                    if scope._k.GetFileType(original) not in (1, 2, 3):
                        raise ValueError("invalid resource")
                    if scope._k.GetConsoleMode(original, ctypes.byref(flags)):
                        raise ValueError("console inheritance refused")
                except (OSError, ValueError) as exc:
                    raise NativeProcessError(
                        "Native stdio requires actual nonconsole resources"
                    ) from exc
                duplicate = w.HANDLE()
                _check(
                    scope._k.DuplicateHandle(
                        current, original, current, ctypes.byref(duplicate), 0, True, 2
                    ),
                    "Native stdio duplication",
                )
                value = duplicate.value
                if value is None:
                    raise NativeProcessError("Native stdio duplication returned no handle")
                duplicates.append(int(value))
            required = ctypes.c_size_t()
            scope._k.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(required))
            if not 0 < required.value <= 65536:
                raise NativeProcessError("Native startup attribute size refused")
            attributes = ctypes.create_string_buffer(required.value)
            _check(
                scope._k.InitializeProcThreadAttributeList(
                    attributes, 1, 0, ctypes.byref(required)
                ),
                "Native startup attributes",
            )
            initialized = True
            handles = (w.HANDLE * 3)(*duplicates)
            _check(
                scope._k.UpdateProcThreadAttribute(
                    attributes, 0, 0x20002, handles, ctypes.sizeof(handles), None, None
                ),
                "Native STD handle list",
            )
            startup = _StartupEx()
            startup.StartupInfo.cb = ctypes.sizeof(startup)
            startup.StartupInfo.dwFlags = 0x100
            (
                startup.StartupInfo.hStdInput,
                startup.StartupInfo.hStdOutput,
                startup.StartupInfo.hStdError,
            ) = duplicates
            startup.lpAttributeList = ctypes.cast(attributes, ctypes.c_void_p)
            info = _Information()
            created = scope._k.CreateProcessW(
                str(executable),
                ctypes.create_unicode_buffer(command),
                None,
                None,
                True,
                0x4 | 0x08000000 | 0x80000 | 0x400,
                env,
                str(directory),
                ctypes.cast(ctypes.byref(startup), ctypes.POINTER(_Startup)),
                ctypes.byref(info),
            )
            _check(created, "Suspended native creation")
            scope._process, scope._thread, scope._pid = (
                int(info.hProcess),
                int(info.hThread),
                int(info.dwProcessId),
            )
            _check(
                scope._k.AssignProcessToJobObject(scope._job, scope._process),
                "Suspended native assignment",
            )
            scope._assigned = True
            inside = w.BOOL()
            _check(
                scope._k.IsProcessInJob(scope._process, scope._job, ctypes.byref(inside)),
                "Suspended native membership",
            )
            if not inside.value or scope.members() != (scope._pid,):
                raise NativeProcessError("Suspended native membership differs")
            scope._verify_image()
            scope._state = "suspended"
            scope._finalizer = weakref.finalize(
                scope,
                _discard,
                scope._k,
                scope._job,
                scope._process,
                scope._thread,
                scope._image,
                scope._observed,
            )
            return scope
        except (OSError, ValueError, UnicodeError) as exc:
            scope.close()
            raise NativeProcessError("Native launch resource admission failed") from exc
        except BaseException:
            scope.close()
            raise
        finally:
            if initialized:
                scope._k.DeleteProcThreadAttributeList(attributes)
            for handle in duplicates:
                scope._k.CloseHandle(handle)

    @property
    def process_id(self) -> int:
        """Diagnostic only; the original held process, never this ID, is controlled."""
        return self._pid

    def _live(self) -> None:
        if os.getpid() != self._owner_pid:
            raise NativeProcessError("Native scope belongs to another owner process")
        if not self._job or self._state == "closed":
            raise NativeProcessError("Native scope is closed")

    def _verify_image(self) -> None:
        import msvcrt

        if self._image is None:
            raise NativeProcessError("Native image lease unavailable")
        held = os.fstat(self._image.fileno())
        current = self._image_path.stat()
        if (held.st_dev, held.st_ino, held.st_nlink) != (
            current.st_dev,
            current.st_ino,
            1,
        ) or _held_path(self._k, msvcrt.get_osfhandle(self._image.fileno())) != self._image_path:
            raise NativeProcessError("Native image lease identity changed")
        buffer = ctypes.create_unicode_buffer(32768)
        length = w.DWORD(len(buffer))
        _check(
            self._k.QueryFullProcessImageNameW(self._process, 0, buffer, ctypes.byref(length)),
            "Original native image",
        )
        if Path(buffer.value) != self._image_path:
            raise NativeProcessError("Original native image differs from admitted executable")

    def members(self) -> tuple[int, ...]:
        """Actual bounded job observation; IDs are not transferable capabilities."""
        with self._lock:
            self._live()
            data = _ProcessList()
            _check(
                self._k.QueryInformationJobObject(
                    self._job, 3, ctypes.byref(data), ctypes.sizeof(data), None
                ),
                "Native member enumeration",
            )
            if (
                data.NumberOfAssignedProcesses != data.NumberOfProcessIdsInList
                or data.NumberOfProcessIdsInList > _MAX_MEMBERS
            ):
                raise NativeProcessError("Native member enumeration is incomplete")
            members = tuple(int(pid) for pid in data.ProcessIdList[: data.NumberOfProcessIdsInList])
            if os.getpid() in members:
                raise NativeProcessError("Native scope contains its owner")
            return members

    def resume(self) -> None:
        with self._lock:
            self._live()
            if self._state != "suspended":
                raise NativeProcessError("Native resume is single use")
            self._verify_image()
            if self.members() != (self._pid,):
                raise NativeProcessError("Native membership changed before resume")
            if int(self._k.ResumeThread(self._thread)) != 1:
                self._state = "uncertain"
                raise NativeProcessError("Native resume suspension count refused")
            self._state = "running"

    def _retain_members(self) -> None:
        # Observation rights only; never control a process found through a PID.
        for pid, handle in tuple(self._observed.items()):
            status = int(self._k.WaitForSingleObject(handle, 0))
            if status == 0:
                _check(self._k.CloseHandle(handle), "Observed native handle release")
                del self._observed[pid]
            elif status != 258:
                raise _error("Observed native wait")
        for pid in self.members():
            if pid == self._pid or pid in self._observed:
                continue
            handle = int(self._k.OpenProcess(0x00100000 | 0x1000, False, pid) or 0)
            _check(handle, "Native member observation")
            try:
                inside = w.BOOL()
                _check(
                    self._k.IsProcessInJob(handle, self._job, ctypes.byref(inside)),
                    "Observed native membership",
                )
                if not inside.value or int(self._k.GetProcessId(handle)) != pid:
                    raise NativeProcessError("Observed native identity changed")
                self._observed[pid] = handle
            except BaseException:
                self._k.CloseHandle(handle)
                raise

    def _quiescent(self) -> bool:
        self._retain_members()
        accounting = _Accounting()
        _check(
            self._k.QueryInformationJobObject(
                self._job, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None
            ),
            "Native accounting",
        )
        root_wait = int(self._k.WaitForSingleObject(self._process, 0))
        if root_wait not in (0, 258):
            raise _error("Original native wait")
        return (
            root_wait == 0
            and not self._observed
            and accounting.ActiveProcesses == 0
            and not self.members()
        )

    def wait(self, timeout_seconds: float) -> int:
        if (
            type(timeout_seconds) not in (int, float)
            or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= 43200
        ):
            raise NativeProcessError("Native deadline must be finite, positive and bounded")
        deadline = time.monotonic() + timeout_seconds
        while True:
            with self._lock:
                self._live()
                if self._state in ("stopped", "uncertain"):
                    raise NativeProcessError("Native scope was stopped or is uncertain")
                if self._state not in ("running", "finished"):
                    raise NativeProcessError("Native scope must resume before waiting")
                if self._quiescent():
                    code = w.DWORD()
                    _check(
                        self._k.GetExitCodeProcess(self._process, ctypes.byref(code)),
                        "Original native exit code",
                    )
                    self._state = "finished"
                    return int(code.value)
                if time.monotonic() >= deadline:
                    self.stop()
                    raise NativeProcessError("Native deadline expired; owned scope stopped")
            time.sleep(0.01)

    def _retain_uncertainty(self) -> None:
        if not any(scope is self for scope in _UNCERTAIN_SCOPES):
            _UNCERTAIN_SCOPES.append(self)
        self._state = "uncertain"
        if self._finalizer is not None:
            self._finalizer.detach()

    def stop(self) -> None:
        with self._lock:
            self._live()
            if any(scope is self for scope in _UNCERTAIN_SCOPES):
                raise NativeProcessError("Uncertain native scope retained; automatic retry refused")
            self._state = "stopped"
            try:
                try:
                    self._retain_members()
                finally:
                    _check(
                        self._k.TerminateJobObject(self._job, 0xC001), "Owned native termination"
                    )
                deadline = time.monotonic() + _CLEANUP_SECONDS
                while not self._quiescent():
                    if time.monotonic() >= deadline:
                        raise NativeProcessError(
                            "Native shutdown uncertain; retain durable exclusion"
                        )
                    time.sleep(0.01)
            except BaseException:
                self._retain_uncertainty()
                raise

    def close(self) -> None:
        with self._lock:
            if self._state == "closed":
                return
            if os.getpid() != self._owner_pid:
                raise NativeProcessError("Native scope belongs to another owner process")
            if any(scope is self for scope in _UNCERTAIN_SCOPES):
                raise NativeProcessError("Uncertain native scope retained; automatic retry refused")
            try:
                if self._process:
                    if self._assigned:
                        try:
                            quiescent = self._quiescent()
                        except BaseException:
                            self.stop()
                            raise
                        if not quiescent:
                            self.stop()
                    else:
                        _check(
                            self._k.TerminateProcess(self._process, 0xC002),
                            "Unassigned original native termination",
                        )
                        if int(self._k.WaitForSingleObject(self._process, 5000)) != 0:
                            raise NativeProcessError("Unassigned native shutdown uncertain")
                if self._finalizer is not None:
                    self._finalizer.detach()
                # Keep each capability until its own release is confirmed.
                for name in ("_thread", "_process", "_job"):
                    handle = getattr(self, name)
                    if handle:
                        _check(self._k.CloseHandle(handle), "Original native handle release")
                        setattr(self, name, 0)
                for pid, handle in tuple(self._observed.items()):
                    _check(self._k.CloseHandle(handle), "Observed native handle release")
                    del self._observed[pid]
                if self._image is not None:
                    self._image.close()
                    self._image = None
                self._state = "closed"
            except BaseException:
                self._retain_uncertainty()
                raise

    def __enter__(self) -> NativeJob:
        self._live()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
