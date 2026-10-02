"""Native, non-destructive history adoption; no publication or model-quality claims."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

import pytest

from hawedit.studio_history import HistoryError, read_historical_job, read_history
from hawedit.web import JobInfo, JobManager
from test_web import _handle_request


def stored_job(root: Path, job_id: str = "old-job", **changes: Any) -> Path:
    document = JobInfo(
        job_id,
        "C:/private/creator/video.mp4",
        "completed",
        "render",
        6,
        100,
        1,
        2,
        "title",
        clips=[{"clip_id": "invented", "duration_s": 60, "virality_score": 99}],
        client_token="private-token-that-must-not-leak",
        options={"private": "never-echo-this-value"},
    ).to_dict()
    document.update(changes)
    directory = root / job_id
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "job.json"
    target.write_text(json.dumps(document), encoding="utf-8")
    return target


def http(path: str, *, method: str = "GET") -> tuple[int, dict[str, str], bytes]:
    return _handle_request(f"{method} {path} HTTP/1.1\r\nHost: localhost:8080\r\n\r\n".encode())


def test_studio_migrates_legacy_completion_without_publishing(tmp_path: Path) -> None:
    root = tmp_path / "jobs"
    record = stored_job(root)
    media = record.parent / "clip.mp4"
    media.write_bytes(Path("tests/fixtures/kurdish-speech-3cuts.mp4").read_bytes())
    original = {path: path.read_bytes() for path in (record, media)}
    for _ in range(2):
        history = read_history(root)
        job = history["jobs"][0]
        assert history["available"] is True and history["truncated"] is False
        assert job["status"] == "unverified-historical"
        assert job["recorded_status"] == "completed" and job["historical"] is True
        assert job["publication_verified"] is False and job["published_count"] == 0
        assert job["record_sha256"] == hashlib.sha256(original[record]).hexdigest()
        assert job["clips"] == [] and job["progress_percent"] is None
        assert job["work_progress"] is None and job["stages"] == []
        assert job["source"] == "video.mp4"
        encoded = json.dumps(history)
        assert "private-token" not in encoded and "never-echo" not in encoded
        assert "C:/private" not in encoded and "virality_score" not in encoded
        assert "client_token" not in job and "options" not in job
        assert {path: path.read_bytes() for path in original} == original


@pytest.mark.parametrize("state", ["queued", "running"])
def test_studio_history_abandoned_work_requires_reconciliation(tmp_path: Path, state: str) -> None:
    root = tmp_path / "jobs"
    original = stored_job(root, status=state).read_bytes()
    view = read_historical_job(root, "old-job")
    assert view["status"] == "interrupted" and view["recorded_status"] == state
    assert view["recovery_required"] is True and view["progress_percent"] is None
    assert view["stage"] is None and view["recorded_stage"] == "render"
    assert view["code"] == "legacy_recovery_required"
    assert (root / "old-job" / "job.json").read_bytes() == original


@pytest.mark.parametrize("state", ["failed", "cancelled", "interrupted"])
def test_studio_history_retains_terminal_refusal(tmp_path: Path, state: str) -> None:
    root = tmp_path / "jobs"
    stored_job(root, status=state, error="private C:/secret/provider/key text")
    view = read_historical_job(root, "old-job")
    assert view["status"] == state and view["publication_verified"] is False
    assert view["recovery_required"] is (state == "interrupted")
    assert "C:/secret" not in json.dumps(view)
    assert view["recorded_error_present"] is True


@pytest.mark.parametrize("state", ["awaiting-review", "partially-completed"])
def test_studio_history_review_flags_are_not_authenticated(tmp_path: Path, state: str) -> None:
    root = tmp_path / "jobs"
    stored_job(root, status=state)
    view = read_historical_job(root, "old-job")
    assert view["status"] == "unverified-historical" and view["recorded_status"] == state
    assert view["publication_verified"] is False


@pytest.mark.parametrize(
    "damage",
    [
        "duplicate-json",
        "nonfinite-json",
        "deep-json",
        "invalid-utf8",
        "non-object",
        "wrong-id",
        "unknown-field",
        "unknown-status",
        "boolean-time",
        "string-time",
        "negative-time",
        "boolean-progress",
        "bad-clips",
        "bad-source",
        "surrogate-text",
        "huge-headline",
        "missing-field",
        "oversize",
        "empty",
        "job-directory",
    ],
)
def test_studio_history_malformed_records_are_visible(tmp_path: Path, damage: str) -> None:
    root = tmp_path / "jobs"
    bad = stored_job(root, "bad-job")
    stored_job(root, "good-job")
    data = json.loads(bad.read_bytes())
    replacements: dict[str, Any] = {
        "wrong-id": {"job_id": "elsewhere"},
        "unknown-field": {"published": True},
        "unknown-status": {"status": "trusted-published"},
        "boolean-time": {"created_at": True},
        "string-time": {"created_at": "1"},
        "negative-time": {"updated_at": -1},
        "boolean-progress": {"progress_percent": True},
        "bad-clips": {"clips": {}},
        "bad-source": {"source": []},
        "surrogate-text": {"headline": "\ud800"},
        "huge-headline": {"headline": "x" * 4097},
    }
    if damage in replacements:
        data.update(replacements[damage])
        bad.write_text(json.dumps(data), encoding="utf-8")
    elif damage == "missing-field":
        del data["status"]
        bad.write_text(json.dumps(data), encoding="utf-8")
    elif damage == "job-directory":
        bad.unlink()
        bad.mkdir()
    else:
        payloads = {
            "duplicate-json": b'{"job_id":"bad-job","job_id":"good-job"}',
            "nonfinite-json": b'{"created_at":NaN}',
            "deep-json": b'{"nested":' + b"[" * 16384 + b"0" + b"]" * 16384 + b"}",
            "invalid-utf8": b"\xff",
            "non-object": b"[]",
            "empty": b"",
            "oversize": b" " * (2 * 1024**2 + 1),
        }
        bad.write_bytes(payloads[damage])
    before = bad.read_bytes() if bad.is_file() else None
    result = read_history(root)
    assert [job["job_id"] for job in result["jobs"]] == ["good-job"]
    assert result["available"] is True and result["truncated"] is False
    assert result["diagnostics"] and result["diagnostics"][0]["job_id"] == "bad-job"
    with pytest.raises(HistoryError) as refused:
        read_historical_job(root, "bad-job")
    assert refused.value.status == 409
    if before is not None:
        assert bad.read_bytes() == before


@pytest.mark.parametrize("member", ["job-record", "job-folder", "root"])
def test_studio_history_refuses_links(tmp_path: Path, member: str) -> None:
    original = tmp_path / "original"
    record = stored_job(original)
    original_bytes = record.read_bytes()
    root = tmp_path / "jobs"
    root.mkdir()
    if member == "job-record":
        (root / "old-job").mkdir()
        os.link(record, root / "old-job" / "job.json")
    else:
        link = root if member == "root" else root / "old-job"
        target = original if member == "root" else record.parent
        if member == "root":
            root.rmdir()
        if os.name == "nt":
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(target)],
                check=True,
                capture_output=True,
                timeout=10,
            )
        else:
            link.symlink_to(target, target_is_directory=True)
    result = read_history(root)
    assert result["jobs"] == [] and result["diagnostics"]
    if member == "root":
        assert result["available"] is False
    assert record.read_bytes() == original_bytes


def test_studio_history_limits_and_storage_are_visible(tmp_path: Path) -> None:
    absent = read_history(tmp_path / "missing")
    assert absent["available"] is False and absent["diagnostics"]
    assert absent["jobs"] == [] and absent["truncated"] is False
    root = tmp_path / "jobs"
    for index in range(4):
        stored_job(root, f"old-{index}")
    limited = read_history(root, max_entries=3)
    assert limited["truncated"] is True and len(limited["jobs"]) <= 3
    assert any(item["code"] == "history_scan_limit" for item in limited["diagnostics"])
    with pytest.raises(ValueError):
        read_history(root, max_entries=True)
    with pytest.raises(ValueError):
        read_history(root, max_entries=1001)
    root_file = tmp_path / "root-file"
    root_file.write_bytes(b"foreign storage preserved")
    assert read_history(root_file)["available"] is False
    assert root_file.read_bytes() == b"foreign storage preserved"


def test_studio_history_does_not_silently_drop_unrecognized_entries(tmp_path: Path) -> None:
    root = tmp_path / "jobs"
    stored_job(root)
    (root / "missing-record").mkdir()
    (root / ".hidden-job").mkdir()
    (root / "foreign.txt").write_bytes(b"not a job")
    result = read_history(root)
    assert len(result["jobs"]) == 1 and len(result["diagnostics"]) == 3
    assert all("message" in item and "code" in item for item in result["diagnostics"])
    assert ".hidden-job" not in json.dumps(result)


def test_studio_history_invalid_bytes_count_toward_scan_budget(tmp_path: Path) -> None:
    root = tmp_path / "jobs"
    for index in range(12):
        record = stored_job(root, f"bad-{index}")
        record.write_bytes(b" " * (1024**2 + 1))
    result = read_history(root)
    assert result["jobs"] == [] and result["truncated"] is True
    assert any(item["code"] == "history_scan_limit" for item in result["diagnostics"])


def test_studio_history_encodes_portable_job_and_clip_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from urllib.parse import quote

    import hawedit.web as web

    root = tmp_path / "jobs"
    job_id, clip_id = "old job % name", "clip # name"
    record = stored_job(root, job_id)
    (record.parent / "report.json").write_text(
        json.dumps(
            {
                "episode_manifest": {
                    "clips": [
                        {
                            "clip_id": clip_id,
                            "delivery_dir": "review/clip-directory",
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(web, "JOB_MANAGER", JobManager(root))
    status, _, body = http(f"/api/jobs/{quote(job_id, safe='')}")
    assert status == 200
    view = json.loads(body)
    assert view["job_id"] == job_id
    assert view["clips"][0]["preview_url"] == (
        f"/api/jobs/{quote(job_id, safe='')}/clips/{quote(clip_id, safe='')}/preview"
    )


def test_studio_history_jobs_list_cannot_hide_refused_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hawedit.web as web

    root = tmp_path / "jobs"
    stored_job(root)
    bad = stored_job(root, "bad-job")
    bad.write_bytes(b"malformed persisted record")
    monkeypatch.setattr(web, "JOB_MANAGER", JobManager(root))
    status, _, body = http("/api/jobs")
    document = json.loads(body)
    assert status == 409 and document["code"] == "history_incomplete"
    assert len(document["jobs"]) == 1 and document["diagnostics"]


def test_studio_history_manifest_not_cached_clips_supplies_candidates(tmp_path: Path) -> None:
    root = tmp_path / "jobs"
    record = stored_job(root)
    report = {
        "episode_manifest": {
            "clips": [
                {
                    "clip_id": "actual-clip",
                    "delivery_dir": "review/actual-clip",
                    "title_ckb": "reported",
                    "hook_score": 0.99,
                    "duration_ms": 60000,
                    "publication_verified": True,
                }
            ]
        },
        "publication_verified": True,
    }
    (record.parent / "report.json").write_text(json.dumps(report), encoding="utf-8")
    view = read_historical_job(root, "old-job")
    assert len(view["clips"]) == 1 and view["clips"][0]["clip_id"] == "actual-clip"
    clip = view["clips"][0]
    assert clip["preview_url"] == "/api/jobs/old-job/clips/actual-clip/preview"
    assert clip["state"] == "unverified" and clip["preview_verified"] is False
    assert clip["duration_s"] is None and clip["hook_score"] is None and clip["sha256"] is None
    assert view["publication_verified"] is False and view["published_count"] == 0
    assert read_history(root)["jobs"][0]["clips"] == []


@pytest.mark.parametrize("damage", ["duplicate", "escape", "missing-directory", "wrong-type"])
def test_studio_history_bad_candidate_manifest_is_visible(tmp_path: Path, damage: str) -> None:
    root = tmp_path / "jobs"
    record = stored_job(root)
    row: dict[str, Any] = {"clip_id": "clip-one", "delivery_dir": "review/clip-one"}
    rows: Any = [row]
    if damage == "duplicate":
        rows = [row, row]
    elif damage == "escape":
        row["delivery_dir"] = "../outside"
    elif damage == "missing-directory":
        del row["delivery_dir"]
    else:
        rows = {}
    (record.parent / "report.json").write_text(
        json.dumps({"episode_manifest": {"clips": rows}}), encoding="utf-8"
    )
    view = read_historical_job(root, "old-job")
    assert view["clips"] == [] and view["diagnostics"]
    assert view["diagnostics"][0]["code"] == "candidate_manifest_refused"


def test_studio_history_http_refresh_reads_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hawedit.web as web

    root = tmp_path / "jobs"
    record = stored_job(root)
    manager = JobManager(root)
    monkeypatch.setattr(web, "JOB_MANAGER", manager)
    code, _, body = http("/api/jobs/old-job")
    document = json.loads(body)
    assert code == 200 and document["status"] == "unverified-historical"
    previous = document["record_sha256"]
    stored_job(root, headline="changed-on-disk", status="running")
    code, _, body = http("/api/jobs/old-job")
    document = json.loads(body)
    assert code == 200 and document["headline"] == "changed-on-disk"
    assert document["status"] == "interrupted" and document["record_sha256"] != previous
    record.write_bytes(b"{broken")
    code, _, body = http("/api/jobs/old-job")
    assert code == 409 and json.loads(body)["code"] == "history_record_refused"
    code, _, body = http("/api/history")
    result = json.loads(body)
    assert code == 200 and result["jobs"] == [] and result["diagnostics"]
    code, _, body = http("/api/status")
    result = json.loads(body)
    assert code == 200 and result["history_diagnostics"]
    assert result["history_available"] is True and result["historical_job_count"] == 0
    assert result["latest_reel"] is None
    record.unlink()
    code, _, _ = http("/api/jobs/old-job")
    assert code == 404


@pytest.mark.parametrize("path", ["/api/jobs", "/api/history", "/api/jobs/old-job", "/api/status"])
def test_studio_history_http_head_and_unavailable_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    import hawedit.web as web

    root = tmp_path / "jobs"
    stored_job(root)
    monkeypatch.setattr(web, "JOB_MANAGER", JobManager(root))
    status, headers, body = http(path, method="HEAD")
    assert status == 200 and body == b"" and int(headers["content-length"]) > 0
    (root / "old-job" / "job.json").unlink()
    (root / "old-job").rmdir()
    root.rmdir()
    status, _, body = http(path)
    assert status == 503
    document = json.loads(body)
    assert (
        document.get("history_available", document.get("available")) is False or "error" in document
    )


@pytest.mark.parametrize("path", ["/api/jobs/../outside", "/api/jobs/a/b", "/api/jobs/%2e%2e"])
def test_studio_history_http_scope_is_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    import hawedit.web as web

    root = tmp_path / "jobs"
    stored_job(root)
    monkeypatch.setattr(web, "JOB_MANAGER", JobManager(root))
    status, _, body = http(path)
    assert status in {400, 404} and b"C:/private" not in body


def test_studio_legacy_caption_edit_refuses_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hawedit.web as web

    root = tmp_path / "jobs"
    record = stored_job(root)
    transcript = record.parent / "raw.json"
    media = record.parent / "clip.mp4"
    transcript.write_bytes(b'{"canonical":"write-once text"}')
    media.write_bytes(Path("tests/fixtures/kurdish-speech-3cuts.mp4").read_bytes())
    originals = {path: path.read_bytes() for path in (record, transcript, media)}
    monkeypatch.setattr(web, "JOB_MANAGER", JobManager(root))
    body = json.dumps({"job_id": "old-job", "headline": "different burned-in title"}).encode()
    status, _, response = _handle_request(
        b"POST /api/edit_caption HTTP/1.1\r\nHost: localhost:8080\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
    )
    assert status == 409 and json.loads(response)["code"] == "revision_required"
    assert {path: path.read_bytes() for path in originals} == originals
    assert web.JOB_MANAGER.get_job("old-job")["headline"] == "title"  # type: ignore[index]


@pytest.mark.parametrize(
    "payload", [b"[]", b"{broken", b'{"job_id":"old-job"}', b'{"headline":true}']
)
def test_studio_legacy_edit_json_is_bounded_and_strict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: bytes
) -> None:
    import hawedit.web as web

    root = tmp_path / "jobs"
    original = stored_job(root).read_bytes()
    monkeypatch.setattr(web, "JOB_MANAGER", JobManager(root))
    status, _, _ = _handle_request(
        b"POST /api/edit_caption HTTP/1.1\r\nHost: localhost:8080\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Length: " + str(len(payload)).encode() + b"\r\n\r\n" + payload
    )
    assert status == 400 and (root / "old-job" / "job.json").read_bytes() == original


@pytest.mark.parametrize("path", ["/api/uploads", "/api/repurpose", "/api/edit_caption"])
def test_studio_json_depth_refusal_is_contextual(path: str) -> None:
    payload = b'{"nested":' + b"[" * 16384 + b"0" + b"]" * 16384 + b"}"
    with pytest.raises(RecursionError):
        json.loads(payload)
    status, _, body = _handle_request(
        f"POST {path} HTTP/1.1\r\nHost: localhost:8080\r\n".encode()
        + b"Content-Type: application/json\r\nContent-Length: "
        + str(len(payload)).encode()
        + b"\r\n\r\n"
        + payload
    )
    assert status == 400 and json.loads(body)["error"] == "Invalid JSON request"


@pytest.mark.parametrize(
    "headers",
    [
        "Content-Length: 99999999999999999999999999999\r\n",
        "Content-Length: 5\r\nContent-Length: 5\r\n",
        "Transfer-Encoding: chunked\r\nContent-Length: 5\r\n",
        "Content-Length: 65537\r\n",
        "Content-Length: -5\r\n",
    ],
)
def test_studio_legacy_edit_length_refusal_is_contextual(headers: str) -> None:
    status, _, body = _handle_request(
        b"POST /api/edit_caption HTTP/1.1\r\nHost: localhost:8080\r\n"
        b"Content-Type: application/json\r\n" + headers.encode() + b"\r\n"
    )
    assert status == 400 and json.loads(body)["error"]


def test_studio_history_native_http_refresh_and_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hawedit.web as web

    root = tmp_path / "jobs"
    record = stored_job(root)
    monkeypatch.setattr(web, "JOB_MANAGER", JobManager(root))
    observed_timeouts: list[float | None] = []
    configured = threading.Event()

    class ObservingHandler(web.HawEditWebHandler):
        def setup(self) -> None:
            super().setup()
            observed_timeouts.append(self.connection.gettimeout())
            configured.set()

    with web.ThreadingTCPServer(("127.0.0.1", 0), ObservingHandler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
        try:
            connection.request("GET", "/api/history")
            response = connection.getresponse()
            assert response.status == 200
            history = json.loads(response.read())
            assert configured.wait(2) and observed_timeouts[0] == 60
            assert history["jobs"][0]["status"] == "unverified-historical"
            record.write_bytes(b"{crashed-write")
            connection.request("GET", "/api/history")
            response = connection.getresponse()
            assert response.status == 200
            history = json.loads(response.read())
            assert history["jobs"] == [] and history["diagnostics"]
            connection.request("GET", "/api/history", headers={"Origin": "https://foreign.invalid"})
            response = connection.getresponse()
            assert response.status == 403 and b"old-job" not in response.read()
        finally:
            connection.close()
            server.shutdown()
            thread.join(timeout=5)
            assert not thread.is_alive()
