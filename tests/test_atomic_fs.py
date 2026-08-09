"""Atomic filesystem publication has identical no-replace semantics on every host."""

from __future__ import annotations

import ctypes
import errno
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from hawedit.atomic_fs import rename_directory_noreplace


def test_native_publication_never_replaces_an_empty_destination(tmp_path: Path) -> None:
    source = tmp_path / "private"
    source.mkdir()
    (source / "payload").write_bytes(b"verified")
    destination = tmp_path / "winner"
    destination.mkdir()
    winner_identity = destination.stat().st_ino

    with pytest.raises(FileExistsError):
        rename_directory_noreplace(source, destination)

    assert destination.stat().st_ino == winner_identity
    assert not tuple(destination.iterdir())
    assert (source / "payload").read_bytes() == b"verified"


def test_posix_publication_uses_the_kernel_no_replace_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "private"
    destination = tmp_path / "winner"
    calls: list[tuple[object, ...]] = []

    class FakeFunction:
        argtypes: object = None
        restype: object = None

        def __call__(self, *args: object) -> int:
            calls.append(args)
            return -1

    function = FakeFunction()
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr(
        ctypes,
        "CDLL",
        lambda *args, **kwargs: SimpleNamespace(renameat2=function),
    )
    monkeypatch.setattr(ctypes, "get_errno", lambda: errno.EEXIST)

    with pytest.raises(FileExistsError):
        rename_directory_noreplace(source, destination)

    assert len(calls) == 1
    assert calls[0][-1] == 1  # Linux RENAME_NOREPLACE.
