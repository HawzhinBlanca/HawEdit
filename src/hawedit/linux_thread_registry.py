"""Bounded original kernel births in a private controller, not model admission.

This component is opt-in and does not alter LinuxSnapshot's default fence.
The controller must be a sealed, capability-free private PID1. Only its stopped
original child can bootstrap tracing; model code cannot attach other processes.
"""

from __future__ import annotations

import ctypes
import errno
import math
import os
import platform
import select
import signal
import stat
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, ClassVar

from hawedit.linux_scope import LinuxScopeError, _pid_info

__all__ = ["LinuxThreadRegistry", "LinuxThreadRegistryError", "trace_original_worker"]

_TRACE_OPTIONS = 0x100018  # TRACECLONE | TRACEEXEC | EXITKILL
_WALL = 0x40000000
_DIRECTORY = 0x10000
_NOFOLLOW = 0x20000
_CLOEXEC = 0x80000
_ACTIVE: LinuxThreadRegistry | None = None


class LinuxThreadRegistryError(RuntimeError):
    """Original membership or custody is refused; no caller PID is authority."""


class _Filter(ctypes.Structure):
    _fields_: ClassVar[list[tuple[str, Any]]] = [
        ("code", ctypes.c_ushort),
        ("jt", ctypes.c_ubyte),
        ("jf", ctypes.c_ubyte),
        ("k", ctypes.c_uint),
    ]


class _Program(ctypes.Structure):
    _fields_: ClassVar[list[tuple[str, Any]]] = [
        ("length", ctypes.c_ushort),
        ("filter", ctypes.POINTER(_Filter)),
    ]


def _fcntl() -> Any:
    import fcntl

    return fcntl


def _api(module: object, name: str) -> Any:
    value = getattr(module, name, None)
    if value is None:
        raise LinuxThreadRegistryError(f"Original registry kernel capability unavailable: {name}")
    return value


def _native() -> Any:
    library = ctypes.CDLL(None, use_errno=True)
    library.syscall.restype = ctypes.c_long
    library.ptrace.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    library.ptrace.restype = ctypes.c_long
    library.pidfd_send_signal.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint,
    ]
    library.pidfd_send_signal.restype = ctypes.c_int
    return library


def _host() -> None:
    if sys.platform != "linux" or platform.machine() != "x86_64":
        raise LinuxThreadRegistryError("Original thread registry requires Linux x86_64")


def _status(fd: int) -> dict[str, str]:
    current = os.open("status", os.O_RDONLY | _NOFOLLOW | _CLOEXEC, dir_fd=fd)
    try:
        raw = os.read(current, 65537)
    finally:
        os.close(current)
    if len(raw) > 65536:
        raise LinuxThreadRegistryError("Original task status exceeds bound")
    fields: dict[str, str] = {}
    for line in raw.decode("ascii", "strict").splitlines():
        key, separator, value = line.partition(":")
        if separator:
            if key in fields:
                raise LinuxThreadRegistryError("Duplicate original task status field")
            fields[key] = value.strip()
    return fields


def _task_directory(tid: int, parent: int | None = None) -> int:
    path = str(tid) if parent is not None else f"/proc/{tid}/task/{tid}"
    return os.open(path, os.O_RDONLY | _DIRECTORY | _NOFOLLOW | _CLOEXEC, dir_fd=parent)


def _proc(native: Any, fd: int) -> None:
    buffer = (ctypes.c_long * 32)()
    if native.fstatfs(fd, ctypes.byref(buffer)) != 0 or buffer[0] != 0x9FA0:
        raise LinuxThreadRegistryError("Original task description is not genuine procfs")


def _sealed(fields: dict[str, str]) -> None:
    if fields.get("NoNewPrivs") != "1" or fields.get("Seccomp") != "2":
        raise LinuxThreadRegistryError("Original controller requires NNP and a kernel fence")
    for key in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"):
        if int(fields.get(key, "-1"), 16) != 0:
            raise LinuxThreadRegistryError("Original controller requires zero capabilities")


