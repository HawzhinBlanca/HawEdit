"""Actual file write faults and decoded ingest, not provider or release evidence."""

from __future__ import annotations

import io
import json
from collections.abc import Iterator
from pathlib import Path
from typing import TextIO

import pytest

from hawedit.events import JsonlEventSink, RunEvent, RunEventLog, read_events
from hawedit.pipeline import run_pipeline

MEDIA = Path(__file__).parent / "fixtures" / "kurdish-speech-3cuts.mp4"


class _Journal:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: TextIO = path.open("x", encoding="utf-8")
        self.flip_after_first = False

    def __call__(self, event: RunEvent) -> None:
        self.handle.write(json.dumps(event.to_dict()) + "\n")
        self.handle.flush()
        if self.flip_after_first and event.sequence == 1:
            self.readonly()

    def readonly(self) -> None:
        self.handle.close()
        self.handle = self.path.open("r", encoding="utf-8")

    def recover(self) -> None:
        self.handle.close()
        self.handle = self.path.open("a", encoding="utf-8")

    def close(self) -> None:
        self.handle.close()


@pytest.fixture
def journal(tmp_path: Path) -> Iterator[_Journal]:
    sink = _Journal(tmp_path / "events.jsonl")
    try:
        yield sink
    finally:
        sink.close()


def _emit(log: RunEventLog, kind: str) -> None:
    if kind == "started":
        log.started("editorial")
    elif kind == "finished":
        log.finished("editorial")
    else:
        # Event validation only; no provider call or measured cost.
        log.billed("editorial", "no-provider-call", 1, 0.001)


@pytest.mark.parametrize("kind", ["started", "finished", "billed"])
def test_event_write_failure_is_sticky_after_actual_file_recovery(
    journal: _Journal, kind: str
) -> None:
    log = RunEventLog("actual-file", journal)
    log.started("ingest")
    original = journal.path.read_bytes()
    journal.readonly()
    with pytest.raises(RuntimeError, match="persistence") as failed:
        _emit(log, kind)
    assert type(failed.value).__name__ == "EventPersistenceError"
    assert isinstance(failed.value.__cause__, io.UnsupportedOperation)
    sequence = log._sequence
    journal.recover()
    for later in ("started", "finished", "billed"):
        with pytest.raises(RuntimeError, match="persistence") as refused:
            _emit(log, later)
        assert refused.value.__cause__ is failed.value.__cause__
    with pytest.raises(RuntimeError, match="persistence"):
        log.require_persistence()
    assert log._sequence == sequence
    assert journal.path.read_bytes() == original
    assert len(read_events(journal.path)) == 1


def test_pipeline_propagates_actual_ingest_event_storage_failure(
    journal: _Journal, tmp_path: Path
) -> None:
    journal.flip_after_first = True
    with pytest.raises(RuntimeError, match="persistence") as failed:
        run_pipeline(MEDIA, tmp_path / "work", on_event=journal)
    assert type(failed.value).__name__ == "EventPersistenceError"
    assert isinstance(failed.value.__cause__, io.UnsupportedOperation)
    committed = read_events(journal.path)
    assert len(committed) == 1
    assert committed[0].stage == "ingest"
    assert committed[0].state.value == "started"
    assert (tmp_path / "work" / "stage0").is_dir()


def test_invalid_event_does_not_consume_sequence_or_fence_healthy_sink(journal: _Journal) -> None:
    log = RunEventLog("actual-file", journal)
    with pytest.raises(ValueError, match="names no stage"):
        log.started("")
    assert journal.path.read_bytes() == b""
    first = log.started("ingest")
    assert first.sequence == 1
    log.require_persistence()
    assert read_events(journal.path) == (first,)


def test_closed_jsonl_sink_latches_original_write_error(tmp_path: Path) -> None:
    path = tmp_path / "legacy.jsonl"
    sink = JsonlEventSink(path)
    log = RunEventLog("actual-closed-file", sink)
    sink.close()
    with pytest.raises(RuntimeError, match="persistence") as failed:
        log.started("ingest")
    assert type(failed.value).__name__ == "EventPersistenceError"
    assert isinstance(failed.value.__cause__, ValueError)
    with pytest.raises(RuntimeError, match="persistence") as refused:
        log.require_persistence()
    assert refused.value.__cause__ is failed.value.__cause__
    assert path.read_bytes() == b""
