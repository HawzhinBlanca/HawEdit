"""Structured logging and JSONL log sinks for HawEdit — Phase 1.3.

Provides per-module loggers, rotating JSONL file handlers in the pipeline
working directory, and adapters for the events subsystem.
"""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from hawedit.events import EventSink, RunEvent, RunState

__all__ = [
    "EventLogHandler",
    "JsonlFormatter",
    "configure_logging",
    "get_logger",
]

_DEFAULT_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s"


class JsonlFormatter(logging.Formatter):
    """Formats log records as valid, single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp_ms": int(record.created * 1000),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "filename": record.filename,
            "lineno": record.lineno,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # Include custom extra attributes if passed in extra={}
        for key, val in record.__dict__.items():
            if (
                key not in logging.LogRecord.__dict__
                and not key.startswith("_")
                and key not in payload
            ):
                try:
                    json.dumps(val)  # Check JSON serializability
                    payload[key] = val
                except (TypeError, ValueError):
                    payload[key] = str(val)
        return json.dumps(payload, ensure_ascii=False)


class EventLogHandler(logging.Handler):
    """Logging handler that translates structured log records into RunEvent objects."""

    def __init__(
        self,
        run_id: str,
        sink: EventSink,
        *,
        stage: str = "pipeline",
    ) -> None:
        super().__init__()
        self.run_id = run_id
        self.sink = sink
        self.stage = stage
        self._sequence = 0

    def emit(self, record: logging.LogRecord) -> None:
        self._sequence += 1
        # Extract stage or reason if provided in extra
        stage = getattr(record, "stage", self.stage)
        state_str = getattr(record, "run_state", None)
        if state_str == "completed":
            state = RunState.COMPLETED
        elif state_str == "started":
            state = RunState.STARTED
        elif state_str == "skipped":
            state = RunState.SKIPPED
        elif state_str == "billed":
            state = RunState.BILLED
        else:
            state = RunState.STARTED if record.levelno < logging.WARNING else RunState.COMPLETED

        reason = getattr(record, "reason", "") if state == RunState.SKIPPED else ""
        try:
            event = RunEvent(
                run_id=self.run_id,
                sequence=self._sequence,
                at_ms=int(record.created * 1000),
                stage=stage,
                state=state,
                reason=reason,
                model=str(getattr(record, "model", "")),
                tokens=int(getattr(record, "tokens", 0)),
                cost_usd_estimate=float(getattr(record, "cost_usd_estimate", 0.0)),
                candidate_id=str(getattr(record, "candidate_id", "")),
            )
            self.sink(event)
        except Exception:
            self.handleError(record)


def get_logger(name: str = "hawedit") -> logging.Logger:
    """Obtain a namespaced logger for a HawEdit module."""
    if not name.startswith("hawedit") and name != "":
        name = f"hawedit.{name}"
    return logging.getLogger(name)


def configure_logging(
    work_dir: Path | None = None,
    level: int | str = logging.INFO,
    *,
    log_filename: str = "hawedit.jsonl",
    max_bytes: int = 10_485_760,  # 10 MiB
    backup_count: int = 3,
    jsonl: bool = True,
) -> logging.Logger:
    """Configure HawEdit root logger with rotating file handler and console handler."""
    root_logger = logging.getLogger("hawedit")
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)
    root_logger.setLevel(level)

    # Avoid duplicate handlers if configure_logging is called multiple times
    root_logger.handlers.clear()

    # 1. Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_formatter = logging.Formatter(_DEFAULT_LOG_FORMAT)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # 2. Rotating file handler (if work_dir is provided)
    if work_dir is not None:
        work_dir = Path(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        log_path = work_dir / log_filename
        file_handler = RotatingFileHandler(
            str(log_path),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        if jsonl:
            file_handler.setFormatter(JsonlFormatter())
        else:
            file_handler.setFormatter(console_formatter)
        root_logger.addHandler(file_handler)

    return root_logger
