"""Schedule a real filesystem mutation at an actual validation exception."""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from types import FrameType
from typing import TYPE_CHECKING

import pytest

from hawedit.studio_private import PrivateSqlitePath, StudioStorageError

if TYPE_CHECKING:
    from _typeshed import TraceFunction


def _sidecar_transition(tmp_path: Path, *, replace: bool) -> None:
    storage = PrivateSqlitePath(tmp_path / "private" / "billing.sqlite3")
    outside = tmp_path / "retained-original"
    original = b"original evidence stays intact"
    outside.write_bytes(original)
    sidecar = storage.path.with_name(storage.path.name + "-shm")
    os.link(outside, sidecar)
    observed = threading.Event()
    changed = threading.Event()
    errors: list[BaseException] = []

    def mutate() -> None:
        try:
            assert observed.wait(3), "Actual validation exception was not observed"
            sidecar.unlink()
            if replace:
                sidecar.write_bytes(b"new uninspected private sidecar")
            changed.set()
        except BaseException as exc:
            errors.append(exc)
            changed.set()

    # The observer only schedules the other thread after the real exception.
    # No function, stat result, return value, frame local or kernel result is replaced.
    def observe(
        frame: FrameType, event: str, argument: object
    ) -> TraceFunction:
        if (
            event == "exception"
            and frame.f_code.co_name == "_plain"
            and frame.f_globals.get("__name__") == "hawedit.studio_private"
            and frame.f_locals.get("path") == sidecar
        ):
            assert isinstance(argument, tuple) and argument[0] is StudioStorageError
            observed.set()
            assert changed.wait(3), "Actual filesystem transition did not finish"
        return observe

    worker = threading.Thread(target=mutate)
    before = sys.gettrace()
    worker.start()
    try:
        sys.settrace(observe)
        if replace:
            with pytest.raises(StudioStorageError, match="linked|nonregular"):
                storage.verify()
        else:
            storage.verify()
    finally:
        sys.settrace(before)
        worker.join(3)
    assert not worker.is_alive() and not errors
    assert observed.is_set() and changed.is_set()
    assert outside.read_bytes() == original and storage.path.read_bytes() == b""
    assert sidecar.exists() is replace
    if replace:
        assert sidecar.read_bytes() == b"new uninspected private sidecar"
    else:
        storage.verify()


def test_studio_private_disappearing_invalid_sidecar_is_absent_not_adopted(tmp_path: Path) -> None:
    _sidecar_transition(tmp_path, replace=False)


def test_studio_private_changed_invalid_sidecar_is_not_adopted(tmp_path: Path) -> None:
    _sidecar_transition(tmp_path, replace=True)
