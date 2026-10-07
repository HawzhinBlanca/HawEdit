"""Deterministic render-request provenance; never approval or runtime authority."""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from hawedit.ingest_cache import IngestCacheError, _open
from hawedit.wsl_setup import package_digest

_MAX_MEMBERS = 512
_MAX_FILE_BYTES = 32 * 1024**3


def _plain_stat(path: Path) -> os.stat_result:
    for member in (path, *path.parents):
        info = member.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("render request assets must not traverse links or reparse points")
    return path.lstat()


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _file_snapshot(path: Path) -> dict[str, object]:
    before = _plain_stat(path)
    if not stat.S_ISREG(before.st_mode) or not 0 <= before.st_size <= _MAX_FILE_BYTES:
        raise ValueError("render request asset must be a bounded regular file")
    try:
        with _open(path, single_link=False) as opened:
            digest = opened.digest()
    except IngestCacheError as exc:
        raise ValueError("render request asset changed or could not be safely read") from exc
    if _identity(_plain_stat(path)) != _identity(before):
        raise ValueError("render request asset changed during inspection")
    return {"path": str(path), "size_bytes": before.st_size, "sha256": digest}


def _directory_members(path: Path) -> dict[Path, tuple[int, ...]]:
    members: dict[Path, tuple[int, ...]] = {}
    pending = [path]
    total_bytes = 0
    while pending:
        directory = pending.pop()
        _plain_stat(directory)
        for member in directory.iterdir():
            if len(members) >= _MAX_MEMBERS:
                raise ValueError("render request asset directory exceeded its member limit")
            info = _plain_stat(member)
            members[member] = _identity(info)
            if stat.S_ISDIR(info.st_mode):
                pending.append(member)
            elif stat.S_ISREG(info.st_mode):
                total_bytes += info.st_size
                if total_bytes > 512 * 1024**2:
                    raise ValueError("render request asset directory exceeded its byte limit")
            else:
                raise ValueError("render request directory contains a special file")
    return members


def _path_snapshot(value: Path) -> dict[str, object]:
    path = Path(os.path.abspath(value))
    before = _plain_stat(path)
    if stat.S_ISREG(before.st_mode):
        result = _file_snapshot(path)
        sidecar = path.with_name(path.name + ".provenance.json")
        present = os.path.lexists(sidecar)
        result["provenance"] = _file_snapshot(sidecar) if present else None
        if os.path.lexists(sidecar) != present:
            raise ValueError("render request asset provenance appeared or disappeared")
        return result
    if not stat.S_ISDIR(before.st_mode):
        raise ValueError("render request asset must be a regular file or directory")
    members = _directory_members(path)
    snapshots = {
        member.relative_to(path).as_posix(): _file_snapshot(member)
        for member in sorted(members)
        if member.is_file()
    }
    if _directory_members(path) != members or _identity(_plain_stat(path)) != _identity(before):
        raise ValueError("render request asset directory changed during inspection")
    return {"path": str(path), "members": snapshots}


def _structured(value: object, *, depth: int = 0) -> Any:
    if depth > 32:
        raise ValueError("render request nesting exceeded its limit")
    if isinstance(value, Path):
        return _path_snapshot(value)
    if isinstance(value, Enum):
        return _structured(value.value, depth=depth + 1)
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("render request numbers must be finite")
        return value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _structured(getattr(value, field.name), depth=depth + 1)
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        if len(value) > 100_000 or any(type(key) is not str for key in value):
            raise ValueError("render request mapping must have bounded string keys")
        return {key: _structured(item, depth=depth + 1) for key, item in value.items()}
    if isinstance(value, list | tuple | frozenset):
        if len(value) > 100_000:
            raise ValueError("render request collection exceeded its limit")
        items = [_structured(item, depth=depth + 1) for item in value]
        return sorted(items) if isinstance(value, frozenset) else items
    raise TypeError(f"unsupported render request value: {type(value).__name__}")


def render_input_digest(inputs: Mapping[str, object]) -> str:
    """Bind explicit resolved inputs and referenced bytes; do not mint authority.

    This does not attest every dynamic native library or mutable process resource.
    Callers must still measure media and consume authenticated review separately.
    """
    before = package_digest()
    value = {"schema": 1, "package_sha256": before, "inputs": _structured(inputs)}
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    if len(encoded) > 16 * 1024 * 1024:
        raise ValueError("render request exceeded its encoded size limit")
    if package_digest() != before:
        raise ValueError("render request package changed during inspection")
    return hashlib.sha256(encoded).hexdigest()
