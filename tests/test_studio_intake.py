"""Real private SQLite intake bounds, not runtime, authorization or publication evidence."""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import subprocess
import sys
import textwrap
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import pytest

from hawedit.studio_generation import GenerationRequest, ProducerSelection, prepare_generation
from hawedit.studio_submissions import StudioStorageError, SubmissionStore, _identity
from hawedit.studio_uploads import UploadStore
from studio_test_storage import create_private_test_root

MEDIA = Path(__file__).resolve().parents[1] / "tests/fixtures/kurdish-speech-3cuts.mp4"


@pytest.fixture(name="tmp_path")
def _private_tmp_path(tmp_path: Path) -> Path:
    return create_private_test_root(tmp_path)


@pytest.fixture
def store(tmp_path: Path) -> SubmissionStore:
    uploads = UploadStore(tmp_path / "uploads")
    data = MEDIA.read_bytes()
    ticket = uploads.begin("episode.mp4", len(data))
    source = uploads.receive(ticket["upload_id"], io.BytesIO(data), len(data))
    request = GenerationRequest.from_payload(
        {
            "schema": 1,
            "source_id": source["source_id"],
            "client_token": "intake-source-token-0001",
            "options": {},
        }
    )
    prepared = prepare_generation(
        request, uploads, tmp_path / "temporary", ProducerSelection("gemini")
    )
    result = SubmissionStore(tmp_path / "intake.sqlite")
    result.reserve(prepared, "b" * 64, "hawedit.studio.intake.probe")
    return result


def _rows(store: SubmissionStore) -> list[tuple[Any, ...]]:
    with sqlite3.connect(store.path) as connection:
        return connection.execute("SELECT * FROM submissions ORDER BY job_id").fetchall()


def _seed(store: SubmissionStore, count: int) -> list[str]:
    """Seed valid immutable identity controls, never execution authority or model output."""
    with sqlite3.connect(store.path) as connection:
        original = connection.execute(
            "SELECT job_id,snapshot_json,created_at FROM submissions LIMIT 1"
        ).fetchone()
        ids = [original[0]]
        for number in range(1, count):
            snapshot = json.loads(original[1])
            snapshot["execution_binding_sha256"] = hashlib.sha256(str(number).encode()).hexdigest()
            job_id = _identity(snapshot)
            raw = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False)
            connection.execute(
                "INSERT INTO submissions VALUES (?,?, 'pending',NULL,?)",
                (job_id, raw, original[2] + number),
            )
            connection.execute(
                "INSERT INTO client_tokens VALUES (?,?)", (f"intake-seed-token-{number}", job_id)
            )
            ids.append(job_id)
        return ids


def test_pending_overflow_refuses_before_decode_and_preserves_jobs(store: SubmissionStore) -> None:
    _seed(store, 1001)
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE submissions SET snapshot_json='{' "
            "WHERE created_at=(SELECT MIN(created_at) FROM submissions)"
        )
    before = _rows(store)
    with pytest.raises(StudioStorageError, match="job limit"):
        store.pending()
    assert _rows(store) == before and len(before) == 1001


def test_pending_byte_overflow_refuses_before_decode(store: SubmissionStore) -> None:
    with sqlite3.connect(store.path) as connection:
        connection.execute("UPDATE submissions SET snapshot_json='{'")
    before = _rows(store)
    with pytest.raises(StudioStorageError, match="byte limit"):
        store.pending(max_bytes=1)
    assert _rows(store) == before


@pytest.mark.parametrize(
    "limits",
    [
        {"max_jobs": True},
        {"max_jobs": 0},
        {"max_jobs": 1.5},
        {"max_jobs": 10001},
        {"max_bytes": True},
        {"max_bytes": 0},
        {"max_bytes": 256 * 1024 * 1024 + 1},
        {"max_seconds": True},
        {"max_seconds": 0},
        {"max_seconds": -1},
        {"max_seconds": float("nan")},
        {"max_seconds": float("inf")},
        {"max_seconds": 11},
        {"max_seconds": 10**1000},
        {"max_seconds": -(10**1000)},
    ],
)
def test_invalid_intake_limits_are_refused(store: SubmissionStore, limits: dict[str, Any]) -> None:
    before = _rows(store)
    with pytest.raises(ValueError, match="limit|deadline"):
        store.pending(**limits)
    assert _rows(store) == before


def test_native_query_deadline_refuses_without_losing_jobs(store: SubmissionStore) -> None:
    _seed(store, 300)
    before = _rows(store)
    with pytest.raises(StudioStorageError, match="query budget") as refusal:
        store.pending(max_seconds=1e-9)
    assert isinstance(refusal.value.__cause__, sqlite3.OperationalError)
    assert refusal.value.__cause__.sqlite_errorcode == sqlite3.SQLITE_INTERRUPT
    assert _rows(store) == before
    assert len(store.pending()) == 300


