"""Real filesystem competition during a real caption/boundary encode."""

from __future__ import annotations

import os
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import FrameType

from hawedit.clip import Clip
from hawedit.render import render_clip


@contextmanager
def observed_render_inputs() -> Iterator[list[Clip]]:
    inputs: list[Clip] = []
    previous = sys.getprofile()

    def observe(frame: FrameType, event: str, argument: object) -> None:
        if event == "call" and frame.f_code is render_clip.__code__:
            value = frame.f_locals["clip"]
            assert isinstance(value, Clip)
            inputs.append(value)
        if previous is not None:
            previous(frame, event, argument)

    sys.setprofile(observe)
    try:
        yield inputs
    finally:
        sys.setprofile(previous)


@contextmanager
def competing_artifact(
    work: Path, revision_id: str, suffix: str, original_mp4: Path
) -> Iterator[threading.Event]:
    directory = work / "revisions"
    target = directory / f"{revision_id}.{suffix}"
    stop = threading.Event()
    published = threading.Event()
    failures: list[BaseException] = []

    def compete() -> None:
        end = time.monotonic() + 15
        try:
            while not stop.is_set():
                if (directory / f"{revision_id}.ass").exists() or tuple(
                    directory.glob(f".{revision_id}.ass-*.tmp")
                ):
                    if suffix == "mp4":
                        os.link(original_mp4, target)
                    else:
                        with target.open("xb") as stream:
                            stream.write(b"competing sidecar: preserve exact original bytes\n")
                    published.set()
                    return
                if time.monotonic() >= end:
                    raise AssertionError("No real revision caption preparation observed")
                time.sleep(0.001)
        except BaseException as exc:
            failures.append(exc)

    thread = threading.Thread(target=compete, name="revision-artifact-competitor")
    thread.start()
    try:
        yield published
    finally:
        stop.set()
        thread.join(5)
        assert not thread.is_alive(), "Original artifact competitor did not exit"
        if failures:
            raise failures[0]
