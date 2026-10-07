"""Real private uploads/SQLite/event replay, not producer or publication evidence."""

from __future__ import annotations

import io
import json
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from hawedit.events import RunEvent, RunState
from hawedit.studio_generation import GenerationRequest, ProducerSelection, prepare_generation
from hawedit.studio_submissions import SubmissionStore
from hawedit.studio_uploads import UploadStore
from studio_test_storage import create_private_test_root

if TYPE_CHECKING:
    from hawedit.studio_attempts import AttemptStore

MEDIA = Path(__file__).parent / "fixtures" / "kurdish-speech-3cuts.mp4"


@pytest.fixture(name="tmp_path")
def _private_tmp_path(tmp_path: Path) -> Path:
    return create_private_test_root(tmp_path)


def _state(root: Path) -> tuple[AttemptStore, SubmissionStore, str]:
    from hawedit.studio_attempts import AttemptStore

    uploads = UploadStore(root / "uploads")
    data = MEDIA.read_bytes()
    ticket = uploads.begin("episode.mp4", len(data))
    source = uploads.receive(ticket["upload_id"], io.BytesIO(data), len(data))
    request = GenerationRequest.from_payload(
        {
            "schema": 1,
            "source_id": source["source_id"],
            "client_token": "attempt-journal-token-1",
            "options": {},
        }
    )
    prepared = prepare_generation(request, uploads, root / "unused", ProducerSelection("gemini"))
    submissions = SubmissionStore(root / "submissions.sqlite")
    job = submissions.reserve(prepared, "b" * 64, "hawedit.studio.producer")
    attempts = AttemptStore(root / "attempts.sqlite", submissions, timeout_seconds=0.1)
    return attempts, submissions, job.job_id


def _event(sequence: int = 1, run_id: str = "episode-1") -> RunEvent:
    return RunEvent(run_id, sequence, 1234, "ingest", RunState.STARTED)


