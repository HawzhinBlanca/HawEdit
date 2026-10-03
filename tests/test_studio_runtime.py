"""Native owned startup/lifecycle, not producer or publication acceptance."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import pickle
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
from dbos._serialization import DBOSPortableJSONSerializer
from dbos._sys_db import SystemDatabase

from hawedit.studio_admission import JournalPolicy, inspect_studio_connection
from hawedit.studio_generation import GenerationRequest, ProducerSelection, prepare_generation
from hawedit.studio_private import PrivateDirectory, PrivateSqlitePath, StudioStorageError
from hawedit.studio_runtime import StudioLease, studio_runtime_policy
from hawedit.studio_submissions import SubmissionStore
from hawedit.studio_uploads import UploadStore
from studio_test_storage import create_private_test_root

WORKFLOW = "hawedit.studio.owned.inert"
MEDIA = Path(__file__).resolve().parent / "fixtures/kurdish-speech-3cuts.mp4"


@pytest.fixture
def owned_job(tmp_path: Path) -> tuple[PrivateSqlitePath, SubmissionStore, str, JournalPolicy]:
    root = create_private_test_root(tmp_path)
    storage = PrivateSqlitePath(root / "dbos.sqlite")
    uploads = UploadStore(root / "uploads")
    data = MEDIA.read_bytes()
    ticket = uploads.begin("source.mp4", len(data))
    source = uploads.receive(ticket["upload_id"], io.BytesIO(data), len(data))
    request = GenerationRequest.from_payload(
        {
            "schema": 1,
            "source_id": source["source_id"],
            "client_token": "owned-runtime-token-0001",
            "options": {},
        }
    )
    prepared = prepare_generation(request, uploads, root / "temporary", ProducerSelection("gemini"))
    store = SubmissionStore(root / "outbox.sqlite")
    policy = studio_runtime_policy(WORKFLOW)
    job = store.reserve(prepared, "b" * 64, policy.workflow_name)
    return storage, store, job.job_id, policy


def _seed(job: tuple[PrivateSqlitePath, SubmissionStore, str, JournalPolicy]) -> None:
    storage, _, job_id, policy = job
    database = SystemDatabase.create(
        f"sqlite:///{storage.path.as_posix()}",
        {},
        None,
        None,
        DBOSPortableJSONSerializer(),
        policy.executor_id,
    )
    try:
        database.run_migrations()
    finally:
        database.destroy()
    with closing(sqlite3.connect(storage.path)) as connection, connection:
        connection.execute(
            "INSERT INTO workflow_status (workflow_uuid,status,name,inputs,serialization,"
            "queue_name,application_version,executor_id,application_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                job_id,
                "ENQUEUED",
                policy.workflow_name,
                json.dumps({"positionalArgs": [job_id], "namedArgs": {}}),
                "portable_json",
                "hawedit-studio-v1",
                policy.application_version,
                policy.executor_id,
                "",
            ),
        )
        connection.execute(
            "INSERT INTO queues (queue_id,name,concurrency,worker_concurrency) VALUES (?,?,1,1)",
            ("a" * 32, "hawedit-studio-v1"),
        )
        connection.execute(
            "INSERT INTO application_versions (version_id,version_name) VALUES (?,?)",
            ("c" * 32, policy.application_version),
        )


_RUNTIME = r"""
import importlib,json,os,sys,threading,time
from contextlib import closing
from pathlib import Path
from dbos import DBOS
from hawedit.studio_private import PrivateDirectory,PrivateSqlitePath,StudioStorageError
from hawedit.studio_runtime import OwnedStudioRuntime,studio_runtime_policy
from hawedit.studio_submissions import SubmissionStore
from hawedit.studio_queue import reconcile_studio_submission
root=Path(sys.argv[1]); mode=sys.argv[2]; job_id=sys.argv[3]
module=importlib.import_module("dbos._dbos")
name="hawedit.studio.owned.inert"
counter=root/"executions.txt"
entered=threading.Event(); finish=threading.Event()
@DBOS.workflow(name=name)
def worker(job_id):
    counter.write_text(str(int(counter.read_text())+1 if counter.exists() else 1))
    if mode=="crash": os._exit(23)
    if mode=="drain":
        entered.set()
        assert finish.wait(12)
    return {"job_id":job_id,"private":True}
