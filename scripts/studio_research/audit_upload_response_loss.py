"""Test-only HTTP acknowledgement loss after the real upload store commits bytes."""

from __future__ import annotations

import http.server
import json
import socket
import tempfile
from pathlib import Path
from typing import Any

import hawedit.web as web
from hawedit.studio_uploads import UploadStore
from hawedit.wsl_setup import package_digest

EXPECTED_SOURCE = "66a377dabc4c08b265994e85ab18d66d8a89f90553e7a90cdec0f19ff8ebbd39"
PORT = 8083


class LostAcknowledgementHandler(web.HawEditWebHandler):
    """Change transport only; actual reservation, receive and recovery stay untouched."""

    lost_once = False

    def _json_reply(self, status: int, payload: Any) -> None:
        if self.command == "PUT" and status == 201 and not type(self).lost_once:
            type(self).lost_once = True
            print(
                "TEST_ACK_DROPPED_AFTER_REAL_COMMIT="
                + json.dumps(payload, ensure_ascii=True, sort_keys=True),
                flush=True,
            )
            self.close_connection = True
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return
        super()._json_reply(status, payload)


def main() -> None:
    digest = package_digest()
    if digest != EXPECTED_SOURCE:
        raise RuntimeError("Test source differs from the frozen gate package")
    root = Path(tempfile.mkdtemp(prefix="hawedit-ui-loss-"))
    web.JOB_MANAGER = web.JobManager(root / "jobs")
    web.UPLOAD_STORE = UploadStore(root / "uploads", reserve_bytes=0)
    print("TEST_STORAGE=" + str(root), flush=True)
    print("SOURCE_PACKAGE_SHA256=" + digest, flush=True)
    print("TEST_LOOPBACK_PORT=" + str(PORT), flush=True)
    with http.server.ThreadingHTTPServer(("127.0.0.1", PORT), LostAcknowledgementHandler) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
