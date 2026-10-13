"""Held original Linux namespace members, not model/GPU/effect admission."""

from __future__ import annotations

import array
import ctypes
import errno
import math
import os
import select
import signal
import socket
import struct
import sys
import threading
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

__all__ = ["LinuxScope", "LinuxScopeError"]

_MAX_FDS = 131
_ADMISSION = threading.Lock()
_ACTIVE: LinuxScope | None = None


class LinuxScopeError(RuntimeError):
    """Original ownership is refused/uncertain; never release an attempt on this."""


def _seconds(value: float) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 43200:
        raise LinuxScopeError("Linux scope deadline must be finite, positive and bounded")
    return float(value)


def _fcntl() -> Any:
    import fcntl

    return fcntl


def _capability(module: object, name: str) -> Any:
    value = getattr(module, name, None)
    if value is None:
        raise LinuxScopeError(f"Linux scope required capability unavailable: {name}")
    return value


def _space(size: int) -> int:
    return int(_capability(socket, "CMSG_SPACE")(size))


def _recvmsg(channel: socket.socket, flags: int) -> tuple[bytes, list[tuple[int, int, bytes]], int]:
    packet, ancillary, received_flags, _ = _capability(channel, "recvmsg")(
        40, _space(_MAX_FDS * array.array("i").itemsize) + _space(12), flags
    )
    return packet, ancillary, received_flags


def _identity(fd: int) -> tuple[int, int, int]:
    info = os.fstat(fd)
    return info.st_dev, info.st_ino, info.st_mode


def _pid_info(fd: int) -> tuple[int, ...]:
    with Path(f"/proc/self/fdinfo/{fd}").open("rb") as source:
        raw = source.read(8193)
    if len(raw) > 8192:
        raise LinuxScopeError("Linux scope original pidfd information exceeds bound")
    fields: dict[str, str] = {}
    for line in raw.decode("ascii").splitlines():
        key, separator, value = line.partition(":")
        if separator:
            if key in fields:
                raise LinuxScopeError("Linux scope duplicate original pidfd information")
            fields[key] = value.strip()
    ids = tuple(int(item) for item in fields.get("NSpid", "").split())
    if not ids or any(item <= 0 for item in ids) or int(fields.get("Pid", "-1")) != ids[0]:
        raise LinuxScopeError("Linux scope original pidfd identity is not live/visible")
    return ids