storage=PrivateSqlitePath(root/"dbos.sqlite")
store=SubmissionStore(root/"outbox.sqlite")
policy=studio_runtime_policy(name)
runtime=OwnedStudioRuntime(storage,store,policy)
if mode=="constructor-race":
    holder=[]
    def trace(frame,event,arg):
        if frame.f_code is OwnedStudioRuntime.launch.__code__ and "config" in frame.f_locals:
            sys.settrace(None)
            thread=threading.Thread(target=lambda:holder.append(DBOS(config={
                "name":"foreign-race","system_database_url":"sqlite:///:memory:",
                "run_admin_server":False,"enable_otlp":False})))
            thread.start(); thread.join(5)
            assert len(holder)==1
            return None
        return trace
    sys.settrace(trace)
    try:
        runtime.launch()
        raise AssertionError("foreign constructor race admitted")
    except StudioStorageError:
        foreign=holder[0]
        assert module._dbos_global_instance is foreign
        assert foreign._initialized
        assert foreign._listening_queues is None
        assert not counter.exists()
        print(json.dumps({"preserved":True}))
    finally:
        sys.settrace(None)
        DBOS.destroy(destroy_registry=True)
elif mode=="foreign-singleton":
    foreign=DBOS(config={"name":"foreign","system_database_url":"sqlite:///:memory:",
                         "run_admin_server":False,"enable_otlp":False})
    try:
        runtime.launch()
        raise AssertionError("foreign instance admitted")
    except StudioStorageError:
        print(json.dumps({"preserved":module._dbos_global_instance is foreign,
                          "initialized":foreign._initialized,
                          "lease_absent":not (root/"studio-supervisor.lock").exists()}))
    DBOS.destroy(destroy_registry=True)
elif mode=="foreign-registry":
    @DBOS.workflow(name="foreign.workflow")
    def foreign(): return "foreign"
    try:
        runtime.launch()
        raise AssertionError("foreign registry admitted")
    except StudioStorageError:
        print(json.dumps({"preserved":
                          "foreign.workflow" in module._dbos_global_registry.workflow_info_map,
                          "instance_absent":module._dbos_global_instance is None,
                          "lease_absent":not (root/"studio-supervisor.lock").exists()}))
elif mode=="ambient":
    os.environ[sys.argv[4]]=sys.argv[5]
    try:
        runtime.launch()
        raise AssertionError("ambient override admitted")
    except StudioStorageError:
        print(json.dumps({"instance_absent":module._dbos_global_instance is None,
                          "lease_absent":not (root/"studio-supervisor.lock").exists()}))
elif mode=="bad-journal":
    try:
        runtime.launch()
        raise AssertionError("bad persisted state admitted")
    except StudioStorageError:
        print(json.dumps({"instance_absent":module._dbos_global_instance is None,
                          "worker_absent":not counter.exists()}))
