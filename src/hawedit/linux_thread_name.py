"""Exact original-thread comm FD injection, not a filesystem or model service."""

from __future__ import annotations

import ctypes
import errno
import math
import os
import signal
import struct
import threading
import time
from dataclasses import dataclass
from types import FrameType
from typing import Any, ClassVar

from hawedit.linux_thread_registry import (
    LinuxThreadRegistry,
    LinuxThreadRegistryError,
    _Description,
)

__all__ = ["LinuxThreadNameBroker", "LinuxThreadNameError", "ThreadNameResult"]

_RECV = 0xC0502100
_SEND = 0xC0182101
_VALID = 0x40082102
_ADDFD = 0x40182103
_ACTIVE: LinuxThreadNameBroker | None = None


class LinuxThreadNameError(RuntimeError):
    """Original listener/request custody or bounded operation is refused."""


@dataclass(frozen=True)
class ThreadNameResult:
    caller_tid: int
    target_tid: int | None
    path: str | None
    accepted: bool
    descriptor: int | None
    error: int | None


class _Iovec(ctypes.Structure):
    _fields_: ClassVar[list[tuple[str, Any]]] = [
        ("base", ctypes.c_void_p),
        ("length", ctypes.c_size_t),
    ]


class _Sigevent(ctypes.Structure):
    _fields_: ClassVar[list[tuple[str, Any]]] = [
        ("value", ctypes.c_void_p),
        ("signo", ctypes.c_int),
        ("notify", ctypes.c_int),
        ("padding", ctypes.c_byte * 48),
    ]


class _Timespec(ctypes.Structure):
    _fields_: ClassVar[list[tuple[str, Any]]] = [
        ("seconds", ctypes.c_long),
        ("nanoseconds", ctypes.c_long),
    ]


class _TimerSpec(ctypes.Structure):
    _fields_: ClassVar[list[tuple[str, Any]]] = [
        ("interval", _Timespec),
        ("value", _Timespec),
    ]


def _api(module: object, name: str) -> Any:
    value = getattr(module, name, None)
    if value is None:
        raise LinuxThreadNameError(f"Thread broker required kernel capability unavailable: {name}")
    return value


def _fcntl() -> Any:
    import fcntl

    return fcntl


