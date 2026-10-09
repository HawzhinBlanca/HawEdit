"""Owned read-only consumed bytes, not producer or general sandbox admission."""

from __future__ import annotations

import ctypes
import errno
import hashlib
import math
import os
import platform
import re
import stat
import sys
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

__all__ = ["LinuxSnapshot", "LinuxSnapshotError", "SnapshotFile"]

_ATTEMPTED = False
_CAPS = ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")
_CHUNK = 1024**2


class LinuxSnapshotError(RuntimeError):
    """Byte custody uncertain; drain the original process scope, never retry it."""


def _seconds(value: float) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 43200:
        raise LinuxSnapshotError("Snapshot deadline must be finite, positive and bounded")
    return float(value)


def _name(value: str) -> str:
    if (
        type(value) is not str
        or not value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
        or "\\" in value
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise LinuxSnapshotError("Snapshot name must be a normalized relative POSIX path")
    try:
        if len(value.encode("utf-8")) > 4096 or any(
            len(part.encode("utf-8")) > 255 for part in value.split("/")
        ):
            raise LinuxSnapshotError("Snapshot name exceeds path bounds")
    except UnicodeError as exc:
        raise LinuxSnapshotError("Snapshot name encoding refused") from exc
    return value


@dataclass(frozen=True)
class SnapshotFile:
    """Declared source bytes; declarations alone never authorize consumption."""

    source: Path
    relative_path: str
    sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        _name(self.relative_path)
        if (
            not isinstance(self.source, Path)
            or not self.source.is_absolute()
            or any(part in (".", "..") for part in self.source.parts)
            or type(self.sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", self.sha256) is None
            or type(self.size_bytes) is not int
            or not 0 <= self.size_bytes <= 32 * 1024**3
        ):
            raise LinuxSnapshotError("Snapshot source path/hash/size declaration invalid")


def _identity(fd: int) -> tuple[int, int, int]:
    info = os.fstat(fd)
    return info.st_dev, info.st_ino, info.st_mode


def _api(module: object, name: str) -> Any:
    value = getattr(module, name, None)
    if value is None:
        raise LinuxSnapshotError(f"Snapshot kernel capability unavailable: {name}")
    return value


def _fcntl() -> Any:
    import fcntl

    return fcntl


def _flags(*names: str) -> int:
    value = 0
    for name in names:
        value |= int(_api(os, name))
    return value


def _status() -> dict[str, str]:
    with Path("/proc/self/status").open() as stream:
        text = stream.read(65537)
    if len(text) > 65536:
        raise LinuxSnapshotError("Snapshot kernel status exceeds bound")
    return dict(line.split(":", 1) for line in text.splitlines() if ":" in line)


def _zero_caps(status: dict[str, str]) -> bool:
    return all(int(status[key].strip(), 16) == 0 for key in _CAPS)


def _directory(path: Path) -> int:
    """Walk original directory descriptions; do not follow user path symlinks."""
    flags = _flags("O_RDONLY", "O_DIRECTORY", "O_CLOEXEC", "O_NOFOLLOW")
    fd = os.open("/", flags)
    try:
        for part in path.parts[1:]:
            if part in (".", ".."):
                raise LinuxSnapshotError("Snapshot directory traversal refused")
            next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


class LinuxSnapshot:
    """One irreversible preparation in a dedicated PID1, before model release.

    Caller must own/drain the original LinuxScope and provide the complete byte
    closure. The byte budget is NOT an RSS/cgroup/VRAM limit. Deadline checks do
    not replace the external scope's bounded cancellation of stalled syscalls.
    Returned paths are original root-description anchored, never source-backed.
    Closing only invalidates descriptors; process exit releases its mount.
    """

    _native: Any
    _known: dict[int, tuple[int, int, int]]
    _namespaces: dict[str, tuple[int, int]]
    _creator: tuple[int, int]
    _thread: threading.Thread
    _root_fd: int
    _anchor: int
    _closed: bool
    _failed: bool
    _filters: int
    _names: frozenset[str]

    def __init__(
        self,
        root: Path,
        files: tuple[SnapshotFile, ...],
        *,
        max_bytes: int = 1024**3,
        max_files: int = 4096,
        timeout_seconds: float = 30.0,
    ) -> None:
        global _ATTEMPTED
        end = time.monotonic() + _seconds(timeout_seconds)
        if sys.platform != "linux":
            raise LinuxSnapshotError("Owned snapshots require a dedicated Linux PID1")
        if (
            os.getpid() != 1
            or len(tuple(Path("/proc/self/task").iterdir())) != 1
            or platform.machine() != "x86_64"
            or _ATTEMPTED
        ):
            raise LinuxSnapshotError("Snapshot requires a fresh dedicated single-thread Linux PID1")
        status = _status()
        if status.get("NoNewPrivs", "").strip() != "1" or any(
            int(status[key].strip(), 16) != 0 for key in _CAPS if key != "CapBnd"
        ):
            raise LinuxSnapshotError(
                "Snapshot initial no-new-privileges/zero capabilities required"
            )
        names = self._declarations(root, files, max_bytes, max_files)
        self._root = root
        self._names = frozenset(names)
        self._creator = (os.getpid(), threading.get_ident())
        self._thread = threading.current_thread()
        self._root_fd = self._anchor = -1
        self._known = {}
        self._namespaces = {}
        self._closed = self._failed = False
        self._filters = 0
        self._native = self._libc()
        before = -1
        try:
            before = _directory(root)
            info = os.fstat(before)
            if (
                info.st_uid != int(_api(os, "getuid")())
                or stat.S_IMODE(info.st_mode) != 0o700
                or os.listdir(before)
            ):
                raise LinuxSnapshotError("Snapshot root must be an empty private owned directory")
            _ATTEMPTED = True
            self._initialize(end)
            self._mount(
                b"tmpfs",
                os.fsencode(root),
                b"tmpfs",
                2 | 4,
                f"size={max_bytes + (max_files * 16 + 16) * 4096},mode=0700".encode(),
            )
            self._root_fd = _directory(root)
            if _identity(before) == _identity(self._root_fd):
                raise LinuxSnapshotError("Snapshot private mount did not replace the backing root")
            self._remember(self._root_fd)
            self._anchor = os.dup(self._root_fd)
            self._remember(self._anchor)
            for item in files:
                self._copy(item, end)
            # A live writer makes remount fail. Never keep any copied write FD.
            self._mount(None, os.fsencode(root), None, 32 | 1 | 2 | 4)
            self._drop_caps()
            self._fence()
            for label in ("user", "mnt", "pid"):
                fd = os.open(f"/proc/self/ns/{label}", _flags("O_RDONLY", "O_CLOEXEC"))
                self._remember(fd)
                self._namespaces[label] = (fd, os.dup(fd))
                self._remember(self._namespaces[label][1])
            self._inspect(end)
        except BaseException as exc:
            self._failed = True
            self._cleanup()
            if not isinstance(exc, Exception):
                raise
            raise LinuxSnapshotError(
                "Snapshot byte/namespace admission refused; exit and drain original scope"
            ) from exc
        finally:
            if before >= 0:
                os.close(before)

    @staticmethod
    def _declarations(
        root: Path, files: tuple[SnapshotFile, ...], max_bytes: int, max_files: int
    ) -> set[str]:
        if (
            not isinstance(root, Path)
            or not root.is_absolute()
            or root == Path("/")
            or ".." in root.parts
            or type(files) is not tuple
            or type(max_bytes) is not int
            or not 0 < max_bytes <= 32 * 1024**3
            or type(max_files) is not int
            or not 0 < max_files <= 100000
            or not 1 <= len(files) <= max_files
            or any(type(item) is not SnapshotFile for item in files)
        ):
            raise LinuxSnapshotError("Snapshot root/file/count/byte bounds invalid")
        names: set[str] = set()
        directories: set[str] = set()
        total = 0
        for item in files:
            name = _name(item.relative_path)
            parts = name.split("/")
            ancestors = {"/".join(parts[:count]) for count in range(1, len(parts))}
            if name in names or name in directories or names & ancestors:
                raise LinuxSnapshotError("Snapshot duplicate or file/directory collision refused")
            names.add(name)
            directories.update(ancestors)
            total += item.size_bytes
            if total > max_bytes:
                raise LinuxSnapshotError("Snapshot declared bytes exceed capacity")
        return names

    @staticmethod
    def _libc() -> Any:
        native = ctypes.CDLL(None, use_errno=True)
        native.unshare.argtypes = [ctypes.c_int]
        native.unshare.restype = ctypes.c_int
        native.mount.argtypes = [
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_ulong,
            ctypes.c_void_p,
        ]
        native.mount.restype = ctypes.c_int
        native.prctl.argtypes = [ctypes.c_int, *([ctypes.c_ulong] * 4)]
        native.prctl.restype = ctypes.c_int
        return native

    @staticmethod
    def _left(end: float) -> None:
        if time.monotonic() >= end:
            raise LinuxSnapshotError("Snapshot original deadline exceeded")

    def _remember(self, fd: int) -> None:
        self._known[fd] = _identity(fd)

    def _initialize(self, end: float) -> None:
        self._left(end)
        uid, gid = int(_api(os, "getuid")()), int(_api(os, "getgid")())
        if self._native.unshare(0x10000000 | 0x00020000) != 0:
            raise OSError(ctypes.get_errno(), "Snapshot private user/mount initialization")
        Path("/proc/self/setgroups").write_text("deny", encoding="ascii")
        Path("/proc/self/uid_map").write_text(f"{uid} {uid} 1", encoding="ascii")
        Path("/proc/self/gid_map").write_text(f"{gid} {gid} 1", encoding="ascii")
        if (
            int(_api(os, "getuid")()) != uid
            or int(_api(os, "getgid")()) != gid
            or self._native.prctl(39, 0, 0, 0, 0) != 1
        ):
            raise LinuxSnapshotError("Snapshot initializer identity/privilege policy changed")
        # Do not propagate any mount operation back to the creator namespace.
        self._mount(None, b"/", None, (1 << 18) | (1 << 14))

    def _mount(
        self,
        source: bytes | None,
        target: bytes,
        kind: bytes | None,
        flags: int,
        data: bytes | None = None,
    ) -> None:
        if self._native.mount(source, target, kind, flags, data) != 0:
            raise OSError(ctypes.get_errno(), "Snapshot private mount refused")

    def _copy(self, item: SnapshotFile, end: float) -> None:
        self._left(end)
        parent = _directory(item.source.parent)
        try:
            source = os.open(
                item.source.name,
                _flags("O_RDONLY", "O_CLOEXEC", "O_NOFOLLOW", "O_NONBLOCK"),
                dir_fd=parent,
            )
        finally:
            os.close(parent)
        destination = directory = -1
        try:
            info = os.fstat(source)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_size != item.size_bytes
            ):
                raise LinuxSnapshotError("Snapshot source must be regular, single-link, exact size")
            directory = os.dup(self._anchor)
            parts = item.relative_path.split("/")
            for part in parts[:-1]:
                self._left(end)
                with suppress(FileExistsError):
                    os.mkdir(part, 0o700, dir_fd=directory)
                next_fd = os.open(
                    part,
                    _flags("O_RDONLY", "O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC"),
                    dir_fd=directory,
                )
                os.close(directory)
                directory = next_fd
            destination = os.open(
                parts[-1],
                _flags("O_WRONLY", "O_CREAT", "O_EXCL", "O_CLOEXEC", "O_NOFOLLOW"),
                0o400,
                dir_fd=directory,
            )
            digest = hashlib.sha256()
            copied = 0
            while copied < item.size_bytes:
                self._left(end)
                data = os.read(source, min(_CHUNK, item.size_bytes - copied))
                if not data:
                    raise LinuxSnapshotError("Snapshot source truncated during copy")
                digest.update(data)
                offset = 0
                while offset < len(data):
                    self._left(end)
                    written = os.write(destination, data[offset:])
                    if written <= 0:
                        raise LinuxSnapshotError("Snapshot copy write did not advance")
                    offset += written
                copied += len(data)
            after = os.fstat(source)
            if (
                os.read(source, 1)
                or digest.hexdigest() != item.sha256
                or after.st_size != item.size_bytes
                or after.st_nlink != 1
                or (after.st_dev, after.st_ino) != (info.st_dev, info.st_ino)
            ):
                raise LinuxSnapshotError("Snapshot consumed source bytes/hash/size refused")
            os.fsync(destination)
            if _identity(source)[:2] == _identity(destination)[:2]:
                raise LinuxSnapshotError("Snapshot did not acquire independent byte ownership")
            self._left(end)
        finally:
            for fd in (destination, directory, source):
                if fd >= 0:
                    os.close(fd)

    def _drop_caps(self) -> None:
        last = int(Path("/proc/sys/kernel/cap_last_cap").read_text(encoding="ascii"))
        if not 0 <= last <= 63:
            raise LinuxSnapshotError("Snapshot capability ABI exceeds supported bound")
        for number in range(last + 1):
            if self._native.prctl(24, number, 0, 0, 0) != 0:
                raise OSError(ctypes.get_errno(), "Snapshot bounding capability drop")

        class Header(ctypes.Structure):
            _fields_: ClassVar[Any] = [("version", ctypes.c_uint32), ("pid", ctypes.c_int)]

        class Data(ctypes.Structure):
            _fields_: ClassVar[Any] = [
                ("effective", ctypes.c_uint32),
                ("permitted", ctypes.c_uint32),
                ("inheritable", ctypes.c_uint32),
            ]

        capset = self._native.capset
        capset.argtypes = [ctypes.POINTER(Header), ctypes.POINTER(Data)]
        capset.restype = ctypes.c_int
        if capset(ctypes.byref(Header(0x20080522, 0)), (Data * 2)()) != 0:
            raise OSError(ctypes.get_errno(), "Snapshot effective/permitted capability drop")
        if not _zero_caps(_status()):
            raise LinuxSnapshotError("Snapshot capabilities remain after drop")

    def _fence(self) -> None:
        class Filter(ctypes.Structure):
            _fields_: ClassVar[Any] = [
                ("code", ctypes.c_ushort),
                ("jt", ctypes.c_ubyte),
                ("jf", ctypes.c_ubyte),
                ("k", ctypes.c_uint32),
            ]

        class Program(ctypes.Structure):
            _fields_: ClassVar[Any] = [("len", ctypes.c_ushort), ("filter", ctypes.POINTER(Filter))]

        # x86_64 only; deny x32, namespace/mount entry, and namespace clone flags.
        instructions = [
            (0x20, 0, 0, 4),
            (0x15, 1, 0, 0xC000003E),
            (0x06, 0, 0, 0x80000000),
            (0x20, 0, 0, 0),
            (0x35, 0, 1, 0x40000000),
            (0x06, 0, 0, 0x50000 | errno.ENOSYS),
        ]
        for number in (272, 308, 165, 166, 155, 161, 428, 429, 430, 431, 432, 433, 442, 435):
            instructions.extend(
                [
                    (0x15, 0, 1, number),
                    (0x06, 0, 0, 0x50000 | (errno.ENOSYS if number == 435 else errno.EPERM)),
                ]
            )
        instructions.extend(
            [
                (0x15, 0, 3, 56),
                (0x20, 0, 0, 16),
                (0x45, 0, 1, 0x7E020000),
                (0x06, 0, 0, 0x50000 | errno.EPERM),
                (0x06, 0, 0, 0x7FFF0000),
            ]
        )
        array = (Filter * len(instructions))(*(Filter(*item) for item in instructions))
        program = Program(len(instructions), array)
        prior = int(_status()["Seccomp_filters"].strip())
        if self._native.prctl(22, 2, ctypes.addressof(program), 0, 0) != 0:
            raise OSError(ctypes.get_errno(), "Snapshot namespace reentry fence refused")
        self._filters = prior + 1

    def _owner(self) -> None:
        if (
            self._creator != (os.getpid(), threading.get_ident())
            or self._thread is not threading.current_thread()
        ):
            raise LinuxSnapshotError("Snapshot original process/thread owner differs")

    def _inspect(self, end: float) -> None:
        self._owner()
        if self._closed or self._failed:
            raise LinuxSnapshotError("Snapshot is closed/refused; original scope drain required")
        self._left(end)
        try:
            for fd, expected in self._known.items():
                if _identity(fd) != expected or os.get_inheritable(fd):
                    raise LinuxSnapshotError("Snapshot original descriptor substituted")
            pairs = [(self._root_fd, self._anchor), *self._namespaces.values()]
            for fd, anchor in pairs:
                if _fcntl().fcntl(fd, 1027, anchor) != 1:
                    raise LinuxSnapshotError("Snapshot original description substituted")
            for label, (fd, _) in self._namespaces.items():
                current = os.stat(f"/proc/self/ns/{label}")
                if (current.st_dev, current.st_ino, current.st_mode) != _identity(fd):
                    raise LinuxSnapshotError("Snapshot original namespace changed")
            if not int(_api(os, "fstatvfs")(self._anchor).f_flag) & int(_api(os, "ST_RDONLY")):
                raise LinuxSnapshotError("Snapshot original root is not read-only")
            status = _status()
            if (
                not _zero_caps(status)
                or status.get("NoNewPrivs", "").strip() != "1"
                or status.get("Seccomp", "").strip() != "2"
                or int(status["Seccomp_filters"].strip()) != self._filters
            ):
                raise LinuxSnapshotError("Snapshot original privilege/fence state changed")
            self._left(end)
        except (OSError, ValueError, KeyError, LinuxSnapshotError) as exc:
            self._failed = True
            raise LinuxSnapshotError("Snapshot original byte/namespace custody uncertain") from exc

    def verify(self, *, timeout_seconds: float = 5.0) -> None:
        """Inspect live original custody; metadata cannot recreate a snapshot."""
        self._inspect(time.monotonic() + _seconds(timeout_seconds))

    def path(self, relative_path: str) -> Path:
        """Only declared copied bytes, rooted at the original live description."""
        self.verify()
        if _name(relative_path) not in self._names:
            raise LinuxSnapshotError("Snapshot file was not admitted")
        return Path(f"/proc/self/fd/{self._anchor}") / relative_path

    def _cleanup(self) -> None:
        uncertain: set[int] = set()
        for first, anchor in [(self._root_fd, self._anchor), *self._namespaces.values()]:
            if first >= 0 and anchor >= 0:
                try:
                    if _fcntl().fcntl(first, 1027, anchor) != 1:
                        uncertain.update((first, anchor))
                except OSError:
                    uncertain.update((first, anchor))
        for fd, expected in tuple(self._known.items()):
            try:
                if fd not in uncertain and _identity(fd) == expected:
                    os.close(fd)
            except OSError:
                pass
            del self._known[fd]

    def close(self) -> None:
        """Invalidate owned descriptors only; never claim process/GPU drain."""
        self._owner()
        if not self._closed:
            self._closed = True
            self._cleanup()
            self._root_fd = self._anchor = -1