def _filter(native: Any, worker: bool) -> None:
    rows: list[tuple[int, int | str, int | str, int]] = []
    labels: dict[str, int] = {}

    def emit(code: int, value: int = 0, jt: int | str = 0, jf: int | str = 0) -> None:
        rows.append((code, jt, jf, value))

    def label(name: str) -> None:
        labels[name] = len(rows)

    emit(0x20, 4)
    emit(0x15, 0xC000003E, jf="kill")
    emit(0x20, 0)
    emit(0x45, 0x40000000, jt="deny")
    if worker:
        emit(0x15, 435, jt="unsupported")
        for number in (57, 58, 101, 311):
            emit(0x15, number, jt="deny")
        emit(0x15, 56, jf="allow")
        emit(0x20, 20)
        emit(0x15, 0, jf="deny")
        emit(0x20, 16)
        # Permit same-group pthread creation only, never namespace/process births.
        emit(0x45, 0xFEC2F0FF, jt="deny")
        emit(0x54, 0x10900)
        emit(0x15, 0x10900, jt="allow", jf="deny")
    else:
        emit(0x15, 101, jf="allow")
        for offset in (20, 28, 32, 36):
            emit(0x20, offset)
            emit(0x15, 0, jf="deny")
        emit(0x20, 24)
        emit(0x25, 1, jf="deny")
        emit(0x45, 0x80000000, jt="deny")
        emit(0x20, 16)
        emit(0x15, 0x4201, jt="allow")
        emit(0x15, 7, jt="continue")
        emit(0x15, 0x4200, jt="options", jf="deny")
        label("continue")
        emit(0x20, 40)
        emit(0x15, 0, jf="deny")
        emit(0x20, 44)
        emit(0x15, 0, jt="allow", jf="deny")
        label("options")
        emit(0x20, 40)
        emit(0x15, _TRACE_OPTIONS, jf="deny")
        emit(0x20, 44)
        emit(0x15, 0, jt="allow", jf="deny")
    label("deny")
    emit(0x06, 0x50000 | errno.EPERM)
    label("unsupported")
    emit(0x06, 0x50000 | errno.ENOSYS)
    label("kill")
    emit(0x06, 0x80000000)
    label("allow")
    emit(0x06, 0x7FFF0000)

    def jump(value: int | str, index: int) -> int:
        result = labels[value] - index - 1 if isinstance(value, str) else value
        if not 0 <= result <= 255:
            raise LinuxThreadRegistryError("Original trace filter branch exceeds bound")
        return result

    items = [
        _Filter(code, jump(jt, i), jump(jf, i), value)
        for i, (code, jt, jf, value) in enumerate(rows)
    ]
    filters = (_Filter * len(items))(*items)
    program = _Program(len(filters), filters)
    if native.syscall(317, 1, 0, ctypes.byref(program)) != 0:
        raise LinuxThreadRegistryError("Original restricted trace filter refused")


def trace_original_worker() -> None:
    """Trusted child bootstrap only; irrevocably deny tracing/process creation afterwards."""
    _host()
    if os.getpid() != 2 or os.getppid() != 1 or threading.get_native_id() != 2:
        raise LinuxThreadRegistryError("Original trace bootstrap requires private original child")
    native = _native()
    current = _task_directory(2)
    try:
        fields = _status(current)
        if fields.get("Threads") != "1" or fields.get("TracerPid") != "0":
            raise LinuxThreadRegistryError("Original trace bootstrap is not fresh/single-thread")
        if fields.get("NoNewPrivs") != "1":
            raise LinuxThreadRegistryError("Original trace bootstrap requires NNP")
        for key in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"):
            if int(fields.get(key, "-1"), 16) != 0:
                raise LinuxThreadRegistryError(
                    "Original trace bootstrap requires zero capabilities"
                )
    finally:
        os.close(current)
    if native.ptrace(0, 0, None, None) != 0:
        raise LinuxThreadRegistryError("Original kernel TRACEME bootstrap refused")
    os.kill(2, int(_api(signal, "SIGSTOP")))
    _filter(native, True)


