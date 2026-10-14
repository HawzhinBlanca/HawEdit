"""Original stopped-worker execution component, not a production/model release grant."""

from __future__ import annotations

import array
import codecs
import ctypes
import errno
import hashlib
import os
import re
import select
import signal
import socket
import stat
import struct
import sys
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from hawedit.linux_scope import _pid_info
from hawedit.linux_snapshot import (
    LinuxSnapshot,
    LinuxSnapshotError,
    SnapshotFile,
    SnapshotMode,
    _api,
    _apply_landlock,
    _drop_capabilities,
    _FenceRole,
    _flags,
    _identity,
    _install_namespace_fence,
    _name,
    _status,
)
from hawedit.linux_thread_registry import _Description, trace_original_worker

__all__ = ["RootedCommand", "execute_original_worker"]


@dataclass(frozen=True)
class RootedCommand:
    """Exact copied manifest, direct ELF argv and explicit environment; no shell dispatch."""

    files: tuple[SnapshotFile, ...]
    executable: str
    arguments: tuple[str, ...] = ()
    environment: tuple[tuple[str, str], ...] = ()
    wsl_gpu: bool = False

    def __post_init__(self) -> None:
        LinuxSnapshot._declarations(
            Path("/hawedit-rooted-command").absolute(),
            self.files,
            128 * 1024**3,
            4096,
            SnapshotMode.ROOTED_IMAGE,
            True,
            self.wsl_gpu,
        )
        if (
            not any(
                file.relative_path == _name(self.executable) and file.executable
                for file in self.files
            )
            or type(self.arguments) is not tuple
            or len(self.arguments) > 64
            or type(self.environment) is not tuple
            or len(self.environment) > 64
            or type(self.wsl_gpu) is not bool
        ):
            raise LinuxSnapshotError("Rooted command manifest/argv/environment refused")
        total = 0
        keys: set[str] = set()
        for argument in self.arguments:
            total += self._text(argument)
        for entry in self.environment:
            if type(entry) is not tuple or len(entry) != 2:
                raise LinuxSnapshotError("Rooted command environment pair refused")
            key, value = entry
            if (
                type(key) is not str
                or re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", key) is None
                or key in keys
            ):
                raise LinuxSnapshotError("Rooted command environment key refused")
            keys.add(key)
            total += self._text(key) + self._text(value)
        if total > 65536:
            raise LinuxSnapshotError("Rooted command configuration exceeds bound")

    @staticmethod
    def _text(value: str) -> int:
        if type(value) is not str or "\0" in value:
            raise LinuxSnapshotError("Rooted command text refused")
        try:
            size = len(value.encode("utf-8"))
        except UnicodeError as exc:
            raise LinuxSnapshotError("Rooted command text encoding refused") from exc
        if size > 4096:
            raise LinuxSnapshotError("Rooted command argument exceeds bound")
        return size


def _directory(name: str, parent: int | None = None) -> int:
    return os.open(
        name, _flags("O_RDONLY", "O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC"), dir_fd=parent
    )


def _filesystem(native: Any, fd: int, kind: int) -> None:
    # Native is the already-bound trusted libc, never a callback supplied to the entry.
    buffer = (ctypes.c_long * 32)()
    call = native.fstatfs
    call.argtypes = [ctypes.c_int, ctypes.c_void_p]
    call.restype = ctypes.c_int
    if call(fd, ctypes.byref(buffer)) != 0 or buffer[0] != kind:
        raise LinuxSnapshotError("Rooted worker genuine filesystem refused")