class LinuxScope:
    """One dedicated creator adopts a kernel handoff before caller worker release.

    The borrowed unnamed socketpair stays owned by the caller. Received rights
    and independent description anchors belong here. This component neither
    launches a namespace nor admits executable/model bytes or billed effects.
    """

    _creator: tuple[int, int]
    _creator_thread: threading.Thread
    _borrowed: socket.socket
    _channel_fd: int
    _signal: Any
    _cmsg_cloexec: int
    _dontwait: int
    _failed: bool
    _closed: bool
    _stopped: bool
    _admitted: bool
    _uid: int
    _gid: int
    _euid: int

    def __init__(self, channel: socket.socket, *, timeout_seconds: float = 5.0) -> None:
        global _ACTIVE
        seconds = _seconds(timeout_seconds)
        if sys.platform != "linux":
            raise LinuxScopeError("Original Linux scope requires Linux")
        with _ADMISSION:
            if _ACTIVE is not None:
                raise LinuxScopeError("Original Linux scope lifetime retained; admission refused")
        if type(channel) is not socket.socket:
            raise LinuxScopeError("Linux scope requires an original unnamed owner socketpair")
        if len(tuple(Path("/proc/self/task").iterdir())) != 1:
            raise LinuxScopeError(
                "Linux scope admission requires a dedicated single-thread creator"
            )
        self._creator = (os.getpid(), threading.get_ident())
        self._creator_thread = threading.current_thread()
        self._borrowed = channel
        self._channel_fd = channel.fileno()
        self._socket: socket.socket | None = None
        self._held: list[int] = []
        self._anchors: list[int] = []
        self._scratch: list[int] = []
        self._identities: list[tuple[int, int, int]] = []
        self._failed = self._closed = self._stopped = self._admitted = False
        try:
            self._uid = int(_capability(os, "getuid")())
            self._gid = int(_capability(os, "getgid")())
            self._euid = int(_capability(os, "geteuid")())
            _capability(socket, "CMSG_SPACE")
            _capability(channel, "recvmsg")
            _capability(select, "poll")
            if (
                channel.family != socket.AF_UNIX
                or channel.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_SEQPACKET
                or channel.getsockname() != ""
                or channel.getpeername() != ""
                or not channel.getblocking()
                or os.get_inheritable(self._channel_fd)
                or channel.getsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED) != 1
                or struct.unpack(
                    "3i", channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
                )
                != (os.getpid(), self._uid, self._gid)
            ):
                raise LinuxScopeError("Linux scope original owner socketpair admission refused")
            self._signal = ctypes.CDLL(None, use_errno=True).pidfd_send_signal
            self._signal.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint]
            self._signal.restype = ctypes.c_int
            self._cmsg_cloexec = int(socket.MSG_CMSG_CLOEXEC)
            self._dontwait = int(socket.MSG_DONTWAIT)
        except (OSError, AttributeError, ValueError) as exc:
            raise LinuxScopeError("Linux scope socket/kernel/libc capability unavailable") from exc
        with _ADMISSION:
            if _ACTIVE is not None:
                raise LinuxScopeError("Original Linux scope lifetime retained; admission refused")
            _ACTIVE = self
        try:
            self._socket = channel.dup()
            self._inspect_channel()
            end = time.monotonic() + seconds
            nonce = os.urandom(32)
            if len(nonce) != 32:
                raise LinuxScopeError("Linux scope challenge generation refused")
            self._request(b"HEA1" + nonce, end)
            self._handoff(nonce, end)
            self._seal_handoff(end)
            self._admit()
            self._left(end)
            for fd in self._held:
                self._anchors.append(os.dup(fd))
                self._identities.append(_identity(fd))
            self._inspect()
            self._close_list(self._scratch)
            self._left(end)
            self._admitted = True
            self.require_live()
        except (OSError, ValueError, LinuxScopeError) as exc:
            self._failed = True
            # No received descriptor is signal authority until full admission.
            if not self._admitted:
                self._cleanup_unadmitted()
            raise LinuxScopeError(
                "Original Linux scope handoff refused; uncertainty retained"
            ) from exc

    def _creator_check(self) -> None:
        if (
            self._creator != (os.getpid(), threading.get_ident())
            or self._creator_thread is not threading.current_thread()
        ):
            raise LinuxScopeError("Linux scope creator process/thread mismatch")

    def _inspect_channel(self) -> None:
        if self._socket is None or (
            self._borrowed.fileno() != self._channel_fd
            or os.get_inheritable(self._channel_fd)
            or os.get_inheritable(self._socket.fileno())
            or _fcntl().fcntl(self._channel_fd, 1027, self._socket.fileno()) != 1
        ):
            raise LinuxScopeError("Linux scope original owner socket description substituted")

    def _left(self, end: float) -> float:
        left = end - time.monotonic()
        if left <= 0:
            raise LinuxScopeError("Linux scope original control deadline exceeded")
        return left

    def _wait_channel(self, end: float, *, reading: bool) -> None:
        assert self._socket is not None
        while True:
            self._inspect_channel()
            try:
                result = select.select(
                    [self._socket] if reading else [],
                    [] if reading else [self._socket],
                    [],
                    self._left(end),
                )
            except InterruptedError:
                continue
            self._inspect_channel()
            self._left(end)
            if result[0] if reading else result[1]:
                return

    def _request(self, packet: bytes, end: float) -> None:
        assert self._socket is not None
        while True:
            self._wait_channel(end, reading=False)
            try:
                count = self._socket.send(packet, self._dontwait)
            except (BlockingIOError, InterruptedError):
                continue
            if count != len(packet):
                raise LinuxScopeError("Linux scope partial original challenge refused")
            self._left(end)
            return

    def _handoff(self, nonce: bytes, end: float) -> None:
        assert self._socket is not None
        while True:
            self._wait_channel(end, reading=True)
            try:
                packet, ancillary, flags = _recvmsg(
                    self._socket, self._cmsg_cloexec | self._dontwait
                )
                break
            except (BlockingIOError, InterruptedError):
                continue
        credentials: list[tuple[int, int, int]] = []
        malformed = False
        # Collect every delivered right before refusing malformed ancillary data.
        for level, kind, data in ancillary:
            if level == socket.SOL_SOCKET and kind == _capability(socket, "SCM_RIGHTS"):
                integers = array.array("i")
                size = integers.itemsize
                malformed |= len(data) % size != 0
                integers.frombytes(data[: len(data) // size * size])
                self._held.extend(integers)
            elif (
                level == socket.SOL_SOCKET
                and kind == _capability(socket, "SCM_CREDENTIALS")
                and len(data) == 12
            ):
                credentials.append(struct.unpack("3i", data))
            else:
                malformed = True
        if (
            malformed
            or flags & ~self._cmsg_cloexec
            or len(packet) != 40
            or packet[:36] != b"HES1" + nonce
            or not 4 <= len(self._held) <= _MAX_FDS
            or struct.unpack("!I", packet[36:])[0] != len(self._held)
            or len(credentials) != 1
            or credentials[0][1:] != (self._uid, self._gid)
        ):
            raise LinuxScopeError("Linux scope handoff framing/rights/credentials refused")
        self._sender_pid = credentials[0][0]
        self._left(end)

    def _seal_handoff(self, end: float) -> None:
        assert self._socket is not None
        while True:
            self._wait_channel(end, reading=True)
            try:
                packet, ancillary, flags = _recvmsg(
                    self._socket, self._cmsg_cloexec | self._dontwait
                )
                break
            except (BlockingIOError, InterruptedError):
                continue
        for level, kind, data in ancillary:
            if level == socket.SOL_SOCKET and kind == _capability(socket, "SCM_RIGHTS"):
                integers = array.array("i")
                size = integers.itemsize
                integers.frombytes(data[: len(data) // size * size])
                self._held.extend(integers)
        # Linux UAPI POLLRDHUP distinguishes peer write-shutdown from an empty packet.
        poll = _capability(select, "poll")()
        poll.register(self._socket.fileno(), int(_capability(select, "POLLIN")) | 0x2000)
        observed = poll.poll(0)
        if (
            packet
            or ancillary
            or flags & ~self._cmsg_cloexec
            or len(observed) != 1
            or not observed[0][1] & 0x2000
            or observed[0][1]
            & (int(_capability(select, "POLLERR")) | int(_capability(select, "POLLNVAL")))
        ):
            raise LinuxScopeError("Linux scope handoff trailing packet or unsealed sender refused")
        self._left(end)

    def _query(self, fd: int, operation: int) -> int:
        result = int(_fcntl().ioctl(fd, operation))
        self._scratch.append(result)
        if os.get_inheritable(result):
            raise LinuxScopeError("Linux scope inheritable namespace query refused")
        return result

    def _own_namespace(self, name: str) -> int:
        result = os.open(f"/proc/self/ns/{name}", os.O_RDONLY | int(_capability(os, "O_CLOEXEC")))
        self._scratch.append(result)
        return result

    def _admit(self) -> None:
        init, namespace, user, *members = self._held
        fcntl = _fcntl()
        if any(os.get_inheritable(fd) for fd in self._held):
            raise LinuxScopeError("Linux scope inheritable received rights refused")
        if fcntl.ioctl(namespace, 0xB703) != 0x20000000 or fcntl.ioctl(user, 0xB703) != 0x10000000:
            raise LinuxScopeError("Linux scope namespace types refused")
        if (
            _identity(self._query(namespace, 0xB702)) != _identity(self._own_namespace("pid"))
            or _identity(self._query(namespace, 0xB701)) != _identity(user)
            or _identity(self._query(user, 0xB702)) != _identity(self._own_namespace("user"))
        ):
            raise LinuxScopeError("Linux scope direct original namespace relationships refused")
        owner = array.array("I", [0])
        if fcntl.ioctl(user, 0xB704, owner, True) != 0 or owner[0] != self._euid:
            raise LinuxScopeError("Linux scope original user namespace owner refused")
        init_ids = _pid_info(init)
        if len(init_ids) < 2 or init_ids[-1] != 1 or init_ids[0] != self._sender_pid:
            raise LinuxScopeError("Linux scope kernel sender is not original child namespace init")
        ids: set[int] = set()
        for fd in (init, *members):
            current = _pid_info(fd)
            if (
                current[0] <= 1
                or current[0] == os.getpid()
                or current[0] in ids
                or len(current) != len(init_ids)
                or (fd != init and current[-1] <= 1)
                or fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_EXCL
                or _identity(self._query(fd, 0xFF05)) != _identity(namespace)
                or _identity(self._query(fd, 0xFF09)) != _identity(user)
            ):
                raise LinuxScopeError("Linux scope original member identity/namespace refused")
            ids.add(current[0])
        if self._ready((init, *members), 0):
            raise LinuxScopeError("Linux scope original member exited during admission")

    def _inspect(self) -> None:
        self._inspect_channel()
        for fd, anchor, identity in zip(self._held, self._anchors, self._identities, strict=True):
            if (
                _identity(fd) != identity
                or _identity(anchor) != identity
                or os.get_inheritable(fd)
                or os.get_inheritable(anchor)
                or _fcntl().fcntl(fd, 1027, anchor) != 1
            ):
                raise LinuxScopeError("Linux scope original descriptor description substituted")

    @staticmethod
    def _ready(fds: tuple[int, ...], milliseconds: int) -> set[int]:
        poll = _capability(select, "poll")()
        pollin = int(_capability(select, "POLLIN"))
        errors = int(_capability(select, "POLLERR")) | int(_capability(select, "POLLNVAL"))
        for fd in fds:
            poll.register(fd, pollin)
        result: set[int] = set()
        for fd, mask in poll.poll(milliseconds):
            if mask & errors or not mask & pollin:
                raise LinuxScopeError("Linux scope original pidfd exit observation uncertain")
            result.add(fd)
        return result

    def _guard(self) -> None:
        self._creator_check()
        if self._failed or self._closed or not self._admitted:
            raise LinuxScopeError("Original Linux scope refused/closed; uncertainty retained")
        try:
            self._inspect()
        except (OSError, LinuxScopeError) as exc:
            self._failed = True
            raise LinuxScopeError(
                "Original Linux scope inspection uncertain; capabilities retained"
            ) from exc

    def require_live(self) -> None:
        self._guard()
        try:
            if self._ready((self._anchors[0], *self._anchors[3:]), 0):
                raise LinuxScopeError("Linux scope original admitted member is no longer live")
        except (OSError, LinuxScopeError) as exc:
            self._failed = True
            raise LinuxScopeError("Linux scope liveness uncertain; capabilities retained") from exc

    def require_preparation_ready(self, *, timeout_seconds: float = 5.0) -> None:
        """Check original PID1/stopped PID2 before copying; never release a worker.

        This is a point-in-time precondition, not a prepared-view or SDK grant.
        The trusted launch must hold PID2 stopped through preparation and perform
        the separate original namespace/root transition proof before execution.
        Refusal preserves the original scope's cancellation authority.
        """
        seconds = _seconds(timeout_seconds)
        if seconds > 30:
            raise LinuxScopeError("Preparation deadline exceeds thirty seconds")
        end = time.monotonic() + seconds
        self._guard()
        if len(tuple(Path("/proc/self/task").iterdir())) != 1:
            raise LinuxScopeError("Preparation requires a dedicated single-thread creator")
        if self._stopped or len(self._anchors) != 4:
            raise LinuxScopeError("Preparation requires exactly original PID1 and PID2")
        temporary: list[int] = []
        try:
            init, namespace, user, worker = self._anchors
            init_ids, worker_ids = _pid_info(init), _pid_info(worker)
            if (
                init_ids[-1] != 1
                or worker_ids[-1] != 2
                or len(init_ids) != len(worker_ids)
                or init_ids[0] != self._sender_pid
                or self._ready((init, worker), 0)
            ):
                raise LinuxScopeError("Preparation original process identities refused")
            mounts: list[tuple[int, int, int]] = []
            for member in (init, worker):
                self._left(end)
                for operation, expected in ((0xFF05, namespace), (0xFF09, user)):
                    observed = int(_fcntl().ioctl(member, operation))
                    temporary.append(observed)
                    if os.get_inheritable(observed) or _identity(observed) != _identity(expected):
                        raise LinuxScopeError("Preparation already transitioned original member")
                mount = int(_fcntl().ioctl(member, 0xFF03))
                temporary.append(mount)
                owner = int(_fcntl().ioctl(mount, 0xB701))
                temporary.append(owner)
                if (
                    os.get_inheritable(mount)
                    or os.get_inheritable(owner)
                    or _fcntl().ioctl(mount, 0xB703) != 0x20000
                    or _identity(owner) != _identity(user)
                ):
                    raise LinuxScopeError("Preparation original mount/user binding refused")
                mounts.append(_identity(mount))
            if mounts[0] != mounts[1]:
                raise LinuxScopeError("Preparation worker differs from original mount view")
            self._preparation_member(init, init_ids, parent=None, stopped=False)
            self._left(end)
            self._preparation_member(worker, worker_ids, parent=init_ids[0], stopped=True)
            self._inspect()
            if (
                _pid_info(init) != init_ids
                or _pid_info(worker) != worker_ids
                or self._ready((init, worker), 0)
            ):
                raise LinuxScopeError("Preparation original liveness changed during observation")
            self._left(end)
        except (OSError, ValueError, KeyError, struct.error) as exc:
            raise LinuxScopeError(
                "Preparation kernel evidence unavailable; worker not admitted"
            ) from exc
        finally:
            self._close_list(temporary)

    def _preparation_member(
        self, member: int, ids: tuple[int, ...], *, parent: int | None, stopped: bool
    ) -> None:
        # Version-zero PIDFD_GET_INFO: only kernel-filled PID/credential fields.
        info = bytearray(64)
        _fcntl().ioctl(member, 0xC040FF0B, info, True)
        fields = struct.unpack("=QQ12I", info)
        if (
            fields[0] & 3 != 3
            or fields[2] != ids[0]
            or fields[3] != ids[0]
            or (parent is not None and fields[4] != parent)
            or fields[5:13] != (self._uid, self._gid) * 4
        ):
            raise LinuxScopeError("Preparation original kernel lineage/credentials refused")
        directory = os.open(
            f"/proc/{ids[0]}",
            os.O_RDONLY
            | int(_capability(os, "O_DIRECTORY"))
            | int(_capability(os, "O_NOFOLLOW"))
            | int(_capability(os, "O_CLOEXEC")),
        )
        try:
            status_fd = os.open(
                "status",
                os.O_RDONLY
                | int(_capability(os, "O_NOFOLLOW"))
                | int(_capability(os, "O_CLOEXEC")),
                dir_fd=directory,
            )
            with os.fdopen(status_fd, "rb") as stream:
                raw = stream.read(65537)
            if len(raw) > 65536:
                raise LinuxScopeError("Preparation original kernel status exceeds bound")
            status: dict[str, str] = {}
            for line in raw.decode("ascii").splitlines():
                name, separator, value = line.partition(":")
                if not separator or name in status:
                    raise LinuxScopeError("Preparation original kernel status malformed")
                status[name] = value.strip()
            task = os.open(
                "task",
                os.O_RDONLY
                | int(_capability(os, "O_DIRECTORY"))
                | int(_capability(os, "O_NOFOLLOW"))
                | int(_capability(os, "O_CLOEXEC")),
                dir_fd=directory,
            )
            try:
                threads = os.listdir(task)
            finally:
                os.close(task)
            if (
                status["NoNewPrivs"] != "1"
                or status["Threads"] != "1"
                or threads != [str(ids[0])]
                or any(int(status[key], 16) for key in ("CapInh", "CapPrm", "CapEff", "CapAmb"))
                or int(status["TracerPid"]) != 0
                or (stopped and not status["State"].startswith("T ("))
                or tuple(int(item) for item in status["NSpid"].split()) != ids
            ):
                raise LinuxScopeError(
                    "Preparation requires original single-thread zero-cap stopped worker"
                )
        finally:
            os.close(directory)

    def stop(self, *, timeout_seconds: float = 5.0) -> None:
        seconds = _seconds(timeout_seconds)
        self._guard()
        if self._stopped:
            return
        end = time.monotonic() + seconds
        originals = (self._anchors[0], *self._anchors[3:])
        try:
            if not self._ready((originals[0],), 0):
                ctypes.set_errno(0)
                if self._signal(originals[0], int(_capability(signal, "SIGKILL")), None, 0) < 0:
                    code = ctypes.get_errno()
                    if code != errno.ESRCH or not self._ready((originals[0],), 0):
                        raise OSError(code, "Original Linux init pidfd signal refused")
            pending = set(originals)
            while pending:
                self._inspect()
                left = self._left(end)
                pending.difference_update(self._ready(tuple(pending), math.ceil(left * 1000)))
                self._inspect()
                self._left(end)
            self._stopped = True
        except (OSError, LinuxScopeError) as exc:
            self._failed = True
            raise LinuxScopeError(
                "Linux scope stop uncertain; original capabilities retained"
            ) from exc

    @staticmethod
    def _close_list(values: list[int]) -> None:
        failure: OSError | None = None
        for index, fd in enumerate(values):
            if fd >= 0:
                try:
                    os.close(fd)
                    values[index] = -1
                except OSError as exc:
                    failure = exc
        if failure is not None:
            raise failure

    def _cleanup_unadmitted(self) -> None:
        for values in (self._scratch, self._anchors, self._held):
            with suppress(OSError):
                self._close_list(values)
        if self._socket is not None:
            with suppress(OSError):
                self._socket.close()
        # _ACTIVE retains the uncertain object; no reset or retry is authorized.

    def close(self) -> None:
        global _ACTIVE
        self._creator_check()
        if self._closed:
            return
        self._guard()
        if not self._stopped:
            raise LinuxScopeError("Linux scope must observe original stop before releasing handles")
        try:
            for values in (self._scratch, self._held, self._anchors):
                self._close_list(values)
            assert self._socket is not None
            self._socket.close()
        except OSError as exc:
            self._failed = True
            raise LinuxScopeError(
                "Linux scope cleanup uncertain; original capabilities retained"
            ) from exc
        self._closed = True
        with _ADMISSION:
            if _ACTIVE is self:
                _ACTIVE = None
