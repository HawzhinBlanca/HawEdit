"""Tests for HawEdit local web dashboard server — Claim S1."""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from hawedit.web import DASHBOARD_HTML, HawEditWebHandler


class MockSocket:
    def __init__(self, data: bytes) -> None:
        self.rfile = io.BytesIO(data)
        self.wfile = io.BytesIO()

    def makefile(self, mode: str, *args: object, **kwargs: object) -> io.BytesIO:
        if "r" in mode:
            return self.rfile
        return self.wfile

    def sendall(self, b: bytes) -> None:
        self.wfile.write(b)


def _handle_request(raw_request: bytes) -> tuple[int, dict[str, str], bytes]:
    sock = MockSocket(raw_request)
    # Instantiate handler with mock client address and mock server
    _ = HawEditWebHandler(
        sock,  # type: ignore[arg-type]
        ("127.0.0.1", 8080),
        MagicMock(),
    )
    sock.wfile.seek(0)
    response_bytes = sock.wfile.getvalue()
    lines = response_bytes.split(b"\r\n")
    status_line = lines[0].decode("utf-8")
    status_code = int(status_line.split()[1])

    headers: dict[str, str] = {}
    i = 1
    while i < len(lines) and lines[i]:
        parts = lines[i].decode("utf-8").split(": ", 1)
        if len(parts) == 2:
            headers[parts[0].lower()] = parts[1]
        i += 1

    body = b"\r\n".join(lines[i + 1 :])
    return status_code, headers, body


def test_dashboard_html_contains_branding_and_stepper() -> None:
    assert "<title>HawEdit — Pro Kurdish Social Reel Studio</title>" in DASHBOARD_HTML
    assert "Vazirmatn" in DASHBOARD_HTML
    assert "Sanity Gate Audit" in DASHBOARD_HTML
    assert "Story Condensation" in DASHBOARD_HTML


def test_web_handler_serves_dashboard() -> None:
    req = b"GET / HTTP/1.1\r\nHost: localhost:8080\r\n\r\n"
    status_code, headers, body = _handle_request(req)
    assert status_code == 200
    assert "text/html" in headers.get("content-type", "")
    assert b"HawEdit" in body


def test_web_handler_serves_status_json() -> None:
    req = b"GET /api/status HTTP/1.1\r\nHost: localhost:8080\r\n\r\n"
    status_code, headers, body = _handle_request(req)
    assert status_code == 200
    assert "application/json" in headers.get("content-type", "")
    data = json.loads(body.decode("utf-8"))
    assert data["status"] in ("ready", "busy")
    assert data["latest_reel"]["duration_s"] == 48.14


def test_web_handler_post_repurpose_creates_job() -> None:
    body_bytes = b'{"source": "kurdish-speech-3cuts.mp4"}'
    req = (
        b"POST /api/repurpose HTTP/1.1\r\n"
        b"Host: localhost:8080\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Length: " + str(len(body_bytes)).encode("ascii") + b"\r\n\r\n" + body_bytes
    )
    status_code, headers, body = _handle_request(req)
    assert status_code == 201
    assert "application/json" in headers.get("content-type", "")
    data = json.loads(body.decode("utf-8"))
    assert "job_id" in data
    assert "kurdish-speech-3cuts.mp4" in data["source"]
    assert data["status"] in ("queued", "running", "completed")


def test_web_handler_post_repurpose_rejects_missing_and_empty_source() -> None:
    """CD-01: Reject request with HTTP 400 when source video is missing, empty, or nonexistent."""
    # 1. Missing / empty source field
    payload_empty = b'{"source": "  "}'
    bad_req_empty = (
        b"POST /api/repurpose HTTP/1.1\r\n"
        b"Host: localhost:8080\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Length: " + str(len(payload_empty)).encode("ascii") + b"\r\n\r\n" + payload_empty
    )
    status_code, _, body = _handle_request(bad_req_empty)
    assert status_code == 400
    assert "Validation failed" in json.loads(body.decode())["error"]

    # 2. Non-existent file path
    payload_nonexistent = b'{"source": "fake_nonexistent.mp4"}'
    bad_req_nonexistent = (
        b"POST /api/repurpose HTTP/1.1\r\n"
        b"Host: localhost:8080\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Length: "
        + str(len(payload_nonexistent)).encode("ascii")
        + b"\r\n\r\n"
        + payload_nonexistent
    )
    status_code, _, body = _handle_request(bad_req_nonexistent)
    assert status_code == 400
    assert "does not exist on disk" in json.loads(body.decode())["error"]


