"""Owner-private SQLite pathname binding for the protected studio supervisor.

This checks filesystem policy, not HTTP identity, spending authority or provider evidence.
Existing unsafe files and permissions are refused, never repaired or removed.
"""

from __future__ import annotations

import os
import re
import stat
import uuid
from contextlib import suppress
from pathlib import Path
from typing import BinaryIO

from hawedit.windows_security import (
    WindowsSecurityError,
    assert_private_windows_path,
    create_private_directory,
)

__all__ = ["PrivateDirectory", "PrivateSqlitePath", "StudioStorageError", "write_text_atomic"]


class StudioStorageError(RuntimeError):
    """Persistence is unavailable or untrustworthy; never silently ignored."""


_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_DEVICES = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
}
_SIDECARS = ("-wal", "-shm", "-journal")
_TEMPORARY = re.compile(r"\.[a-f0-9]{32}\.tmp\Z")


def _identity(info: os.stat_result) -> tuple[int, int, int]:
    birth = getattr(info, "st_birthtime_ns", info.st_ctime_ns) if os.name == "nt" else 0
    return info.st_dev, info.st_ino, birth


def _plain(path: Path, *, directory: bool) -> os.stat_result:
    info = path.lstat()
    reparse = bool(getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    valid = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not valid or reparse or (not directory and info.st_nlink != 1):
        raise StudioStorageError("Studio private journal refuses linked or nonregular storage")
    return info


def _directories(path: Path) -> None:
    if len(path.parents) > 128:
        raise StudioStorageError("Studio private journal directory depth exceeds its bound")
    for component in reversed((path, *path.parents)):
        _plain(component, directory=True)


def _private(path: Path, *, directory: bool) -> os.stat_result:
    before = _plain(path, directory=directory)
    if os.name == "nt":
        assert_private_windows_path(path, require_protected=directory)
    elif not hasattr(os, "geteuid") or before.st_uid != os.geteuid() or before.st_mode & 0o077:
        raise StudioStorageError("Studio private journal requires current-owner private storage")
    after = _plain(path, directory=directory)
    if _identity(before) != _identity(after):
        raise StudioStorageError("Studio private journal identity changed during inspection")
    return after


def _member(name: str) -> str:
    if (
        not (_NAME.fullmatch(name) or _TEMPORARY.fullmatch(name))
        or name.endswith(".")
        or name.split(".", 1)[0].upper() in _DEVICES
    ):
        raise StudioStorageError("Studio private storage requires a scoped portable member")
    return name


class PrivateDirectory:
    """A lifetime-bound private leaf; never repairs existing owner data or access."""

    def __init__(self, path: Path, *, create: bool = True, exclusive: bool = False) -> None:
        if path.drive.startswith("\\\\") or any(
            part == ".." or part.endswith((".", " ")) for part in path.parts
        ):
            raise StudioStorageError("Studio private storage refuses ambiguous local directories")
        self.path = Path(os.path.abspath(path))
        try:
            _directories(self.path.parent)
            try:
                self.path.lstat()
            except FileNotFoundError:
                if not create:
                    raise
                if os.name == "nt":
                    create_private_directory(self.path)
                else:
                    self.path.mkdir(mode=0o700)
            else:
                if exclusive:
                    raise StudioStorageError("Studio private storage refuses an existing new leaf")
            self._identity = _identity(_private(self.path, directory=True))
            self.verify()
        except (OSError, WindowsSecurityError, ValueError) as exc:
            raise StudioStorageError("Studio private storage is unavailable or nonprivate") from exc

    @property
    def identity(self) -> tuple[int, int, int]:
        return self._identity

    def verify(self) -> None:
        try:
            _directories(self.path)
            if _identity(_private(self.path, directory=True)) != self._identity:
                raise StudioStorageError("Studio private directory identity changed")
        except (OSError, WindowsSecurityError, ValueError) as exc:
            raise StudioStorageError("Studio private storage is unavailable or nonprivate") from exc

    def child(
        self, name: str, *, create: bool = False, exclusive: bool = False
    ) -> PrivateDirectory:
        self.verify()
        child = PrivateDirectory(self.path / _member(name), create=create, exclusive=exclusive)
        self.verify()
        return child

    def check_file(self, name: str) -> os.stat_result:
        self.verify()
        try:
            info = _private(self.path / _member(name), directory=False)
        except WindowsSecurityError as exc:
            raise StudioStorageError("Studio private member access is unsafe") from exc
        self.verify()
        return info

    def member_identity(self, name: str) -> tuple[int, int, int]:
        return _identity(self.check_file(name))

    def open_new_file(self, name: str) -> BinaryIO:
        self.verify()
        path = self.path / _member(name)
        descriptor = os.open(
            path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600
        )
        stream = os.fdopen(descriptor, "wb")
        try:
            if _identity(os.fstat(stream.fileno())) != self.member_identity(name):
                raise StudioStorageError("Studio private file identity changed during creation")
        except BaseException:
            stream.close()
            raise
        return stream

    def remove_owned(self, name: str, expected: tuple[int, int, int]) -> bool:
        """Remove only a known transfer/temp file, never through a changed namespace."""
        if self.member_identity(name) != expected:
            return False
        (self.path / _member(name)).unlink()
        self.verify()
        return True

    def sync(self) -> None:
        self.verify()
        if os.name == "posix":
            descriptor = os.open(self.path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                if _identity(os.fstat(descriptor)) != self._identity:
                    raise StudioStorageError(
                        "Studio private directory identity changed during sync"
                    )
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        self.verify()


def write_text_atomic(path: Path, text: str) -> None:
    """Private/fsynced metadata replacement; no global atomic_fs behavior change."""
    directory = PrivateDirectory(path.parent, create=False)
    name = _member(path.name)
    try:
        before: tuple[int, int, int] | None = directory.member_identity(name)
    except FileNotFoundError:
        before = None
    temporary = f".{uuid.uuid4().hex}.tmp"
    owned: tuple[int, int, int] | None = None
    try:
        with directory.open_new_file(temporary) as stream:
            owned = directory.member_identity(temporary)
            stream.write(text.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        if directory.member_identity(temporary) != owned:
            raise StudioStorageError("Studio private metadata staging identity changed")
        try:
            current = directory.member_identity(name)
        except FileNotFoundError:
            current = None
        if current != before:
            raise StudioStorageError("Studio private metadata destination identity changed")
        (directory.path / temporary).replace(directory.path / name)
        owned = None
        directory.check_file(name)
        directory.sync()
    finally:
        if owned is not None:
            # Lost/unsafe storage is evidence, not permission to clean a new namespace.
            with suppress(OSError, StudioStorageError):
                directory.remove_owned(temporary, owned)


class PrivateSqlitePath:
    """Bind one private root/database; sidecars remain actual SQLite recovery evidence."""

    def __init__(self, path: Path) -> None:
        if (
            not _NAME.fullmatch(path.name)
            or path.name.endswith(".")
            or path.name.split(".", 1)[0].upper() in _DEVICES
            or path.drive.startswith("\\\\")
            or any(part == ".." or part.endswith((".", " ")) for part in path.parts)
        ):
            raise StudioStorageError("Studio private journal requires a portable local filename")
        self.path = Path(os.path.abspath(path))
        self.root = self.path.parent
        try:
            self._directory = PrivateDirectory(self.root)
            self._root_identity = self._directory.identity
            _directories(self.root)
            try:
                self.path.lstat()
            except FileNotFoundError:
                # A missing main file cannot justify deleting/adopting old recovery state.
                for suffix in _SIDECARS:
                    try:
                        self.path.with_name(self.path.name + suffix).lstat()
                    except FileNotFoundError:
                        continue
                    raise StudioStorageError(
                        "Studio private journal refuses orphan SQLite sidecars"
                    ) from None
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
                try:
                    descriptor = os.open(self.path, flags, 0o600)
                except FileExistsError:
                    pass
                else:
                    os.close(descriptor)
            self._file_identity = _identity(_private(self.path, directory=False))
            self.verify()
        except (OSError, WindowsSecurityError, ValueError) as exc:
            raise StudioStorageError(
                "Studio private journal storage is unavailable or nonprivate"
            ) from exc

    def _verify_binding(self) -> None:
        _directories(self.root)
        if _identity(_private(self.root, directory=True)) != self._root_identity:
            raise StudioStorageError("Studio private journal root identity changed")
        if _identity(_private(self.path, directory=False)) != self._file_identity:
            raise StudioStorageError("Studio private journal database identity changed")

    def verify(self) -> None:
        """Fence namespace, access, main-file identity and every existing SQLite sidecar."""
        try:
            self._verify_binding()
            for suffix in _SIDECARS:
                sidecar = self.path.with_name(self.path.name + suffix)
                try:
                    _private(sidecar, directory=False)
                except FileNotFoundError:
                    continue
                except (OSError, WindowsSecurityError, StudioStorageError):
                    # SQLite may remove a sidecar when its last connection closes.
                    try:
                        sidecar.lstat()
                    except FileNotFoundError:
                        continue
                    raise
            self._verify_binding()
        except (OSError, WindowsSecurityError, ValueError) as exc:
            raise StudioStorageError(
                "Studio private journal storage is unavailable or nonprivate"
            ) from exc
