"""Real SQLite identity/outbox behavior; not model or publication acceptance."""

from __future__ import annotations

import io
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from hawedit.studio_generation import (
    GenerationRequest,
    PreparedGeneration,
    ProducerSelection,
    prepare_generation,
)
from hawedit.studio_submissions import (
    StudioStorageError,
    SubmissionConflict,
    SubmissionStore,
)
from hawedit.studio_uploads import UploadStore
from studio_test_storage import create_private_test_root, seed_private_file

MEDIA = Path(__file__).resolve().parents[1] / "tests/fixtures/kurdish-speech-3cuts.mp4"
BINDING = "b" * 64
WORKER = "hawedit.studio.probe"


@pytest.fixture(name="tmp_path")
def _private_tmp_path(tmp_path: Path) -> Path:
    return create_private_test_root(tmp_path)


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
            "client_token": "submission-token-1",
            "options": {},
        }
    )
    return prepare_generation(request, uploads, tmp_path / "temporary", ProducerSelection("gemini"))


def test_studio_submission_tokens_survive_reconstruction(
    prepared: PreparedGeneration, tmp_path: Path
) -> None:
    path = tmp_path / "submissions.sqlite"
    first = SubmissionStore(path).reserve(prepared, BINDING, WORKER)
    second = SubmissionStore(path).reserve(prepared, BINDING, WORKER)
    assert first == second and first.dispatch_state == "pending"
    assert first.job_id.startswith("studio-") and len(first.job_id) == 71
    store = SubmissionStore(path)
    assert store.get(first.job_id) == first
    assert store.pending() == [first]
    assert first.arguments[0] == prepared.argv[0]
    assert not any(argument.startswith("--work-dir=") for argument in first.arguments)
    assert store.work_dir(first.job_id).is_relative_to(path.parent / "studio-artifacts")


def test_studio_submission_same_content_different_token_shares_identity(
    prepared: PreparedGeneration, tmp_path: Path
) -> None:
    store = SubmissionStore(tmp_path / "submissions.sqlite")
    first = store.reserve(prepared, BINDING, WORKER)
    second = store.reserve(replace(prepared, client_token="submission-token-2"), BINDING, WORKER)
    assert first == second and len(store.pending()) == 1
    assert (
        store.reserve(replace(prepared, client_token="submission-token-2"), BINDING, WORKER)
        == first
    )


@pytest.mark.parametrize("change", ["runtime", "worker", "arguments"])
def test_studio_submission_changed_token_content_conflicts(
    prepared: PreparedGeneration, tmp_path: Path, change: str
) -> None:
    store = SubmissionStore(tmp_path / "submissions.sqlite")
    first = store.reserve(prepared, BINDING, WORKER)
    binding, worker = BINDING, WORKER
    if change == "runtime":
        binding = "c" * 64
    elif change == "worker":
        worker = "hawedit.studio.other"
    else:
        prepared = replace(prepared, argv=(*prepared.argv, "--hook-text=changed"))
    with pytest.raises(SubmissionConflict, match="token"):
        store.reserve(prepared, binding, worker)
    assert store.pending() == [first]


def test_studio_submission_ignores_disposable_work_directory(
    prepared: PreparedGeneration, tmp_path: Path
) -> None:
    store = SubmissionStore(tmp_path / "submissions.sqlite")
    first = store.reserve(prepared, BINDING, WORKER)
    changed = replace(
        prepared,
        argv=tuple(
            "--work-dir=elsewhere" if a.startswith("--work-dir=") else a for a in prepared.argv
        ),
    )
    assert store.reserve(changed, BINDING, WORKER) == first