def test_web_handler_candidate_clips_have_distinct_video_urls() -> None:
    """CD-14: Multiple ranked candidates must link to distinct, independent media paths."""
    body_bytes = b'{"source": "kurdish-speech-3cuts.mp4"}'
    req = (
        b"POST /api/repurpose HTTP/1.1\r\n"
        b"Host: localhost:8080\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Length: " + str(len(body_bytes)).encode("ascii") + b"\r\n\r\n" + body_bytes
    )
    status_code, _, body = _handle_request(req)
    assert status_code == 201
    data = json.loads(body.decode("utf-8"))
    clips = data.get("clips", [])
    assert len(clips) >= 2
    video_urls = [c["video_url"] for c in clips]
    # Invariant: No duplicate identical media paths across candidates
    assert len(video_urls) == len(set(video_urls))
    assert clips[0]["video_url"] != clips[1]["video_url"]


def test_web_handler_get_jobs_and_details() -> None:
    # First query all jobs
    req = b"GET /api/jobs HTTP/1.1\r\nHost: localhost:8080\r\n\r\n"
    status_code, headers, body = _handle_request(req)
    assert status_code == 200
    jobs = json.loads(body.decode("utf-8"))
    assert isinstance(jobs, list)

    # If a job exists, query its specific endpoint
    if jobs:
        target_id = jobs[0]["job_id"]
        detail_req = f"GET /api/jobs/{target_id} HTTP/1.1\r\nHost: localhost:8080\r\n\r\n".encode()
        d_status, _, d_body = _handle_request(detail_req)
        assert d_status == 200
        single_job = json.loads(d_body.decode())
        assert single_job["job_id"] == target_id


def test_web_handler_post_edit_caption() -> None:
    # First create a job with valid source
    create_body = b'{"source": "kurdish-speech-3cuts.mp4"}'
    create_req = (
        b"POST /api/repurpose HTTP/1.1\r\n"
        b"Host: localhost:8080\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Length: " + str(len(create_body)).encode("ascii") + b"\r\n\r\n" + create_body
    )
    c_status, _, c_body = _handle_request(create_req)
    assert c_status == 201
    job_id = json.loads(c_body.decode())["job_id"]

    # Now edit caption
    edit_body = json.dumps({"job_id": job_id, "headline": "سەردێڕی نوێ"}).encode()
    edit_req = (
        b"POST /api/edit_caption HTTP/1.1\r\n"
        b"Host: localhost:8080\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Length: " + str(len(edit_body)).encode("ascii") + b"\r\n\r\n" + edit_body
    )
    e_status, _, e_body = _handle_request(edit_req)
    assert e_status == 200
    res = json.loads(e_body.decode())
    assert res["headline"] == "سەردێڕی نوێ"

    # Nonexistent job returns 404
    bad_body = json.dumps({"job_id": "nonexistent-job", "headline": "test"}).encode()
    bad_req = (
        b"POST /api/edit_caption HTTP/1.1\r\n"
        b"Host: localhost:8080\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Length: " + str(len(bad_body)).encode("ascii") + b"\r\n\r\n" + bad_body
    )
    b_status, _, _ = _handle_request(bad_req)
    assert b_status == 404


def test_web_handler_serves_media() -> None:
    # Existing media serves 200
    req = b"GET /media/kurdish-speech-3cuts.mp4 HTTP/1.1\r\nHost: localhost:8080\r\n\r\n"
    status_code, headers, body = _handle_request(req)
    assert status_code == 200
    assert "video/mp4" in headers.get("content-type", "")
    assert len(body) > 0

    # Nonexistent media returns 404
    bad_req = b"GET /media/nonexistent_file.mp4 HTTP/1.1\r\nHost: localhost:8080\r\n\r\n"
    b_status, _, _ = _handle_request(bad_req)
    assert b_status == 404


