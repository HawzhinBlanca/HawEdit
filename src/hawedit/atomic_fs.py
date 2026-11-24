"""Small cross-platform filesystem publication primitives.

The standard :func:`os.rename` call is no-replace on Windows, but on POSIX it can replace an
empty destination directory.  Publication code that checks for a destination and then calls
``os.rename`` therefore has a race.  This module exposes the native atomic no-replace operation
without silently falling back to that unsafe sequence.
"""

from __future__ import annotations

import ctypes
import errno
import os
import stat
from pathlib import Path

__all__ = [
    "file_identity",
    "is_reparse_point",
    "read_bound_file",
    "rename_directory_noreplace",
    "write_text_atomic",
]


def is_reparse_point(info: os.stat_result) -> bool:
    """Return True when ``info`` carries the Windows reparse-point attribute."""
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(getattr(info, "st_file_attributes", 0) & flag)


def file_identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    """Return the comparable inode/size/mtime/link identity tuple for ``info``."""
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_nlink)


def read_bound_file(
    path: Path,
    label: str,
    *,
    max_bytes: int | None,
    error_cls: type[Exception] = OSError,
) -> bytes:
    """Read one regular, single-link, non-symlink file verifying identity before & after read."""
    try:
        before_path = os.lstat(path)
    except OSError as exc:
        raise error_cls(f"cannot inspect {label} {path}: {exc}") from exc
    if stat.S_ISLNK(before_path.st_mode) or is_reparse_point(before_path):
        raise error_cls(f"{label} must not be a symlink or reparse point: {path}")
    if not stat.S_ISREG(before_path.st_mode) or before_path.st_nlink != 1:
        raise error_cls(f"{label} must be one regular, non-hardlinked file: {path}")
    if max_bytes is not None and before_path.st_size > max_bytes:
        raise error_cls(f"{label} exceeds its {max_bytes}-byte limit: {path}")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise error_cls(f"cannot open {label} {path}: {exc}") from exc
    try:
        before_fd = os.fstat(descriptor)
        if file_identity(before_fd) != file_identity(before_path):
            raise error_cls(f"{label} changed while opening: {path}")
        chunks: list[bytes] = []
        total = 0
        while chunk := os.read(descriptor, 1024 * 1024):
            total += len(chunk)
            if max_bytes is not None and total > max_bytes:
                raise error_cls(f"{label} exceeds its {max_bytes}-byte limit: {path}")
            chunks.append(chunk)
        after_fd = os.fstat(descriptor)
        if (
            file_identity(after_fd) != file_identity(before_fd)
            or after_fd.st_ctime_ns != before_fd.st_ctime_ns
        ):
            raise error_cls(f"{label} changed while being read: {path}")
    finally:
        os.close(descriptor)
    try:
        after_path = os.lstat(path)
    except OSError as exc:
        raise error_cls(f"cannot re-inspect {label} {path}: {exc}") from exc
    if (
        file_identity(after_path) != file_identity(before_path)
        or after_path.st_ctime_ns != before_path.st_ctime_ns
    ):
        raise error_cls(f"{label} path changed while being read: {path}")
    return b"".join(chunks)


def write_text_atomic(path: Path, text: str) -> None:
    """Write one file through a staging file and a single rename, so a kill cannot half-write it.

    `Path.write_text` truncates first: a process that dies mid-write leaves a file that exists,
    is readable and is wrong — and every reader of these artifacts checks existence, not
    completeness. The rename is the same shape `transcripts.py` and `visual_pipeline.py` already
    use for their own artifacts. D-146.

    Lives here rather than in `pipeline.py` (where it was `_write_atomic` until the merge that
    brought `artifact_bundle.py` in): that module's own atomic publication is now directory-
    shaped, while `proposals.py`'s revision records and `durable_workflow.py`'s `report.json`
    are single files. Two different primitives, and this module already owns the other. D-A26.
    """
    staging = path.with_name(f".{path.name}.tmp")
    try:
        staging.write_text(text, encoding="utf-8")
        staging.replace(path)
    except OSError:
        # Otherwise a failed write leaves a dotfile that looks exactly like the partial state
        # this function exists to prevent.
        staging.unlink(missing_ok=True)
        raise


def rename_directory_noreplace(source: Path, destination: Path) -> None:
    """Atomically rename one directory while refusing every existing destination path."""
    if os.name == "nt":
        # Windows MoveFile already has no-replace semantics for os.rename().
        os.rename(source, destination)
        return

    encoded_source = os.fsencode(source)
    encoded_destination = os.fsencode(destination)
    library = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(library, "renameat2", None)
    if renameat2 is not None:
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        # Linux: RENAME_NOREPLACE, relative to the current directory when paths are relative.
        result = renameat2(-100, encoded_source, -100, encoded_destination, 1)
    else:
        renamex_np = getattr(library, "renamex_np", None)
        if renamex_np is None:
            raise OSError(
                errno.ENOTSUP,
                "this platform has no atomic no-replace directory publication primitive",
                destination,
            )
        renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        renamex_np.restype = ctypes.c_int
        # Darwin: RENAME_EXCL.
        result = renamex_np(encoded_source, encoded_destination, 0x00000004)
    if result != 0:
        error = ctypes.get_errno()
        if error in {errno.EEXIST, errno.ENOTEMPTY}:
            raise FileExistsError(error, os.strerror(error), destination)
        raise OSError(error, os.strerror(error), destination)
