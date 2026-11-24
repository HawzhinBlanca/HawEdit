"""Typed bounded copied-worker controller; not full SDK/model/ASR admission."""

from __future__ import annotations

import array
import math
import os
import select
import signal
import socket
import struct
import sys
import threading
import time
from dataclasses import dataclass

from hawedit.linux_rooted_worker import RootedCommand, execute_original_worker
from hawedit.linux_scope import _pid_info
from hawedit.linux_snapshot import (
    LinuxSnapshot,
    LinuxSnapshotError,
    SnapshotFile,
    SnapshotMode,
    _api,
    _apply_landlock,
    _flags,
    _status,
)
from hawedit.linux_thread_name import LinuxThreadNameBroker
from hawedit.linux_thread_registry import LinuxThreadRegistry, _Description

__all__ = ["RootedLaunch", "RootedResult"]


@dataclass(frozen=True)
class RootedResult:
    """Bounded combined stdout/stderr, not a validated producer response."""

    exit_code: int
    output: bytes
    exec_count: int
    observed_tids: tuple[int, ...]
    reaped_tids: tuple[int, ...]


class RootedLaunch:
    """Borrow only original held capabilities; external Scope must own preparation.

    Creates only original PID2; no namespace discovery or generic FD allowlist.
    Holds only its original task root for bounded comm service before final policy. Runtime
    and output ceilings are diagnostic only; no permission for model release.
    """

    _command: RootedCommand
    _pidfd: int
    _task: int
    _worker: socket.socket
    _view: socket.socket
    _limit: int
    _timeout: float
    _owner: tuple[int, int, threading.Thread]
    _started: bool
    _closed: bool

    def __init__(
        self,
        command: RootedCommand,
        view_channel: socket.socket,
        *,
        output_limit_bytes: int = 65536,
        timeout_seconds: float = 30,
    ) -> None:
        if (
            type(command) is not RootedCommand
            or type(view_channel) is not socket.socket
            or type(output_limit_bytes) is not int
            or not 0 < output_limit_bytes <= 65536
            or type(timeout_seconds) not in (int, float)
            or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= 30
        ):
            raise LinuxSnapshotError("Rooted controller declaration refused")
        if sys.platform != "linux" or os.getpid() != 1 or threading.get_native_id() != 1:
            raise LinuxSnapshotError(
                "Rooted controller including GPU requires original private PID1"
            )
        self._command = command
        self._view = view_channel
        self._limit = output_limit_bytes
        self._timeout = float(timeout_seconds)
        self._owner = (os.getpid(), threading.get_ident(), threading.current_thread())
        self._held: list[_Description] = []
        self._nonce: bytes | None = None
        self._started = self._closed = False
        self._result: RootedResult | None = None
        self._pending: RootedResult | None = None
        self._socket(view_channel)
        with open("/proc/1/task/1/children", "rb") as stream:
            if stream.read(257).strip():
                raise LinuxSnapshotError("Rooted controller requires no earlier child")
        parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        for channel in (parent, child):
            channel.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
            self._socket(channel)
        self._worker = parent
        self._pidfd = -1
        self._task = -1
        worker = os.fork()
        if worker == 0:
            parent.close()
            view_channel.close()
            null = os.open("/dev/null", os.O_RDWR | os.O_CLOEXEC)
            for fd in (0, 1, 2):
                os.dup2(null, fd)
            if null > 2:
                os.close(null)
            execute_original_worker(command, child)
        child.close()
        try:
            if worker != 2:
                raise LinuxSnapshotError("Rooted controller fork was not original PID2")
            self._pidfd = os.pidfd_open(worker)
            self._task = os.open(
                "/proc/2/task", _flags("O_RDONLY", "O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC")
            )
            for fd in (self._pidfd, parent.fileno(), view_channel.fileno(), self._task):
                self._held.append(_Description.hold(fd))
            packet, rights = self._worker_packet(5, 64, 0)
            if rights or len(packet) != 36 or packet[:4] != b"HEW1":
                raise LinuxSnapshotError("Rooted controller original worker challenge refused")
            self._nonce = packet[4:]
            end = time.monotonic() + 5
            while True:
                pid, status = os.waitpid(worker, os.WNOHANG | os.WUNTRACED)
                if pid:
                    if (
                        pid != 2
                        or not os.WIFSTOPPED(status)
                        or os.WSTOPSIG(status) != signal.SIGSTOP
                    ):
                        raise LinuxSnapshotError(
                            "Rooted controller original preparation stop refused"
                        )
                    break
                if time.monotonic() >= end:
                    raise LinuxSnapshotError(
                        "Rooted controller original preparation deadline expired"
                    )
                time.sleep(0.001)
        except BaseException:
            if self._pidfd >= 0:
                signal.pidfd_send_signal(self._pidfd, signal.SIGKILL)
                if not select.select([self._pidfd], [], [], 2)[0]:
                    raise LinuxSnapshotError("Rooted controller initial drain uncertain") from None
                os.waitpid(worker, 0)
                self._close_anchors()
            parent.close()
            if self._pidfd >= 0:
                os.close(self._pidfd)
            if self._task >= 0:
                os.close(self._task)
            raise

    @property
    def worker_pidfd(self) -> int:
        """Original held description for the external Scope's sealed admission."""
        self._context()
        return self._pidfd

    @property
    def result(self) -> RootedResult | None:
        return self._result

    def _context(self) -> None:
        if self._owner != (os.getpid(), threading.get_ident(), threading.current_thread()):
            raise LinuxSnapshotError("Rooted controller original owner differs")
        for held in self._held:
            held.inspect()

    @staticmethod
    def _socket(channel: socket.socket) -> None:
        if (
            channel.family != _api(socket, "AF_UNIX")
            or channel.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_SEQPACKET
            or channel.getsockname() != ""
            or channel.getpeername() != ""
            or not channel.getblocking()
            or os.get_inheritable(channel.fileno())
        ):
            raise LinuxSnapshotError("Rooted controller requires original unnamed channels")

    def _before_copy(
        self, files: tuple[SnapshotFile, ...], mode: SnapshotMode, entropy: bool, gpu: bool
    ) -> frozenset[int]:
        self._context()
        if (
            self._started
            or files != self._command.files
            or mode is not SnapshotMode.ROOTED_IMAGE
            or not entropy
            or gpu is not self._command.wsl_gpu
        ):
            raise LinuxSnapshotError("Rooted controller manifest/mode binding refused")
        if _pid_info(self._pidfd) != (2,) or select.select([self._pidfd], [], [], 0)[0]:
            raise LinuxSnapshotError("Rooted controller original worker differs/exited")
        with open("/proc/2/status", encoding="ascii") as stream:
            fields = dict(line.split(":", 1) for line in stream if ":" in line)
        if fields.get("PPid", "").strip() != "1" or not fields.get("State", "").strip().startswith(
            "T ("
        ):
            raise LinuxSnapshotError("Rooted controller original worker must be held")
        with open("/proc/1/task/1/children", "rb") as stream:
            children = stream.read(257).strip()
        if children != b"2":
            raise LinuxSnapshotError("Rooted controller requires only original PID2")
        if len({self._pidfd, self._worker.fileno(), self._view.fileno(), self._task}) != 4:
            raise LinuxSnapshotError("Rooted controller capabilities alias")
        if self._nonce is None or self._closed:
            raise LinuxSnapshotError("Rooted controller original preparation unavailable")
        self._started = True
        return frozenset(fd for held in self._held for fd in (held.fd, held.anchor, held.witness))

    def _worker_packet(
        self, seconds: float, size: int, expected_rights: int
    ) -> tuple[bytes, list[int]]:
        self._context()
        if not select.select([self._worker], [], [], max(0, seconds))[0]:
            raise LinuxSnapshotError("Rooted controller worker packet deadline expired")
        packet, ancillary, flags, _ = _api(self._worker, "recvmsg")(
            size,
            _api(socket, "CMSG_SPACE")(16) + _api(socket, "CMSG_SPACE")(12),
            int(_api(socket, "MSG_CMSG_CLOEXEC")),
        )
        rights: list[int] = []
        credentials: list[tuple[int, int, int]] = []
        malformed = False
        for level, kind, data in ancillary:
            if level == socket.SOL_SOCKET and kind == _api(socket, "SCM_RIGHTS"):
                values = array.array("i")
                malformed |= len(data) % values.itemsize != 0
                values.frombytes(data[: len(data) // values.itemsize * values.itemsize])
                rights.extend(values)
            elif (
                level == socket.SOL_SOCKET
                and kind == _api(socket, "SCM_CREDENTIALS")
                and len(data) == 12
            ):
                credentials.append(struct.unpack("3i", data))
            else:
                malformed = True
        if (
            malformed
            or flags & ~int(_api(socket, "MSG_CMSG_CLOEXEC"))
            or len(rights) != expected_rights
            or credentials != [(2, _api(os, "getuid")(), _api(os, "getgid")())]
        ):
            for fd in rights:
                os.close(fd)
            raise LinuxSnapshotError("Rooted controller worker framing/credentials refused")
        return packet, rights

    def _view_token(self, expected: bytes, end: float) -> None:
        self._context()
        if not select.select([self._view], [], [], min(5, max(0, end - time.monotonic())))[0]:
            raise LinuxSnapshotError("Rooted controller owner observation deadline expired")
        packet, ancillary, flags, _ = _api(self._view, "recvmsg")(
            65, _api(socket, "CMSG_SPACE")(16), int(_api(socket, "MSG_CMSG_CLOEXEC"))
        )
        if packet != expected or ancillary or flags & ~int(_api(socket, "MSG_CMSG_CLOEXEC")):
            for level, kind, data in ancillary:
                if level == socket.SOL_SOCKET and kind == _api(socket, "SCM_RIGHTS"):
                    values = array.array("i")
                    values.frombytes(data[: len(data) // values.itemsize * values.itemsize])
                    for fd in values:
                        os.close(fd)
            raise LinuxSnapshotError("Rooted controller original owner token refused")

    def _run(self, snapshot: LinuxSnapshot, preparation_end: float) -> None:
        self._context()
        if (
            type(snapshot) is not LinuxSnapshot
            or not self._started
            or self._nonce is None
            or self._closed
        ):
            raise LinuxSnapshotError("Rooted controller was not bound before preparation")
        root, native = snapshot._anchor, snapshot._native
        rights: list[int] = []
        listener = -1
        task = self._task
        registry = None
        broker = None
        output = bytearray()
        try:
            for name in ("user", "mnt"):
                rights.append(os.open("/proc/self/ns/" + name, _flags("O_RDONLY", "O_CLOEXEC")))
            rights.append(os.dup(root))
            _api(self._worker, "sendmsg")(
                [b"HEV1" + self._nonce],
                [(socket.SOL_SOCKET, int(_api(socket, "SCM_RIGHTS")), array.array("i", rights))],
            )
            self._worker.shutdown(socket.SHUT_WR)
            self._view_token_prefix(rights, preparation_end)
            self._view_token(b"J", preparation_end)
            packet, delivered = self._worker_packet(5, 1024, 1)
            listener = delivered[0]
            if packet != b"HEL1" + self._nonce:
                raise LinuxSnapshotError("Rooted controller worker listener refused")
            packet, _ = self._worker_packet(5, 64, 0)
            if packet != b"HER1" + self._nonce:
                raise LinuxSnapshotError("Rooted controller joined worker token refused")
            pid, status = os.waitpid(2, int(_api(os, "WUNTRACED")))
            if pid != 2 or not _api(os, "WIFSTOPPED")(status):
                raise LinuxSnapshotError("Rooted controller joined worker stop refused")
            self._view_token(b"R", preparation_end)
            snapshot._controller_fence()
            registry = LinuxThreadRegistry(self._pidfd, task, timeout_seconds=self._timeout)
            if int(_status()["Seccomp_filters"].strip()) != snapshot._filters + 1:
                raise LinuxSnapshotError("Rooted controller original registry filter uncertain")
            snapshot._filters += 1
            broker = LinuxThreadNameBroker(registry, listener, timeout_seconds=self._timeout)
            notifications = _api(select, "poll")()
            notifications.register(listener, int(_api(select, "POLLIN")))
            while not registry.drained:
                while registry.poll():
                    pass
                readable = select.select([self._worker], [], [], 0.001)[0]
                pending = notifications.poll(0)
                if not registry.drained and any(
                    mask & int(_api(select, "POLLIN")) for _, mask in pending
                ):
                    broker.serve_once()
                if self._worker in readable:
                    packet = self._worker.recv(self._limit + 1)
                    output.extend(packet)
                    if len(output) > self._limit:
                        raise LinuxSnapshotError("Rooted controller output byte bound exceeded")
            while select.select([self._worker], [], [], 0)[0]:
                packet = self._worker.recv(self._limit + 1)
                if not packet:
                    break
                output.extend(packet)
                if len(output) > self._limit:
                    raise LinuxSnapshotError("Rooted controller output byte bound exceeded")
            if registry.exec_count != 1 or registry.worker_exit is None:
                raise LinuxSnapshotError("Rooted controller actual exec/result uncertain")
            candidate = RootedResult(
                registry.worker_exit,
                bytes(output),
                registry.exec_count,
                registry.observed_tids,
                registry.reaped_tids,
            )
            broker.close()
            registry.close()
            broker = registry = None
            if self._command.wsl_gpu:
                snapshot._enforce_gpu_policy()
            else:
                _apply_landlock(native, root)
            self._pending = candidate
        except BaseException:
            self._result = None
            if registry is not None:
                registry.stop()
                if broker is not None:
                    broker.close()
                registry.close()
            else:
                _api(signal, "pidfd_send_signal")(self._pidfd, int(_api(signal, "SIGKILL")))
                if not select.select([self._pidfd], [], [], 2)[0]:
                    raise LinuxSnapshotError("Rooted controller pre-exec drain uncertain") from None
                os.waitpid(2, 0)
            raise
        finally:
            for fd in (*rights, listener):
                if fd >= 0:
                    os.close(fd)
            self._close_anchors()
            os.close(task)
            self._task = -1

    def _complete(self) -> None:
        if not self._closed or self._pending is None or self._result is not None:
            raise LinuxSnapshotError("Rooted controller final completion refused")
        self._result, self._pending = self._pending, None

    def _view_token_prefix(self, rights: list[int], end: float) -> None:
        self._context()
        if not select.select([self._view], [], [], max(0, end - time.monotonic()))[0]:
            raise LinuxSnapshotError("Rooted controller prepared challenge deadline expired")
        packet = self._view.recv(65)
        if len(packet) != 36 or packet[:4] != b"HEQ1":
            raise LinuxSnapshotError("Rooted controller prepared challenge refused")
        _api(self._view, "sendmsg")(
            [b"HEP1" + packet[4:]],
            [(socket.SOL_SOCKET, int(_api(socket, "SCM_RIGHTS")), array.array("i", rights))],
        )
        self._view.shutdown(socket.SHUT_WR)

    def _close_anchors(self) -> None:
        for held in self._held:
            if not held.close(borrowed=True):
                raise LinuxSnapshotError("Rooted controller original descriptions changed")
        self._held.clear()
        self._closed = True
