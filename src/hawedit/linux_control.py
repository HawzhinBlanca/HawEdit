"""Dedicated Linux supervisor framing; not worker/GPU/billing completion."""

from __future__ import annotations

import math
import os
import select
import stat
import struct
import sys
import threading
import time
from typing import NoReturn

__all__ = ["LinuxOwnerChannel", "LinuxOwnerError"]

_MAX_REQUEST = 16 * 1024**2
_MAX_EXCHANGES = 65536
_ADMISSION = threading.Lock()
_ACTIVE: LinuxOwnerChannel | None = None


class LinuxOwnerError(RuntimeError):
    """Refused control IO; callers must not release an uncertain attempt."""


def _deadline(value: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, float | int)
        or not math.isfinite(value)
        or not 0 < value <= 43200
    ):
        raise LinuxOwnerError("Linux owner deadline invalid")
    return float(value)


def _identity(fd: int) -> tuple[int, int, int, int]:
    info = os.fstat(fd)
    if (
        not stat.S_ISFIFO(info.st_mode)
        or os.readlink(f"/proc/self/fd/{fd}") != f"pipe:[{info.st_ino}]"
    ):
        raise LinuxOwnerError("Linux owner requires original anonymous pipe descriptors")
    return info.st_dev, info.st_ino, info.st_mode, info.st_nlink


def _get_blocking(fd: int) -> bool:
    function = getattr(os, "get_blocking", None)
    if not callable(function):
        raise LinuxOwnerError("Linux owner blocking inspection unavailable")
    return bool(function(fd))


def _set_blocking(fd: int, value: bool) -> None:
    function = getattr(os, "set_blocking", None)
    if not callable(function):
        raise LinuxOwnerError("Linux owner blocking control unavailable")
    function(fd, value)


def _same_description(first: int, second: int) -> bool:
    import fcntl

    function = getattr(fcntl, "fcntl", None)
    if not callable(function):
        raise LinuxOwnerError("Linux owner file-description query unavailable")
    # Linux UAPI F_DUPFD_QUERY; Python 3.11/3.12 do not expose its name.
    value = int(function(first, 1027, second))
    if value not in (0, 1):
        raise LinuxOwnerError("Linux owner file-description query refused")
    return value == 1