def _copied_executable(command: RootedCommand, root: int, end: float) -> int:
    chosen = -1
    try:
        for file in command.files:
            directory = os.dup(root)
            fd = -1
            try:
                parts = file.relative_path.split("/")
                for part in parts[:-1]:
                    next_fd = _directory(part, directory)
                    os.close(directory)
                    directory = next_fd
                fd = os.open(
                    parts[-1], _flags("O_RDONLY", "O_NOFOLLOW", "O_CLOEXEC"), dir_fd=directory
                )
                info = os.fstat(fd)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_nlink != 1
                    or info.st_size != file.size_bytes
                    or info.st_uid != int(_api(os, "getuid")())
                    or stat.S_IMODE(info.st_mode) != (0o500 if file.executable else 0o400)
                ):
                    raise LinuxSnapshotError("Rooted worker copied file metadata refused")
                digest = hashlib.sha256()
                offset = 0
                prefix = b""
                while offset < file.size_bytes:
                    LinuxSnapshot._left(end)
                    data = _api(os, "pread")(fd, min(1048576, file.size_bytes - offset), offset)
                    if not data:
                        raise LinuxSnapshotError("Rooted worker copied file truncated")
                    if offset == 0:
                        prefix = data[:4]
                    digest.update(data)
                    offset += len(data)
                if digest.hexdigest() != file.sha256:
                    raise LinuxSnapshotError("Rooted worker copied file hash differs")
                if file.relative_path == command.executable:
                    if prefix != b"\x7fELF":
                        raise LinuxSnapshotError("Rooted worker requires a copied ELF executable")
                    chosen, fd = fd, -1
            finally:
                if fd >= 0:
                    os.close(fd)
                os.close(directory)
        if chosen < 0:
            raise LinuxSnapshotError("Rooted worker copied executable absent")
        return chosen
    except BaseException:
        if chosen >= 0:
            os.close(chosen)
        raise


def execute_original_worker(command: RootedCommand, channel: socket.socket) -> NoReturn:
    """Trusted fork-child entry only. Fence then exec, or exit; never return a worker."""
    if sys.platform != "linux" or os.getpid() != 2 or os.getppid() != 1:
        raise LinuxSnapshotError("Rooted entry must never run in a host/controller process")
    try:
        _execute(command, channel)
    except BaseException as exc:
        with suppress(BaseException):
            channel.send(b"HEF1" + str(exc).encode("utf-8", "replace")[:512])
        os._exit(74)


