"""Exercise real DBOS dispatch, serial execution and cross-process outbox recovery."""

from __future__ import annotations

import io
import json
import sqlite3
import subprocess
import sys
import textwrap
import threading
import time
from collections.abc import Iterator
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pytest
from dbos import DBOS, SetWorkflowID

from hawedit.durable_workflow import configure_dbos
from hawedit.studio_generation import (
    GenerationRequest,
    PreparedGeneration,
    ProducerSelection,
    prepare_generation,
)
from hawedit.studio_queue import (
    STUDIO_QUEUE_NAME,
    StudioQueueError,
    configure_studio_queue,
    submit_studio_workflow,
)
from hawedit.studio_submissions import StudioStorageError, SubmissionConflict, SubmissionStore
from hawedit.studio_uploads import UploadStore
from studio_test_storage import create_private_test_root

MEDIA = Path(__file__).resolve().parents[1] / "tests/fixtures/kurdish-speech-3cuts.mp4"
BINDING = "b" * 64


@pytest.fixture(name="tmp_path")
def _private_tmp_path(tmp_path: Path) -> Path:
    return create_private_test_root(tmp_path)


_LOCK = threading.Lock()
_ENTERED = threading.Event()
_RELEASE = threading.Event()
_CALLS: list[str] = []
_ACTIVE = 0
_MAX_ACTIVE = 0


@DBOS.workflow(name="hawedit.studio.queue.probe")
def _probe(job_id: str) -> dict[str, Any]:
    global _ACTIVE, _MAX_ACTIVE
    with _LOCK:
        _ACTIVE += 1
        _MAX_ACTIVE = max(_MAX_ACTIVE, _ACTIVE)
        _CALLS.append(job_id)
    _ENTERED.set()
    try:
        assert _RELEASE.wait(10), "Local probe release timed out"
        return {"job_id": job_id, "probe_only": True}
    finally:
        with _LOCK:
            _ACTIVE -= 1