else:
    runtime.launch()
    try:
        runtime.verify()
        if mode in ("duplicate","drain","resume","crash"):
            if mode!="resume":
                reconcile_studio_submission(store,job_id,worker)
            if mode=="drain":
                assert entered.wait(8)
                try:
                    runtime.close(timeout_seconds=0.05)
                    raise AssertionError("live worker released lease")
                except StudioStorageError:
                    assert runtime.state=="draining"
                from hawedit.studio_runtime import StudioLease
                try:
                    StudioLease(PrivateDirectory(root,create=False))
                    raise AssertionError("draining lease not held")
                except StudioStorageError:
                    pass
                if len(sys.argv)>4:
                    from hawedit.studio_queue import StudioQueueError
                    other=sys.argv[4]
                    try:
                        reconcile_studio_submission(store,other,worker)
                        raise AssertionError("draining accepted new dispatch")
                    except StudioStorageError:
                        pass
                    assert DBOS.get_workflow_status(other) is None
                    assert store.get(other).dispatch_state=="pending"
                    assert store.get(other).last_error
                finish.set()
            deadline=time.monotonic()+12
            while time.monotonic()<deadline:
                status=DBOS.get_workflow_status(job_id)
                if status and status.status=="SUCCESS": break
                time.sleep(0.05)
            else: raise AssertionError("inert workflow did not finish")
            if mode=="duplicate":
                reconcile_studio_submission(store,job_id,worker)
            if mode=="resume":
                reconcile_studio_submission(store,job_id,worker)
            assert DBOS.get_result(job_id)=={"job_id":job_id,"private":True}
            result={"count":int(counter.read_text()),"confirmed":store.get(job_id).dispatch_state,
                    "completed_deliverable":False}
        elif mode=="held-connection":
            connection=runtime._owned_engine.engine.connect()
            try:
                runtime.close(timeout_seconds=0.05)
                raise AssertionError("held connection released lease")
            except StudioStorageError:
                result={"retained":runtime.state=="draining"}
            connection.close()
        elif mode=="unsafe-commit":
            import sqlalchemy as sa
            try:
                with runtime._owned_engine.engine.begin() as connection:
                    connection.exec_driver_sql(
                        "INSERT INTO notifications "
                        "(destination_uuid,topic,message,message_uuid,serialization) "
                        "VALUES (?,'','unsafe','n1','portable_json')",(job_id,))
                raise AssertionError("unsafe commit admitted")
            except StudioStorageError:
                pass
            with runtime._owned_engine.engine.begin() as connection:
                assert connection.exec_driver_sql("SELECT count(*) FROM notifications").scalar()==0
            result={"rolled_back":True}
        elif mode=="changed-row":
            import sqlite3
            with closing(sqlite3.connect(storage.path)) as native, native:
                native.execute(
                    "INSERT INTO workflow_status "
                    "(workflow_uuid,status,name,inputs,serialization,queue_name,application_version,"
                    "executor_id,application_id,output) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (job_id,"SUCCESS",name,sys.argv[4],"py_pickle","hawedit-studio-v1",
                     policy.application_version,policy.executor_id,"","null"))
            try:
                DBOS.get_workflow_status(job_id)
                raise AssertionError("changed raw row deserialized")
            except StudioStorageError:
                result={"refused":True}
        elif mode=="identity-drift":
            original=runtime._instance._serializer
            runtime._instance._serializer=object()
            try:
                runtime.verify()
                raise AssertionError("serializer drift admitted")
            except StudioStorageError:
                result={"refused":True}
            runtime._instance._serializer=original
        elif mode=="contention":
            import sqlite3
            native=sqlite3.connect(storage.path)
            native.execute("BEGIN IMMEDIATE")
            started=time.monotonic()
            try:
                try:
                    DBOS.get_workflow_status(job_id)
                    raise AssertionError("locked storage did not refuse")
                except StudioStorageError as error:
                    assert "database is locked" not in str(error)
                    result={"bounded":time.monotonic()-started<8}
            finally:
                native.rollback(); native.close()
        else:
            config=runtime._instance._config
            result={"active":runtime.state=="active",
                    "actual_pool":(runtime._instance._sys_db.engine.pool
                                   is runtime._owned_engine.engine.pool),
                    "custom_owned":not runtime._instance._sys_db.created_engine,
                    "admin":config["runtimeConfig"]["run_admin_server"],
                    "otlp":not config["telemetry"]["disable_otlp"],
                    "version":DBOS.application_version,"executor":DBOS.executor_id}
    finally:
        finish.set()
        runtime.close(timeout_seconds=8)
    result["closed"]=runtime.state=="closed"
    result["instance_absent"]=module._dbos_global_instance is None
    if mode=="cli":
        from hawedit.durable_workflow import configure_dbos
        configure_dbos(f"sqlite:///{(root/'cli.sqlite').as_posix()}")
        foreign=module._dbos_global_instance
        assert Path(foreign._sys_db.engine.url.database)==root/"cli.sqlite"
        runtime.close()
        result["cli_preserved"]=module._dbos_global_instance is foreign
        DBOS.destroy(destroy_registry=True)
    print(json.dumps(result))