def test_recovery_snapshot_reads_exact_ids_in_requested_order(store: SubmissionStore) -> None:
    ids = _seed(store, 3)
    store.confirm_dispatch(ids[0])
    result = store.recovery_snapshot([ids[2], ids[0]])
    assert isinstance(result, tuple)
    assert tuple(record.job_id for record in result) == (ids[2], ids[0])
    assert result == (store.get(ids[2]), store.get(ids[0]))
    assert result[1].dispatch_state == "confirmed"
    assert store.recovery_snapshot([]) == ()


@pytest.mark.parametrize("kind", ["duplicate", "missing", "malformed", "overflow"])
def test_recovery_snapshot_never_omits_or_duplicates_work(
    store: SubmissionStore, kind: str
) -> None:
    ids = _seed(store, 2)
    selected = {
        "duplicate": [ids[0], ids[0]],
        "missing": [ids[0], "studio-" + "f" * 64],
        "malformed": ["filename.mp4"],
        "overflow": ids,
    }[kind]
    before = _rows(store)
    with pytest.raises(
        (ValueError, StudioStorageError), match="duplicate|missing|Invalid|job limit"
    ):
        store.recovery_snapshot(selected, max_jobs=1 if kind == "overflow" else 1000)
    assert _rows(store) == before


@pytest.mark.parametrize("selected", ["studio-" + "b" * 64, [7]])
def test_recovery_snapshot_refuses_wrong_input_container(
    store: SubmissionStore, selected: object
) -> None:
    with pytest.raises(ValueError, match="IDs|Invalid"):
        store.recovery_snapshot(cast(Sequence[str], selected))


@pytest.mark.parametrize("field", ["job_id", "dispatch_state", "created_at"])
def test_bounded_projection_does_not_repair_invalid_records(
    store: SubmissionStore, field: str
) -> None:
    with sqlite3.connect(store.path) as connection:
        connection.execute("PRAGMA ignore_check_constraints=ON")
        original_id = connection.execute("SELECT job_id FROM submissions").fetchone()[0]
        prefix = {"job_id": original_id, "dispatch_state": "confirmed", "created_at": "123"}[field]
        # Field names are a closed test parameter set; values remain bound SQLite parameters.
        connection.execute(f"UPDATE submissions SET {field}=?", (prefix + "x" * 200000,))
        job_id = connection.execute("SELECT job_id FROM submissions").fetchone()[0]
    before = _rows(store)
    with pytest.raises((ValueError, StudioStorageError), match="snapshot|Invalid"):
        if field == "job_id":
            store.pending()
        else:
            store.get(job_id)
    assert _rows(store) == before


def test_normal_pending_snapshot_preserves_list_contract(store: SubmissionStore) -> None:
    ids = _seed(store, 3)
    before = _rows(store)
    result = store.pending(max_jobs=3)
    assert isinstance(result, list)
    assert [record.job_id for record in result] == ids
    assert result == [store.get(job_id) for job_id in ids]
    assert _rows(store) == before


def test_byte_budget_counts_utf8_and_diagnostics(store: SubmissionStore) -> None:
    job_id = _rows(store)[0][0]
    store.note_dispatch_error(job_id, "\u06a9" * 20)
    with sqlite3.connect(store.path) as connection:
        size = connection.execute(
            "SELECT length(CAST(job_id AS BLOB))+length(CAST(snapshot_json AS BLOB))+"
            "length(CAST(last_error AS BLOB)) FROM submissions"
        ).fetchone()[0]
    assert store.pending(max_bytes=size) == [store.get(job_id)]
    with pytest.raises(StudioStorageError, match="byte limit"):
        store.pending(max_bytes=size - 1)


def test_null_primary_key_refuses_contextually_without_repair(store: SubmissionStore) -> None:
    with sqlite3.connect(store.path) as connection:
        connection.execute("UPDATE submissions SET job_id=NULL")
    before = _rows(store)
    assert before[0][0] is None
    with pytest.raises(StudioStorageError, match="snapshot"):
        store.pending()
    assert _rows(store) == before


def test_byte_refusal_does_not_bulk_materialize_remaining_records(store: SubmissionStore) -> None:
    _seed(store, 60)
    with sqlite3.connect(store.path) as connection:
        connection.execute("UPDATE submissions SET snapshot_json=?", ("x" * 80000,))
    before = _rows(store)
    code = textwrap.dedent(
        """
        import json, sys, tracemalloc
        from pathlib import Path
        from hawedit.studio_submissions import SubmissionStore, StudioStorageError
        store = SubmissionStore(Path(sys.argv[1]))
        tracemalloc.start()
        try:
            store.pending(max_bytes=1)
        except StudioStorageError as error:
            assert 'byte limit' in str(error), str(error)
            print(json.dumps({'python_heap_peak': tracemalloc.get_traced_memory()[1]}))
        else:
            raise AssertionError('Byte overflow was not refused')
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(store.path)], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    observation = json.loads(result.stdout)
    assert observation["python_heap_peak"] < 1024 * 1024, observation
    assert _rows(store) == before


def test_empty_recovery_snapshot_does_not_hide_lost_storage(store: SubmissionStore) -> None:
    store.path.unlink()
    with pytest.raises(StudioStorageError):
        store.recovery_snapshot([])
    assert not store.path.exists()
