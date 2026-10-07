"""Private transactional observations for initial protected producer attempts.

This journal is not execution, retry, billing-settlement or publication authority.
Retained attempts block automatic relaunch, including after process exit. The
supervisor must separately prove quiescence and reconcile effects before retry.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from hawedit.events import RunEvent, RunState
from hawedit.studio_generation import project_events
from hawedit.studio_private import PrivateSqlitePath, StudioStorageError
from hawedit.studio_submissions import SubmissionStore

__all__ = ["AttemptConflict", "AttemptStore", "StoredAttempt"]

_TERMINAL = {"awaiting-review", "partially-completed", "failed", "interrupted", "cancelled"}
_MAX_EVENTS = 4096
_MAX_JOBS = 1024
_MAX_EVENT_BYTES = 16 * 1024
_MAX_RECORD_BYTES = 8 * 1024
_MAX_STREAM_BYTES = 4 * 1024 * 1024
_SCHEMA = {
    "attempts": "CREATE TABLE attempts (job_id TEXT PRIMARY KEY, state TEXT NOT NULL, "
    "record_json TEXT NOT NULL)",
    "events": "CREATE TABLE events (job_id TEXT NOT NULL REFERENCES attempts(job_id), "
    "sequence INTEGER NOT NULL, event_json TEXT NOT NULL, PRIMARY KEY(job_id,sequence))",
    "one_running_attempt": "CREATE UNIQUE INDEX one_running_attempt ON attempts((1)) "
    "WHERE state='running'",
}


class AttemptConflict(ValueError):
    """Retained execution/event evidence conflicts; reconciliation is required."""


@dataclass(frozen=True, slots=True)
class StoredAttempt:
    job_id: str
    number: int
    source_sha256: str
    request_sha256: str
    execution_binding_sha256: str
    run_id: str
    state: str
    diagnostic: str
    created_ms: int
    finished_ms: int | None
    last_sequence: int


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _load_json(raw: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("Attempt JSON contains duplicate fields")
            result[key] = value
        return result

    def constant(value: str) -> Any:
        raise ValueError(f"Attempt JSON contains a nonfinite constant: {value}")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def _text(value: object, limit: int, *, empty: bool = False) -> str:
    if (
        not isinstance(value, str)
        or (not empty and not value.strip())
        or len(value.encode("utf-8")) > limit
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ValueError("Attempt text is empty, unsafe or exceeds its byte limit")
    return value


def _integer(value: object, minimum: int, maximum: int = 2**63 - 1) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("Attempt integer is outside its strict finite range")
    return value


def _job_id(value: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"studio-[a-f0-9]{64}", value) is None:
        raise ValueError("Invalid studio attempt job ID")


def _validate_event(event: RunEvent) -> str:
    if not isinstance(event, RunEvent) or not isinstance(event.state, RunState):
        raise ValueError("A genuine typed run event is required")
    _text(event.run_id, 128)
    _text(event.stage, 128)
    _text(event.reason, 4096, empty=True)
    _text(event.model, 256, empty=True)
    _text(event.candidate_id, 256, empty=True)
    _integer(event.sequence, 1, _MAX_EVENTS)
    _integer(event.at_ms, 0)
    _integer(event.tokens, 0)
    cost = event.cost_usd_estimate
    if type(cost) not in (int, float) or not math.isfinite(cost) or not 0 <= cost <= 1_000_000:
        raise ValueError("Attempt event cost must be finite and bounded")
    if event.state is not RunState.BILLED and (
        event.model or event.candidate_id or event.tokens != 0 or cost != 0
    ):
        raise ValueError("Non-billed event carries billing fields")
    # The legacy constructor is intentionally unchanged; enforce the durable boundary here.
    event.__post_init__()
    raw = _json(event.to_dict())
    if len(raw.encode("utf-8")) > _MAX_EVENT_BYTES:
        raise ValueError("Attempt event exceeds its record limit")
    return raw


def _decode_event(raw: str) -> RunEvent:
    value = _load_json(raw)
    if not isinstance(value, dict):
        raise ValueError("Attempt event is not an object")
    for name in ("run_id", "stage", "state", "reason"):
        if not isinstance(value.get(name), str):
            raise ValueError("Attempt event text type differs")
    _integer(value.get("sequence"), 1, _MAX_EVENTS)
    _integer(value.get("at_ms"), 0)
    if "tokens" in value:
        _integer(value["tokens"], 0)
    for name in ("model", "candidate_id"):
        if name in value and not isinstance(value[name], str):
            raise ValueError("Attempt billing text type differs")
    if "cost_usd_estimate" in value and type(value["cost_usd_estimate"]) not in (int, float):
        raise ValueError("Attempt cost type differs")
    event = RunEvent.from_dict(value)
    _validate_event(event)
    if value != event.to_dict():
        raise ValueError("Attempt event contains foreign or noncanonical fields")
    return event


class AttemptStore:
    def __init__(
        self, path: Path, submissions: SubmissionStore, *, timeout_seconds: float = 5.0
    ) -> None:
        if not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 10:
            raise ValueError("Attempt storage timeout must be positive and at most 10 seconds")
        # Reject overlap before constructing a path (and before any schema mutation).
        absolute = path.absolute()
        if absolute.parent != submissions.path.parent or absolute == submissions.path:
            raise StudioStorageError("Attempt journal must be distinct and colocated with outbox")
        self._storage = PrivateSqlitePath(absolute)
        self.path = self._storage.path
        self.submissions = submissions
        self.timeout_seconds = timeout_seconds
        with self._connection(initialize=True) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("BEGIN IMMEDIATE")
            self._schema(connection, initialize=True)
            if connection.execute("PRAGMA user_version").fetchone()[0] == 0:
                for statement in _SCHEMA.values():
                    connection.execute(statement)
                connection.execute("PRAGMA user_version=1")

    @staticmethod
    def _schema(connection: sqlite3.Connection, *, initialize: bool = False) -> None:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        rows = connection.execute("SELECT name,sql FROM sqlite_master LIMIT 17").fetchall()
        if initialize and version == 0 and not rows:
            return
        expected: dict[str, str | None] = dict(_SCHEMA)
        expected.update(sqlite_autoindex_attempts_1=None, sqlite_autoindex_events_1=None)
        if version != 1 or len(rows) != len(expected) or dict(rows) != expected:
            raise StudioStorageError("Attempt journal schema is foreign or unsupported")

    @contextmanager
    def _connection(self, *, initialize: bool = False) -> Iterator[sqlite3.Connection]:
        connection: sqlite3.Connection | None = None
        try:
            self._storage.verify()
            size = self.path.stat().st_size
            for suffix in ("-wal", "-shm", "-journal"):
                with suppress(FileNotFoundError):
                    size += self.path.with_name(self.path.name + suffix).stat().st_size
            if size > 64 * 1024 * 1024:
                raise StudioStorageError("Attempt journal exceeds its storage inspection budget")
            connection = sqlite3.connect(
                self.path.as_uri() + "?mode=rw", uri=True, timeout=self.timeout_seconds
            )
            self._storage.verify()
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA synchronous=FULL")
            deadline = time.monotonic() + 10
            connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            self._schema(connection, initialize=initialize)
            with connection:
                yield connection
                self._schema(connection)
                self._storage.verify()
            self._storage.verify()
        except (sqlite3.Error, OSError) as exc:
            raise StudioStorageError(f"Attempt storage failed: {exc}") from exc
        finally:
            if connection is not None:
                connection.close()
                self._storage.verify()

    def _record(self, connection: sqlite3.Connection, job_id: str) -> StoredAttempt:
        row = connection.execute(
            "SELECT substr(job_id,1,72),length(CAST(job_id AS BLOB)),"
            "substr(state,1,32),length(CAST(state AS BLOB)),"
            "substr(record_json,1,8193),length(CAST(record_json AS BLOB)) "
            "FROM attempts WHERE job_id=?",
            (job_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Studio attempt {job_id} not found")
        try:
            for text, size, limit in (
                (row[0], row[1], 71),
                (row[2], row[3], 32),
                (row[4], row[5], _MAX_RECORD_BYTES),
            ):
                if not isinstance(text, str) or len(text.encode("utf-8")) != size or size > limit:
                    raise ValueError("Attempt bounded text projection differs")
            value = _load_json(row[4])
            if not isinstance(value, dict) or set(value) != set(StoredAttempt.__dataclass_fields__):
                raise ValueError("Attempt record fields differ")
            record = StoredAttempt(**value)
            job = self.submissions.get(job_id)
            if (
                record.job_id != job_id
                or row[0] != job_id
                or record.source_sha256 != job.source_sha256
                or record.request_sha256 != job.request_sha256
                or record.execution_binding_sha256 != job.execution_binding_sha256
                or record.state != row[2]
                or record.state not in _TERMINAL | {"running"}
            ):
                raise ValueError("Attempt submission identity or state differs")
            _integer(record.number, 1, 1)
            _integer(record.created_ms, 1)
            _integer(record.last_sequence, 0, _MAX_EVENTS)
            _text(record.run_id, 128)
            _text(record.diagnostic, 2048, empty=True)
            if record.state == "running":
                if record.finished_ms is not None or record.diagnostic:
                    raise ValueError("Running attempt has terminal fields")
            else:
                _integer(record.finished_ms, record.created_ms)
                _text(record.diagnostic, 2048)
            return record
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
            raise StudioStorageError(f"Attempt evidence refused: {exc}") from exc

    @staticmethod
    def _events(connection: sqlite3.Connection, record: StoredAttempt) -> tuple[RunEvent, ...]:
        count, size = connection.execute(
            "SELECT count(*),coalesce(sum(length(CAST(event_json AS BLOB))),0) "
            "FROM events WHERE job_id=?",
            (record.job_id,),
        ).fetchone()
        if count != record.last_sequence or count > _MAX_EVENTS or size > _MAX_STREAM_BYTES:
            raise StudioStorageError("Attempt event cursor or stream budget differs")
        rows = connection.execute(
            "SELECT sequence,substr(event_json,1,16385),length(CAST(event_json AS BLOB)) "
            "FROM events WHERE job_id=? ORDER BY sequence LIMIT 4097",
            (record.job_id,),
        ).fetchall()
        events: list[RunEvent] = []
        try:
            for expected, (sequence, raw, length) in enumerate(rows, 1):
                _integer(sequence, expected, expected)
                if (
                    not isinstance(raw, str)
                    or length > _MAX_EVENT_BYTES
                    or len(raw.encode("utf-8")) != length
                ):
                    raise ValueError("Attempt event bounded projection differs")
                event = _decode_event(raw)
                if event.sequence != expected or event.run_id != record.run_id:
                    raise ValueError("Attempt event sequence or run identity differs")
                events.append(event)
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
            raise StudioStorageError(f"Attempt events refused: {exc}") from exc
        return tuple(events)

    def begin(self, job_id: str, run_id: str) -> StoredAttempt:
        _job_id(job_id)
        _text(run_id, 128)
        job = self.submissions.get(job_id)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            ids = connection.execute(
                "SELECT substr(job_id,1,72),length(CAST(job_id AS BLOB)) FROM attempts LIMIT 1025"
            ).fetchall()
            if len(ids) >= _MAX_JOBS:
                raise StudioStorageError("Attempt journal job budget reached; preserve history")
            for retained_id, length in ids:
                if not isinstance(retained_id, str) or length != 71:
                    raise StudioStorageError("Retained attempt job identity differs")
                try:
                    _job_id(retained_id)
                except ValueError as exc:
                    raise StudioStorageError("Retained attempt job identity differs") from exc
                record = self._record(connection, retained_id)
                self._events(connection, record)
                if retained_id == job_id:
                    raise AttemptConflict(
                        "Attempt retained; explicit supervisor reconciliation required"
                    )
                if record.state == "running":
                    raise AttemptConflict(
                        "Another attempt remains running; reconciliation required"
                    )
            record = StoredAttempt(
                job_id,
                1,
                job.source_sha256,
                job.request_sha256,
                job.execution_binding_sha256,
                run_id,
                "running",
                "",
                time.time_ns() // 1_000_000,
                None,
                0,
            )
            connection.execute(
                "INSERT INTO attempts VALUES (?,?,?)", (job_id, record.state, _json(asdict(record)))
            )
            return record

    def get(self, job_id: str) -> StoredAttempt:
        _job_id(job_id)
        with self._connection() as connection:
            connection.execute("BEGIN")
            record = self._record(connection, job_id)
            self._events(connection, record)
            return record

    def events(self, job_id: str) -> tuple[RunEvent, ...]:
        _job_id(job_id)
        with self._connection() as connection:
            connection.execute("BEGIN")
            return self._events(connection, self._record(connection, job_id))

    def append(self, job_id: str, event: RunEvent) -> None:
        _job_id(job_id)
        raw = _validate_event(event)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            record = self._record(connection, job_id)
            self._events(connection, record)
            if (
                record.state != "running"
                or event.run_id != record.run_id
                or event.sequence != record.last_sequence + 1
            ):
                raise AttemptConflict("Event does not continue the running bound attempt")
            stream_bytes = connection.execute(
                "SELECT coalesce(sum(length(CAST(event_json AS BLOB))),0) "
                "FROM events WHERE job_id=?",
                (job_id,),
            ).fetchone()[0]
            if stream_bytes + len(raw.encode("utf-8")) > _MAX_STREAM_BYTES:
                raise StudioStorageError("Attempt event stream budget reached")
            connection.execute("INSERT INTO events VALUES (?,?,?)", (job_id, event.sequence, raw))
            updated = replace(record, last_sequence=event.sequence)
            connection.execute(
                "UPDATE attempts SET record_json=? WHERE job_id=?", (_json(asdict(updated)), job_id)
            )

    def finish(self, job_id: str, state: str, diagnostic: str) -> None:
        _job_id(job_id)
        if state not in _TERMINAL:
            raise ValueError(
                "Only a terminal private attempt outcome is supported; never completed"
            )
        _text(diagnostic, 2048)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            record = self._record(connection, job_id)
            self._events(connection, record)
            if record.state != "running":
                raise AttemptConflict("Terminal attempt is immutable; reconciliation is separate")
            updated = replace(
                record,
                state=state,
                diagnostic=diagnostic,
                finished_ms=max(record.created_ms, time.time_ns() // 1_000_000),
            )
            connection.execute(
                "UPDATE attempts SET state=?,record_json=? WHERE job_id=?",
                (state, _json(asdict(updated)), job_id),
            )

    def projection(self, job_id: str) -> dict[str, Any]:
        _job_id(job_id)
        with self._connection() as connection:
            connection.execute("BEGIN")
            record = self._record(connection, job_id)
            projected = project_events(self._events(connection, record), attempt=record.number)
            projected.update(
                state=record.state,
                diagnostic=record.diagnostic,
                publication_verified=False,
                requires_reconciliation=True,
            )
            return projected
