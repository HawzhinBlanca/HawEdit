"""Sealed namespace utility and original parent death, not producer admission."""

from __future__ import annotations

import ctypes
import hashlib
import math
import os
import re
import select
import signal
import stat
import sys
import threading
import time
from pathlib import Path
from typing import Any, NoReturn

from hawedit.linux_scope import LinuxScopeError, _pid_info

__all__ = ["LinuxBootstrapError", "LinuxNamespaceBootstrap"]

_MAX_UTILITY = 8 * 1024**2
_RETAINED: list[LinuxNamespaceBootstrap] = []


class LinuxBootstrapError(RuntimeError):
    """Original bootstrap refused; not a declaration of resource reconciliation."""


def _seconds(value: float) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 43200:
        raise LinuxBootstrapError("Linux bootstrap deadline must be finite, positive and bounded")
    return float(value)


def _api(module: object, name: str) -> Any:
    value = getattr(module, name, None)
    if value is None:
        raise LinuxBootstrapError(f"Linux bootstrap capability unavailable: {name}")
    return value


def _fcntl() -> Any:
    import fcntl

    return fcntl


def _identity(fd: int) -> tuple[int, int, int]:
    item = os.fstat(fd)
    return item.st_dev, item.st_ino, item.st_mode


class LinuxNamespaceBootstrap:
    """Prepare in one dedicated creator; execute only in its direct fork child.

    Owns a sealed copy of the caller-selected utility and the creator's original
    self-pidfd. It neither forks nor releases a model worker. The caller must
    separately admit all consumed interpreter/source/model/input/authority bytes
    and retain actual namespace/member ownership before model release.
    """

    _creator: tuple[int, int]
    _thread: threading.Thread
    _fd: int
    _anchor: int
    _owner: int
    _owner_anchor: int
    _failed: bool
    _closed: bool
    _memfd: Any
    _pidfd: Any
    _prctl: Any
    _known: dict[int, tuple[int, int, int]]
    _utility_hash: str
    _utility_name: str
    _utility_size: int

    def __init__(
        self, utility_path: Path, expected_sha256: str, *, timeout_seconds: float = 5.0
    ) -> None:
        end = time.monotonic() + _seconds(timeout_seconds)
        if sys.platform != "linux":
            raise LinuxBootstrapError("Original namespace bootstrap requires Linux")
        if (
            not isinstance(utility_path, Path)
            or not utility_path.is_absolute()
            or not isinstance(expected_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
        ):
            raise LinuxBootstrapError("Linux bootstrap utility path/hash invalid")
        self._single_thread()
        try:
            for fd in (0, 1, 2):
                os.fstat(fd)
        except OSError as exc:
            raise LinuxBootstrapError(
                "Linux bootstrap creator standard streams must be open"
            ) from exc
        if os.execve not in _api(os, "supports_fd"):
            raise LinuxBootstrapError("Linux bootstrap original FD execution unavailable")
        self._creator = (os.getpid(), threading.get_ident())
        self._thread = threading.current_thread()
        self._fd = self._anchor = self._owner = self._owner_anchor = -1
        self._failed = self._closed = False
        self._known: dict[int, tuple[int, int, int]] = {}
        self._utility_hash = expected_sha256
        self._utility_name = str(utility_path)
        self._utility_size = 0
        self._bind_libc()
        try:
            flags = os.O_RDONLY | int(_api(os, "O_CLOEXEC"))
            flags |= int(_api(os, "O_NOFOLLOW")) | os.O_NONBLOCK
            with os.fdopen(os.open(utility_path, flags), "rb") as source:
                info = os.fstat(source.fileno())
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_nlink != 1
                    or not 4 <= info.st_size <= _MAX_UTILITY
                ):
                    raise LinuxBootstrapError("Linux bootstrap regular bounded utility required")
                payload = bytearray()
                while len(payload) <= _MAX_UTILITY:
                    self._left(end)
                    part = source.read(min(65536, _MAX_UTILITY + 1 - len(payload)))
                    if not part:
                        break
                    payload.extend(part)
                if (
                    len(payload) != info.st_size
                    or not payload.startswith(b"\x7fELF")
                    or hashlib.sha256(payload).hexdigest() != expected_sha256
                ):
                    raise LinuxBootstrapError("Linux bootstrap utility ELF bytes/hash refused")
            self._fd = self._native_fd(self._memfd(b"hawedit-original-unshare", 0x13), "memfd")
            self._known[self._fd] = _identity(self._fd)
            offset = 0
            while offset < len(payload):
                self._left(end)
                count = os.write(self._fd, payload[offset : offset + 65536])
                if count <= 0:
                    raise LinuxBootstrapError("Linux bootstrap utility copy refused")
                offset += count
            os.fchmod(self._fd, 0o500)
            self._known[self._fd] = _identity(self._fd)
            # Verified Linux UAPI: EXEC implies WRITE/GROW/SHRINK/FUTURE_WRITE.
            if _fcntl().fcntl(self._fd, 1033, 0x2F) != 0:
                raise LinuxBootstrapError("Linux bootstrap utility sealing refused")
            self._utility_size = len(payload)
            self._anchor = self._duplicate(self._fd)
            self._owner = self._native_fd(self._pidfd(os.getpid(), 0), "self-pidfd")
            self._known[self._owner] = _identity(self._owner)
            self._owner_anchor = self._duplicate(self._owner)
            if _pid_info(self._owner)[0] != self._creator[0]:
                raise LinuxBootstrapError("Linux bootstrap original self-owner identity refused")
            self._inspect(end)
        except BaseException as exc:
            self._failed = True
            self._cleanup_acquired()
            if not isinstance(exc, Exception):
                raise
            raise LinuxBootstrapError("Linux bootstrap utility/owner admission refused") from exc

    @staticmethod
    def _single_thread() -> None:
        if len(tuple(Path("/proc/self/task").iterdir())) != 1:
            raise LinuxBootstrapError("Linux bootstrap requires a dedicated single-thread creator")

    def _bind_libc(self) -> None:
        try:
            native = ctypes.CDLL(None, use_errno=True)
            self._memfd = native.memfd_create
            self._memfd.argtypes = [ctypes.c_char_p, ctypes.c_uint]
            self._memfd.restype = ctypes.c_int
            self._pidfd = native.pidfd_open
            self._pidfd.argtypes = [ctypes.c_int, ctypes.c_uint]
            self._pidfd.restype = ctypes.c_int
            self._prctl = native.prctl
            self._prctl.argtypes = [ctypes.c_int, *([ctypes.c_ulong] * 4)]
            self._prctl.restype = ctypes.c_int
        except (OSError, AttributeError) as exc:
            raise LinuxBootstrapError(
                "Linux bootstrap required local libc ABI unavailable"
            ) from exc

    @staticmethod
    def _left(end: float) -> None:
        if time.monotonic() >= end:
            raise LinuxBootstrapError("Linux bootstrap original deadline exceeded")

    @staticmethod
    def _native_fd(value: int, label: str) -> int:
        if value < 0:
            raise OSError(ctypes.get_errno(), "Original Linux bootstrap " + label)
        if os.get_inheritable(value):
            os.close(value)
            raise LinuxBootstrapError("Linux bootstrap inheritable original FD refused")
        return value

    def _duplicate(self, fd: int) -> int:
        value = os.dup(fd)
        self._known[value] = _identity(value)
        return value

    def _inspect(self, end: float) -> None:
        if self._failed or self._closed:
            raise LinuxBootstrapError("Linux bootstrap refused/closed; capabilities retained")
        self._left(end)
        try:
            for fd, expected in self._known.items():
                if _identity(fd) != expected or os.get_inheritable(fd):
                    raise LinuxBootstrapError("Linux bootstrap original descriptor substituted")
            for fd, anchor in ((self._fd, self._anchor), (self._owner, self._owner_anchor)):
                if _fcntl().fcntl(fd, 1027, anchor) != 1:
                    raise LinuxBootstrapError("Linux bootstrap original description substituted")
            if (
                _fcntl().fcntl(self._anchor, 1034) != 63
                or os.fstat(self._anchor).st_size != self._utility_size
            ):
                raise LinuxBootstrapError("Linux bootstrap sealed executable binding changed")
            digest = hashlib.sha256()
            offset = 0
            while offset < self._utility_size:
                self._left(end)
                data = _api(os, "pread")(
                    self._anchor, min(65536, self._utility_size - offset), offset
                )
                if not data:
                    raise LinuxBootstrapError("Linux bootstrap sealed executable truncated")
                digest.update(data)
                offset += len(data)
            if digest.hexdigest() != self._utility_hash:
                raise LinuxBootstrapError("Linux bootstrap sealed utility hash changed")
            self._left(end)
        except (OSError, LinuxBootstrapError) as exc:
            self._failed = True
            _RETAINED.append(self)
            raise LinuxBootstrapError("Linux bootstrap original inspection uncertain") from exc

    def _owner_live(self) -> None:
        if select.select([self._owner_anchor], [], [], 0)[0]:
            raise LinuxBootstrapError("Linux bootstrap original owner is dead; exec refused")
        if _pid_info(self._owner_anchor)[0] != self._creator[0]:
            raise LinuxBootstrapError("Linux bootstrap original owner identity refused")

    def exec(
        self,
        command: tuple[str, ...],
        *,
        pass_fds: tuple[int, ...] = (),
        timeout_seconds: float = 5.0,
    ) -> NoReturn:
        end = time.monotonic() + _seconds(timeout_seconds)
        if (
            os.getpid() == self._creator[0]
            or self._creator[1] != threading.get_ident()
            or self._thread is not threading.current_thread()
        ):
            raise LinuxBootstrapError("Linux bootstrap exec requires original direct fork child")
        self._single_thread()
        try:
            self._inspect(end)
            self._owner_live()
            if int(_api(os, "getppid")()) != self._creator[0]:
                raise LinuxBootstrapError("Linux bootstrap original direct child relationship lost")
            if (
                type(command) is not tuple
                or not 1 <= len(command) <= 64
                or any(type(arg) is not str or not arg or "\0" in arg for arg in command)
                or sum(len(arg.encode("utf-8")) for arg in command) > 65536
                or not command[0].startswith("/")
                or type(pass_fds) is not tuple
                or len(pass_fds) > 131
                or any(type(fd) is not int or fd < 3 or fd in self._known for fd in pass_fds)
                or len(set(pass_fds)) != len(pass_fds)
            ):
                raise LinuxBootstrapError("Linux bootstrap fixed command/control FD inputs invalid")
            for fd in pass_fds:
                kind = os.fstat(fd).st_mode
                if not (stat.S_ISSOCK(kind) or stat.S_ISFIFO(kind)):
                    raise LinuxBootstrapError("Linux bootstrap control FD is not socket/pipe")
            if self._prctl(1, int(_api(signal, "SIGKILL")), 0, 0, 0) != 0:
                raise OSError(ctypes.get_errno(), "Original parent-death installation refused")
            observed = ctypes.c_int()
            if self._prctl(2, ctypes.addressof(observed), 0, 0, 0) != 0:
                raise OSError(ctypes.get_errno(), "Original parent-death observation refused")
            if observed.value != int(_api(signal, "SIGKILL")):
                raise LinuxBootstrapError("Linux bootstrap parent-death binding differs")
            self._owner_live()
            if self._prctl(38, 1, 0, 0, 0) != 0 or self._prctl(39, 0, 0, 0, 0) != 1:
                raise LinuxBootstrapError("Linux bootstrap no-new-privileges admission refused")
            self._isolate(pass_fds)
            self._inspect(end)
            self._owner_live()
            self._left(end)
            os.execve(
                self._anchor,
                (
                    self._utility_name,
                    "--user",
                    "--map-current-user",
                    "--pid",
                    "--fork",
                    "--kill-child=SIGKILL",
                    "--mount-proc",
                    *command,
                ),
                {"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
            )
        except (OSError, ValueError, LinuxScopeError, LinuxBootstrapError) as exc:
            self._failed = True
            _RETAINED.append(self)
            raise LinuxBootstrapError("Linux bootstrap original owner/exec refused") from exc
        raise LinuxBootstrapError("Linux bootstrap original exec unexpectedly returned")

    def _isolate(self, pass_fds: tuple[int, ...]) -> None:
        entries = tuple(Path("/proc/self/fd").iterdir())
        if len(entries) > 4096:
            raise LinuxBootstrapError("Linux bootstrap inherited FD inventory exceeds bound")
        keep = {*self._known, *pass_fds}
        for entry in entries:
            fd = int(entry.name)
            if fd > 2 and fd not in keep:
                try:
                    os.close(fd)
                except OSError as exc:
                    # The directory iterator's own temporary FD is already closed.
                    if exc.errno != 9:
                        raise
        original_null = os.open("/dev/null", os.O_RDWR | int(_api(os, "O_CLOEXEC")))
        try:
            null = int(_fcntl().fcntl(original_null, _fcntl().F_DUPFD_CLOEXEC, 3))
        finally:
            os.close(original_null)
        try:
            info = os.fstat(null)
            if not stat.S_ISCHR(info.st_mode) or int(_api(info, "st_rdev")) != int(
                _api(os, "makedev")(1, 3)
            ):
                raise LinuxBootstrapError("Linux bootstrap null device refused")
            for fd in (0, 1, 2):
                os.dup2(null, fd, inheritable=True)
        finally:
            os.close(null)
        for fd in pass_fds:
            os.set_inheritable(fd, True)

    def _cleanup_acquired(self) -> None:
        for fd, expected in tuple(self._known.items()):
            try:
                if _identity(fd) != expected:
                    raise LinuxBootstrapError("Linux bootstrap cleanup foreign FD refused")
                os.close(fd)
                del self._known[fd]
            except (OSError, LinuxBootstrapError):
                _RETAINED.append(self)

    def close(self) -> None:
        if (
            self._creator != (os.getpid(), threading.get_ident())
            or self._thread is not threading.current_thread()
        ):
            raise LinuxBootstrapError("Linux bootstrap close creator process/thread mismatch")
        if self._closed:
            return
        self._inspect(time.monotonic() + 5)
        self._cleanup_acquired()
        if self._known:
            self._failed = True
            raise LinuxBootstrapError("Linux bootstrap cleanup uncertain; capabilities retained")
        self._fd = self._anchor = self._owner = self._owner_anchor = -1
        self._closed = True