@pytest.fixture(scope="module", autouse=True)
def _dbos_instance(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    path = tmp_path_factory.mktemp("studio-queue-dbos") / "dbos.sqlite"
    configure_dbos(f"sqlite:///{path}")
    yield
    _RELEASE.set()
    DBOS.destroy()


@pytest.fixture(autouse=True)
def _probe_state() -> Iterator[None]:
    global _MAX_ACTIVE
    assert _ACTIVE == 0
    _CALLS.clear()
    _MAX_ACTIVE = 0
    _ENTERED.clear()
    _RELEASE.set()
    yield
    _RELEASE.set()


@pytest.fixture
def prepared(tmp_path: Path) -> PreparedGeneration:
    uploads = UploadStore(tmp_path / "uploads")
    data = MEDIA.read_bytes()
    ticket = uploads.begin("episode.mp4", len(data))
    source = uploads.receive(ticket["upload_id"], io.BytesIO(data), len(data))
    request = GenerationRequest.from_payload(
        {
            "schema": 1,
            "source_id": source["source_id"],
            "client_token": "queued-token-001",
            "options": {},
        }
    )
    return prepare_generation(request, uploads, tmp_path / "temporary", ProducerSelection("gemini"))


def _complete(job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        status = DBOS.get_workflow_status(job_id)
        if status is not None and status.status == "SUCCESS":
            result: object = DBOS.retrieve_workflow(job_id).get_result()
            assert isinstance(result, dict)
            return result
        time.sleep(0.02)
    pytest.fail(f"Local queue probe {job_id} did not complete within its bounded wait")


def test_studio_queue_runs_serially_and_reuses_completed_work(
    prepared: PreparedGeneration, tmp_path: Path
) -> None:
    store = SubmissionStore(tmp_path / "submissions.sqlite")
    _RELEASE.clear()
    first = submit_studio_workflow(store, prepared, BINDING, _probe)
    assert _ENTERED.wait(5)
    try:
        second = submit_studio_workflow(
            store, replace(prepared, client_token="queued-token-002"), "c" * 64, _probe
        )
        duplicate = submit_studio_workflow(store, prepared, BINDING, _probe)
        assert duplicate.job_id == first.job_id
        status = DBOS.get_workflow_status(second.job_id)
        assert status is not None and status.status == "ENQUEUED"
        assert status.queue_name == STUDIO_QUEUE_NAME
        assert list(_CALLS) == [first.job_id] and _MAX_ACTIVE == 1
    finally:
        _RELEASE.set()
    assert _complete(first.job_id)["probe_only"]
    assert _complete(second.job_id)["probe_only"]
    repeated = submit_studio_workflow(SubmissionStore(store.path), prepared, BINDING, _probe)
    assert repeated.job_id == first.job_id and repeated.dispatch_state == "confirmed"
    assert _CALLS.count(first.job_id) == 1 and _CALLS.count(second.job_id) == 1
    assert _MAX_ACTIVE == 1 and store.pending() == []


def test_studio_queue_recovers_lost_acknowledgement(
    prepared: PreparedGeneration, tmp_path: Path
) -> None:
    path = tmp_path / "submissions.sqlite"
    store = SubmissionStore(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TRIGGER reject_confirmation BEFORE UPDATE ON submissions "
            "WHEN NEW.dispatch_state='confirmed' BEGIN SELECT RAISE(ABORT,'ack outage'); END"
        )
    with pytest.raises(StudioStorageError, match="ack outage"):
        submit_studio_workflow(store, prepared, BINDING, _probe)
    pending = store.pending()
    assert len(pending) == 1 and pending[0].dispatch_state == "pending"
    assert _complete(pending[0].job_id)["probe_only"]
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TRIGGER reject_confirmation")
    recovered = submit_studio_workflow(SubmissionStore(path), prepared, BINDING, _probe)
    assert recovered.job_id == pending[0].job_id and recovered.dispatch_state == "confirmed"
    assert _CALLS.count(recovered.job_id) == 1


def test_studio_queue_token_conflict_never_dispatches_new_work(
    prepared: PreparedGeneration, tmp_path: Path
) -> None:
    store = SubmissionStore(tmp_path / "submissions.sqlite")
    first = submit_studio_workflow(store, prepared, BINDING, _probe)
    with pytest.raises(SubmissionConflict):
        submit_studio_workflow(store, prepared, "c" * 64, _probe)
    _complete(first.job_id)
    assert list(_CALLS) == [first.job_id]


def test_studio_queue_refuses_conflicting_limits() -> None:
    queue = configure_studio_queue()
    assert queue.concurrency == 1 and queue.worker_concurrency == 1
    queue.set_concurrency(2)
    try:
        with pytest.raises(StudioQueueError, match="configuration"):
            configure_studio_queue()
        assert queue.concurrency == 2
    finally:
        queue.set_concurrency(1)


def test_studio_queue_refuses_unregistered_callback_without_reservation(
    prepared: PreparedGeneration, tmp_path: Path
) -> None:
    store = SubmissionStore(tmp_path / "submissions.sqlite")
    with pytest.raises(StudioQueueError, match="registered"):
        submit_studio_workflow(store, prepared, BINDING, lambda job_id: {"job_id": job_id})
    assert store.pending() == []


def test_studio_queue_refuses_existing_identity_on_wrong_queue(
    prepared: PreparedGeneration, tmp_path: Path
) -> None:
    store = SubmissionStore(tmp_path / "submissions.sqlite")
    reserved = store.reserve(prepared, BINDING, "hawedit.studio.queue.probe")
    with SetWorkflowID(reserved.job_id):
        DBOS.start_workflow(_probe, reserved.job_id)
    _complete(reserved.job_id)
    with pytest.raises(StudioQueueError):
        submit_studio_workflow(store, prepared, BINDING, _probe)
    refused = store.get(reserved.job_id)
    assert refused.dispatch_state == "pending" and refused.last_error
    assert _CALLS.count(reserved.job_id) == 1


def test_studio_outbox_reconciles_enqueued_work_in_another_process(
    prepared: PreparedGeneration, tmp_path: Path
) -> None:
    packet = tmp_path / "prepared.json"
    packet.write_text(json.dumps(asdict(prepared)), encoding="utf-8")
    child = textwrap.dedent("""
        import json, os, sqlite3, sys, time
        from pathlib import Path
        from dbos import DBOS
        from hawedit.studio_generation import PreparedGeneration
        from hawedit.studio_queue import submit_studio_workflow
        from hawedit.studio_submissions import SubmissionStore, StudioStorageError
        root, phase = Path(sys.argv[1]), sys.argv[2]
        @DBOS.workflow(name="hawedit.studio.process.probe")
        def probe(job_id):
            with (root / "probe-calls.txt").open("a", encoding="utf-8") as stream:
                stream.write(job_id + "\\n")
            return {"job_id": job_id, "probe_only": True}
        DBOS(config={"name":"hawedit", "system_database_url":f"sqlite:///{root / 'dbos.sqlite'}"})
        if phase == "crash":
            DBOS.listen_queues([])
        DBOS.launch()
        data = json.loads((root / "prepared.json").read_text(encoding="utf-8"))
        data["argv"] = tuple(data["argv"])
        prepared = PreparedGeneration(**data)
        store = SubmissionStore(root / "submissions.sqlite")
        if phase == "crash":
            with sqlite3.connect(store.path) as connection:
                connection.execute("CREATE TRIGGER reject_ack BEFORE UPDATE ON submissions "
                    "WHEN NEW.dispatch_state='confirmed' BEGIN SELECT RAISE(ABORT,'lost ack'); END")
            try:
                submit_studio_workflow(store, prepared, "b" * 64, probe)
            except StudioStorageError:
                pending = store.pending()
                assert len(pending) == 1
                assert DBOS.get_workflow_status(pending[0].job_id).status == "ENQUEUED"
                assert not (root / "probe-calls.txt").exists()
                os._exit(17)
            raise AssertionError("Expected interrupted acknowledgement")
        with sqlite3.connect(store.path) as connection:
            connection.execute("DROP TRIGGER reject_ack")
        job = submit_studio_workflow(store, prepared, "b" * 64, probe)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            status = DBOS.get_workflow_status(job.job_id)
            if status is not None and status.status == "SUCCESS":
                break
            time.sleep(0.02)
        else:
            raise AssertionError("Bounded recovery timeout")
        assert DBOS.retrieve_workflow(job.job_id).get_result()["probe_only"]
        assert store.get(job.job_id).dispatch_state == "confirmed" and store.pending() == []
        print(json.dumps({"job_id":job.job_id,"status":"confirmed-probe"}), flush=True)
        DBOS.destroy()
    """)
    first = subprocess.run(
        [sys.executable, "-c", child, str(tmp_path), "crash"],
        capture_output=True,
        text=True,
        timeout=25,
    )
    assert first.returncode == 17, first.stderr
    assert SubmissionStore(tmp_path / "submissions.sqlite").pending()
    second = subprocess.run(
        [sys.executable, "-c", child, str(tmp_path), "recover"],
        capture_output=True,
        text=True,
        timeout=25,
    )
    assert second.returncode == 0, second.stderr
    observation = json.loads(second.stdout.splitlines()[-1])
    assert (tmp_path / "probe-calls.txt").read_text(encoding="utf-8").splitlines() == [
        observation["job_id"]
    ]
    assert SubmissionStore(tmp_path / "submissions.sqlite").pending() == []
