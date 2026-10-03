"""Bounded raw DBOS journal inspection before any runtime deserialization.

This read-only snapshot is not execution, replay or publication authority. The owned
supervisor must adopt it before launch and independently fence later connections/work.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass
from typing import Any

from hawedit.studio_private import PrivateSqlitePath, StudioStorageError
from hawedit.studio_submissions import SubmissionStore

# Actual complete DBOS2.29.0 publisher schemas, including migration bookkeeping.
_SCHEMAS = frozenset(
    {
        "a7e199f20dde1278b6512693e1352ba760c12af43c9f3f4fce268c25d2c64a69",
        "adcfecb0227887283c09f07d3632527d194628987ccd10943f32efca87bd2da3",
    }
)
_UNSUPPORTED = (
    "notifications",
    "workflow_events",
    "workflow_events_history",
    "streams",
    "workflow_schedules",
)
_QUEUE = "hawedit-studio-v1"
_INTERNAL = "_dbos_internal_queue"
_STATES = {"ENQUEUED", "PENDING", "SUCCESS", "ERROR", "CANCELLED", "MAX_RECOVERY_ATTEMPTS_EXCEEDED"}


@dataclass(frozen=True)
class JournalPolicy:
    """Host-selected expected identity, never a web-supplied grant."""

    workflow_name: str
    application_version: str
    executor_id: str
    application_id: str | None = None
    step_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class JournalSnapshot:
    workflow_ids: tuple[str, ...]
    schema_sha256: str
    total_rows: int
    total_bytes: int


@dataclass
class _Budget:
    rows: int
    bytes: int
    deadline: float
    used_rows: int = 0
    used_bytes: int = 0

    def check(self) -> None:
        if time.perf_counter() >= self.deadline:
            raise StudioStorageError("Raw journal query budget exceeded; work preserved")

    def charge(self, size: int, *, row: bool = False) -> None:
        self.check()
        self.used_bytes += size
        self.used_rows += int(row)
        if self.used_rows > self.rows or self.used_bytes > self.bytes:
            raise StudioStorageError("Raw journal row/byte limit exceeded; no work omitted")


def _policy(policy: JournalPolicy) -> None:
    def text(value: object) -> bool:
        return (
            isinstance(value, str) and 0 < len(value) <= 128 and not any(ord(c) < 32 for c in value)
        )

    if (
        not isinstance(policy, JournalPolicy)
        or not all(
            text(v) for v in (policy.workflow_name, policy.application_version, policy.executor_id)
        )
        or (policy.application_id not in (None, "") and not text(policy.application_id))
        or type(policy.step_names) is not tuple
        or len(policy.step_names) > 32
        or not all(text(v) for v in policy.step_names)
        or len(set(policy.step_names)) != len(policy.step_names)
    ):
        raise ValueError("Raw journal requires a bounded host identity policy")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _constant(value: str) -> Any:
    raise ValueError(f"Nonfinite JSON constant {value}")


def _json(raw: str) -> Any:
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
        pending = [(value, 0)]
        count = 0
        while pending:
            item, depth = pending.pop()
            count += 1
            if count > 10000 or depth > 32:
                raise ValueError("JSON tree limit exceeded")
            if isinstance(item, float) and not math.isfinite(item):
                raise ValueError("Nonfinite JSON number")
            if isinstance(item, str):
                item.encode("utf-8", errors="strict")
            elif isinstance(item, dict):
                pending.extend((child, depth + 1) for child in item.values())
                pending.extend((key, depth + 1) for key in item)
            elif isinstance(item, list):
                pending.extend((child, depth + 1) for child in item)
        return value
    except (ValueError, RecursionError, UnicodeError) as exc:
        raise StudioStorageError("Raw journal JSON payload is invalid or unbounded") from exc


def _error(raw: str) -> None:
    value = _json(raw)
    if (
        not isinstance(value, dict)
        or not {"name", "message"} <= value.keys() <= {"name", "message", "code", "data"}
        or not isinstance(value["name"], str)
        or not value["name"]
        or not isinstance(value["message"], str)
        or (value.get("code") is not None and type(value["code"]) not in (str, int))
    ):
        raise StudioStorageError("Raw journal portable error shape is invalid")


def _projection(names: list[str], cap: int) -> str:
    parts: list[str] = []
    for name in names:
        if not re.fullmatch(r"[a-z_]+", name):
            raise StudioStorageError("Raw journal schema column is unsupported")
        column = f'"{name}"'
        parts.extend(
            (
                f"typeof({column})",
                f"CASE WHEN typeof({column})='text' THEN substr({column},1,{cap + 1}) "
                f"WHEN typeof({column}) IN ('integer','real','null') THEN {column} ELSE NULL END",
                f"length(CAST({column} AS BLOB))",
            )
        )
    return ",".join(parts)


def _read(
    connection: sqlite3.Connection,
    table: str,
    columns: list[tuple[str, str, bool]],
    budget: _Budget,
    *,
    schema: bool = False,
) -> list[dict[str, Any]]:
    cap = 16384 if schema else 131072
    limit = 128 if schema else budget.rows - budget.used_rows
    projection = _projection([name for name, _, _ in columns], cap)
    order = " ORDER BY type,name,tbl_name" if schema else ""
    cursor = connection.execute(f'SELECT {projection} FROM "{table}"{order} LIMIT ?', (limit + 1,))
    records: list[dict[str, Any]] = []
    for row in cursor:
        if len(records) >= limit:
            raise StudioStorageError("Raw journal schema/row limit exceeded; no work omitted")
        budget.charge(sum(row[index + 2] or 0 for index in range(0, len(row), 3)), row=not schema)
        record: dict[str, Any] = {}
        for index, (name, declaration, required) in enumerate(columns):
            kind, value, size = row[index * 3 : index * 3 + 3]
            if kind == "null" and not required:
                record[name] = None
                continue
            expected = (
                {"text"}
                if declaration == "TEXT"
                else {"integer", "real"}
                if declaration == "REAL"
                else {"integer"}
            )
            if kind not in expected:
                raise StudioStorageError(f"Raw journal field type refused: {table}.{name}")
            if size > cap:
                raise StudioStorageError(f"Raw journal field limit refused: {table}.{name}")
            if kind == "text" and len(value.encode("utf-8")) != size:
                raise StudioStorageError(f"Raw journal text projection differs: {table}.{name}")
            if isinstance(value, float) and not math.isfinite(value):
                raise StudioStorageError(f"Raw journal nonfinite field refused: {table}.{name}")
            record[name] = value
        records.append(record)
    return records


def _raw(
    connection: sqlite3.Connection, budget: _Budget
) -> tuple[str, dict[str, list[dict[str, Any]]]]:
    if connection.execute("PRAGMA encoding").fetchone()[0] != "UTF-8":
        raise StudioStorageError("Raw journal schema requires UTF-8 encoding")
    columns = [
        ("type", "TEXT", True),
        ("name", "TEXT", True),
        ("tbl_name", "TEXT", True),
        ("sql", "TEXT", False),
    ]
    schema = _read(connection, "sqlite_schema", columns, budget, schema=True)
    encoded = json.dumps(
        [list(row.values()) for row in schema], ensure_ascii=True, separators=(",", ":")
    ).encode("ascii")
    digest = hashlib.sha256(encoded).hexdigest()
    if digest not in _SCHEMAS:
        raise StudioStorageError("Raw journal schema differs from reviewed DBOS2.29.0")
    tables: dict[str, list[dict[str, Any]]] = {}
    for row in schema:
        if row["type"] != "table":
            continue
        table = row["name"]
        if table in _UNSUPPORTED:
            if connection.execute(f'SELECT 1 FROM "{table}" LIMIT 1').fetchone() is not None:
                raise StudioStorageError(f"Raw journal unsupported nonempty surface: {table}")
            continue
        info = connection.execute(f'PRAGMA table_xinfo("{table}")').fetchall()
        fields = [(column[1], column[2], bool(column[3])) for column in info]
        tables[table] = _read(connection, table, fields, budget)
    budget.check()
    return digest, tables


def _validate(
    tables: dict[str, list[dict[str, Any]]],
    store: SubmissionStore,
    policy: JournalPolicy,
    budget: _Budget,
) -> tuple[str, ...]:
    if tables["dbos_migrations"] != [{"version": 40}]:
        raise StudioStorageError("Raw journal migration version is not exactly40")
    queues = tables["queues"]
    seen = set()
    for queue in queues:
        name = queue["name"]
        internal = name == _INTERNAL
        if (
            name not in (_QUEUE, _INTERNAL)
            or name in seen
            or not isinstance(queue["queue_id"], str)
            or not queue["queue_id"]
            or queue["concurrency"] != (None if internal else 1)
            or queue["worker_concurrency"] != (None if internal else 1)
            or queue["rate_limit_max"] is not None
            or queue["rate_limit_period_sec"] is not None
            or queue["priority_enabled"] != 0
            or queue["partition_queue"] != 0
            or queue["polling_interval_sec"] != 1.0
        ):
            raise StudioStorageError("Raw journal queue policy conflicts with serial studio")
        seen.add(name)
    workflows = tables["workflow_status"]
    ids = [row["workflow_uuid"] for row in workflows]
    if any(
        not isinstance(value, str) or not re.fullmatch(r"studio-[0-9a-f]{64}", value)
        for value in ids
    ) or len(set(ids)) != len(ids):
        raise StudioStorageError("Raw journal workflow identities are invalid or duplicate")
    if workflows and _QUEUE not in seen:
        raise StudioStorageError("Raw journal studio queue is missing")
    budget.check()
    remaining = budget.deadline - time.perf_counter()
    if remaining <= 0:
        budget.check()
    jobs = store.recovery_snapshot(
        ids, max_jobs=budget.rows, max_bytes=budget.bytes, max_seconds=min(10.0, remaining)
    )
    versions = {row["version_name"] for row in tables["application_versions"]}
    for row in tables["application_versions"]:
        if not row["version_id"] or not row["version_name"]:
            raise StudioStorageError("Raw journal application version identity is invalid")
    if workflows and policy.application_version not in versions:
        raise StudioStorageError("Raw journal application version is missing")
    null_fields = (
        "class_name",
        "config_name",
        "request",
        "authenticated_user",
        "assumed_role",
        "deduplication_id",
        "queue_partition_key",
        "forked_from",
        "parent_workflow_id",
        "delay_until_epoch_ms",
        "schedule_name",
        "debounce_deadline_epoch_ms",
    )
    for row, job in zip(workflows, jobs, strict=True):
        if row["serialization"] != "portable_json":
            raise StudioStorageError("Raw journal serialization must be explicit portable_json")
        owner = row["owner_xid"]
        if owner is not None:
            try:
                execution_id = uuid.UUID(owner)
            except ValueError as exc:
                raise StudioStorageError("Raw journal execution identity is invalid") from exc
            if str(execution_id) != owner or execution_id.version != 4:
                raise StudioStorageError("Raw journal execution identity is not canonical UUID4")
        queue_ok = row["queue_name"] == _QUEUE or (
            row["queue_name"] is None
            and row["status"] in ("CANCELLED", "MAX_RECOVERY_ATTEMPTS_EXCEEDED")
        )
        if (
            row["name"] != policy.workflow_name
            or job.workflow_name != policy.workflow_name
            or not queue_ok
            or row["status"] not in _STATES
            or row["application_version"] != policy.application_version
            or row["application_id"] != policy.application_id
            or row["executor_id"] not in (None, policy.executor_id)
            or any(row[field] is not None for field in null_fields)
            or any(
                row[field] != 0
                for field in ("priority", "was_forked_from", "rate_limited", "is_debounced")
            )
        ):
            raise StudioStorageError(
                "Raw journal workflow policy differs from immutable studio job"
            )
        if row["inputs"] is None or _json(row["inputs"]) != {
            "positionalArgs": [job.job_id],
            "namedArgs": {},
        }:
            raise StudioStorageError("Raw journal input must be exactly one immutable job ID")
        for field, expected in (("authenticated_roles", []), ("attributes", {})):
            if row[field] is not None:
                value = _json(row[field])
                if value != expected and not (field == "attributes" and value is None):
                    raise StudioStorageError("Raw journal unauthenticated roles/attributes refused")
        if row["output"] is not None:
            _json(row["output"])
        if row["error"] is not None:
            _error(row["error"])
        output_present = row["output"] is not None
        error_present = row["error"] is not None
        if (
            (row["status"] == "SUCCESS" and (not output_present or error_present))
            or (row["status"] == "ERROR" and (output_present or not error_present))
            or (row["status"] not in ("SUCCESS", "ERROR") and (output_present or error_present))
        ):
            raise StudioStorageError("Raw journal state conflicts with its output/error")
    for row in tables["operation_outputs"]:
        if row["serialization"] != "portable_json":
            raise StudioStorageError("Raw journal step serialization must be portable_json")
        if (
            row["workflow_uuid"] not in ids
            or row["function_name"] not in policy.step_names
            or row["child_workflow_id"] is not None
        ):
            raise StudioStorageError("Raw journal step identity is unsupported")
        if row["output"] is not None:
            _json(row["output"])
        if row["error"] is not None:
            _error(row["error"])
        if (row["output"] is None) == (row["error"] is None):
            raise StudioStorageError("Raw journal step requires exactly one output/error")
    for rows in tables.values():
        for row in rows:
            for value in row.values():
                if type(value) in (int, float) and value < 0:
                    raise StudioStorageError("Raw journal negative numeric field refused")
    budget.check()
    return tuple(ids)


def inspect_studio_journal(
    storage: PrivateSqlitePath,
    submissions: SubmissionStore,
    policy: JournalPolicy,
    *,
    max_rows: int = 1000,
    max_bytes: int = 16 * 1024 * 1024,
    max_seconds: float = 5.0,
) -> JournalSnapshot:
    """Inspect without ORM/getters/launch, repair, pickle or execution-authority tokens."""
    if type(max_rows) is not int or not 1 <= max_rows <= 10000:
        raise ValueError("Raw journal row limit must be an integer1..10000")
    if type(max_bytes) is not int or not 1 <= max_bytes <= 256 * 1024 * 1024:
        raise ValueError("Raw journal byte limit must be an integer1..256MiB")
    if (
        type(max_seconds) not in (int, float)
        or not 0 < max_seconds <= 10
        or not math.isfinite(max_seconds)
    ):
        raise ValueError("Raw journal deadline must be finite, positive and at most10 seconds")
    _policy(policy)
    budget = _Budget(max_rows, max_bytes, time.perf_counter() + max_seconds)
    storage.verify()
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(storage.path.as_uri() + "?mode=ro", uri=True, timeout=0)
        storage.verify()
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA query_only=ON")
        connection.set_progress_handler(lambda: int(time.perf_counter() >= budget.deadline), 1000)
        connection.execute("BEGIN")
        digest, tables = _raw(connection, budget)
        ids = _validate(tables, submissions, policy, budget)
        storage.verify()
        return JournalSnapshot(ids, digest, budget.used_rows, budget.used_bytes)
    except sqlite3.Error as exc:
        if time.perf_counter() >= budget.deadline:
            raise StudioStorageError("Raw journal query budget exceeded; work preserved") from exc
        raise StudioStorageError("Raw journal cannot be inspected safely; work preserved") from exc
    finally:
        if connection is not None:
            connection.set_progress_handler(None, 0)
            connection.close()
        storage.verify()
