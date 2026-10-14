"""Owned read-only consumed bytes, not producer or general sandbox admission."""

from __future__ import annotations

import ctypes
import errno
import hashlib
import math
import os
import platform
import re
import socket
import stat
import sys
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from hawedit.linux_rooted_launch import RootedLaunch

__all__ = ["LinuxSnapshot", "LinuxSnapshotError", "SnapshotFile", "SnapshotMode"]

_ATTEMPTED = False
_CAPS = ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")
_CHUNK = 1024**2


class LinuxSnapshotError(RuntimeError):
    """Byte custody uncertain; drain the original process scope, never retry it."""


class SnapshotMode(str, Enum):
    DATA_ONLY = "data_only"
    ROOTED_IMAGE = "rooted_image"


# Prepare ctypes layouts before a rooted transition removes ambient imports.
class _CapHeader(ctypes.Structure):
    _fields_: ClassVar[Any] = [("version", ctypes.c_uint32), ("pid", ctypes.c_int)]


class _CapData(ctypes.Structure):
    _fields_: ClassVar[Any] = [
        ("effective", ctypes.c_uint32),
        ("permitted", ctypes.c_uint32),
        ("inheritable", ctypes.c_uint32),
    ]


class _Filter(ctypes.Structure):
    _fields_: ClassVar[Any] = [
        ("code", ctypes.c_ushort),
        ("jt", ctypes.c_ubyte),
        ("jf", ctypes.c_ubyte),
        ("k", ctypes.c_uint32),
    ]


class _Program(ctypes.Structure):
    _fields_: ClassVar[Any] = [("len", ctypes.c_ushort), ("filter", ctypes.POINTER(_Filter))]


class _LandlockRuleset(ctypes.Structure):
    _fields_: ClassVar[Any] = [
        ("handled_access_fs", ctypes.c_uint64),
        ("handled_access_net", ctypes.c_uint64),
        ("scoped", ctypes.c_uint64),
    ]


class _LandlockPath(ctypes.Structure):
    _pack_ = 1
    _fields_: ClassVar[Any] = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]


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
    executable: bool = False

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
            or type(self.executable) is not bool
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


class _FenceRole(Enum):
    SNAPSHOT = "snapshot"
    WORKER = "worker"
    CONTROLLER = "controller"


def _drop_capabilities(native: Any) -> None:
    last = int(Path("/proc/sys/kernel/cap_last_cap").read_text(encoding="ascii"))
    if not 0 <= last <= 63:
        raise LinuxSnapshotError("Snapshot capability ABI exceeds supported bound")
    for number in range(last + 1):
        if native.prctl(24, number, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), "Snapshot bounding capability drop")
    if native.capset(ctypes.byref(_CapHeader(0x20080522, 0)), (_CapData * 2)()) != 0:
        raise OSError(ctypes.get_errno(), "Snapshot effective/permitted capability drop")
    if not _zero_caps(_status()):
        raise LinuxSnapshotError("Snapshot capabilities remain after drop")


def _apply_landlock(native: Any, root: int, gpu: int | None = None) -> int:
    if len(tuple(Path("/proc/self/task").iterdir())) != 1 or not _zero_caps(_status()):
        raise LinuxSnapshotError("GPU policy requires single thread and dropped capabilities")
    call = native.syscall
    call.restype = ctypes.c_long
    abi = int(call(444, 0, 0, 1))
    if abi < 0:
        raise OSError(ctypes.get_errno(), "Required GPU Landlock ABI query refused")
    if abi < 6:
        raise LinuxSnapshotError("GPU requires Landlock ABI >= 6; no compatibility fallback")
    rules = _LandlockRuleset((1 << 16) - 1, 3, 3)
    fd = int(call(444, ctypes.byref(rules), ctypes.sizeof(rules), 0))
    if fd < 0:
        raise OSError(ctypes.get_errno(), "Required GPU Landlock ruleset refused")
    try:
        leaves = [(root, 1 | 4 | 8)]
        if gpu is not None:
            leaves.append((gpu, 2 | 4 | (1 << 15)))
        for parent, access in leaves:
            rule = _LandlockPath(access, parent)
            if call(445, fd, 1, ctypes.byref(rule), 0) != 0:
                raise OSError(ctypes.get_errno(), "Required GPU Landlock leaf rule refused")
        if call(446, fd, 0) != 0:
            raise OSError(ctypes.get_errno(), "Required GPU Landlock enforcement refused")
        return abi
    finally:
        os.close(fd)


