"""Isolated, descriptor-bound storage for the ephemeral Linux audit scanner."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Final

_PATH = re.compile(r"/tmp/hawedit-wsl-audit\.[A-Za-z0-9]{10}\Z")


@dataclass(frozen=True)
class ScannerDirectory:
    path: str
    device: int
    inode: int
    uid: int

    def arguments(self) -> list[str]:
        return [self.path, str(self.device), str(self.inode), str(self.uid)]


def _unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate scanner directory identity field")
        result[key] = value
    return result


def scanner_directory_identity(payload: bytes) -> ScannerDirectory:
    """Parse only the exact creation receipt, not a caller-supplied deletion path."""
    try:
        value: object = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_fields)
    except (UnicodeError, ValueError) as exc:
        raise ValueError("invalid scanner directory identity") from exc
    if type(value) is not dict or set(value) != {"path", "device", "inode", "uid"}:
        raise ValueError("invalid scanner directory identity fields")
    path, device, inode, uid = (value[key] for key in ("path", "device", "inode", "uid"))
    if (
        type(path) is not str
        or _PATH.fullmatch(path) is None
        or any(type(number) is not int for number in (device, inode, uid))
        or device < 0
        or inode <= 0
        or uid < 0
    ):
        raise ValueError("invalid scanner directory identity values")
    return ScannerDirectory(path, device, inode, uid)


# Sent through the already pinned interpreter with -I: no environment import path,
# shell expansion, package installation or dependency on a refreshed WSL snapshot.
STORAGE_SCRIPT: Final = r"""
import json, os, re, secrets, stat, sys, time

if sys.platform != "linux":
    raise RuntimeError("Linux directory descriptors are required")
flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
parent = os.open("/tmp", flags)
deadline = time.monotonic() + 55
remaining = [100000]

def identity(info):
    return (info.st_dev, info.st_ino, info.st_uid)

def verify(info, expected):
    if (not stat.S_ISDIR(info.st_mode) or identity(info) != expected
            or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700):
        raise RuntimeError("scanner directory identity changed or is not private")

def remove_contents(directory, device, depth):
    if depth > 128:
        raise RuntimeError("scanner cleanup depth limit exceeded")
    with os.scandir(directory) as entries:
        for entry in entries:
            remaining[0] -= 1
            if remaining[0] < 0 or time.monotonic() > deadline:
                raise RuntimeError("scanner cleanup work limit exceeded")
            before = os.stat(entry.name, dir_fd=directory, follow_symlinks=False)
            if before.st_dev != device or before.st_uid != os.geteuid():
                raise RuntimeError("foreign scanner entry refused")
            if stat.S_ISDIR(before.st_mode):
                child = os.open(entry.name, flags, dir_fd=directory)
                try:
                    held = os.fstat(child)
                    if identity(held) != identity(before):
                        raise RuntimeError("scanner child identity changed")
                    remove_contents(child, device, depth + 1)
                    after = os.stat(entry.name, dir_fd=directory, follow_symlinks=False)
                    if identity(after) != identity(held) or not stat.S_ISDIR(after.st_mode):
                        raise RuntimeError("scanner child identity changed")
                    os.rmdir(entry.name, dir_fd=directory)
                finally:
                    os.close(child)
            else:
                os.unlink(entry.name, dir_fd=directory)

try:
    if sys.argv[1:] == ["create"]:
        for attempt in range(100):
            name = "hawedit-wsl-audit." + secrets.token_hex(5)
            try:
                os.mkdir(name, 0o700, dir_fd=parent)
                break
            except FileExistsError:
                continue
        else:
            raise RuntimeError("cannot allocate scanner directory")
        root = os.open(name, flags, dir_fd=parent)
        try:
            info = os.fstat(root)
            verify(info, identity(info))
            print(json.dumps(dict(path="/tmp/" + name, device=info.st_dev,
                                  inode=info.st_ino, uid=info.st_uid), sort_keys=True))
        finally:
            os.close(root)
    elif len(sys.argv) == 6 and sys.argv[1] == "cleanup":
        path = sys.argv[2]
        if re.fullmatch(r"/tmp/hawedit-wsl-audit\.[A-Za-z0-9]{10}", path) is None:
            raise RuntimeError("unsafe scanner cleanup path")
        if any(re.fullmatch(r"[0-9]+", value) is None for value in sys.argv[3:]):
            raise RuntimeError("invalid scanner directory identity")
        expected = tuple(int(value) for value in sys.argv[3:])
        if expected[1] <= 0 or expected[2] != os.geteuid():
            raise RuntimeError("invalid scanner directory identity")
        name = path.rsplit("/", 1)[1]
        root = os.open(name, flags, dir_fd=parent)
        try:
            verify(os.fstat(root), expected)
            verify(os.stat(name, dir_fd=parent, follow_symlinks=False), expected)
            remove_contents(root, expected[0], 0)
            verify(os.stat(name, dir_fd=parent, follow_symlinks=False), expected)
            os.rmdir(name, dir_fd=parent)
        finally:
            os.close(root)
    else:
        raise RuntimeError("invalid scanner storage operation")
finally:
    os.close(parent)
"""