def test_attempt_binds_real_submission_and_preserves_outbox(tmp_path: Path) -> None:
    attempts, submissions, job_id = _state(tmp_path)
    before = submissions.get(job_id)
    record = attempts.begin(job_id, "episode-1")
    assert record.job_id == job_id
    assert record.number == 1
    assert record.state == "running"
    assert record.source_sha256 == before.source_sha256
    assert record.request_sha256 == before.request_sha256
    assert record.execution_binding_sha256 == before.execution_binding_sha256
    assert attempts.get(job_id) == record
    assert submissions.get(job_id) == before
    with sqlite3.connect(submissions.path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (1,)
        assert connection.execute("SELECT count(*) FROM submissions").fetchone() == (1,)
    with pytest.raises(KeyError):
        attempts.begin("studio-" + "c" * 64, "episode-2")


def test_attempt_duplicate_and_serial_launch_refuse(tmp_path: Path) -> None:
    from hawedit.studio_attempts import AttemptConflict

    attempts, submissions, job_id = _state(tmp_path)
    original = attempts.begin(job_id, "episode-1")
    with pytest.raises(AttemptConflict, match="retained"):
        attempts.begin(job_id, "episode-1")
    # A distinct actual immutable job must not start alongside the retained worker.
    with sqlite3.connect(submissions.path) as connection:
        snapshot = json.loads(
            connection.execute("SELECT snapshot_json FROM submissions").fetchone()[0]
        )
    from hawedit.studio_submissions import _identity

    snapshot["execution_binding_sha256"] = "d" * 64
    other_id = _identity(snapshot)
    with sqlite3.connect(submissions.path) as connection:
        connection.execute(
            "INSERT INTO submissions VALUES (?,?,'pending',NULL,?)",
            (other_id, json.dumps(snapshot), time.time()),
        )
    with pytest.raises(AttemptConflict, match="running"):
        attempts.begin(other_id, "episode-2")
    assert attempts.get(job_id) == original
    with pytest.raises(KeyError):
        attempts.get(other_id)


def test_attempt_events_are_transactional_and_scoped(tmp_path: Path) -> None:
    from hawedit.studio_attempts import AttemptConflict

    attempts, _, job_id = _state(tmp_path)
    attempts.begin(job_id, "episode-1")
    attempts.append(job_id, _event())
    attempts.append(job_id, replace(_event(2), state=RunState.COMPLETED))
    before = attempts.get(job_id)
    for event in (_event(2), _event(4), _event(3, "wrong-run")):
        with pytest.raises(AttemptConflict):
            attempts.append(job_id, event)
    assert attempts.get(job_id) == before
    assert attempts.events(job_id) == (_event(), replace(_event(2), state=RunState.COMPLETED))
    projection = attempts.projection(job_id)
    assert projection["attempt"] == 1
    assert projection["stage_progress"] == {"observed": 1, "finished": 1}
    assert projection["work_progress"] is None
    assert projection["publication_verified"] is False
    assert projection["state"] == "running"


@pytest.mark.parametrize(
    "changes",
    [
        {"sequence": True},
        {"sequence": 1.0},
        {"at_ms": True},
        {"at_ms": 2**63},
        {"stage": "x\x00y"},
        {"stage": "x" * 129},
        {"model": "not-a-billed-event"},
        {"candidate_id": "not-a-billed-event"},
        {"tokens": True},
        {"cost_usd_estimate": float("nan")},
        {"cost_usd_estimate": float("inf")},
        {"reason": "x" * 4097, "state": RunState.SKIPPED},
    ],
)
def test_attempt_rejects_malformed_event(tmp_path: Path, changes: dict[str, Any]) -> None:
    attempts, _, job_id = _state(tmp_path)
    attempts.begin(job_id, "episode-1")
    with pytest.raises(ValueError):
        attempts.append(job_id, replace(_event(), **changes))
    assert attempts.events(job_id) == ()
    assert attempts.get(job_id).last_sequence == 0


@pytest.mark.parametrize(
    "state", ["awaiting-review", "partially-completed", "failed", "interrupted", "cancelled"]
)
def test_attempt_terminal_outcome_is_not_publication(tmp_path: Path, state: str) -> None:
    from hawedit.studio_attempts import AttemptConflict

    attempts, _, job_id = _state(tmp_path)
    attempts.begin(job_id, "episode-1")
    attempts.append(job_id, _event())
    attempts.finish(job_id, state, "Private outcome; reconciliation is separate")
    record = attempts.get(job_id)
    assert record.state == state
    assert record.finished_ms is not None
    assert attempts.projection(job_id)["publication_verified"] is False
    with pytest.raises(AttemptConflict):
        attempts.begin(job_id, "episode-1")
    with pytest.raises(AttemptConflict):
        attempts.append(job_id, _event(2))
    with pytest.raises(AttemptConflict):
        attempts.finish(job_id, state, "changed")
    assert attempts.get(job_id) == record
    with pytest.raises(ValueError):
        attempts.finish(job_id, "completed", "not publication")
    assert attempts.events(job_id) == (_event(),)


@pytest.mark.parametrize(
    "damage", ["identity", "state", "nul", "oversize", "event", "gap", "cursor"]
)
def test_attempt_refuses_corrupted_evidence(tmp_path: Path, damage: str) -> None:
    from hawedit.studio_private import StudioStorageError

    attempts, _, job_id = _state(tmp_path)
    attempts.begin(job_id, "episode-1")
    attempts.append(job_id, _event())
    with sqlite3.connect(attempts.path) as connection:
        raw = json.loads(connection.execute("SELECT record_json FROM attempts").fetchone()[0])
        if damage == "identity":
            raw["source_sha256"] = "e" * 64
        elif damage == "state":
            raw["state"] = "completed"
        elif damage == "nul":
            raw["diagnostic"] = "before\x00after"
        elif damage == "oversize":
            raw["diagnostic"] = "x" * 9000
        elif damage == "cursor":
            raw["last_sequence"] = 2
        elif damage == "event":
            event = _event().to_dict()
            event["run_id"] = "wrong"
            connection.execute("UPDATE events SET event_json=?", (json.dumps(event),))
        elif damage == "gap":
            connection.execute("DELETE FROM events")
        connection.execute("UPDATE attempts SET record_json=?", (json.dumps(raw),))
    with pytest.raises(StudioStorageError):
        attempts.projection(job_id)
    with pytest.raises(StudioStorageError):
        attempts.append(job_id, _event(2))


@pytest.mark.parametrize("damage", ["trigger", "table", "version", "unversioned"])
def test_attempt_refuses_foreign_schema(tmp_path: Path, damage: str) -> None:
    from hawedit.studio_attempts import AttemptStore
    from hawedit.studio_private import StudioStorageError

    attempts, submissions, job_id = _state(tmp_path)
    attempts.begin(job_id, "episode-1")
    with sqlite3.connect(attempts.path) as connection:
        if damage == "trigger":
            connection.execute(
                "CREATE TRIGGER foreign_trigger AFTER INSERT ON events "
                "BEGIN DELETE FROM events; END"
            )
        elif damage == "table":
            connection.execute("CREATE TABLE foreign_table(value TEXT)")
        else:
            connection.execute("PRAGMA user_version=" + ("99" if damage == "version" else "0"))
    with pytest.raises(StudioStorageError):
        AttemptStore(attempts.path, submissions)
    with pytest.raises(StudioStorageError):
        attempts.get(job_id)
    with sqlite3.connect(attempts.path) as connection:
        assert connection.execute("SELECT count(*) FROM attempts").fetchone() == (1,)


def test_attempt_storage_contention_is_bounded(tmp_path: Path) -> None:
    from hawedit.studio_private import StudioStorageError

    attempts, _, job_id = _state(tmp_path)
    attempts.begin(job_id, "episode-1")
    with sqlite3.connect(attempts.path) as blocker:
        blocker.execute("BEGIN IMMEDIATE")
        started = time.monotonic()
        with pytest.raises(StudioStorageError, match="storage"):
            attempts.append(job_id, _event())
        assert time.monotonic() - started < 3
    assert attempts.events(job_id) == ()
    assert attempts.get(job_id).last_sequence == 0


def test_attempt_refuses_replaced_storage(tmp_path: Path) -> None:
    from hawedit.studio_private import StudioStorageError

    attempts, _, job_id = _state(tmp_path)
    attempts.begin(job_id, "episode-1")
    retained = attempts.path.with_name("retained.sqlite")
    attempts.path.rename(retained)
    attempts.path.touch()
    with pytest.raises(StudioStorageError):
        attempts.get(job_id)
    assert retained.stat().st_size > 0
    assert attempts.path.stat().st_size == 0


def test_attempt_process_exit_retains_uncertainty(tmp_path: Path) -> None:
    from hawedit.studio_attempts import AttemptConflict, AttemptStore

    attempts, submissions, job_id = _state(tmp_path)
    program = """
import os, sys
from pathlib import Path
from hawedit.events import RunEvent, RunState
from hawedit.studio_attempts import AttemptStore
from hawedit.studio_submissions import SubmissionStore
root = Path(sys.argv[1])
store = AttemptStore(root/'attempts.sqlite', SubmissionStore(root/'submissions.sqlite'))
store.begin(sys.argv[2], 'episode-1')
store.append(sys.argv[2], RunEvent('episode-1', 1, 1234, 'ingest', RunState.STARTED))
os._exit(17)
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", program, str(tmp_path), job_id],
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 17, result.stderr.decode(errors="replace")
    reopened = AttemptStore(attempts.path, submissions)
    assert reopened.get(job_id).state == "running"
    assert reopened.events(job_id) == (_event(),)
    with pytest.raises(AttemptConflict):
        reopened.begin(job_id, "episode-1")
    assert reopened.projection(job_id)["publication_verified"] is False


@pytest.mark.parametrize("run_id", ["", " ", "x" * 129, "a\x00b", "a\nb"])
def test_attempt_invalid_run_id_creates_no_record(tmp_path: Path, run_id: str) -> None:
    attempts, _, job_id = _state(tmp_path)
    with pytest.raises(ValueError):
        attempts.begin(job_id, run_id)
    with pytest.raises(KeyError):
        attempts.get(job_id)


@pytest.mark.parametrize(
    "field,value",
    [
        ("created_ms", True),
        ("number", 1.0),
        ("last_sequence", True),
        ("finished_ms", 123),
        ("diagnostic", "unexpected"),
    ],
)
def test_attempt_strict_record_types(tmp_path: Path, field: str, value: object) -> None:
    from hawedit.studio_private import StudioStorageError

    attempts, _, job_id = _state(tmp_path)
    attempts.begin(job_id, "episode-1")
    with sqlite3.connect(attempts.path) as connection:
        raw = json.loads(connection.execute("SELECT record_json FROM attempts").fetchone()[0])
        raw[field] = value
        connection.execute("UPDATE attempts SET record_json=?", (json.dumps(raw),))
    with pytest.raises(StudioStorageError):
        attempts.get(job_id)


def test_attempt_refuses_duplicate_json_fields(tmp_path: Path) -> None:
    from hawedit.studio_private import StudioStorageError

    attempts, _, job_id = _state(tmp_path)
    attempts.begin(job_id, "episode-1")
    attempts.append(job_id, _event())
    with sqlite3.connect(attempts.path) as connection:
        raw = connection.execute("SELECT event_json FROM events").fetchone()[0]
        connection.execute("UPDATE events SET event_json=?", (raw[:-1] + ',"sequence":1}',))
    with pytest.raises(StudioStorageError):
        attempts.events(job_id)


def test_attempt_uncommitted_process_exit_rolls_back_events_and_cursor(tmp_path: Path) -> None:
    attempts, _, job_id = _state(tmp_path)
    original = attempts.begin(job_id, "episode-1")
    program = """
import json, os, sqlite3, sys
with sqlite3.connect(sys.argv[1]) as connection:
    connection.execute('BEGIN IMMEDIATE')
    record = json.loads(connection.execute('SELECT record_json FROM attempts').fetchone()[0])
    record['last_sequence'] = 1
    connection.execute('UPDATE attempts SET record_json=?', (json.dumps(record),))
    connection.execute('INSERT INTO events VALUES (?,?,?)', (sys.argv[2], 1, '{}'))
    os._exit(19)
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", program, str(attempts.path), job_id],
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 19, result.stderr.decode(errors="replace")
    assert attempts.get(job_id) == original
    assert attempts.events(job_id) == ()


def test_attempt_refuses_outbox_overlap_before_mutation(tmp_path: Path) -> None:
    from hawedit.studio_attempts import AttemptStore
    from hawedit.studio_private import StudioStorageError

    _, submissions, job_id = _state(tmp_path)
    original = submissions.get(job_id)
    with pytest.raises(StudioStorageError):
        AttemptStore(submissions.path, submissions)
    assert submissions.get(job_id) == original


def test_attempt_concurrent_reservations_commit_once(tmp_path: Path) -> None:
    from hawedit.studio_attempts import AttemptConflict, AttemptStore

    attempts, submissions, job_id = _state(tmp_path)
    other = AttemptStore(attempts.path, submissions)

    def reserve(store: AttemptStore) -> str:
        try:
            store.begin(job_id, "episode-1")
            return "reserved"
        except AttemptConflict:
            return "refused"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(reserve, (attempts, other)))
    assert sorted(outcomes) == ["refused", "reserved"]
    assert attempts.get(job_id) == other.get(job_id)
    with sqlite3.connect(attempts.path) as connection:
        assert connection.execute("SELECT count(*) FROM attempts").fetchone() == (1,)


def test_attempt_preserves_skip_billing_and_unicode(tmp_path: Path) -> None:
    attempts, _, job_id = _state(tmp_path)
    attempts.begin(job_id, "episode-1")
    skipped = RunEvent(
        "episode-1",
        1,
        1000,
        "visual",
        RunState.SKIPPED,
        reason="\u0646\u06d5\u0628\u0648\u0648\u0646\u06cc \u0628\u06d5\u06b5\u06af\u06d5",
    )
    billed = RunEvent(
        "episode-1",
        2,
        999,
        "judge",
        RunState.BILLED,
        model="Gemini",
        tokens=123,
        cost_usd_estimate=0.125,
        candidate_id="candidate-1",
    )
    attempts.append(job_id, skipped)
    attempts.append(job_id, billed)
    assert attempts.events(job_id) == (skipped, billed)
    projected = attempts.projection(job_id)
    assert projected["stages"] == [skipped.to_dict()]
    assert projected["stage_progress"] == {"observed": 1, "finished": 1}
    assert projected["events"] == [skipped.to_dict(), billed.to_dict()]
    assert projected["publication_verified"] is False
