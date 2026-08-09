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
from pathlib import Path

__all__ = ["rename_directory_noreplace"]


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