"""


def _run(root: Path, mode: str, job_id: str = "", *extra: str) -> dict[str, Any]:
    process = subprocess.run(
        [sys.executable, "-c", _RUNTIME, str(root), mode, job_id, *extra],
        capture_output=True,
        text=True,
        timeout=35,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    result = json.loads(process.stdout.strip().splitlines()[-1])
    assert isinstance(result, dict)
    return result


def test_native_lease_contends_across_processes_and_releases_after_exit(tmp_path: Path) -> None:
    root = create_private_test_root(tmp_path)
    script = (
        "import os,sys; from pathlib import Path; "
        "from hawedit.studio_private import PrivateDirectory,StudioStorageError; "
        "from hawedit.studio_runtime import StudioLease; "
        "lease=StudioLease(PrivateDirectory(Path(sys.argv[1]),create=False)); os._exit(0)"
    )
    lease = StudioLease(PrivateDirectory(root, create=False))
    original = (root / "studio-supervisor.lock").stat()
    try:
        conflict = subprocess.run(
            [sys.executable, "-c", script, str(root)], capture_output=True, timeout=15
        )
        assert conflict.returncode != 0
        assert b"StudioStorageError" in conflict.stderr
        lease.verify()
    finally:
        lease.release()
    exited = subprocess.run([sys.executable, "-c", script, str(root)], timeout=15)
    assert exited.returncode == 0
    after = (root / "studio-supervisor.lock").stat()
    assert (after.st_dev, after.st_ino, after.st_size) == (
        original.st_dev,
        original.st_ino,
        0,
    )
    final = StudioLease(PrivateDirectory(root, create=False))
    final.release()


def test_lease_refuses_changed_binding_and_preserves_members(tmp_path: Path) -> None:
    root = create_private_test_root(tmp_path)
    lease = StudioLease(PrivateDirectory(root, create=False))
    try:
        with (root / "studio-supervisor.lock").open("r+b") as stream:
            stream.seek(2)
            stream.write(b"unsafe")
        with pytest.raises(StudioStorageError):
            lease.verify()
    finally:
        lease.release()
    assert (root / "studio-supervisor.lock").read_bytes() == b"\x00\x00unsafe"


def test_same_connection_inspection_sees_uncommitted_data_without_ending_transaction(
    owned_job: tuple[PrivateSqlitePath, SubmissionStore, str, JournalPolicy],
) -> None:
    _seed(owned_job)
    storage, store, job_id, policy = owned_job
    with closing(sqlite3.connect(storage.path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        snapshot = inspect_studio_connection(connection, storage, store, policy)
        assert snapshot.workflow_ids == (job_id,)
        assert connection.in_transaction
        connection.execute("UPDATE workflow_status SET serialization='py_pickle'")
        with pytest.raises(StudioStorageError, match="portable_json"):
            inspect_studio_connection(connection, storage, store, policy)
        assert connection.in_transaction
        connection.rollback()
        assert connection.execute("SELECT serialization FROM workflow_status").fetchone() == (
            "portable_json",
        )


@pytest.mark.parametrize("mode", ["wrong-main", "attach", "temp"])
def test_same_connection_inspection_refuses_other_database_and_attachments(
    owned_job: tuple[PrivateSqlitePath, SubmissionStore, str, JournalPolicy], mode: str
) -> None:
    _seed(owned_job)
    storage, store, _, policy = owned_job
    path = storage.root / "foreign.sqlite" if mode == "wrong-main" else storage.path
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        if mode == "attach":
            connection.execute("ATTACH DATABASE ':memory:' AS foreign_db")
        elif mode == "temp":
            connection.execute("CREATE TEMP TABLE workflow_status (inputs TEXT)")
        with pytest.raises(StudioStorageError):
            inspect_studio_connection(connection, storage, store, policy)
        assert connection.in_transaction


def test_owned_runtime_bootstraps_actual_pinned_database(
    owned_job: tuple[PrivateSqlitePath, SubmissionStore, str, JournalPolicy],
) -> None:
    storage, _, _, policy = owned_job
    result = _run(storage.root, "bootstrap")
    assert result == {
        "active": True,
        "actual_pool": True,
        "custom_owned": True,
        "admin": False,
        "otlp": False,
        "version": policy.application_version,
        "executor": policy.executor_id,
        "closed": True,
        "instance_absent": True,
    }
    with closing(sqlite3.connect(storage.path)) as connection:
        assert connection.execute("SELECT version FROM dbos_migrations").fetchall() == [(40,)]
        assert connection.execute(
            "SELECT concurrency,worker_concurrency FROM queues WHERE name='hawedit-studio-v1'"
        ).fetchall() == [(1, 1)]
        assert connection.execute("SELECT count(*) FROM workflow_status").fetchone() == (0,)


@pytest.mark.parametrize("mode", ["foreign-singleton", "foreign-registry"])
def test_owned_runtime_refuses_foreign_singleton_without_destroying_it(
    owned_job: tuple[PrivateSqlitePath, SubmissionStore, str, JournalPolicy], mode: str
) -> None:
    storage = owned_job[0]
    original = storage.path.read_bytes()
    result = _run(storage.root, mode)
    assert result["preserved"] is True
    assert result["lease_absent"] is True
    assert result.get("initialized", result.get("instance_absent")) is True
    assert storage.path.read_bytes() == original


@pytest.mark.parametrize(
    "name,value",
    [("DBOS__CLOUD", "true"), ("DBOS__APPVERSION", "other"), ("DBOS__VMID", "other")],
)
def test_owned_runtime_refuses_ambient_overrides(
    owned_job: tuple[PrivateSqlitePath, SubmissionStore, str, JournalPolicy], name: str, value: str
) -> None:
    storage = owned_job[0]
    result = _run(storage.root, "ambient", "", name, value)
    assert result == {"instance_absent": True, "lease_absent": True}


class _UnpickleMarker:
    def __init__(self, marker: Path) -> None:
        self.marker = marker

    def __reduce__(self) -> tuple[Any, tuple[str]]:
        return eval, (f"__import__('pathlib').Path({str(self.marker)!r}).write_text('executed')",)


def test_owned_runtime_refuses_bad_existing_journal_before_launch(
    owned_job: tuple[PrivateSqlitePath, SubmissionStore, str, JournalPolicy],
) -> None:
    _seed(owned_job)
    storage = owned_job[0]
    marker = storage.root / "unpickled.txt"
    payload = base64.b64encode(pickle.dumps(_UnpickleMarker(marker))).decode("ascii")
    with closing(sqlite3.connect(storage.path)) as connection, connection:
        connection.execute(
            "UPDATE workflow_status SET inputs=?,serialization='py_pickle'", (payload,)
        )
    before = hashlib.sha256(storage.path.read_bytes()).hexdigest()
    result = _run(storage.root, "bad-journal")
    assert result == {"instance_absent": True, "worker_absent": True}
    assert hashlib.sha256(storage.path.read_bytes()).hexdigest() == before
    assert not marker.exists()


def test_owned_runtime_duplicate_dispatch_executes_once(
    owned_job: tuple[PrivateSqlitePath, SubmissionStore, str, JournalPolicy],
) -> None:
    storage, _, job_id, _ = owned_job
    result = _run(storage.root, "duplicate", job_id)
    assert result == {
        "count": 1,
        "confirmed": "confirmed",
        "completed_deliverable": False,
        "closed": True,
        "instance_absent": True,
    }


def test_owned_engine_refuses_unsafe_uncommitted_commit(
    owned_job: tuple[PrivateSqlitePath, SubmissionStore, str, JournalPolicy],
) -> None:
    _seed(owned_job)
    result = _run(owned_job[0].root, "unsafe-commit", owned_job[2])
    assert result == {"rolled_back": True, "closed": True, "instance_absent": True}


def test_owned_runtime_refuses_runtime_identity_drift(
    owned_job: tuple[PrivateSqlitePath, SubmissionStore, str, JournalPolicy],
) -> None:
    result = _run(owned_job[0].root, "identity-drift")
    assert result == {"refused": True, "closed": True, "instance_absent": True}


def test_shutdown_retains_lease_until_real_worker_exits(
    owned_job: tuple[PrivateSqlitePath, SubmissionStore, str, JournalPolicy],
) -> None:
    storage, _, job_id, _ = owned_job
    result = _run(storage.root, "drain", job_id)
    assert result["count"] == 1
    assert result["closed"] and result["instance_absent"]


def test_shutdown_refuses_held_engine_connection(
    owned_job: tuple[PrivateSqlitePath, SubmissionStore, str, JournalPolicy],
) -> None:
    result = _run(owned_job[0].root, "held-connection")
    assert result == {"retained": True, "closed": True, "instance_absent": True}


def test_draining_refuses_new_dispatch_without_losing_reserved_job(
    owned_job: tuple[PrivateSqlitePath, SubmissionStore, str, JournalPolicy],
) -> None:
    storage, store, job_id, policy = owned_job
    request = GenerationRequest.from_payload(
        {
            "schema": 1,
            "source_id": store.get(job_id).source_id,
            "client_token": "owned-runtime-token-0002",
            "options": {"max_clips": 1},
        }
    )
    prepared = prepare_generation(
        request,
        UploadStore(storage.root / "uploads"),
        storage.root / "temporary",
        ProducerSelection("gemini"),
    )
    other = store.reserve(prepared, "b" * 64, policy.workflow_name)
    assert other.job_id != job_id
    result = _run(storage.root, "drain", job_id, other.job_id)
    assert result["count"] == 1
    assert result["closed"] and result["instance_absent"]
    assert store.get(other.job_id).dispatch_state == "pending"


def test_owned_engine_refuses_changed_raw_rows_before_getter(
    owned_job: tuple[PrivateSqlitePath, SubmissionStore, str, JournalPolicy],
) -> None:
    storage, _, job_id, _ = owned_job
    marker = storage.root / "late-unpickled.txt"
    payload = base64.b64encode(pickle.dumps(_UnpickleMarker(marker))).decode("ascii")
    result = _run(storage.root, "changed-row", job_id, payload)
    assert result == {"refused": True, "closed": True, "instance_absent": True}
    assert not marker.exists()
    with closing(sqlite3.connect(storage.path)) as connection:
        assert connection.execute("SELECT serialization FROM workflow_status").fetchone() == (
            "py_pickle",
        )


def test_owned_runtime_recovers_actual_pending_job_after_process_exit(
    owned_job: tuple[PrivateSqlitePath, SubmissionStore, str, JournalPolicy],
) -> None:
    storage, _, job_id, _ = owned_job
    crashed = subprocess.run(
        [sys.executable, "-c", _RUNTIME, str(storage.root), "crash", job_id],
        capture_output=True,
        text=True,
        timeout=35,
    )
    assert crashed.returncode == 23, crashed.stdout + crashed.stderr
    with closing(sqlite3.connect(storage.path)) as connection:
        assert connection.execute("SELECT status FROM workflow_status").fetchone() == ("PENDING",)
    lock = (storage.root / "studio-supervisor.lock").stat()
    result = _run(storage.root, "resume", job_id)
    assert result["count"] == 2  # Interrupted coarse work re-enters; no exactly-once claim.
    assert result["confirmed"] == "confirmed"
    assert result["closed"] and result["instance_absent"]
    after = (storage.root / "studio-supervisor.lock").stat()
    assert (after.st_dev, after.st_ino, after.st_size) == (lock.st_dev, lock.st_ino, 0)


def test_bootstrap_ddl_rolls_back_on_process_exit(
    owned_job: tuple[PrivateSqlitePath, SubmissionStore, str, JournalPolicy],
) -> None:
    storage = owned_job[0]
    script = r"""
