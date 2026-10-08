"""Native pre-count refusals stay distinct from real local transport failures."""

from __future__ import annotations

import json
import socket
import sqlite3
import sys
import threading
import time
import urllib.request
from collections.abc import Iterator, Mapping
from contextlib import closing
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import FrameType
from typing import Any

import pytest

from hawedit.gemini import API_ROOT
from hawedit.judge import KURDISH_EDITORIAL_JUDGE
from hawedit.studio_billing import BillingPolicy, GuardedGeminiTransport
from hawedit.studio_private import StudioStorageError
from hawedit.workflow_recovery import ExternalReconciliationError
from studio_test_storage import create_private_test_root

BASE = API_ROOT + "/models/" + KURDISH_EDITORIAL_JUDGE
PAYLOAD = json.dumps(
    {
        "contents": [{"parts": [{"text": "local count boundary"}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
).encode()


@pytest.fixture
def journal(tmp_path: Path) -> Path:
    return create_private_test_root(tmp_path) / "billing.sqlite"


def _policy(expires_at: int) -> BillingPolicy:
    return BillingPolicy(
        "a" * 64, BASE, expires_at, 1000, 128, 128, 128, 1_250_000, 10_000_000, 10_000_000
    )


def test_count_boundary_preserves_actual_policy_expiry(journal: Path) -> None:
    calls: list[str] = []
    controlled: list[bool] = []
    policy = _policy(int(time.time()) + 5)

    def upstream(url: str, body: bytes | None, headers: Mapping[str, str]) -> tuple[int, str]:
        calls.append(url)
        raise AssertionError("Expired policy must refuse before upstream")

    guard = GuardedGeminiTransport(journal, "studio-" + "b" * 64, policy, upstream)

    def trace(frame: FrameType, event: str, arg: Any) -> Any:
        if frame.f_code is not GuardedGeminiTransport._send.__code__:
            return None
        if event == "call" and frame.f_locals["url"].endswith(":countTokens"):
            sys.settrace(None)
            controlled.append(True)
            time.sleep(max(0, policy.expires_at - time.time()) + 0.05)
        return trace

    sys.settrace(trace)
    try:
        with pytest.raises(ExternalReconciliationError, match="expired before egress"):
            guard(BASE + ":generateContent", PAYLOAD, {})
    finally:
        sys.settrace(None)
    assert controlled == [True]
    assert calls == []
    with closing(sqlite3.connect(journal)) as connection:
        assert connection.execute("SELECT count(*) FROM calls").fetchone() == (0,)


def test_count_boundary_preserves_actual_storage_refusal(journal: Path) -> None:
    calls: list[str] = []
    controlled: list[bool] = []

    def upstream(url: str, body: bytes | None, headers: Mapping[str, str]) -> tuple[int, str]:
        calls.append(url)
        raise AssertionError("Invalid native journal must refuse before upstream")

    guard = GuardedGeminiTransport(
        journal, "studio-" + "b" * 64, _policy(int(time.time()) + 3600), upstream
    )

    def trace(frame: FrameType, event: str, arg: Any) -> Any:
        if frame.f_code is not GuardedGeminiTransport._send.__code__:
            return None
        if event == "call" and frame.f_locals["url"].endswith(":countTokens"):
            sys.settrace(None)
            controlled.append(True)
            with closing(sqlite3.connect(journal)) as connection, connection:
                connection.execute("DROP TABLE calls")
        return trace

    sys.settrace(trace)
    try:
        with pytest.raises(ExternalReconciliationError, match="Billing journal refused") as error:
            guard(BASE + ":generateContent", PAYLOAD, {})
    finally:
        sys.settrace(None)
    assert controlled == [True]
    assert calls == []
    assert isinstance(error.value.__cause__, StudioStorageError)
    assert "schema" in str(error.value.__cause__)
    with closing(sqlite3.connect(journal)) as connection:
        assert connection.execute(
            "SELECT count(*) FROM sqlite_schema WHERE name='calls'"
        ).fetchone() == (0,)


@pytest.fixture
def disconnected_count() -> Iterator[tuple[HTTPServer, list[str]]]:
    calls: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers["Content-Length"]))
            calls.append(self.path)
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield server, calls
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        assert not thread.is_alive()


def test_count_boundary_retains_actual_provider_failure(
    journal: Path, disconnected_count: tuple[HTTPServer, list[str]]
) -> None:
    server, calls = disconnected_count

    def upstream(url: str, body: bytes | None, headers: Mapping[str, str]) -> tuple[int, str]:
        method = url.rsplit(":", 1)[1]
        local = f"http://127.0.0.1:{server.server_port}/{method}"
        request = urllib.request.Request(local, data=body, headers=dict(headers))
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status, response.read().decode()

    guard = GuardedGeminiTransport(
        journal, "studio-" + "b" * 64, _policy(int(time.time()) + 3600), upstream
    )
    with pytest.raises(ExternalReconciliationError, match="Provider count unavailable") as error:
        guard(BASE + ":generateContent", PAYLOAD, {})
    assert isinstance(error.value.__cause__, OSError)
    assert calls == ["/countTokens"]
    with closing(sqlite3.connect(journal)) as connection:
        assert connection.execute("SELECT count(*) FROM calls").fetchone() == (0,)
