"""Authenticated HTTP requests must never forward credentials through redirects."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from hawedit.http_transport import open_without_redirects


def test_authenticated_http_never_contacts_a_redirect_target() -> None:
    target_headers: list[dict[str, str]] = []

    class Target(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            target_headers.append({name.lower(): value for name, value in self.headers.items()})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"unexpected")

        def log_message(self, _format: str, *_args: object) -> None:
            return

    target = ThreadingHTTPServer(("127.0.0.1", 0), Target)
    target_port = target.server_address[1]

    class Redirect(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{target_port}/stolen")
            self.end_headers()

        def log_message(self, _format: str, *_args: object) -> None:
            return

    source = ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
    source_port = source.server_address[1]
    threads = [
        threading.Thread(target=target.serve_forever, daemon=True),
        threading.Thread(target=source.serve_forever, daemon=True),
    ]
    for thread in threads:
        thread.start()

    request = Request(
        f"http://127.0.0.1:{source_port}/start",
        headers={
            "x-goog-api-key": "FAKE-SECRET-MUST-STAY-AT-SOURCE",
            "Authorization": "Bearer FAKE-TOKEN-MUST-STAY-AT-SOURCE",
        },
    )
    try:
        with pytest.raises(HTTPError) as caught:
            open_without_redirects(request, timeout=5)
    finally:
        source.shutdown()
        target.shutdown()
        source.server_close()
        target.server_close()
        for thread in threads:
            thread.join(timeout=5)

    assert caught.value.code == 302
    assert target_headers == [], (
        "the redirect target was contacted and could read an authentication header"
    )
