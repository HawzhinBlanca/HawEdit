"""Tests for HawEdit local web dashboard server — Claim S1."""

from __future__ import annotations

import io
import json
from unittest.mock import MagicMock

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
    req = b"GET /media/audit_02s_hook_115pt.jpg HTTP/1.1\r\nHost: localhost:8080\r\n\r\n"
    status_code, headers, body = _handle_request(req)
    assert status_code == 200
    assert "image/jpeg" in headers.get("content-type", "")
    assert len(body) > 0

    # Nonexistent media returns 404
    bad_req = b"GET /media/nonexistent_file.mp4 HTTP/1.1\r\nHost: localhost:8080\r\n\r\n"
    b_status, _, _ = _handle_request(bad_req)
    assert b_status == 404
