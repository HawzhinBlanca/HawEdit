"""Real offline pinned journal inspection; no producer or publication authority."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import pickle
import sqlite3
import subprocess
import sys
import textwrap
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from dbos._serialization import DBOSPortableJSONSerializer
from dbos._sys_db import SystemDatabase

from hawedit.studio_admission import JournalPolicy, inspect_studio_journal
from hawedit.studio_generation import GenerationRequest, ProducerSelection, prepare_generation
from hawedit.studio_private import PrivateSqlitePath, StudioStorageError
from hawedit.studio_submissions import SubmissionStore
from hawedit.studio_uploads import UploadStore
from studio_test_storage import create_private_test_root

MEDIA = Path(__file__).resolve().parent / "fixtures/kurdish-speech-3cuts.mp4"
POLICY = JournalPolicy("hawedit.studio.raw.probe", "test-package-v1", "raw-executor")


@pytest.fixture
def journal(tmp_path: Path) -> tuple[PrivateSqlitePath, SubmissionStore, str]:
    root = create_private_test_root(tmp_path)
    binding = PrivateSqlitePath(root / "dbos.sqlite")
    database = SystemDatabase.create(
        f"sqlite:///{binding.path.as_posix()}",
        {},
        None,
        None,
        DBOSPortableJSONSerializer(),
        POLICY.executor_id,
    )
    try:
        database.run_migrations()
    finally:
        database.destroy()
    binding.verify()
    uploads = UploadStore(root / "uploads")
    data = MEDIA.read_bytes()
    ticket = uploads.begin("source.mp4", len(data))
    source = uploads.receive(ticket["upload_id"], io.BytesIO(data), len(data))
    request = GenerationRequest.from_payload(
        {
            "schema": 1,
            "source_id": source["source_id"],
            "client_token": "raw-admission-token-0001",
            "options": {},
        }
    )
    prepared = prepare_generation(request, uploads, root / "temporary", ProducerSelection("gemini"))
    store = SubmissionStore(root / "outbox.sqlite")
    job = store.reserve(prepared, "b" * 64, POLICY.workflow_name)
    with closing(sqlite3.connect(binding.path)) as connection, connection:
        connection.execute(
            "INSERT INTO workflow_status (workflow_uuid,status,name,inputs,serialization,"
            "queue_name,application_version,executor_id) VALUES (?,?,?,?,?,?,?,?)",
            (
                job.job_id,
                "ENQUEUED",
                POLICY.workflow_name,
                json.dumps({"positionalArgs": [job.job_id], "namedArgs": {}}),
                "portable_json",
                "hawedit-studio-v1",
                POLICY.application_version,
                POLICY.executor_id,
            ),
        )
        connection.execute(
            "INSERT INTO queues (queue_id,name,concurrency,worker_concurrency) VALUES (?,?,1,1)",
            ("a" * 32, "hawedit-studio-v1"),
        )
        connection.execute(
            "INSERT INTO application_versions (version_id,version_name) VALUES (?,?)",
            ("c" * 32, POLICY.application_version),
        )
    return binding, store, job.job_id


def _set(
    journal: tuple[PrivateSqlitePath, SubmissionStore, str], table: str, field: str, value: Any
) -> None:
    with closing(sqlite3.connect(journal[0].path)) as connection, connection:
        connection.execute(f'UPDATE "{table}" SET "{field}"=?', (value,))


def _digest(journal: tuple[PrivateSqlitePath, SubmissionStore, str]) -> tuple[str, str]:
    return (
        hashlib.sha256(journal[0].path.read_bytes()).hexdigest(),
        hashlib.sha256(journal[1].path.read_bytes()).hexdigest(),
    )


def test_actual_pinned_schema_accepts(
    journal: tuple[PrivateSqlitePath, SubmissionStore, str],
) -> None:
    before = _digest(journal)
    result = inspect_studio_journal(journal[0], journal[1], POLICY)
    assert result.workflow_ids == (journal[2],)
    assert result.total_rows == 4
    assert result.schema_sha256 in {
        "a7e199f20dde1278b6512693e1352ba760c12af43c9f3f4fce268c25d2c64a69",
        "adcfecb0227887283c09f07d3632527d194628987ccd10943f32efca87bd2da3",
    }
    assert _digest(journal) == before


@pytest.mark.parametrize(
    "sql",
    [
        "CREATE TABLE foreign_table (x)",
        "CREATE VIEW foreign_view AS SELECT inputs FROM workflow_status",
        "CREATE TRIGGER foreign_trigger AFTER INSERT ON workflow_status BEGIN SELECT 1; END",
        "CREATE INDEX foreign_index ON workflow_status(name)",
        "ALTER TABLE workflow_status ADD COLUMN extra TEXT",
        "ALTER TABLE workflow_status ADD COLUMN generated TEXT GENERATED ALWAYS AS (name)",
        "DROP INDEX idx_workflow_status_pending",
    ],
)
def test_raw_schema_drift_refuses(
    journal: tuple[PrivateSqlitePath, SubmissionStore, str], sql: str
) -> None:
    with closing(sqlite3.connect(journal[0].path)) as connection, connection:
        connection.execute(sql)
    before = _digest(journal)
    with pytest.raises(StudioStorageError, match="schema"):
        inspect_studio_journal(journal[0], journal[1], POLICY)
    assert _digest(journal) == before


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE dbos_migrations SET version=39",
        "UPDATE dbos_migrations SET version=41",
        "DELETE FROM dbos_migrations",
        "INSERT INTO dbos_migrations VALUES(41)",
    ],
)
def test_raw_migration_drift_refuses(
    journal: tuple[PrivateSqlitePath, SubmissionStore, str], sql: str
) -> None:
    with closing(sqlite3.connect(journal[0].path)) as connection, connection:
        connection.execute(sql)
    with pytest.raises(StudioStorageError, match="migration"):
        inspect_studio_journal(journal[0], journal[1], POLICY)


@pytest.mark.parametrize(
    "field,value",
    [
        ("workflow_uuid", None),
        ("name", "foreign.worker"),
        ("queue_name", "_dbos_internal_queue"),
        ("application_version", "foreign-package"),
        ("executor_id", "foreign-executor"),
        ("application_id", "foreign-app"),
        ("status", "MADE_UP"),
        ("class_name", "Class"),
        ("config_name", "config"),
        ("request", "{}"),
        ("authenticated_user", "user"),
        ("assumed_role", "admin"),
        ("authenticated_roles", '["admin"]'),
        ("attributes", '{"owner":true}'),
        ("forked_from", "foreign"),
        ("parent_workflow_id", "foreign"),
        ("owner_xid", "foreign"),
        ("deduplication_id", "foreign"),
        ("queue_partition_key", "partition"),
        ("schedule_name", "schedule"),
        ("delay_until_epoch_ms", 1),
        ("debounce_deadline_epoch_ms", 1),
        ("priority", 1),
        ("was_forked_from", 1),
        ("rate_limited", 1),
        ("is_debounced", 1),
        ("recovery_attempts", -1),
        ("created_at", -1),
        ("updated_at", "unknown"),
    ],
)
def test_raw_workflow_policy_refuses(
    journal: tuple[PrivateSqlitePath, SubmissionStore, str], field: str, value: Any
) -> None:
    _set(journal, "workflow_status", field, value)
    before = _digest(journal)
    with pytest.raises(StudioStorageError):
        inspect_studio_journal(journal[0], journal[1], POLICY)
    assert _digest(journal) == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("serialization", "py_pickle"),
        ("serialization", None),
        ("serialization", "json"),
        ("inputs", "{}"),
        ("inputs", '{"namedArgs":{},"positionalArgs":null}'),
        ("inputs", '{"namedArgs":{},"positionalArgs":["foreign"]}'),
        ("inputs", '{"namedArgs":{},"namedArgs":{},"positionalArgs":[]}'),
        ("output", "NaN"),
        ("output", "1e9999"),
        ("output", '{"a":1,"a":2}'),
        ("output", "[" * 40 + "0" + "]" * 40),
        ("output", "{"),
        ("error", "{}"),
        ("error", '{"name":"Error","message":"bad","foreign":true}'),
        ("authenticated_roles", "null"),
        ("attributes", "[]"),
    ],
)
def test_raw_workflow_payload_refuses(
    journal: tuple[PrivateSqlitePath, SubmissionStore, str], field: str, value: Any
) -> None:
    _set(journal, "workflow_status", field, value)
    with pytest.raises(StudioStorageError):
        inspect_studio_journal(journal[0], journal[1], POLICY)


@pytest.mark.parametrize(
    "table,columns,values",
    [
        ("notifications", "message_uuid,destination_uuid,message", ("n", "JOB", "bad")),
        ("workflow_events", "workflow_uuid,key,value", ("JOB", "event", "bad")),
        (
            "workflow_events_history",
            "workflow_uuid,function_id,key,value",
            ("JOB", 1, "event", "bad"),
        ),
        ("streams", 'workflow_uuid,key,value,"offset"', ("JOB", "stream", "bad", 0)),
        (
            "workflow_schedules",
            "schedule_id,schedule_name,workflow_name,schedule,context",
            ("s", "s", "foreign", "* * * * *", "bad"),
        ),
    ],
)
def test_raw_unsupported_surfaces_refuse(
    journal: tuple[PrivateSqlitePath, SubmissionStore, str],
    table: str,
    columns: str,
    values: tuple[Any, ...],
) -> None:
    values = tuple(journal[2] if value == "JOB" else value for value in values)
    with closing(sqlite3.connect(journal[0].path)) as connection, connection:
        connection.execute(
            f'INSERT INTO "{table}" ({columns}) VALUES ({",".join("?" for _ in values)})', values
        )
    before = _digest(journal)
    with pytest.raises(StudioStorageError, match="unsupported"):
        inspect_studio_journal(journal[0], journal[1], POLICY)
    assert _digest(journal) == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("concurrency", 2),
        ("worker_concurrency", None),
        ("name", "foreign"),
        ("rate_limit_max", 1),
        ("rate_limit_period_sec", 1.0),
        ("priority_enabled", 1),
        ("partition_queue", 1),
        ("polling_interval_sec", 0.5),
    ],
)
def test_raw_queue_policy_refuses(
    journal: tuple[PrivateSqlitePath, SubmissionStore, str], field: str, value: Any
) -> None:
    _set(journal, "queues", field, value)
    with pytest.raises(StudioStorageError, match="queue"):
        inspect_studio_journal(journal[0], journal[1], POLICY)


def test_raw_confirmed_job_is_included(
    journal: tuple[PrivateSqlitePath, SubmissionStore, str],
) -> None:
    journal[1].confirm_dispatch(journal[2])
    _set(journal, "workflow_status", "status", "SUCCESS")
    _set(journal, "workflow_status", "output", '{"publication_verified":false}')
    result = inspect_studio_journal(journal[0], journal[1], POLICY)
    assert result.workflow_ids == (journal[2],)


def test_raw_missing_outbox_refuses(
    journal: tuple[PrivateSqlitePath, SubmissionStore, str],
) -> None:
    _set(journal, "workflow_status", "workflow_uuid", "studio-" + "d" * 64)
    with pytest.raises(StudioStorageError, match="missing"):
        inspect_studio_journal(journal[0], journal[1], POLICY)


@pytest.mark.parametrize("limits", [{"max_rows": 1}, {"max_bytes": 1}])
def test_raw_limits_refuse_before_json(
    journal: tuple[PrivateSqlitePath, SubmissionStore, str], limits: dict[str, Any]
) -> None:
    _set(journal, "workflow_status", "inputs", "{")
    with pytest.raises(StudioStorageError, match="limit"):
        inspect_studio_journal(journal[0], journal[1], POLICY, **limits)


@pytest.mark.parametrize(
    "field,value",
    [("inputs", b"binary"), ("inputs", "x" * 131073), ("created_at", 1.5)],
    ids=["binary-input", "oversized-input", "fractional-clock"],
)
def test_raw_field_type_and_size_refuse(
    journal: tuple[PrivateSqlitePath, SubmissionStore, str], field: str, value: Any
) -> None:
    _set(journal, "workflow_status", field, value)
    with pytest.raises(StudioStorageError, match="type|field"):
        inspect_studio_journal(journal[0], journal[1], POLICY)


@pytest.mark.parametrize(
    "limits",
    [
        {"max_rows": True},
        {"max_rows": 0},
        {"max_rows": 10001},
        {"max_bytes": True},
        {"max_bytes": 0},
        {"max_bytes": 256 * 1024 * 1024 + 1},
        {"max_seconds": True},
        {"max_seconds": 0},
        {"max_seconds": 11},
        {"max_seconds": float("nan")},
        {"max_seconds": float("inf")},
        {"max_seconds": 10**1000},
        {"max_seconds": -(10**1000)},
    ],
)
def test_raw_invalid_limits_refuse(
    journal: tuple[PrivateSqlitePath, SubmissionStore, str], limits: dict[str, Any]
) -> None:
    before = _digest(journal)
    with pytest.raises(ValueError):
        inspect_studio_journal(journal[0], journal[1], POLICY, **limits)
    assert _digest(journal) == before


def test_raw_deadline_refuses(journal: tuple[PrivateSqlitePath, SubmissionStore, str]) -> None:
    before = _digest(journal)
    with pytest.raises(StudioStorageError, match="budget"):
        inspect_studio_journal(journal[0], journal[1], POLICY, max_seconds=1e-9)
    assert _digest(journal) == before


def test_raw_read_only_preserves(journal: tuple[PrivateSqlitePath, SubmissionStore, str]) -> None:
    before = _digest(journal)
    inspect_studio_journal(journal[0], journal[1], POLICY)
    _set(journal, "workflow_status", "serialization", "py_pickle")
    altered = _digest(journal)
    with pytest.raises(StudioStorageError):
        inspect_studio_journal(journal[0], journal[1], POLICY)
    assert _digest(journal) == altered and altered != before


def test_raw_lost_binding_refuses_without_recreation(
    journal: tuple[PrivateSqlitePath, SubmissionStore, str],
) -> None:
    journal[0].path.rename(journal[0].path.with_suffix(".preserved"))
    with pytest.raises(StudioStorageError):
        inspect_studio_journal(journal[0], journal[1], POLICY)
    assert not journal[0].path.exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("serialization", "py_pickle"),
        ("serialization", None),
        ("output", "NaN"),
        ("output", '{"x":0,"x":1}'),
        ("error", "{}"),
        ("child_workflow_id", "foreign"),
        ("function_name", "foreign.step"),
        ("workflow_uuid", "foreign"),
        ("function_id", -1),
    ],
)
def test_raw_step_payload_refuses(
    journal: tuple[PrivateSqlitePath, SubmissionStore, str], field: str, value: Any
) -> None:
    with closing(sqlite3.connect(journal[0].path)) as connection, connection:
        connection.execute(
            "INSERT INTO operation_outputs (workflow_uuid,function_id,function_name,output,"
            "serialization) VALUES (?,1,'inert.step','{}','portable_json')",
            (journal[2],),
        )
    _set(journal, "operation_outputs", field, value)
    with pytest.raises(StudioStorageError):
        inspect_studio_journal(journal[0], journal[1], replace(POLICY, step_names=("inert.step",)))


def test_raw_portable_step_accepts_without_execution(
    journal: tuple[PrivateSqlitePath, SubmissionStore, str],
) -> None:
    with closing(sqlite3.connect(journal[0].path)) as connection, connection:
        connection.execute(
            "INSERT INTO operation_outputs (workflow_uuid,function_id,function_name,output,"
            "serialization) VALUES (?,1,'inert.step','{}','portable_json')",
            (journal[2],),
        )
    before = _digest(journal)
    result = inspect_studio_journal(
        journal[0], journal[1], replace(POLICY, step_names=("inert.step",))
    )
    assert result.total_rows == 5 and _digest(journal) == before


def test_raw_pickle_never_executes(
    journal: tuple[PrivateSqlitePath, SubmissionStore, str], tmp_path: Path
) -> None:
    marker = tmp_path / "execution-marker"

    class Payload:
        def __reduce__(self) -> tuple[Any, tuple[Any, ...]]:
            return (eval, (f"__import__('pathlib').Path({str(marker)!r}).touch()",))

    raw = base64.b64encode(pickle.dumps(Payload())).decode("ascii")
    _set(journal, "workflow_status", "serialization", "py_pickle")
    _set(journal, "workflow_status", "inputs", raw)
    with pytest.raises(StudioStorageError, match="serialization"):
        inspect_studio_journal(journal[0], journal[1], POLICY)
    assert not marker.exists()


@pytest.mark.parametrize(
    "status,output,error",
    [
        ("SUCCESS", None, None),
        ("SUCCESS", None, '{"name":"Error","message":"bad"}'),
        ("ERROR", None, None),
        ("ERROR", "{}", None),
        ("ENQUEUED", "{}", None),
        ("PENDING", None, '{"name":"Error","message":"bad"}'),
    ],
)
def test_raw_state_payload_conflict_refuses(
    journal: tuple[PrivateSqlitePath, SubmissionStore, str],
    status: str,
    output: str | None,
    error: str | None,
) -> None:
    _set(journal, "workflow_status", "status", status)
    _set(journal, "workflow_status", "output", output)
    _set(journal, "workflow_status", "error", error)
    before = _digest(journal)
    with pytest.raises(StudioStorageError, match="state"):
        inspect_studio_journal(journal[0], journal[1], POLICY)
    assert _digest(journal) == before


def test_actual_inert_dbos_output_is_admitted(
    journal: tuple[PrivateSqlitePath, SubmissionStore, str],
) -> None:
    with closing(sqlite3.connect(journal[0].path)) as connection, connection:
        connection.execute("DELETE FROM workflow_status")
    script = textwrap.dedent("""
        import sys
        from dbos import DBOS, SetWorkflowID
        from dbos._serialization import DBOSPortableJSONSerializer
        path, job_id = sys.argv[1:]
        DBOS(config={
            'name':'hawedit-raw-inert-test', 'system_database_url': 'sqlite:///' + path,
            'serializer':DBOSPortableJSONSerializer(), 'application_version':'test-package-v1',
            'executor_id':'raw-executor', 'run_admin_server':False, 'enable_otlp':False,
        })
        @DBOS.workflow(name='hawedit.studio.raw.probe')
        def inert(job_id):
            return {'job_id':job_id, 'probe_only':True, 'publication_verified':False}
        try:
            DBOS.launch()
            DBOS.register_queue('hawedit-studio-v1', concurrency=1, worker_concurrency=1,
                                on_conflict='never_update')
            with SetWorkflowID(job_id):
                handle = DBOS.enqueue_workflow('hawedit-studio-v1', inert, job_id)
            result = handle.get_result()
            assert result['job_id'] == job_id and result['publication_verified'] is False
        finally:
            DBOS.destroy()
    """)
    result = subprocess.run(
        [sys.executable, "-c", script, journal[0].path.as_posix(), journal[2]],
        capture_output=True,
        text=True,
        timeout=40,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    policy = replace(POLICY, application_id="")
    before = _digest(journal)
    snapshot = inspect_studio_journal(journal[0], journal[1], policy)
    assert snapshot.workflow_ids == (journal[2],) and _digest(journal) == before
    with closing(sqlite3.connect(journal[0].path)) as connection:
        row = connection.execute("SELECT status,owner_xid FROM workflow_status").fetchone()
    assert row[0] == "SUCCESS" and row[1] is not None


@pytest.mark.parametrize("status", ["CANCELLED", "MAX_RECOVERY_ATTEMPTS_EXCEEDED"])
def test_raw_terminal_null_queue_accepts_without_recovery(
    journal: tuple[PrivateSqlitePath, SubmissionStore, str],
    status: str,
) -> None:
    _set(journal, "workflow_status", "status", status)
    _set(journal, "workflow_status", "queue_name", None)
    _set(journal, "workflow_status", "owner_xid", "36e7dabc-7687-4288-91b3-0f85d509dc2e")
    before = _digest(journal)
    assert inspect_studio_journal(journal[0], journal[1], POLICY).workflow_ids == (journal[2],)
    assert _digest(journal) == before


def test_raw_portable_error_accepts_without_replay(
    journal: tuple[PrivateSqlitePath, SubmissionStore, str],
) -> None:
    _set(journal, "workflow_status", "status", "ERROR")
    _set(journal, "workflow_status", "error", '{"name":"Error","message":"inert refusal"}')
    before = _digest(journal)
    assert inspect_studio_journal(journal[0], journal[1], POLICY).workflow_ids == (journal[2],)
    assert _digest(journal) == before


def test_raw_absent_orm_attributes_accept_without_authority(
    journal: tuple[PrivateSqlitePath, SubmissionStore, str],
) -> None:
    _set(journal, "workflow_status", "attributes", "null")
    before = _digest(journal)
    assert inspect_studio_journal(journal[0], journal[1], POLICY).workflow_ids == (journal[2],)
    assert _digest(journal) == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("serialization", "portable_json\0foreign"),
        ("name", POLICY.workflow_name + "\0foreign"),
        ("queue_name", "hawedit-studio-v1\0foreign"),
        ("inputs", "VALID_INPUT"),
        ("attributes", "{}\0foreign"),
        ("authenticated_roles", "[]\0foreign"),
    ],
)
def test_raw_nul_prefix_refuses_without_repair(
    journal: tuple[PrivateSqlitePath, SubmissionStore, str],
    field: str,
    value: str,
) -> None:
    if value == "VALID_INPUT":
        value = json.dumps({"positionalArgs": [journal[2]], "namedArgs": {}}) + "\0foreign"
    _set(journal, "workflow_status", field, value)
    before = _digest(journal)
    with pytest.raises(StudioStorageError, match="projection"):
        inspect_studio_journal(journal[0], journal[1], POLICY)
    assert _digest(journal) == before


@pytest.mark.parametrize("field", ["snapshot_json", "dispatch_state", "last_error"])
@pytest.mark.parametrize("reader", ["get", "pending", "recovery_snapshot"])
def test_outbox_nul_prefix_refuses(
    journal: tuple[PrivateSqlitePath, SubmissionStore, str],
    field: str,
    reader: str,
) -> None:
    with closing(sqlite3.connect(journal[1].path)) as connection, connection:
        # Exercise damaged persisted rows, not the normal writer's CHECK constraint.
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute(
            f'UPDATE submissions SET "{field}"=coalesce("{field}",\'visible\')'
            "||char(0)||'foreign'"
        )
    before = _digest(journal)
    with pytest.raises(StudioStorageError, match="projection"):
        if reader == "get":
            journal[1].get(journal[2])
        elif reader == "pending":
            journal[1].pending()
        else:
            journal[1].recovery_snapshot([journal[2]])
    assert _digest(journal) == before


def test_outbox_hidden_job_id_refuses(
    journal: tuple[PrivateSqlitePath, SubmissionStore, str],
) -> None:
    with closing(sqlite3.connect(journal[1].path)) as connection, connection:
        connection.execute("UPDATE submissions SET job_id=job_id||char(0)||'foreign'")
    before = _digest(journal)
    with pytest.raises(StudioStorageError, match="projection"):
        journal[1].pending()
    assert _digest(journal) == before


def test_outbox_nul_diagnostic_is_not_written(
    journal: tuple[PrivateSqlitePath, SubmissionStore, str],
) -> None:
    before = _digest(journal)
    with pytest.raises(ValueError):
        journal[1].note_dispatch_error(journal[2], "visible\0foreign")
    assert _digest(journal) == before