class LinuxThreadNameBroker:
    """One original private controller services a borrowed genuine listener.

    Each operation owns a fixed local alarm handler, never a caller callback.
    The original registry's lifetime is the ceiling; external Scope still must
    authenticate and bound the full preparation/model/resource lifecycle.
    """

    def __init__(
        self,
        registry: LinuxThreadRegistry,
        listener: int,
        *,
        timeout_seconds: float = 30,
    ) -> None:
        global _ACTIVE
        if (
            type(timeout_seconds) not in (int, float)
            or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= 30
        ):
            raise LinuxThreadNameError("Thread broker deadline must be finite, positive, <=30s")
        if type(registry) is not LinuxThreadRegistry:
            raise LinuxThreadNameError("Thread broker requires an original kernel registry")
        if _ACTIVE is not None:
            raise LinuxThreadNameError("Original thread broker lifetime already retained")
        self._registry = registry
        self._creator = (os.getpid(), threading.get_ident(), threading.current_thread())
        self._end = min(registry._end, time.monotonic() + float(timeout_seconds))
        self._requests = 0
        self._failed = self._closed = False
        self._listener: _Description | None = None
        self._handler = self._deadline
        try:
            registry._check()
            if registry.drained or type(listener) is not int or listener < 3:
                raise LinuxThreadNameError("Thread broker original listener is not live")
            if os.readlink(f"/proc/self/fd/{listener}") != "anon_inode:seccomp notify":
                raise LinuxThreadNameError("Thread broker requires a genuine seccomp listener")
            self._native = ctypes.CDLL(None, use_errno=True)
            self._native.syscall.restype = ctypes.c_long
            self._native.process_vm_readv.argtypes = [
                ctypes.c_int,
                ctypes.POINTER(_Iovec),
                ctypes.c_ulong,
                ctypes.POINTER(_Iovec),
                ctypes.c_ulong,
                ctypes.c_ulong,
            ]
            self._native.process_vm_readv.restype = ctypes.c_ssize_t
            self._native.timer_create.argtypes = [
                ctypes.c_int,
                ctypes.POINTER(_Sigevent),
                ctypes.POINTER(ctypes.c_void_p),
            ]
            self._native.timer_create.restype = ctypes.c_int
            self._native.timer_settime.argtypes = [
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.POINTER(_TimerSpec),
                ctypes.c_void_p,
            ]
            self._native.timer_settime.restype = ctypes.c_int
            self._native.timer_delete.argtypes = [ctypes.c_void_p]
            self._native.timer_delete.restype = ctypes.c_int
            if ctypes.sizeof(_Sigevent) != 64 or ctypes.sizeof(_TimerSpec) != 32:
                raise LinuxThreadNameError("Thread broker timer ABI unsupported")
            sizes = (ctypes.c_ushort * 3)()
            if self._native.syscall(317, 3, 0, ctypes.byref(sizes)) != 0:
                raise LinuxThreadNameError("Thread broker kernel notification ABI unavailable")
            if tuple(sizes) != (80, 24, 64):
                raise LinuxThreadNameError("Thread broker unsupported notification ABI sizes")
            try:
                _fcntl().ioctl(listener, _VALID, struct.pack("<Q", 0))
            except OSError as exc:
                if exc.errno != errno.ENOENT:
                    raise LinuxThreadNameError(
                        "Thread broker listener ioctl identity refused"
                    ) from exc
            else:
                raise LinuxThreadNameError("Thread broker invalid notification identity admitted")
            self._listener = _Description.hold(listener)
            self._listener.inspect()
        except (OSError, ValueError, LinuxThreadRegistryError, LinuxThreadNameError) as exc:
            if self._listener is not None:
                self._listener.close(borrowed=True)
            raise LinuxThreadNameError(
                f"Original thread broker listener admission refused: {exc}"
            ) from exc
        _ACTIVE = self

    def _context(self) -> None:
        if self._creator != (os.getpid(), threading.get_ident(), threading.current_thread()):
            raise LinuxThreadNameError("Thread broker creator process/thread differs")
        if self._closed:
            raise LinuxThreadNameError("Thread broker is closed")
        self._registry._check()

    def _deadline(self, signum: int, frame: FrameType | None) -> None:
        raise LinuxThreadNameError("Original thread broker receive/response deadline expired")

    def _read_path(self, pid: int, address: int) -> str:
        output = ctypes.create_string_buffer(128)
        local = _Iovec(ctypes.addressof(output), 128)
        remote = _Iovec(address, 128)
        size = self._native.process_vm_readv(
            pid, ctypes.byref(local), 1, ctypes.byref(remote), 1, 0
        )
        if not 0 < size <= 128:
            raise LinuxThreadNameError("Original thread broker bounded pathname copy refused")
        raw = output.raw[:size]
        end = raw.find(b"\0")
        if end < 0:
            raise LinuxThreadNameError("Original thread broker pathname is unterminated")
        return raw[:end].decode("ascii", "strict")

    def _receive_and_respond(self) -> ThreadNameResult:
        assert self._listener is not None
        listener = self._listener.fd
        notification = bytearray(80)
        _fcntl().ioctl(listener, _RECV, notification, True)
        ident, pid, flags, number, arch, _, *args = struct.unpack("<QIIiIQ6Q", notification)
        self._requests += 1
        _fcntl().ioctl(listener, _VALID, struct.pack("<Q", ident))
        path: str | None = None
        target: int | None = None
        accepted = bool(
            ident
            and not flags
            and arch == 0xC000003E
            and pid in self._registry.registered_tids
            and number in (2, 257)
        )
        if accepted:
            try:
                path = self._read_path(pid, args[0] if number == 2 else args[1])
                prefix, suffix = "/proc/self/task/", "/comm"
                token = (
                    path[len(prefix) : -len(suffix)]
                    if path.startswith(prefix) and path.endswith(suffix)
                    else ""
                )
                if token.isascii() and token.isdecimal() and len(token) <= 10:
                    target = int(token)
                openflags = args[1] if number == 2 else args[2]
                mode = args[2] if number == 2 else args[3]
                accepted = bool(
                    target is not None
                    and target in self._registry.registered_tids
                    and path == prefix + str(target) + suffix
                    and openflags in (0x241, 0x80241)
                    and mode == 0o666
                    and (number == 2 or args[0] == (1 << 64) - 100)
                )
            except (ValueError, LinuxThreadNameError):
                accepted = False
        self._listener.inspect()
        if not accepted:
            _fcntl().ioctl(
                listener, _SEND, bytearray(struct.pack("<QqiI", ident, 0, -errno.EPERM, 0)), True
            )
            return ThreadNameResult(pid, target, path, False, None, errno.EPERM)
        assert target is not None
        source = self._registry.open_comm(pid, target)
        try:
            self._listener.inspect()
            _fcntl().ioctl(listener, _VALID, struct.pack("<Q", ident))
            injected = int(
                _fcntl().ioctl(
                    listener,
                    _ADDFD,
                    bytearray(
                        struct.pack(
                            "<QIIII",
                            ident,
                            2,
                            source,
                            0,
                            0x80000 if openflags & 0x80000 else 0,
                        )
                    ),
                    True,
                )
            )
        finally:
            os.close(source)
        return ThreadNameResult(pid, target, path, True, injected, None)

    def serve_once(self) -> ThreadNameResult:
        """Bound receive/copy/injection with a genuine controller-only kernel timer."""
        try:
            self._context()
            assert self._listener is not None
            self._listener.inspect()
            if self._failed or self._requests >= 32 or self._registry.drained:
                raise LinuxThreadNameError(
                    "Thread broker refused/drained or request budget exhausted"
                )
            remaining = self._end - time.monotonic()
            if remaining <= 0:
                raise LinuxThreadNameError("Thread broker deadline expired")
            alarm = int(_api(signal, "SIGALRM"))
            timer = int(_api(signal, "ITIMER_REAL"))
            previous = signal.getsignal(alarm)
            delay, interval = _api(signal, "getitimer")(timer)
            if previous != signal.SIG_DFL or interval != 0:
                raise LinuxThreadNameError(
                    "Thread broker cannot replace another controller watchdog"
                )
            signal.signal(alarm, self._handler)
            clock = ctypes.c_void_p()
            acquired = False
            try:
                # Independent absolute timer: never reset or extend the caller's ITIMER_REAL.
                event = _Sigevent(signo=alarm, notify=0)
                if self._native.timer_create(1, ctypes.byref(event), ctypes.byref(clock)) != 0:
                    raise LinuxThreadNameError("Thread broker genuine controller timer refused")
                acquired = True
                nanos = math.floor(self._end * 1_000_000_000)
                deadline = _TimerSpec(
                    value=_Timespec(nanos // 1_000_000_000, nanos % 1_000_000_000)
                )
                if self._native.timer_settime(clock, 1, ctypes.byref(deadline), None) != 0:
                    raise LinuxThreadNameError("Thread broker absolute controller deadline refused")
                return self._receive_and_respond()
            finally:
                if acquired and self._native.timer_delete(clock) != 0:
                    raise LinuxThreadNameError("Thread broker original timer cleanup uncertain")
                if signal.getsignal(alarm) is not self._handler:
                    raise LinuxThreadNameError("Thread broker controller handler substituted")
                signal.signal(alarm, previous)
        except (OSError, ValueError, LinuxThreadRegistryError, LinuxThreadNameError) as exc:
            self._failed = True
            raise LinuxThreadNameError(f"Original thread broker operation refused: {exc}") from exc

    def close(self) -> None:
        if self._closed:
            return
        self._context()
        if not self._registry.drained:
            raise LinuxThreadNameError("Thread broker requires original full drain before close")
        assert self._listener is not None
        original = self._listener.close(borrowed=True)
        self._closed = True
        if not original:
            raise LinuxThreadNameError(
                "Original listener description changed; foreign slot preserved"
            )
