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
    handler = HawEditWebHandler(
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
    assert data["status"] == "ready"
    assert data["latest_reel"]["duration_s"] == 48.14