@dataclass(frozen=True)
class _Description:
    fd: int
    anchor: int
    witness: int

    @classmethod
    def hold(cls, fd: int) -> _Description:
        anchor = os.dup(fd)
        try:
            witness = os.dup(fd)
        except OSError:
            os.close(anchor)
            raise
        return cls(fd, anchor, witness)

    def inspect(self) -> None:
        if (
            _fcntl().fcntl(self.anchor, 1027, self.witness) != 1
            or _fcntl().fcntl(self.fd, 1027, self.anchor) != 1
            or any(os.get_inheritable(fd) for fd in (self.fd, self.anchor, self.witness))
        ):
            raise LinuxThreadRegistryError("Original description substituted or reopened")

    def close(self, borrowed: bool = False) -> bool:
        # A primary slot may now belong to someone else. Never close that slot.
        if _fcntl().fcntl(self.anchor, 1027, self.witness) != 1:
            raise LinuxThreadRegistryError("Original description cleanup custody uncertain")
        try:
            original = bool(_fcntl().fcntl(self.fd, 1027, self.anchor) == 1)
        except OSError as exc:
            if exc.errno != errno.EBADF:
                raise
            original = False
        if original and not borrowed:
            os.close(self.fd)
        os.close(self.anchor)
        os.close(self.witness)
        return original


