"""Unit tests for HawEdit structured logging and JSONL sinks — Phase 1.3."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from hawedit.events import RunEvent, RunState
from hawedit.log import (
    EventLogHandler,
    JsonlFormatter,
    configure_logging,
    get_logger,
)


def test_get_logger_namespaces_correctly() -> None:
    """get_logger prefixes names with hawedit."""
    log1 = get_logger("pipeline")
    assert log1.name == "hawedit.pipeline"

    log2 = get_logger("hawedit.asr")
    assert log2.name == "hawedit.asr"

    log3 = get_logger()
    assert log3.name == "hawedit"


def test_jsonl_formatter_emits_valid_json() -> None:
    """JsonlFormatter produces single-line valid JSON with expected fields."""
    formatter = JsonlFormatter()
    record = logging.LogRecord(
        name="hawedit.test",
        level=logging.INFO,
        pathname="test.py",
        lineno=42,
        msg="Kurdish subtitle test: %s",
        args=("سڵاو",),
        exc_info=None,
    )
    formatted = formatter.format(record)
    assert "\n" not in formatted

    data = json.loads(formatted)
    assert data["logger"] == "hawedit.test"
    assert data["level"] == "INFO"
    assert data["message"] == "Kurdish subtitle test: سڵاو"
    assert data["lineno"] == 42
    assert "timestamp_ms" in data


def test_jsonl_formatter_includes_custom_extras_and_exceptions() -> None:
    """Formatter includes extra fields and formatted traceback."""
    formatter = JsonlFormatter()
    try:
        raise ValueError("Something broke")
    except ValueError:
        import sys

        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="hawedit.test",
        level=logging.ERROR,
        pathname="test.py",
        lineno=50,
        msg="Failure occurred",
        args=(),
        exc_info=exc_info,
    )
    record.__dict__["stage"] = "stage4_editorial"
    record.__dict__["tokens"] = 1250

    formatted = formatter.format(record)
    data = json.loads(formatted)
    assert data["level"] == "ERROR"
    assert data["stage"] == "stage4_editorial"
    assert data["tokens"] == 1250
    assert "exception" in data
    assert "ValueError: Something broke" in data["exception"]


def test_configure_logging_creates_rotating_file(tmp_path: Path) -> None:
    """configure_logging creates working directory and writes JSONL records."""
    log_dir = tmp_path / "work_log"
    logger = configure_logging(work_dir=log_dir, log_filename="test_run.jsonl")

    logger.info("First message in Kurdish: دەستپێکردنی پڕۆسە")
    logger.warning("Second warning message")

    log_file = log_dir / "test_run.jsonl"
    assert log_file.is_file()

    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2

    row1 = json.loads(lines[0])
    assert row1["level"] == "INFO"
    assert "دەستپێکردنی پڕۆسە" in row1["message"]

    row2 = json.loads(lines[1])
    assert row2["level"] == "WARNING"


def test_event_log_handler_bridges_to_event_sink() -> None:
    """EventLogHandler emits RunEvent instances to an EventSink."""
    emitted: list[RunEvent] = []

    def sink(event: RunEvent) -> None:
        emitted.append(event)

    handler = EventLogHandler(run_id="run-123", sink=sink, stage="stage1_transcript")
    logger = logging.getLogger("test.event_bridge")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    record = logging.LogRecord(
        name="test.event_bridge",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Stage started",
        args=(),
        exc_info=None,
    )
    record.__dict__["run_state"] = "started"
    handler.emit(record)

    assert len(emitted) == 1
    ev = emitted[0]
    assert ev.run_id == "run-123"
    assert ev.sequence == 1
    assert ev.stage == "stage1_transcript"
    assert ev.state == RunState.STARTED
