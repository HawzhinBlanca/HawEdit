"""Immutable studio request identity and the local-to-DBOS submission outbox.

This ledger records dispatch, not generation success or publication authority. Execution
bindings must be verified by the protected worker; accepting their digest is not preflight.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hawedit.studio_generation import GenerationRequest, PreparedGeneration
from hawedit.studio_private import PrivateDirectory, PrivateSqlitePath, StudioStorageError

__all__ = ["StoredSubmission", "StudioStorageError", "SubmissionConflict", "SubmissionStore"]

_MAX_SNAPSHOT_BYTES = 128 * 1024
_JOB_ID = re.compile(r"studio-[a-f0-9]{64}\Z")
_WORKER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_CONFIG_FIELDS = {
    "editorial",
    "max_clips",
    "hook_text",
    "screener",
    "producers",
    "pipeline_source_sha256",
}


class SubmissionConflict(ValueError):
    """A client token is already bound to different immutable execution content."""


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hex(value: object, length: int) -> bool:
    return isinstance(value, str) and re.fullmatch(f"[a-f0-9]{{{length}}}", value) is not None


def _identity(snapshot: dict[str, Any]) -> str:
    if set(snapshot) != {
        "source_id",
        "source_sha256",
        "configuration",
        "request_sha256",
        "execution_binding_sha256",
        "workflow_name",
        "arguments",
    }:
        raise ValueError("Unexpected submission snapshot fields")
    if not _hex(snapshot["source_id"], 32) or not _hex(snapshot["source_sha256"], 64):
        raise ValueError("Invalid submission source identity")
    if not _hex(snapshot["execution_binding_sha256"], 64):
        raise ValueError("An execution-binding digest is required")
    worker = snapshot["workflow_name"]
    if not isinstance(worker, str) or not _WORKER.fullmatch(worker):
        raise ValueError("A bounded registered workflow name is required")
    config = snapshot["configuration"]
    if (
        not isinstance(config, dict)
        or set(config) != _CONFIG_FIELDS
        or not isinstance(config["editorial"], dict)
        or not isinstance(config["producers"], dict)
        or not _hex(config["pipeline_source_sha256"], 64)
    ):
        raise ValueError("Invalid prepared configuration snapshot")
    request = hashlib.sha256(
        _canonical(
            {
                "source_id": snapshot["source_id"],
                "source_sha256": snapshot["source_sha256"],
                "configuration": config,
            }
        ).encode("utf-8")
    ).hexdigest()
    if snapshot["request_sha256"] != request:
        raise ValueError("Prepared request digest does not match its snapshot")
    arguments = snapshot["arguments"]
    if (
        not isinstance(arguments, list)
        or not arguments
        or any(
            not isinstance(arg, str)
            or not arg
            or len(arg) > 4096
            or any(ord(char) < 32 for char in arg)
            or arg.startswith("--work-dir=")
            for arg in arguments
        )
    ):
        raise ValueError("Invalid immutable submission arguments")
    execution = {
        key: snapshot[key]
        for key in ("request_sha256", "execution_binding_sha256", "workflow_name", "arguments")
    }
    return "studio-" + hashlib.sha256(_canonical(execution).encode("utf-8")).hexdigest()


def _job_id(value: str) -> None:
    if not _JOB_ID.fullmatch(value):
        raise ValueError("Invalid studio job ID")


@dataclass(frozen=True, slots=True)
class StoredSubmission:
    job_id: str
    source_id: str
    source_sha256: str
    request_sha256: str
    execution_binding_sha256: str
    workflow_name: str
    arguments: tuple[str, ...]
    configuration_json: str
    dispatch_state: str
    last_error: str | None
    created_at: float


class SubmissionStore:
    def __init__(self, path: Path, *, timeout_seconds: float = 5.0) -> None:
        if not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 10:
            raise ValueError("SQLite timeout must be finite, positive and at most 10 seconds")
        self._storage = PrivateSqlitePath(path)
        self.path = self._storage.path
        self.timeout_seconds = timeout_seconds
        with self._connection() as connection:
            self._check_schema(connection)
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("BEGIN IMMEDIATE")
            version = self._check_schema(connection)
            if version == 0:
                connection.execute(
                    "CREATE TABLE submissions (job_id TEXT PRIMARY KEY, "
                    "snapshot_json TEXT NOT NULL, dispatch_state TEXT NOT NULL "
                    "CHECK(dispatch_state IN ('pending','confirmed')), "
                    "last_error TEXT, created_at REAL NOT NULL)"
                )
                connection.execute(
                    "CREATE TABLE client_tokens (token TEXT PRIMARY KEY, job_id TEXT NOT NULL "
                    "REFERENCES submissions(job_id))"
                )
                connection.execute("PRAGMA user_version=1")
            else:
                connection.execute(
                    "SELECT job_id,snapshot_json,dispatch_state,last_error,created_at "
                    "FROM submissions LIMIT 0"
                )
                connection.execute("SELECT token,job_id FROM client_tokens LIMIT 0")

    @staticmethod
    def _check_schema(connection: sqlite3.Connection) -> int:
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if version not in (0, 1):
            raise StudioStorageError(f"Unsupported studio submission schema {version}")
        if (
            version == 0
            and connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' LIMIT 1"
            ).fetchone()
        ):
            raise StudioStorageError("Unversioned foreign database refused")
        return version

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection: sqlite3.Connection | None = None
        try:
            self._storage.verify()
            connection = sqlite3.connect(self.path, timeout=self.timeout_seconds)
            self._storage.verify()
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA synchronous=FULL")
            with connection:
                yield connection
                self._storage.verify()
            self._storage.verify()
        except (sqlite3.Error, OSError) as exc:
            raise StudioStorageError(f"Studio submission storage failed: {exc}") from exc
        finally:
            if connection is not None:
                connection.close()
                self._storage.verify()

    @staticmethod
    def _decode(row: sqlite3.Row) -> StoredSubmission:
        try:
            raw = row["snapshot_json"]
            if not isinstance(raw, str) or row["snapshot_bytes"] > _MAX_SNAPSHOT_BYTES:
                raise ValueError("Submission snapshot exceeds the record limit")
            snapshot = json.loads(raw)
            if not isinstance(snapshot, dict) or _identity(snapshot) != row["job_id"]:
                raise ValueError("Submission snapshot identity mismatch")
            state, error, created = row["dispatch_state"], row["last_error"], row["created_at"]
            if state not in {"pending", "confirmed"}:
                raise ValueError("Invalid submission dispatch state")
            if error is not None and (
                not isinstance(error, str) or row["error_bytes"] > 2048 or len(error) > 512
            ):
                raise ValueError("Invalid submission diagnostic")
            if not isinstance(created, int | float) or not math.isfinite(created) or created <= 0:
                raise ValueError("Invalid submission timestamp")
            return StoredSubmission(
                row["job_id"],
                snapshot["source_id"],
                snapshot["source_sha256"],
                snapshot["request_sha256"],
                snapshot["execution_binding_sha256"],
                snapshot["workflow_name"],
                tuple(snapshot["arguments"]),
                _canonical(snapshot["configuration"]),
                state,
                error,
                float(created),
            )
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
            raise StudioStorageError(f"Studio submission snapshot refused: {exc}") from exc

    @staticmethod
    def _select() -> str:
        return (
            "SELECT substr(job_id,1,72) AS job_id,length(CAST(job_id AS BLOB)) AS job_id_bytes,"
            "substr(snapshot_json,1,131073) AS snapshot_json,"
            "length(CAST(snapshot_json AS BLOB)) AS snapshot_bytes,"
            "substr(dispatch_state,1,10) AS dispatch_state,substr(last_error,1,513) AS last_error,"
            "length(CAST(last_error AS BLOB)) AS error_bytes,"
            "CASE WHEN typeof(created_at) IN ('integer','real') THEN created_at "
            "ELSE NULL END AS created_at FROM submissions"
        )

    def _get(self, connection: sqlite3.Connection, job_id: str) -> StoredSubmission:
        row = connection.execute(self._select() + " WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(f"Studio submission {job_id} not found")
        return self._decode(row)

    def reserve(
        self, prepared: PreparedGeneration, execution_binding_sha256: str, workflow_name: str
    ) -> StoredSubmission:
        GenerationRequest.from_payload(
            {
                "schema": 1,
                "source_id": prepared.source_id,
                "client_token": prepared.client_token,
                "options": {},
            }
        )
        directories = [arg for arg in prepared.argv if arg.startswith("--work-dir=")]
        if len(directories) != 1 or not directories[0].removeprefix("--work-dir="):
            raise ValueError("Preparation must contain exactly one disposable work directory")
        if len(prepared.configuration_json.encode("utf-8")) > _MAX_SNAPSHOT_BYTES:
            raise ValueError("Prepared configuration exceeds the snapshot limit")
        try:
            configuration = json.loads(prepared.configuration_json)
        except (ValueError, RecursionError) as exc:
            raise ValueError("Invalid prepared configuration JSON") from exc
        snapshot = {
            "source_id": prepared.source_id,
            "source_sha256": prepared.source_sha256,
            "configuration": configuration,
            "request_sha256": prepared.content_sha256,
            "execution_binding_sha256": execution_binding_sha256,
            "workflow_name": workflow_name,
            "arguments": [arg for arg in prepared.argv if not arg.startswith("--work-dir=")],
        }
        job_id = _identity(snapshot)
        raw = _canonical(snapshot)
        if len(raw.encode("utf-8")) > _MAX_SNAPSHOT_BYTES:
            raise ValueError("Submission snapshot exceeds the record limit")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            token = connection.execute(
                "SELECT job_id FROM client_tokens WHERE token=?", (prepared.client_token,)
            ).fetchone()
            if token is not None:
                if token["job_id"] != job_id:
                    raise SubmissionConflict(
                        "Client token is already bound to different execution content"
                    )
                try:
                    return self._get(connection, job_id)
                except KeyError as exc:
                    raise StudioStorageError(
                        "Submission token refers to a missing snapshot"
                    ) from exc
            existing = connection.execute(
                "SELECT job_id FROM submissions WHERE job_id=?", (job_id,)
            ).fetchone()
            if existing is None:
                connection.execute(
                    "INSERT INTO submissions VALUES (?,?, 'pending',NULL,?)",
                    (job_id, raw, time.time()),
                )
            else:
                self._get(connection, job_id)
            connection.execute(
                "INSERT INTO client_tokens VALUES (?,?)", (prepared.client_token, job_id)
            )
            return self._get(connection, job_id)

    def get(self, job_id: str) -> StoredSubmission:
        _job_id(job_id)
        with self._connection() as connection:
            return self._get(connection, job_id)

    def _bounded_read(
        self,
        condition: str,
        parameters: tuple[str, ...],
        *,
        max_jobs: int,
        max_bytes: int,
        max_seconds: float,
    ) -> tuple[StoredSubmission, ...]:
        if type(max_jobs) is not int or not 1 <= max_jobs <= 10000:
            raise ValueError("Recovery job limit must be an integer from 1 to 10000")
        if type(max_bytes) is not int or not 1 <= max_bytes <= 256 * 1024 * 1024:
            raise ValueError("Recovery byte limit must be an integer from 1 to 256 MiB")
        if (
            type(max_seconds) not in (int, float)
            or not math.isfinite(max_seconds)
            or not 0 < max_seconds <= 10
        ):
            raise ValueError(
                "Recovery query deadline must be finite, positive and at most 10 seconds"
            )
        with self._connection() as connection:
            started = time.perf_counter()
            interrupted = False

            def progress() -> int:
                nonlocal interrupted
                interrupted = time.perf_counter() - started >= max_seconds
                return int(interrupted)

            connection.set_progress_handler(progress, 1000)
            rows: list[sqlite3.Row] = []
            size = 0
            try:
                cursor = connection.execute(
                    self._select() + condition + " ORDER BY created_at,job_id LIMIT ?",
                    (*parameters, max_jobs + 1),
                )
                for row in cursor:
                    if len(rows) >= max_jobs:
                        raise StudioStorageError(
                            "Recovery intake exceeds the job limit; no work was omitted"
                        )
                    size += (
                        (row["job_id_bytes"] or 0)
                        + (row["snapshot_bytes"] or 0)
                        + (row["error_bytes"] or 0)
                    )
                    if size > max_bytes:
                        raise StudioStorageError(
                            "Recovery intake exceeds the byte limit; no work was omitted"
                        )
                    rows.append(row)
            except sqlite3.Error as exc:
                if interrupted:
                    raise StudioStorageError(
                        "Recovery intake query budget exceeded; all work is preserved"
                    ) from exc
                raise
            finally:
                connection.set_progress_handler(None, 0)
            if time.perf_counter() - started >= max_seconds:
                raise StudioStorageError(
                    "Recovery intake query budget exceeded; all work is preserved"
                )
            return tuple(self._decode(row) for row in rows)

    def pending(
        self, *, max_jobs: int = 1000, max_bytes: int = 16 * 1024 * 1024, max_seconds: float = 5.0
    ) -> list[StoredSubmission]:
        """Refuse oversized intake before decoding; never silently truncate pending work."""
        return list(
            self._bounded_read(
                " WHERE dispatch_state='pending'",
                (),
                max_jobs=max_jobs,
                max_bytes=max_bytes,
                max_seconds=max_seconds,
            )
        )

    def recovery_snapshot(
        self,
        job_ids: Sequence[str],
        *,
        max_jobs: int = 1000,
        max_bytes: int = 16 * 1024 * 1024,
        max_seconds: float = 5.0,
    ) -> tuple[StoredSubmission, ...]:
        """Read precisely requested outbox IDs; this grants no recovery/execution authority."""
        if not isinstance(job_ids, list | tuple):
            raise ValueError("Recovery IDs must be a bounded list or tuple")
        if type(max_jobs) is not int or not 1 <= max_jobs <= 10000:
            raise ValueError("Recovery job limit must be an integer from 1 to 10000")
        if len(job_ids) > max_jobs:
            raise StudioStorageError("Recovery intake exceeds the job limit; no work was omitted")
        for job_id in job_ids:
            if not isinstance(job_id, str):
                raise ValueError("Invalid studio job ID")
            _job_id(job_id)
        if len(set(job_ids)) != len(job_ids):
            raise ValueError("Recovery IDs contain a duplicate")
        condition = (
            " WHERE job_id IN (" + ",".join("?" for _ in job_ids) + ")" if job_ids else " WHERE 0"
        )
        records = self._bounded_read(
            condition,
            tuple(job_ids),
            max_jobs=max_jobs,
            max_bytes=max_bytes,
            max_seconds=max_seconds,
        )
        by_id = {record.job_id: record for record in records}
        if set(by_id) != set(job_ids) or len(by_id) != len(records):
            raise StudioStorageError(
                "Requested recovery job is missing or duplicated; work preserved"
            )
        return tuple(by_id[job_id] for job_id in job_ids)

    def work_dir(self, job_id: str) -> Path:
        _job_id(job_id)
        self.get(job_id)
        root = PrivateDirectory(self.path.parent, create=False)
        artifacts = root.child("studio-artifacts", create=True)
        result = artifacts.child(job_id, create=True)
        self._storage.verify()
        return result.path

    def confirm_dispatch(self, job_id: str) -> None:
        self._update_dispatch(job_id, "confirmed", None)

    def note_dispatch_error(self, job_id: str, message: str) -> None:
        if not isinstance(message, str) or not message or len(message) > 512:
            raise ValueError("Submission diagnostic must be bounded nonempty text")
        self._update_dispatch(job_id, "pending", message)

    def _update_dispatch(self, job_id: str, state: str, error: str | None) -> None:
        _job_id(job_id)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._get(connection, job_id)
            connection.execute(
                "UPDATE submissions SET dispatch_state=?,last_error=? WHERE job_id=? "
                "AND (dispatch_state='pending' OR ?='confirmed')",
                (state, error, job_id, state),
            )