import os,sys
from pathlib import Path
from sqlalchemy import event
from hawedit.studio_private import PrivateDirectory,PrivateSqlitePath
from hawedit.studio_submissions import SubmissionStore
from hawedit.studio_runtime import StudioLease,_OwnedEngine,studio_runtime_policy
root=Path(sys.argv[1])
lease=StudioLease(PrivateDirectory(root,create=False))
owned=_OwnedEngine(PrivateSqlitePath(root/"dbos.sqlite"),SubmissionStore(root/"outbox.sqlite"),
                   studio_runtime_policy("hawedit.studio.owned.inert"),lease)
@event.listens_for(owned.engine,"after_cursor_execute")
def interrupt(connection,cursor,statement,parameters,context,executemany):
    if statement.startswith("CREATE TABLE workflow_status"):
        os._exit(24)
owned.bootstrap()
raise AssertionError("publisher fault point was not reached")
"""
    process = subprocess.run(
        [sys.executable, "-c", script, str(storage.root)],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert process.returncode == 24, process.stdout + process.stderr
    # Actual SQLite recovery, not deleting a sidecar or hand-repairing schema.
    with closing(sqlite3.connect(storage.path)) as connection:
        assert connection.execute("SELECT name FROM sqlite_schema").fetchall() == []
    result = _run(storage.root, "bootstrap")
    assert result["active"] and result["closed"] and result["instance_absent"]


@pytest.mark.parametrize("factory", ["row", "text"])
def test_same_connection_refuses_custom_decoders_before_queries(
    owned_job: tuple[PrivateSqlitePath, SubmissionStore, str, JournalPolicy], factory: str
) -> None:
    _seed(owned_job)
    storage, store, _, policy = owned_job
    called: list[str] = []

    def decode_row(cursor: sqlite3.Cursor, row: tuple[Any, ...]) -> tuple[Any, ...]:
        called.append("row")
        return row

    def decode_text(value: bytes) -> str:
        called.append("text")
        return value.decode("utf-8")

    with closing(sqlite3.connect(storage.path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        if factory == "row":
            connection.row_factory = decode_row
        else:
            connection.text_factory = decode_text
        with pytest.raises(StudioStorageError):
            inspect_studio_connection(connection, storage, store, policy)
        assert called == []
        assert connection.in_transaction


def test_same_connection_inspection_preserves_vm_handler_and_connection_policy(
    owned_job: tuple[PrivateSqlitePath, SubmissionStore, str, JournalPolicy],
) -> None:
    _seed(owned_job)
    storage, store, _, policy = owned_job
    progress: list[int] = []

    def record_progress() -> int:
        progress.append(1)
        return 0

    with closing(sqlite3.connect(storage.path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.set_progress_handler(record_progress, 1)
        inspect_studio_connection(connection, storage, store, policy)
        before = len(progress)
        connection.execute("SELECT 1").fetchone()
        assert len(progress) > before > 0
        assert connection.execute("PRAGMA query_only").fetchone() == (0,)
        assert connection.total_changes == 0
        assert connection.in_transaction


def test_owned_runtime_refuses_foreign_registry_before_storage_mutation(
    owned_job: tuple[PrivateSqlitePath, SubmissionStore, str, JournalPolicy],
) -> None:
    storage, store, _, _ = owned_job
    before = {path.name: path.read_bytes() for path in (storage.path, store.path)}
    members = {path.name for path in storage.root.iterdir()}
    result = _run(storage.root, "foreign-registry")
    assert result["preserved"] and result["instance_absent"] and result["lease_absent"]
    assert {path.name: path.read_bytes() for path in (storage.path, store.path)} == before
    assert {path.name for path in storage.root.iterdir()} == members


def test_owned_runtime_launches_actual_serial_queue_and_preserves_cli(
    owned_job: tuple[PrivateSqlitePath, SubmissionStore, str, JournalPolicy],
) -> None:
    result = _run(owned_job[0].root, "cli")
    assert result["active"] and result["actual_pool"] and result["cli_preserved"]
    with closing(sqlite3.connect(owned_job[0].path)) as connection:
        assert connection.execute(
            "SELECT concurrency,worker_concurrency FROM queues WHERE name='hawedit-studio-v1'"
        ).fetchone() == (1, 1)


def test_owned_runtime_closes_only_its_own_resources(
    owned_job: tuple[PrivateSqlitePath, SubmissionStore, str, JournalPolicy],
) -> None:
    result = _run(owned_job[0].root, "cli")
    assert result["closed"] and result["instance_absent"] and result["cli_preserved"]


def test_owned_runtime_storage_contention_is_bounded_without_library_retry(
    owned_job: tuple[PrivateSqlitePath, SubmissionStore, str, JournalPolicy],
) -> None:
    result = _run(owned_job[0].root, "contention", owned_job[2])
    assert result == {"bounded": True, "closed": True, "instance_absent": True}


def test_owned_runtime_refuses_real_foreign_constructor_race_without_mutation(
    owned_job: tuple[PrivateSqlitePath, SubmissionStore, str, JournalPolicy],
) -> None:
    result = _run(owned_job[0].root, "constructor-race")
    assert result == {"preserved": True}