def _install_namespace_fence(
    native: Any,
    *,
    entropy: bool,
    gpu: bool,
    role: _FenceRole = _FenceRole.SNAPSHOT,
) -> tuple[int, int | None]:
    if type(role) is not _FenceRole:
        raise LinuxSnapshotError("Rooted fence requires an exact internal role")
    if role is not _FenceRole.SNAPSHOT:
        fields = _status()
        if (
            os.getpid() != (2 if role is _FenceRole.WORKER else 1)
            or len(tuple(Path("/proc/self/task").iterdir())) != 1
            or not _zero_caps(fields)
            or fields.get("NoNewPrivs", "").strip() != "1"
            or not int(_api(os, "statvfs")("/").f_flag) & int(_api(os, "ST_RDONLY"))
            or not int(_api(os, "statvfs")("/proc").f_flag) & int(_api(os, "ST_RDONLY"))
        ):
            raise LinuxSnapshotError("Rooted role requires original readonly zero-cap member")
    instructions = [
        (0x20, 0, 0, 4),
        (0x15, 1, 0, 0xC000003E),
        (0x06, 0, 0, 0x80000000),
        (0x20, 0, 0, 0),
        (0x35, 0, 1, 0x40000000),
        (0x06, 0, 0, 0x50000 | errno.ENOSYS),
    ]
    if entropy:
        write_flags = _flags("O_CREAT", "O_TRUNC", "O_APPEND")
        if not gpu:
            write_flags |= _flags("O_ACCMODE")
        for number, offset in ((2, 24), (257, 32)):
            if role is _FenceRole.SNAPSHOT:
                instructions.extend(
                    [
                        (0x15, 0, 3, number),
                        (0x20, 0, 0, offset),
                        (0x45, 0, 1, write_flags),
                        (0x06, 0, 0, 0x50000 | errno.EPERM),
                        (0x20, 0, 0, 0),
                    ]
                )
            else:
                # Worker fopen is notified; the trusted broker opens an anchored leaf.
                verdict = 0x7FC00000 if role is _FenceRole.WORKER else 0x7FFF0000
                first, second = (
                    (0x241, 0x80241)
                    if role is _FenceRole.WORKER
                    else (_flags("O_WRONLY", "O_NOFOLLOW", "O_CLOEXEC"),) * 2
                )
                instructions.extend(
                    [
                        (0x15, 0, 6, number),
                        (0x20, 0, 0, offset),
                        (0x15, 1, 0, first),
                        (0x15, 0, 1, second),
                        (0x06, 0, 0, verdict),
                        (0x45, 0, 1, write_flags),
                        (0x06, 0, 0, 0x50000 | errno.EPERM),
                        (0x20, 0, 0, 0),
                    ]
                )
        for number, code in (
            (85, errno.EPERM),
            (437, errno.ENOSYS),
            (425, errno.ENOSYS),
            (426, errno.ENOSYS),
            (427, errno.ENOSYS),
        ):
            instructions.extend([(0x15, 0, 1, number), (0x06, 0, 0, 0x50000 | code)])
    if gpu or role is not _FenceRole.SNAPSHOT:
        for number in (41, 53):
            instructions.extend(
                [
                    (0x15, 0, 3, number),
                    (0x20, 0, 0, 16),
                    (0x15, 1, 0, int(_api(socket, "AF_UNIX"))),
                    (0x06, 0, 0, 0x50000 | errno.EPERM),
                    (0x20, 0, 0, 0),
                ]
            )
        for number in (47, 299, 438):
            instructions.extend([(0x15, 0, 1, number), (0x06, 0, 0, 0x50000 | errno.EPERM)])
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
    array = (_Filter * len(instructions))(*(_Filter(*item) for item in instructions))
    program = _Program(len(instructions), array)
    prior = int(_status()["Seccomp_filters"].strip())
    if role is _FenceRole.WORKER:
        native.syscall.restype = ctypes.c_long
        listener = int(native.syscall(317, 1, 8, ctypes.byref(program)))
        if listener < 0:
            raise OSError(ctypes.get_errno(), "Original worker notification fence refused")
        if os.get_inheritable(listener):
            os.close(listener)
            raise LinuxSnapshotError("Original worker listener is inheritable")
        return prior + 1, listener
    native.prctl.argtypes = [ctypes.c_int, *([ctypes.c_ulong] * 4)]
    native.prctl.restype = ctypes.c_int
    if native.prctl(22, 2, ctypes.addressof(program), 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "Snapshot namespace reentry fence refused")
    return prior + 1, None


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
    _mode: SnapshotMode
    _kernel_entropy: bool
    _entropy: tuple[int, int] | None
    _wsl_gpu: bool
    _gpu: tuple[int, int] | None
    _gpu_policy: tuple[int, tuple[int, int, int], tuple[int, int, int]] | None
    _controls: dict[int, tuple[int, tuple[int, int, int]]]
    _control_fds: frozenset[int]
    _retained: dict[int, tuple[int, tuple[int, int, int], SnapshotFile]]

    def __init__(
        self,
        root: Path,
        files: tuple[SnapshotFile, ...],
        *,
        max_bytes: int = 1024**3,
        max_files: int = 4096,
        timeout_seconds: float = 30.0,
        mode: SnapshotMode = SnapshotMode.DATA_ONLY,
        kernel_entropy: bool = False,
        wsl_gpu: bool = False,
        control_fds: tuple[int, ...] = (),
        launch: RootedLaunch | None = None,
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
        names = self._declarations(
            root, files, max_bytes, max_files, mode, kernel_entropy, wsl_gpu, control_fds
        )
        self._root = root
        self._mode = mode
        self._kernel_entropy = kernel_entropy
        self._entropy = None
        self._wsl_gpu = wsl_gpu
        self._gpu = None
        self._gpu_policy = None
        self._controls = {}
        self._control_fds = frozenset(control_fds)
        self._names = frozenset(names)
        self._creator = (os.getpid(), threading.get_ident())
        self._thread = threading.current_thread()
        self._root_fd = self._anchor = -1
        self._known = {}
        self._namespaces = {}
        self._retained = {}
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
            if mode is SnapshotMode.ROOTED_IMAGE:
                launch_descriptions = frozenset()
                if launch is not None:
                    from hawedit.linux_rooted_launch import RootedLaunch

                    if type(launch) is not RootedLaunch:
                        raise LinuxSnapshotError(
                            "Snapshot launch requires an original typed controller"
                        )
                    launch_descriptions = launch._before_copy(files, mode, kernel_entropy, wsl_gpu)
                self._outside_descriptions(before, files, end, launch_descriptions)
            elif launch is not None:
                raise LinuxSnapshotError("Snapshot typed launch requires explicit rooted mode")
            _ATTEMPTED = True
            self._initialize(end)
            if kernel_entropy:
                self._acquire_entropy()
            if wsl_gpu:
                self._acquire_gpu()
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
            if mode is SnapshotMode.ROOTED_IMAGE:
                self._prepare_proc()
                if kernel_entropy:
                    self._prepare_entropy()
                if wsl_gpu:
                    self._prepare_gpu()
            # A live writer makes remount fail. Never keep any copied write FD.
            target = (
                f"/proc/self/fd/{self._anchor}" if mode is SnapshotMode.ROOTED_IMAGE else str(root)
            )
            self._mount(None, os.fsencode(target), None, 32 | 1 | 2 | 4)
            if mode is SnapshotMode.ROOTED_IMAGE:
                self._rebind_retained(end)
                os.close(before)
                before = -1
                self._enter_root()
            self._drop_caps()
            if wsl_gpu:
                self._enforce_gpu_policy()
            if launch is not None:
                launch._run(self._anchor, self._native, end)
            self._fence()
            for label in ("user", "mnt", "pid"):
                fd = os.open(f"/proc/self/ns/{label}", _flags("O_RDONLY", "O_CLOEXEC"))
                self._remember(fd)
                self._namespaces[label] = (fd, os.dup(fd))
                self._remember(self._namespaces[label][1])
            self._inspect(end)
            if launch is not None:
                launch._complete()
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
        root: Path,
        files: tuple[SnapshotFile, ...],
        max_bytes: int,
        max_files: int,
        mode: SnapshotMode = SnapshotMode.DATA_ONLY,
        kernel_entropy: bool = False,
        wsl_gpu: bool = False,
        control_fds: tuple[int, ...] = (),
    ) -> set[str]:
        if (
            not isinstance(root, Path)
            or not root.is_absolute()
            or root == Path("/")
            or ".." in root.parts
            or type(files) is not tuple
            or type(mode) is not SnapshotMode
            or type(kernel_entropy) is not bool
            or (kernel_entropy and mode is not SnapshotMode.ROOTED_IMAGE)
            or type(wsl_gpu) is not bool
            or (wsl_gpu and (mode is not SnapshotMode.ROOTED_IMAGE or not kernel_entropy))
            or type(control_fds) is not tuple
            or len(control_fds) > 131
            or any(type(fd) is not int or fd < 3 for fd in control_fds)
            or len(set(control_fds)) != len(control_fds)
            or (control_fds and not wsl_gpu)
            or type(max_bytes) is not int
            or not 0
            < max_bytes
            <= (128 * 1024**3 if mode is SnapshotMode.ROOTED_IMAGE else 32 * 1024**3)
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
            if mode is SnapshotMode.ROOTED_IMAGE and name.split("/")[0] == "proc":
                raise LinuxSnapshotError("Snapshot proc is reserved for readonly kernel state")
            if kernel_entropy and (
                name in ("dev", "dev/urandom") or name.startswith("dev/urandom/")
            ):
                raise LinuxSnapshotError("Snapshot entropy path is reserved for kernel state")
            if wsl_gpu and (name == "dev/dxg" or name.startswith("dev/dxg/")):
                raise LinuxSnapshotError(
                    "Snapshot GPU path is reserved for the fixed kernel endpoint"
                )
            if item.executable and mode is not SnapshotMode.ROOTED_IMAGE:
                raise LinuxSnapshotError("Snapshot executables require explicit rooted mode")
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
        native.capset.argtypes = [ctypes.POINTER(_CapHeader), ctypes.POINTER(_CapData)]
        native.capset.restype = ctypes.c_int
        _fcntl()
        return native

    def _outside_descriptions(
        self,
        allowed: int,
        files: tuple[SnapshotFile, ...],
        end: float,
        launch_descriptions: frozenset[int] = frozenset(),
    ) -> None:
        entries = os.listdir("/proc/self/fd")
        if len(entries) > 4096:
            raise LinuxSnapshotError("Rooted image outside descriptor inventory exceeds bound")
        inventory: list[tuple[int, tuple[int, int, int]]] = []
        # Freeze live identities before acquiring anchors can reuse the iterator's FD.
        for name in entries:
            self._left(end)
            fd = int(name)
            if fd == allowed or fd in launch_descriptions:
                continue
            try:
                original = _identity(fd)
            except OSError as exc:
                if exc.errno == errno.EBADF:
                    continue
                raise
            inventory.append((fd, original))
        for fd, original in inventory:
            self._left(end)
            mode = original[2]
            if self._wsl_gpu and not stat.S_ISREG(mode):
                self._gpu_outside_description(fd, original)
            if (
                self._kernel_entropy
                and os.readlink(f"/proc/self/fd/{fd}") == "anon_inode:[io_uring]"
            ):
                raise LinuxSnapshotError("Rooted readonly entropy refuses retained async rings")
            if stat.S_ISDIR(mode):
                raise LinuxSnapshotError("Rooted image requires closed outside directories")
            if (
                self._kernel_entropy
                and stat.S_ISCHR(mode)
                and _api(os.fstat(fd), "st_rdev") == _api(os, "makedev")(1, 9)
                and (
                    _fcntl().fcntl(fd, _fcntl().F_GETFL) & int(_api(os, "O_ACCMODE")) != os.O_RDONLY
                    or os.get_inheritable(fd)
                )
            ):
                raise LinuxSnapshotError("Rooted entropy requires no writable/inheritable handles")
            if not stat.S_ISREG(mode):
                continue
            flags = _fcntl().fcntl(fd, _fcntl().F_GETFL)
            if flags & int(_api(os, "O_ACCMODE")) != os.O_RDONLY or os.get_inheritable(fd):
                raise LinuxSnapshotError("Rooted retained file must be readonly/noninheritable")
            selected = None
            for item in files:
                self._left(end)
                if not item.executable:
                    continue
                parent = _directory(item.source.parent)
                try:
                    info = os.stat(item.source.name, dir_fd=parent, follow_symlinks=False)
                finally:
                    os.close(parent)
                if (info.st_dev, info.st_ino, info.st_mode) == original:
                    selected = item
                    break
            if selected is None:
                raise LinuxSnapshotError("Rooted retained file requires declared executable bytes")
            anchor = os.dup(fd)
            self._remember(anchor)
            self._retained[fd] = (anchor, original, selected)
            self._retained_bytes(fd, selected, end)
        if self._wsl_gpu and set(self._controls) != self._control_fds:
            raise LinuxSnapshotError("GPU original control descriptions unavailable")

    def _gpu_outside_description(self, fd: int, original: tuple[int, int, int]) -> None:
        if (
            fd in (0, 1, 2)
            and stat.S_ISCHR(original[2])
            and _api(os.fstat(fd), "st_rdev") == _api(os, "makedev")(1, 3)
        ):
            return
        if fd not in self._control_fds or not stat.S_ISSOCK(original[2]):
            raise LinuxSnapshotError("GPU refuses pre-policy foreign I/O descriptions")
        channel = socket.socket(fileno=fd)
        try:
            if (
                channel.family != int(_api(socket, "AF_UNIX"))
                or channel.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_SEQPACKET
                or channel.getsockname() != ""
                or channel.getpeername() != ""
                or not channel.getblocking()
                or _fcntl().fcntl(fd, _fcntl().F_GETFL) & int(_api(os, "O_NONBLOCK"))
                or os.get_inheritable(fd)
            ):
                raise LinuxSnapshotError(
                    "GPU requires original unnamed noninheritable control socket"
                )
        finally:
            channel.detach()
        anchor = os.dup(fd)
        self._remember(anchor)
        self._controls[fd] = (anchor, original)

    def _retained_bytes(self, fd: int, item: SnapshotFile, end: float) -> None:
        info = os.fstat(fd)
        if info.st_nlink != 1 or info.st_size != item.size_bytes:
            raise LinuxSnapshotError("Rooted retained executable size/link binding refused")
        digest = hashlib.sha256()
        offset = 0
        while offset < item.size_bytes:
            self._left(end)
            data = _api(os, "pread")(fd, min(_CHUNK, item.size_bytes - offset), offset)
            if not data:
                raise LinuxSnapshotError("Rooted retained executable truncated")
            digest.update(data)
            offset += len(data)
        if digest.hexdigest() != item.sha256:
            raise LinuxSnapshotError("Rooted retained executable hash refused")

    def _rebind_retained(self, end: float) -> None:
        for fd, (anchor, original, item) in tuple(self._retained.items()):
            self._left(end)
            if (
                _identity(fd) != original
                or _identity(anchor) != original
                or _fcntl().fcntl(fd, 1027, anchor) != 1
                or os.get_inheritable(fd)
                or _fcntl().fcntl(fd, _fcntl().F_GETFL) & int(_api(os, "O_ACCMODE")) != os.O_RDONLY
            ):
                raise LinuxSnapshotError("Rooted retained original description substituted")
            copied = os.open(
                f"/proc/self/fd/{self._anchor}/{item.relative_path}",
                _flags("O_RDONLY", "O_NOFOLLOW", "O_CLOEXEC"),
            )
            try:
                self._retained_bytes(copied, item, end)
                if _identity(copied)[:2] == original[:2]:
                    raise LinuxSnapshotError("Rooted retained copy is still source-backed")
                os.lseek(copied, os.lseek(fd, 0, os.SEEK_CUR), os.SEEK_SET)
                bound = os.dup(copied)
                self._remember(bound)
                os.dup2(copied, fd, inheritable=False)
                self._retained[fd] = (bound, _identity(copied), item)
                os.close(anchor)
                del self._known[anchor]
            finally:
                os.close(copied)

    def _prepare_proc(self) -> None:
        os.mkdir("proc", 0o700, dir_fd=self._anchor)
        target = os.fsencode(f"/proc/self/fd/{self._anchor}/proc")
        self._mount(b"/proc", target, None, 4096 | 16384)
        self._mount(None, target, None, 32 | 4096 | 1 | 2 | 4 | 8)

    def _acquire_entropy(self) -> None:
        parent = _directory(Path("/dev"))
        try:
            fd = os.open("urandom", _flags("O_RDONLY", "O_NOFOLLOW", "O_CLOEXEC"), dir_fd=parent)
        finally:
            os.close(parent)
        self._remember(fd)
        anchor = os.dup(fd)
        self._remember(anchor)
        self._entropy = (fd, anchor)
        self._entropy_custody()

    def _entropy_custody(self) -> None:
        if self._entropy is None:
            raise LinuxSnapshotError("Snapshot original entropy description unavailable")
        for fd in self._entropy:
            info = os.fstat(fd)
            if (
                not stat.S_ISCHR(info.st_mode)
                or _api(info, "st_rdev") != _api(os, "makedev")(1, 9)
                or _identity(fd) != self._known.get(fd)
                or os.get_inheritable(fd)
                or _fcntl().fcntl(fd, _fcntl().F_GETFL) & int(_api(os, "O_ACCMODE")) != os.O_RDONLY
            ):
                raise LinuxSnapshotError("Snapshot original readonly entropy identity substituted")
        if _fcntl().fcntl(self._entropy[0], 1027, self._entropy[1]) != 1:
            raise LinuxSnapshotError("Snapshot original entropy description substituted")

    def _prepare_entropy(self) -> None:
        self._entropy_custody()
        assert self._entropy is not None
        with suppress(FileExistsError):
            os.mkdir("dev", 0o700, dir_fd=self._anchor)
        directory = os.open(
            "dev", _flags("O_RDONLY", "O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC"), dir_fd=self._anchor
        )
        try:
            placeholder = os.open(
                "urandom",
                _flags("O_WRONLY", "O_CREAT", "O_EXCL", "O_NOFOLLOW", "O_CLOEXEC"),
                0o400,
                dir_fd=directory,
            )
            os.close(placeholder)
            target = os.fsencode(f"/proc/self/fd/{self._anchor}/dev/urandom")
            self._mount(os.fsencode(f"/proc/self/fd/{self._entropy[0]}"), target, None, 4096)
            self._mount(None, target, None, 32 | 4096 | 1 | 2 | 8)
            self._entropy_custody()
        finally:
            os.close(directory)

    def _inspect_entropy(self) -> None:
        self._entropy_custody()
        assert self._entropy is not None
        current = os.stat("/dev/urandom", follow_symlinks=False)
        if (current.st_dev, current.st_ino, current.st_mode) != _identity(self._entropy[0]):
            raise LinuxSnapshotError("Snapshot private entropy endpoint substituted")
        flags = int(_api(os, "statvfs")("/dev/urandom").f_flag)
        required = _flags("ST_RDONLY", "ST_NOSUID", "ST_NOEXEC")
        if (
            flags & required != required
            or flags & int(_api(os, "ST_NODEV"))
            or not int(_api(os, "fstatvfs")(self._anchor).f_flag) & int(_api(os, "ST_NODEV"))
        ):
            raise LinuxSnapshotError("Snapshot private entropy mount policy changed")

    def _acquire_gpu(self) -> None:
        parent = _directory(Path("/dev"))
        try:
            fd = os.open("dxg", _flags("O_PATH", "O_NOFOLLOW", "O_CLOEXEC"), dir_fd=parent)
        finally:
            os.close(parent)
        self._remember(fd)
        anchor = os.dup(fd)
        self._remember(anchor)
        self._gpu = (fd, anchor)
        self._gpu_custody()

    def _gpu_custody(self) -> None:
        if self._gpu is None:
            raise LinuxSnapshotError("Snapshot original GPU description unavailable")
        for fd in self._gpu:
            info = os.fstat(fd)
            if (
                not stat.S_ISCHR(info.st_mode)
                or _api(info, "st_rdev") != _api(os, "makedev")(10, 258)
                or info.st_nlink != 1
                or _identity(fd) != self._known.get(fd)
                or os.get_inheritable(fd)
                or not _fcntl().fcntl(fd, _fcntl().F_GETFL) & int(_api(os, "O_PATH"))
            ):
                raise LinuxSnapshotError("Snapshot fixed original O_PATH GPU identity substituted")
        if _fcntl().fcntl(self._gpu[0], 1027, self._gpu[1]) != 1:
            raise LinuxSnapshotError("Snapshot original GPU description substituted")

    def _prepare_gpu(self) -> None:
        self._gpu_custody()
        assert self._gpu is not None
        directory = os.open(
            "dev", _flags("O_RDONLY", "O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC"), dir_fd=self._anchor
        )
        try:
            fd = os.open(
                "dxg",
                _flags("O_WRONLY", "O_CREAT", "O_EXCL", "O_NOFOLLOW", "O_CLOEXEC"),
                0o600,
                dir_fd=directory,
            )
            os.close(fd)
            target = os.fsencode(f"/proc/self/fd/{self._anchor}/dev/dxg")
            self._mount(os.fsencode(f"/proc/self/fd/{self._gpu[0]}"), target, None, 4096)
            self._mount(None, target, None, 32 | 4096 | 1 | 2 | 8)
            self._gpu_custody()
        finally:
            os.close(directory)

    def _enforce_gpu_policy(self) -> None:
        self._gpu_custody()
        assert self._gpu is not None
        abi = _apply_landlock(self._native, self._anchor, self._gpu[0])
        self._gpu_policy = (abi, _identity(self._anchor), _identity(self._gpu[0]))
        self._check_gpu_policy()

    def _check_gpu_policy(self) -> None:
        self._gpu_custody()
        assert self._gpu is not None
        if (
            self._gpu_policy is None
            or self._gpu_policy[0] < 6
            or self._gpu_policy[1:] != (_identity(self._anchor), _identity(self._gpu[0]))
        ):
            raise LinuxSnapshotError("Snapshot enforced GPU policy custody unavailable")
        # Kernel denial is checked, not inferred from the saved policy declaration.
        for path in (
            "/dev/urandom",
            "/proc/self/fd/" + str(self._entropy[0] if self._entropy else -1),
        ):
            try:
                opened = os.open(path, _flags("O_RDWR", "O_CLOEXEC"))
            except OSError as exc:
                if exc.errno != errno.EACCES:
                    raise LinuxSnapshotError(
                        "GPU readonly entropy policy enforcement uncertain"
                    ) from exc
            else:
                os.close(opened)
                raise LinuxSnapshotError("GPU kernel policy allowed a non-GPU writable open")

    def _inspect_gpu(self) -> None:
        self._check_gpu_policy()
        assert self._gpu is not None
        current = os.stat("/dev/dxg", follow_symlinks=False)
        flags = int(_api(os, "statvfs")("/dev/dxg").f_flag)
        required = _flags("ST_RDONLY", "ST_NOSUID", "ST_NOEXEC")
        if (
            (current.st_dev, current.st_ino, current.st_mode) != _identity(self._gpu[0])
            or flags & required != required
            or flags & int(_api(os, "ST_NODEV"))
        ):
            raise LinuxSnapshotError("Snapshot private GPU identity/mount policy changed")

    def _enter_root(self) -> None:
        _api(os, "fchdir")(self._anchor)
        _api(os, "chroot")(".")
        os.chdir("/")
        current = os.stat("/")
        if (
            _identity(self._anchor) != (current.st_dev, current.st_ino, current.st_mode)
            or os.getcwd() != "/"
        ):
            raise LinuxSnapshotError("Snapshot original process root transition refused")

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
                0o500 if item.executable else 0o400,
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
        _drop_capabilities(self._native)

    def _fence(self) -> None:
        if self._kernel_entropy and self._wsl_gpu:
            self._check_gpu_policy()
        self._filters, listener = _install_namespace_fence(
            self._native, entropy=self._kernel_entropy, gpu=self._wsl_gpu
        )
        assert listener is None

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
            if self._entropy is not None:
                pairs.append(self._entropy)
            if self._gpu is not None:
                pairs.append(self._gpu)
            for fd, (anchor, original) in self._controls.items():
                if (
                    _identity(fd) != original
                    or os.get_inheritable(fd)
                    or _fcntl().fcntl(fd, _fcntl().F_GETFL) & int(_api(os, "O_NONBLOCK"))
                ):
                    raise LinuxSnapshotError("Snapshot original control description substituted")
                pairs.append((fd, anchor))
            for fd, (anchor, original, _) in self._retained.items():
                if _identity(fd) != original or os.get_inheritable(fd):
                    raise LinuxSnapshotError("Snapshot retained private descriptor substituted")
                pairs.append((fd, anchor))
            for fd, anchor in pairs:
                if _fcntl().fcntl(fd, 1027, anchor) != 1:
                    raise LinuxSnapshotError("Snapshot original description substituted")
            for label, (fd, _) in self._namespaces.items():
                current = os.stat(f"/proc/self/ns/{label}")
                if (current.st_dev, current.st_ino, current.st_mode) != _identity(fd):
                    raise LinuxSnapshotError("Snapshot original namespace changed")
            if not int(_api(os, "fstatvfs")(self._anchor).f_flag) & int(_api(os, "ST_RDONLY")):
                raise LinuxSnapshotError("Snapshot original root is not read-only")
            if self._mode is SnapshotMode.ROOTED_IMAGE:
                current = os.stat("/")
                if (
                    (current.st_dev, current.st_ino, current.st_mode) != _identity(self._anchor)
                    or os.getcwd() != "/"
                    or not int(_api(os, "statvfs")("/proc").f_flag) & int(_api(os, "ST_RDONLY"))
                ):
                    raise LinuxSnapshotError("Snapshot original process root/cwd/proc changed")
                if self._kernel_entropy:
                    self._inspect_entropy()
                if self._wsl_gpu:
                    self._inspect_gpu()
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
        pairs = [(self._root_fd, self._anchor), *self._namespaces.values()]
        if self._entropy is not None:
            pairs.append(self._entropy)
        if self._gpu is not None:
            pairs.append(self._gpu)
        pairs.extend((fd, item[0]) for fd, item in self._controls.items())
        pairs.extend((fd, item[0]) for fd, item in self._retained.items())
        for first, anchor in pairs:
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