class LinuxThreadRegistry:
    """Observe kernel births before release; retain anchors through complete reaping.

    Borrowed pidfd/task-root stay caller-owned. Private task descriptions belong
    here. No numeric registration API exists. A refused birth is tracked solely
    for cleanup, never admitted for comm access. The fixed 30s lifetime includes
    cancellation/reaping; this is not permission for a full episode/model run.
    """

    def __init__(
        self,
        worker_pidfd: int,
        task_directory: int,
        *,
        timeout_seconds: float = 30.0,
        max_threads: int = 64,
    ) -> None:
        global _ACTIVE
        if (
            type(timeout_seconds) not in (int, float)
            or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= 30
        ):
            raise LinuxThreadRegistryError(
                "Original registry deadline must be finite, positive, <=30s"
            )
        if type(max_threads) is not int or not 1 <= max_threads <= 64:
            raise LinuxThreadRegistryError("Original registry thread budget must be 1..64")
        _host()
        if _ACTIVE is not None:
            raise LinuxThreadRegistryError("Original registry lifetime already retained")
        if os.getpid() != 1 or threading.get_native_id() != 1:
            raise LinuxThreadRegistryError("Original registry requires private PID1 controller")
        if any(type(fd) is not int or fd < 0 for fd in (worker_pidfd, task_directory)):
            raise LinuxThreadRegistryError("Original registry requires held kernel descriptions")
        self._creator = (os.getpid(), threading.get_ident(), threading.current_thread())
        self._native = _native()
        self._started = time.monotonic()
        self._end = self._started + float(timeout_seconds)
        self._limit = max_threads
        self._failed = self._closed = self._stopping = False
        self._tasks: dict[int, _Description] = {}
        self._births = {2}
        self._members = {2}
        self._configured: set[int] = set()
        self._pending: dict[int, int] = {}
        self._reaped: set[int] = set()
        self._event_count = 0
        self._exec_count = 0
        self._worker_exit: int | None = None
        self._pid: _Description | None = None
        self._root: _Description | None = None
        try:
            current = _task_directory(1)
            try:
                fields = _status(current)
                _sealed(fields)
                if fields.get("Threads") != "1":
                    raise LinuxThreadRegistryError(
                        "Original registry requires single-thread controller"
                    )
                children = os.open("children", os.O_RDONLY | _NOFOLLOW | _CLOEXEC, dir_fd=current)
                try:
                    if os.read(children, 257).strip() != b"2":
                        raise LinuxThreadRegistryError(
                            "Original registry requires only its original child"
                        )
                finally:
                    os.close(children)
            finally:
                os.close(current)
            if not all(
                _api(os, "statvfs")(path).f_flag & int(_api(os, "ST_RDONLY"))
                for path in ("/", "/proc")
            ):
                raise LinuxThreadRegistryError("Original controller root/proc must be readonly")
            if _pid_info(worker_pidfd) != (2,) or select.select([worker_pidfd], [], [], 0)[0]:
                raise LinuxThreadRegistryError("Original worker pidfd differs or exited")
            _proc(self._native, task_directory)
            if not stat.S_ISDIR(os.fstat(task_directory).st_mode):
                raise LinuxThreadRegistryError("Original task root is not a directory")
            expected = os.stat("/proc/2/task", follow_symlinks=False)
            actual = os.fstat(task_directory)
            if (expected.st_dev, expected.st_ino) != (actual.st_dev, actual.st_ino):
                raise LinuxThreadRegistryError("Original worker task root differs")
            main = _task_directory(2, task_directory)
            try:
                fields = _status(main)
                if (
                    fields.get("Pid") != "2"
                    or fields.get("Tgid") != "2"
                    or fields.get("PPid") != "1"
                ):
                    raise LinuxThreadRegistryError("Original worker kernel parent/group differs")
            finally:
                os.close(main)
            self._pid = _Description.hold(worker_pidfd)
            self._root = _Description.hold(task_directory)
            self._pid.inspect()
            self._root.inspect()
            _filter(self._native, False)
        except (OSError, ValueError, LinuxScopeError, LinuxThreadRegistryError) as exc:
            for held in (self._pid, self._root):
                if held is not None:
                    held.close(borrowed=True)
            raise LinuxThreadRegistryError(
                "Original registry controller admission refused"
            ) from exc
        _ACTIVE = self

    @property
    def registered_tids(self) -> tuple[int, ...]:
        return tuple(sorted(self._tasks))

    @property
    def observed_tids(self) -> tuple[int, ...]:
        return tuple(sorted(self._births))

    @property
    def reaped_tids(self) -> tuple[int, ...]:
        return tuple(sorted(self._reaped))

    @property
    def event_count(self) -> int:
        return self._event_count

    @property
    def exec_count(self) -> int:
        return self._exec_count

    @property
    def worker_exit(self) -> int | None:
        return self._worker_exit

    @property
    def drained(self) -> bool:
        return not self._members and not self._pending and self._reaped == self._births

    def _check(self) -> None:
        if self._creator != (os.getpid(), threading.get_ident(), threading.current_thread()):
            raise LinuxThreadRegistryError("Original registry creator differs")
        if self._closed:
            raise LinuxThreadRegistryError("Original registry closed")
        assert self._pid is not None and self._root is not None
        self._pid.inspect()
        self._root.inspect()
        if not self._stopping:
            if self._failed:
                raise LinuxThreadRegistryError("Original registry refused; cancellation required")
            if time.monotonic() >= self._end:
                self._failed = True
                raise LinuxThreadRegistryError("Original registry deadline expired")

    def _trace(self, tid: int, request: int, data: int = 0) -> None:
        if tid not in self._births or tid in self._reaped:
            raise LinuxThreadRegistryError("Trace target is not an original live birth")
        ctypes.set_errno(0)
        if self._native.ptrace(request, tid, None, ctypes.c_void_p(data)) == -1:
            raise LinuxThreadRegistryError("Original kernel event operation refused")

    def _custody(self, tid: int) -> int:
        if type(tid) is not int or tid not in self._tasks or tid in self._reaped:
            raise LinuxThreadRegistryError("Target is not a registered live original task")
        held = self._tasks[tid]
        held.inspect()
        _proc(self._native, held.fd)
        fields = _status(held.fd)
        if (
            fields.get("Pid") != str(tid)
            or fields.get("Tgid") != "2"
            or fields.get("TracerPid") != "1"
        ):
            raise LinuxThreadRegistryError("Original task kernel relationship differs")
        return held.fd

    def _register(self, tid: int) -> None:
        if tid in self._tasks:
            self._custody(tid)
            return
        if len(self._tasks) >= self._limit:
            raise LinuxThreadRegistryError("Original lifetime thread budget exhausted")
        assert self._root is not None
        current = _task_directory(tid, self._root.fd)
        try:
            held = _Description.hold(current)
        except OSError:
            os.close(current)
            raise
        self._tasks[tid] = held
        self._custody(tid)

    def _resume_start(self, tid: int) -> None:
        self._register(tid)
        self._trace(tid, 0x4200, _TRACE_OPTIONS)
        self._configured.add(tid)
        if not self._stopping:
            self._trace(tid, 7)

    def poll(self) -> bool:
        """Consume one real kernel wait event. Unknown child stops remain withheld."""
        self._check()
        if self.drained:
            return False
        try:
            tid, status = os.waitpid(-1, int(_api(os, "WNOHANG")) | _WALL)
            if not tid:
                return False
            self._event_count += 1
            if self._event_count > 256:
                raise LinuxThreadRegistryError("Original registry event budget exhausted")
            if _api(os, "WIFEXITED")(status) or _api(os, "WIFSIGNALED")(status):
                if tid not in self._births or tid in self._reaped:
                    raise LinuxThreadRegistryError("Unowned or repeated original exit")
                self._members.remove(tid)
                self._pending.pop(tid, None)
                self._reaped.add(tid)
                if tid == 2:
                    self._worker_exit = os.waitstatus_to_exitcode(status)
                return True
            if not _api(os, "WIFSTOPPED")(status):
                raise LinuxThreadRegistryError("Unexpected original kernel wait state")
            stopped, event = int(_api(os, "WSTOPSIG")(status)), status >> 16
            if tid not in self._births:
                if (
                    stopped != int(_api(signal, "SIGSTOP"))
                    or event
                    or tid in self._pending
                    or len(self._pending) >= 64
                ):
                    raise LinuxThreadRegistryError("Unowned original kernel stop")
                self._pending[tid] = status
            elif tid not in self._configured:
                if stopped != int(_api(signal, "SIGSTOP")) or event:
                    raise LinuxThreadRegistryError("Original startup stop differs")
                if not self._stopping:
                    self._resume_start(tid)
            elif stopped == int(_api(signal, "SIGTRAP")) and event == 3:
                born = ctypes.c_ulonglong()
                self._trace(tid, 0x4201, ctypes.addressof(born))
                child = int(born.value)
                if child <= 2 or child in self._births or len(self._births) >= 64:
                    raise LinuxThreadRegistryError("Original clone identity/lifetime bound refused")
                self._births.add(child)
                self._members.add(child)
                if not self._stopping:
                    self._register(child)
                if child in self._pending:
                    del self._pending[child]
                    if not self._stopping:
                        self._resume_start(child)
                if not self._stopping:
                    self._trace(tid, 7)
            elif stopped == int(_api(signal, "SIGTRAP")) and event == 4:
                former = ctypes.c_ulonglong()
                self._trace(tid, 0x4201, ctypes.addressof(former))
                if tid != 2 or former.value != 2 or self._members != {2}:
                    raise LinuxThreadRegistryError("Original exec changed thread identity/group")
                self._custody(tid)
                self._exec_count += 1
                if not self._stopping:
                    self._trace(tid, 7)
            else:
                raise LinuxThreadRegistryError("Unexpected original clone/exec-only event")
            return True
        except (OSError, ValueError, LinuxThreadRegistryError) as exc:
            self._failed = True
            raise LinuxThreadRegistryError(
                f"Original registry kernel event refused: {exc}"
            ) from exc

    def open_comm(self, caller_tid: int, target_tid: int) -> int:
        """Return only the genuine leaf for live kernel-registered group members."""
        self._check()
        if self.drained:
            raise LinuxThreadRegistryError("Original registry drained; comm refused")
        try:
            self._custody(caller_tid)
            target = self._custody(target_tid)
            current = os.open("comm", os.O_WRONLY | _NOFOLLOW | _CLOEXEC, dir_fd=target)
            try:
                _proc(self._native, current)
                self._custody(caller_tid)
                self._custody(target_tid)
            except (OSError, ValueError, LinuxThreadRegistryError):
                os.close(current)
                raise
            return current
        except (OSError, ValueError) as exc:
            self._failed = True
            raise LinuxThreadRegistryError("Original comm task custody refused") from exc

    def stop(self) -> None:
        """Kill through the original pidfd only, then reap every kernel-born member."""
        self._stopping = True
        self._check()
        assert self._pid is not None
        if not select.select([self._pid.fd], [], [], 0)[0] and (
            self._native.pidfd_send_signal(self._pid.fd, int(_api(signal, "SIGKILL")), None, 0) != 0
        ):
            raise LinuxThreadRegistryError("Original registry cancellation refused")
        while not self.drained:
            if time.monotonic() >= self._started + 30:
                raise LinuxThreadRegistryError(
                    "Original registry drain uncertain at lifetime deadline"
                )
            if not self.poll():
                time.sleep(0.001)

    def close(self) -> None:
        """Do not release custody while any original membership is still uncertain."""
        if self._closed:
            return
        self._stopping = True
        self._check()
        if not self.drained:
            raise LinuxThreadRegistryError("Original registry must drain before closing")
        changed = False
        for held in self._tasks.values():
            changed = not held.close() or changed
        assert self._pid is not None and self._root is not None
        changed = not self._pid.close(borrowed=True) or changed
        changed = not self._root.close(borrowed=True) or changed
        self._closed = True
        if changed:
            raise LinuxThreadRegistryError("Original description changed; foreign slots preserved")