def test_studio_submission_multiple_connections_commit_one_identity(
    prepared: PreparedGeneration, tmp_path: Path
) -> None:
    path = tmp_path / "submissions.sqlite"
    stores = [SubmissionStore(path) for _ in range(4)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = list(pool.map(lambda store: store.reserve(prepared, BINDING, WORKER), stores))
    assert all(job == jobs[0] for job in jobs)
    assert SubmissionStore(path).pending() == [jobs[0]]


def test_studio_submission_storage_failure_rolls_back_token_and_job(
    prepared: PreparedGeneration, tmp_path: Path
) -> None:
    path = tmp_path / "submissions.sqlite"
    store = SubmissionStore(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TRIGGER reject_token BEFORE INSERT ON client_tokens "
            "BEGIN SELECT RAISE(ABORT, 'injected storage outage'); END"
        )
    with pytest.raises(StudioStorageError, match="storage"):
        store.reserve(prepared, BINDING, WORKER)
    assert store.pending() == []
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT count(*) FROM client_tokens").fetchone()[0] == 0
        connection.execute("DROP TRIGGER reject_token")
    assert store.reserve(prepared, BINDING, WORKER).dispatch_state == "pending"


def test_studio_submission_locked_storage_is_a_bounded_visible_refusal(
    prepared: PreparedGeneration, tmp_path: Path
) -> None:
    path = tmp_path / "submissions.sqlite"
    store = SubmissionStore(path, timeout_seconds=0.1)
    with sqlite3.connect(path) as blocker:
        blocker.execute("BEGIN IMMEDIATE")
        with pytest.raises(StudioStorageError, match="locked"):
            store.reserve(prepared, BINDING, WORKER)
        blocker.rollback()
    assert store.pending() == []


@pytest.mark.parametrize("damage", ["json", "identity", "oversized"])
def test_studio_submission_malformed_snapshot_is_not_silently_loaded(
    prepared: PreparedGeneration, tmp_path: Path, damage: str
) -> None:
    path = tmp_path / "submissions.sqlite"
    store = SubmissionStore(path)
    job = store.reserve(prepared, BINDING, WORKER)
    with sqlite3.connect(path) as connection:
        raw = connection.execute("SELECT snapshot_json FROM submissions").fetchone()[0]
        if damage == "json":
            raw = "{"
        elif damage == "identity":
            snapshot = json.loads(raw)
            snapshot["source_sha256"] = "d" * 64
            raw = json.dumps(snapshot)
        else:
            raw = " " * (128 * 1024 + 1)
        connection.execute("UPDATE submissions SET snapshot_json=?", (raw,))
    with pytest.raises(StudioStorageError, match="snapshot"):
        store.get(job.job_id)
    with pytest.raises(StudioStorageError, match="snapshot"):
        store.pending()


@pytest.mark.parametrize("kind", ["unknown-version", "unversioned-foreign", "not-a-database"])
def test_studio_submission_refuses_unknown_or_corrupt_database(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "submissions.sqlite"
    seed_private_file(path, b"")
    if kind == "not-a-database":
        path.write_bytes(b"not a database")
    else:
        with sqlite3.connect(path) as connection:
            if kind == "unknown-version":
                connection.execute("PRAGMA user_version=99")
            else:
                connection.execute("CREATE TABLE unrelated (value TEXT)")
    before = path.read_bytes()
    with pytest.raises(StudioStorageError):
        SubmissionStore(path)
    assert path.read_bytes() == before


def test_studio_submission_confirmation_is_not_publication(
    prepared: PreparedGeneration, tmp_path: Path
) -> None:
    store = SubmissionStore(tmp_path / "submissions.sqlite")
    job = store.reserve(prepared, BINDING, WORKER)
    store.note_dispatch_error(job.job_id, "Acknowledgement uncertain")
    assert store.get(job.job_id).last_error == "Acknowledgement uncertain"
    store.confirm_dispatch(job.job_id)
    confirmed = store.get(job.job_id)
    assert confirmed.dispatch_state == "confirmed" and confirmed.last_error is None
    assert store.pending() == []
    assert not hasattr(confirmed, "publication_verified") and not hasattr(confirmed, "status")


def test_studio_submission_late_error_cannot_downgrade_confirmed_dispatch(
    prepared: PreparedGeneration, tmp_path: Path
) -> None:
    store = SubmissionStore(tmp_path / "submissions.sqlite")
    job = store.reserve(prepared, BINDING, WORKER)
    store.confirm_dispatch(job.job_id)
    store.note_dispatch_error(job.job_id, "Concurrent request acknowledgement failed")
    confirmed = store.get(job.job_id)
    assert confirmed.dispatch_state == "confirmed" and confirmed.last_error is None


def test_studio_submission_dangling_token_is_visible_corruption(
    prepared: PreparedGeneration, tmp_path: Path
) -> None:
    path = tmp_path / "submissions.sqlite"
    store = SubmissionStore(path)
    job = store.reserve(prepared, BINDING, WORKER)
    with sqlite3.connect(path) as connection:
        connection.execute("DELETE FROM submissions WHERE job_id=?", (job.job_id,))
    with pytest.raises(StudioStorageError, match="missing snapshot"):
        store.reserve(prepared, BINDING, WORKER)


def test_studio_submission_deep_snapshot_is_contextual_refusal(
    prepared: PreparedGeneration, tmp_path: Path
) -> None:
    path = tmp_path / "submissions.sqlite"
    store = SubmissionStore(path)
    job = store.reserve(prepared, BINDING, WORKER)
    depth = 16384
    raw = "[" * depth + "0" + "]" * depth
    assert len(raw) < 128 * 1024
    with pytest.raises(RecursionError):
        json.loads(raw)
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE submissions SET snapshot_json=?", (raw,))
    with pytest.raises(StudioStorageError, match="snapshot"):
        store.get(job.job_id)


def test_studio_submission_deep_preparation_refuses_before_reservation(
    prepared: PreparedGeneration, tmp_path: Path
) -> None:
    store = SubmissionStore(tmp_path / "submissions.sqlite")
    depth = 16384
    raw = "[" * depth + "0" + "]" * depth
    assert len(raw) < 128 * 1024
    with pytest.raises(RecursionError):
        json.loads(raw)
    with pytest.raises(ValueError, match="configuration"):
        store.reserve(replace(prepared, configuration_json=raw), BINDING, WORKER)
    assert store.pending() == []


@pytest.mark.parametrize("damage", ["hash", "configuration", "missing-work-dir"])
def test_studio_submission_refuses_inconsistent_preparation(
    prepared: PreparedGeneration, tmp_path: Path, damage: str
) -> None:
    store = SubmissionStore(tmp_path / "submissions.sqlite")
    if damage == "hash":
        prepared = replace(prepared, content_sha256="a" * 64)
    elif damage == "configuration":
        prepared = replace(prepared, configuration_json="{}")
    else:
        prepared = replace(
            prepared, argv=tuple(a for a in prepared.argv if not a.startswith("--work-dir="))
        )
    with pytest.raises(ValueError):
        store.reserve(prepared, BINDING, WORKER)
    assert store.pending() == []