def test_studio_job_runs_pipeline_and_lists_only_delivered_bundles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Task 5 & Reality Check Item 2: Studio job runs pipeline.

    Lists only delivered bundles with measured.json.
    """
    import hashlib

    from hawedit.pipeline import Delivery, PipelineRun
    from hawedit.web import JOB_MANAGER, JobManager

    # 1. Assert empty clip list before any job runs
    fresh_jm = JobManager(jobs_dir=tmp_path / "fresh_jobs")
    assert fresh_jm.get_all_jobs() == []

    # 2. Setup job on valid fixture video
    fixture_video = Path("tests/fixtures/kurdish-speech-3cuts.mp4")
    assert fixture_video.is_file()

    job_dict = JOB_MANAGER.submit_job(str(fixture_video))
    job_id = str(job_dict["job_id"])

    # Pre-run: job is queued/running
    job_pre = JOB_MANAGER.get_job(job_id)
    assert job_pre is not None
    assert job_pre["status"] in ("queued", "running")

    # Mock run_pipeline to deliver a real bundle with measured.json in job's work dir
    job_work_dir = JOB_MANAGER._jobs_dir / job_id
    job_work_dir.mkdir(parents=True, exist_ok=True)
    clip_id = f"{fixture_video.stem}-clip-01"
    delivered_mp4 = job_work_dir / f"{clip_id}.mp4"
    delivered_mp4.write_bytes(fixture_video.read_bytes())
    mp4_sha256 = hashlib.sha256(delivered_mp4.read_bytes()).hexdigest()

    measured_json_path = job_work_dir / f"{clip_id}.measured.json"
    meas_content = {
        "duration_ms": 4160,
        "sha256": mp4_sha256,
        "loudness_lufs": -14.0,
        "silence_share": 0.04,
        "speaking_face_share": 0.99,
    }
    measured_json_path.write_text(json.dumps(meas_content), encoding="utf-8")

    mock_delivery = Delivery(
        srt_path=str(job_work_dir / f"{clip_id}.srt"),
        edl_path=str(job_work_dir / f"{clip_id}.edl"),
        editing_json_path=str(job_work_dir / f"{clip_id}.json"),
        measured_path=str(measured_json_path),
        edit_plan_path=str(job_work_dir / f"{clip_id}.edit_plan.json"),
    )
    mock_run = PipelineRun(
        media_id="test-media",
        source=str(fixture_video),
        work_dir=str(job_work_dir),
        delivery=mock_delivery,
    )

    def mock_run_pipeline(*args: object, **kwargs: object) -> PipelineRun:
        return mock_run

    monkeypatch.setattr("hawedit.pipeline.run_pipeline", mock_run_pipeline)

    # Run the job synchronously
    JOB_MANAGER.run_job_sync(job_id)

    # Post-run assertions:
    job_post = JOB_MANAGER.get_job(job_id)
    assert job_post is not None
    assert job_post["status"] == "completed"
    clips = job_post["clips"]
    assert len(clips) >= 1
    for clip in clips:
        assert Path(mock_delivery.measured_path).is_file()
        assert clip["sha256"] == mp4_sha256
        assert clip["duration_s"] == 4.16
        # Verify served media matches measured sha256
        req = f"GET {clip['video_url']} HTTP/1.1\r\nHost: localhost:8080\r\n\r\n".encode()
        s_code, _, body = _handle_request(req)
        assert s_code == 200
        assert hashlib.sha256(body).hexdigest() == clip["sha256"]


def test_web_handler_media_rejects_path_traversal_and_forbidden_extensions() -> None:
    # 1. Path traversal with ..
    req1 = b"GET /media/../../pyproject.toml HTTP/1.1\r\nHost: localhost:8080\r\n\r\n"
    code1, _, _ = _handle_request(req1)
    assert code1 == 404

    # 2. Hidden file
    req2 = b"GET /media/.env HTTP/1.1\r\nHost: localhost:8080\r\n\r\n"
    code2, _, _ = _handle_request(req2)
    assert code2 == 404

    # 3. Disallowed extension (e.g. .py, .sh)
    req3 = b"GET /media/web.py HTTP/1.1\r\nHost: localhost:8080\r\n\r\n"
    code3, _, _ = _handle_request(req3)
    assert code3 == 404


def test_web_handler_job_fails_when_pipeline_skips_or_delivery_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from hawedit.pipeline import PipelineRun, StageSkipped
    from hawedit.web import JobManager

    jm = JobManager(jobs_dir=tmp_path / "skip_jobs")
    fixture_video = Path("tests/fixtures/kurdish-speech-3cuts.mp4")
    job = jm.submit_job(str(fixture_video))
    job_id = job["job_id"]

    # Case A: Pipeline skipped a stage
    mock_run_skipped = PipelineRun(
        media_id="test-skip",
        source=str(fixture_video),
        work_dir=str(tmp_path / "work"),
        editorial=StageSkipped("stage4_editorial", "quota exceeded"),
    )
    monkeypatch.setattr("hawedit.pipeline.run_pipeline", lambda *args, **kwargs: mock_run_skipped)
    jm.run_job_sync(job_id)

    updated = jm.get_job(job_id)
    assert updated is not None
    assert updated["status"] == "failed"
    assert "editorial" in str(updated["error"])
    assert "quota exceeded" in str(updated["error"])
    assert updated["progress_percent"] < 100

    # Case B: Pipeline completed without a delivery bundle
    job2 = jm.submit_job(str(fixture_video))
    job2_id = job2["job_id"]
    mock_run_no_del = PipelineRun(
        media_id="test-no-delivery",
        source=str(fixture_video),
        work_dir=str(tmp_path / "work2"),
        delivery=None,
    )
    monkeypatch.setattr("hawedit.pipeline.run_pipeline", lambda *args, **kwargs: mock_run_no_del)
    jm.run_job_sync(job2_id)

    updated2 = jm.get_job(job2_id)
    assert updated2 is not None
    assert updated2["status"] == "failed"
    assert "delivery bundle" in str(updated2["error"])


def test_web_handler_submit_job_supports_idempotency_token(tmp_path: Path) -> None:
    from hawedit.web import JobManager

    jm = JobManager(jobs_dir=tmp_path / "idem_jobs")
    fixture_video = Path("tests/fixtures/kurdish-speech-3cuts.mp4")
    token = "token-12345"

    job1 = jm.submit_job(str(fixture_video), client_token=token)
    job2 = jm.submit_job(str(fixture_video), client_token=token)
    assert job1["job_id"] == job2["job_id"]