def _execute(command: RootedCommand, channel: socket.socket) -> NoReturn:
    if (
        sys.platform != "linux"
        or os.uname().machine != "x86_64"
        or type(command) is not RootedCommand
        or type(channel) is not socket.socket
        or os.getpid() != 2
        or os.getppid() != 1
        or threading.get_native_id() != 2
        or len(tuple(Path("/proc/self/task").iterdir())) != 1
    ):
        raise LinuxSnapshotError("Rooted worker requires original private single-thread PID2")
    native = LinuxSnapshot._libc()
    codecs.lookup("ascii")
    codecs.lookup("utf-8")
    native.setns.argtypes = [ctypes.c_int, ctypes.c_int]
    native.setns.restype = ctypes.c_int
    fields = _status()
    if (
        fields.get("NoNewPrivs", "").strip() != "1"
        or fields.get("TracerPid", "").strip() != "0"
        or any(int(fields[key].strip(), 16) for key in ("CapInh", "CapPrm", "CapEff", "CapAmb"))
    ):
        raise LinuxSnapshotError("Rooted worker initial capability/NNP/trace boundary refused")
    if any(
        name.split(".")[0] in ("torch", "transformers", "omnilingual_asr") for name in sys.modules
    ):
        raise LinuxSnapshotError("Rooted worker bootstrap already imported a model SDK")
    if (
        channel.family != socket.AF_UNIX
        or channel.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_SEQPACKET
        or channel.getsockname() != ""
        or channel.getpeername() != ""
        or not channel.getblocking()
        or os.get_inheritable(channel.fileno())
        or channel.getsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED) != 1
        or struct.unpack("3i", channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        != (1, os.getuid(), os.getgid())
    ):
        raise LinuxSnapshotError("Rooted worker original unnamed channel refused")
    for fd in (0, 1, 2):
        info = os.fstat(fd)
        if not stat.S_ISCHR(info.st_mode) or info.st_rdev != os.makedev(1, 3):
            raise LinuxSnapshotError("Rooted worker initial standard stream is not null")
    parent = os.pidfd_open(1)
    original_user = os.open("/proc/self/ns/user", _flags("O_RDONLY", "O_CLOEXEC"))
    original_pid = os.open("/proc/self/ns/pid", _flags("O_RDONLY", "O_CLOEXEC"))
    original_root = _directory("/")
    parent_task = _directory("/proc/1")
    uid, gid = os.getuid(), os.getgid()
    owned = [
        _Description.hold(fd)
        for fd in (
            parent,
            original_user,
            original_pid,
            original_root,
            parent_task,
            channel.fileno(),
        )
    ]
    if _pid_info(parent) != (1,):
        raise LinuxSnapshotError("Rooted worker original parent differs")
    nonce = os.urandom(32)
    channel.send(b"HEW1" + nonce)
    os.kill(2, signal.SIGSTOP)
    end = time.monotonic() + 30
    if not select.select([channel, parent], [], [], 5)[0] or select.select([parent], [], [], 0)[0]:
        raise LinuxSnapshotError("Rooted worker prepared handoff deadline/parent refused")
    packet, ancillary, flags, _ = channel.recvmsg(
        37, socket.CMSG_SPACE(16) + socket.CMSG_SPACE(12), socket.MSG_CMSG_CLOEXEC
    )
    rights: list[int] = []
    credentials: list[tuple[int, int, int]] = []
    malformed = False
    for level, kind, data in ancillary:
        if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
            values = array.array("i")
            malformed |= len(data) % values.itemsize != 0
            values.frombytes(data[: len(data) // values.itemsize * values.itemsize])
            rights.extend(values)
        elif level == socket.SOL_SOCKET and kind == socket.SCM_CREDENTIALS and len(data) == 12:
            credentials.append(struct.unpack("3i", data))
        else:
            malformed = True
    if (
        packet != b"HEV1" + nonce
        or len(rights) != 3
        or credentials != [(1, uid, gid)]
        or malformed
        or flags & ~socket.MSG_CMSG_CLOEXEC
    ):
        raise LinuxSnapshotError("Rooted worker original framing/rights/credentials refused")
    owned.extend(_Description.hold(fd) for fd in rights)
    if not select.select([channel, parent], [], [], 5)[0]:
        raise LinuxSnapshotError("Rooted worker original handoff was not sealed")
    tail, extra, tail_flags, _ = channel.recvmsg(
        1, socket.CMSG_SPACE(16) + socket.CMSG_SPACE(12), socket.MSG_CMSG_CLOEXEC
    )
    if tail or extra or tail_flags & ~socket.MSG_CMSG_CLOEXEC:
        raise LinuxSnapshotError("Rooted worker trailing prepared handoff refused")
    user, mount, root = rights
    import fcntl

    temporary: list[int] = []

    def query(fd: int, operation: int) -> int:
        current = int(fcntl.ioctl(fd, operation))
        temporary.append(current)
        return current

    for item in owned:
        item.inspect()
    if (
        fcntl.ioctl(user, 0xB703) != 0x10000000
        or fcntl.ioctl(mount, 0xB703) != 0x20000
        or _identity(query(user, 0xB702)) != _identity(original_user)
        or _identity(query(mount, 0xB701)) != _identity(user)
        or _identity(query(parent, 0xFF09)) != _identity(user)
        or _identity(query(parent, 0xFF03)) != _identity(mount)
        or _identity(query(parent, 0xFF05)) != _identity(original_pid)
    ):
        raise LinuxSnapshotError("Rooted worker original prepared namespace binding refused")
    owner = array.array("I", [0])
    if fcntl.ioctl(user, 0xB704, owner, True) != 0 or owner[0] != uid:
        raise LinuxSnapshotError("Rooted worker private user owner differs")
    for leaf in ("root", "cwd"):
        observed = os.open(leaf, _flags("O_RDONLY", "O_DIRECTORY", "O_CLOEXEC"), dir_fd=parent_task)
        temporary.append(observed)
        if _identity(observed) != _identity(root):
            raise LinuxSnapshotError("Rooted worker original PID1 root/cwd differs")
    _filesystem(native, root, 0x01021994)
    if (
        _identity(root) == _identity(original_root)
        or os.fstat(root).st_uid != uid
        or os.fstatvfs(root).f_flag & 7 != 7
    ):
        raise LinuxSnapshotError("Rooted worker root is not private sealed tmpfs")
    proc = _directory("proc", root)
    temporary.append(proc)
    _filesystem(native, proc, 0x9FA0)
    if os.fstatvfs(proc).f_flag & 15 != 15:
        raise LinuxSnapshotError("Rooted worker proc is not genuine readonly/noexec")
    for label, expected in (("pid", original_pid), ("user", user)):
        current = os.open("1/ns/" + label, _flags("O_RDONLY", "O_CLOEXEC"), dir_fd=proc)
        temporary.append(current)
        if _identity(current) != _identity(expected):
            raise LinuxSnapshotError("Rooted worker proc namespace differs")
    for item in owned:
        item.inspect()
    if _pid_info(parent) != (1,) or select.select([parent], [], [], 0)[0]:
        raise LinuxSnapshotError("Rooted worker original parent no longer live")
    if native.setns(user, 0x10000000) != 0 or native.setns(mount, 0x20000) != 0:
        raise OSError(ctypes.get_errno(), "Rooted worker exact private join refused")
    os.fchdir(root)
    os.chroot(".")
    os.chdir("/")
    if _identity(root) != _identity(os.open("/", _flags("O_RDONLY", "O_DIRECTORY", "O_CLOEXEC"))):
        raise LinuxSnapshotError("Rooted worker root entry differs")
    executable = _copied_executable(command, root, end)
    gpu = None
    if command.wsl_gpu:
        gpu = os.open("/dev/dxg", _flags("O_PATH", "O_NOFOLLOW", "O_CLOEXEC"))
        info = os.fstat(gpu)
        if (
            not stat.S_ISCHR(info.st_mode)
            or info.st_rdev != os.makedev(10, 258)
            or info.st_nlink != 1
            or os.statvfs("/dev/dxg").f_flag & os.ST_NODEV
            or os.statvfs("/dev/dxg").f_flag & (os.ST_RDONLY | os.ST_NOSUID | os.ST_NOEXEC)
            != os.ST_RDONLY | os.ST_NOSUID | os.ST_NOEXEC
        ):
            raise LinuxSnapshotError("Rooted worker genuine GPU endpoint refused")
    for fd in temporary:
        os.close(fd)
    _drop_capabilities(native)
    _apply_landlock(native, root, gpu)
    try:
        opened = os.open("/dev/urandom", os.O_RDWR | os.O_CLOEXEC)
    except OSError as exc:
        if exc.errno != errno.EACCES:
            raise LinuxSnapshotError("Rooted worker Landlock refusal uncertain") from exc
    else:
        os.close(opened)
        raise LinuxSnapshotError("Rooted worker Landlock allowed entropy write")
    for item in owned:
        item.inspect()
    kept = {0, 1, 2, channel.fileno(), executable}
    for name in os.listdir("/proc/self/fd"):
        fd = int(name)
        if fd not in kept:
            try:
                os.close(fd)
            except OSError as exc:
                if exc.errno != errno.EBADF:
                    raise
    _, listener = _install_namespace_fence(
        native, entropy=True, gpu=command.wsl_gpu, role=_FenceRole.WORKER
    )
    assert listener is not None
    channel.sendmsg(
        [b"HEL1" + nonce], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [listener]))]
    )
    os.close(listener)
    channel.send(b"HER1" + nonce)
    os.kill(2, signal.SIGSTOP)
    trace_original_worker()
    for fd in (1, 2):
        os.dup2(channel.fileno(), fd, inheritable=True)
    channel.close()
    os.execve(executable, ["/" + command.executable, *command.arguments], dict(command.environment))