class LinuxOwnerChannel:
    """One creator, one request and one lifetime on dedicated original STD pipes.

    Duplicates share blocking flags with STDIO. Do not share this supervisor's
    streams with buffered readers/writers or worker children. Fork still copies
    close-on-exec FDs; worker release must explicitly separate its control IO.
    """

    _creator: tuple[int, int]
    _creator_thread: threading.Thread
    _originals: tuple[tuple[int, int, int, int], tuple[int, int, int, int]]
    _blocking: tuple[bool, bool]
    _read_fd: int
    _write_fd: int
    _failed: bool
    _cleanup_failed: bool
    _closed: bool
    _state: str

    def __init__(
        self, *, exchange_timeout_seconds: float = 5.0, overall_timeout_seconds: float = 3600.0
    ) -> None:
        global _ACTIVE
        self._exchange_seconds = _deadline(exchange_timeout_seconds)
        self._end = time.monotonic() + _deadline(overall_timeout_seconds)
        if sys.platform != "linux":
            raise LinuxOwnerError("Linux owner channel requires Linux")
        import fcntl

        try:
            originals = (_identity(0), _identity(1))
            if (
                not all(stat.S_ISFIFO(item[2]) and item[3] == 1 for item in originals)
                or originals[0] == originals[1]
                or fcntl.fcntl(0, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDONLY
                or fcntl.fcntl(1, fcntl.F_GETFL) & os.O_ACCMODE != os.O_WRONLY
            ):
                raise LinuxOwnerError("Original Linux owner STD pipe admission refused")
            self._blocking = (_get_blocking(0), _get_blocking(1))
            if not _same_description(0, 0) or _same_description(0, 1):
                raise LinuxOwnerError("Linux owner file-description query calibration refused")
        except OSError as exc:
            raise LinuxOwnerError(
                "Original Linux owner pipe inspection/file-description query unavailable"
            ) from exc
        self._creator = (os.getpid(), threading.get_ident())
        self._creator_thread = threading.current_thread()
        self._originals = originals
        self._read_fd = self._write_fd = -1
        self._failed = self._cleanup_failed = self._closed = False
        self._state = "initial"
        self._nonces: set[bytes] = set()
        with _ADMISSION:
            if _ACTIVE is not None:
                raise LinuxOwnerError("Linux owner channel lifetime already admitted")
            # Retain admission even if acquisition/cleanup becomes uncertain.
            _ACTIVE = self
        try:
            self._read_fd = os.dup(0)
            self._write_fd = os.dup(1)
            for fd in (self._read_fd, self._write_fd):
                os.set_inheritable(fd, False)
                _set_blocking(fd, False)
            self._inspect()
        except (OSError, LinuxOwnerError) as exc:
            self._failed = True
            try:
                self.close()
            except LinuxOwnerError as cleanup:
                raise cleanup from exc
            raise LinuxOwnerError("Linux owner pipe acquisition failed") from exc

    def _fail(self, message: str) -> NoReturn:
        self._failed = True
        raise LinuxOwnerError("Linux owner " + message)

    def _creator_check(self) -> None:
        if (
            self._creator != (os.getpid(), threading.get_ident())
            or self._creator_thread is not threading.current_thread()
        ):
            raise LinuxOwnerError("Linux owner creator process/thread mismatch")

    def _inspect(self) -> None:
        try:
            for original, duplicate, expected in zip(
                (0, 1), (self._read_fd, self._write_fd), self._originals, strict=True
            ):
                if _identity(original) != expected:
                    self._fail("original pipe substituted")
                if duplicate >= 0 and (
                    _identity(duplicate) != expected
                    or os.get_inheritable(duplicate)
                    or not _same_description(original, duplicate)
                ):
                    self._fail("owned pipe descriptor substituted")
        except OSError as exc:
            self._failed = True
            raise LinuxOwnerError("Linux owner owned pipe inspection uncertain") from exc

    def _guard(self) -> None:
        self._creator_check()
        if self._failed or self._closed or self._cleanup_failed:
            raise LinuxOwnerError("Linux owner channel refused/closed")
        self._inspect()
        for fd in (self._read_fd, self._write_fd):
            if _get_blocking(fd):
                self._fail("blocking pipe mutation refused")

    def _left(self, end: float) -> float:
        left = min(end, self._end) - time.monotonic()
        if left <= 0:
            self._fail("control deadline exceeded")
        return left

    def _wait(self, fd: int, *, reading: bool, end: float) -> None:
        while True:
            self._guard()
            left = self._left(end)
            try:
                ready = select.select([fd] if reading else [], [] if reading else [fd], [], left)
            except InterruptedError:
                continue
            self._guard()
            self._left(end)
            if ready[0] if reading else ready[1]:
                return

    def _read(self, size: int, *, end: float, phase: str) -> bytes:
        result = bytearray()
        while len(result) < size:
            self._wait(self._read_fd, reading=True, end=end)
            try:
                part = os.read(self._read_fd, min(4096, size - len(result)))
            except (BlockingIOError, InterruptedError):
                continue
            self._left(end)
            if not part:
                self._fail(phase + " premature owner EOF")
            result.extend(part)
        return bytes(result)

    def _write(self, data: bytes, *, end: float) -> None:
        offset = 0
        while offset < len(data):
            self._wait(self._write_fd, reading=False, end=end)
            try:
                count = os.write(self._write_fd, data[offset : offset + 4096])
            except (BlockingIOError, InterruptedError):
                continue
            self._left(end)
            if count <= 0:
                self._fail("control write refused")
            offset += count

    def _no_unsolicited(self, *, end: float) -> None:
        self._guard()
        self._left(end)
        if select.select([self._read_fd], [], [], 0)[0]:
            try:
                value = os.read(self._read_fd, 1)
            except BlockingIOError:
                return
            self._fail("unsolicited reply bytes" if value else "reply premature owner EOF")

    def _run_error(self, exc: OSError) -> NoReturn:
        self._failed = True
        raise LinuxOwnerError("Linux owner control pipe IO refused") from exc

    def receive_request(self) -> bytes:
        self._guard()
        if self._state != "initial":
            self._fail("request order refused")
        end = time.monotonic() + self._exchange_seconds
        try:
            header = self._read(8, end=end, phase="request")
            length = struct.unpack("!I", header[4:])[0]
            if header[:4] != b"HEI1" or length > _MAX_REQUEST:
                self._fail("request framing/size refused")
            payload = self._read(length, end=end, phase="request")
            self._no_unsolicited(end=end)
        except OSError as exc:
            self._run_error(exc)
        self._state = "request"
        return payload

    def exchange(self) -> None:
        self._guard()
        if self._state not in ("request", "exchanged"):
            self._fail("exchange order refused")
        if len(self._nonces) >= _MAX_EXCHANGES:
            self._fail("exchange nonce budget refused")
        end = time.monotonic() + self._exchange_seconds
        try:
            self._no_unsolicited(end=end)
            nonce = os.urandom(16)
            if len(nonce) != 16 or nonce in self._nonces:
                self._fail("exchange nonce freshness refused")
            self._nonces.add(nonce)
            self._write(b"HEC1" + nonce, end=end)
            if self._read(20, end=end, phase="reply") != b"HER1" + nonce:
                self._fail("reply framing/nonce refused")
            self._no_unsolicited(end=end)
        except OSError as exc:
            self._run_error(exc)
        self._state = "exchanged"

    def finish(self) -> None:
        self._guard()
        if self._state != "exchanged":
            self._fail("terminal order refused")
        end = time.monotonic() + self._exchange_seconds
        try:
            self._no_unsolicited(end=end)
            self._write(b"HED1", end=end)
            self._wait(self._read_fd, reading=True, end=end)
            if os.read(self._read_fd, 1):
                self._fail("terminal trailing reply refused")
            self._left(end)
        except OSError as exc:
            self._run_error(exc)
        self._state = "terminal"

    def close(self) -> None:
        self._creator_check()
        if self._cleanup_failed:
            raise LinuxOwnerError("Linux owner uncertain cleanup retained; retry refused")
        if self._closed:
            return
        try:
            self._inspect()
            for fd, blocking in zip((0, 1), self._blocking, strict=True):
                _set_blocking(fd, blocking)
            for attribute in ("_read_fd", "_write_fd"):
                fd = getattr(self, attribute)
                if fd >= 0:
                    os.close(fd)
                    setattr(self, attribute, -1)
        except (OSError, LinuxOwnerError) as exc:
            self._failed = self._cleanup_failed = True
            raise LinuxOwnerError(
                "Linux owner uncertain cleanup retained; original descriptors"
            ) from exc
        self._closed = True
