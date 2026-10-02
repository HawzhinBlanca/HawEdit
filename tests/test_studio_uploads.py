"""Real-media regressions for the studio source boundary (U1-U3)."""

from __future__ import annotations

import hashlib
import io
import json
import threading
from pathlib import Path

import pytest

from hawedit.studio_private import write_text_atomic
from hawedit.studio_uploads import UploadError, UploadStore
from studio_test_storage import create_private_test_root
from test_web import _handle_request

MEDIA = Path(__file__).parent / "fixtures" / "kurdish-speech-3cuts.mp4"


@pytest.fixture(name="tmp_path")
def _private_tmp_path(tmp_path: Path) -> Path:
    return create_private_test_root(tmp_path)


def test_upload_finalizes_real_media_bytes(tmp_path: Path) -> None:
    data = MEDIA.read_bytes()
    store = UploadStore(tmp_path)
    ticket = store.begin("outside-the-server.mp4", len(data))
    with pytest.raises(UploadError):
        store.source(ticket["upload_id"])
    source = store.receive(ticket["upload_id"], io.BytesIO(data), len(data))
    assert source["filename"] == "outside-the-server.mp4"
    assert source["sha256"] == hashlib.sha256(data).hexdigest()
    assert source["duration_ms"] > 0
    assert source["width"] > 0 and source["height"] > 0
    assert store.source(source["source_id"]).read_bytes() == data
    assert UploadStore(tmp_path).source(source["source_id"]).read_bytes() == data


def test_upload_duplicate_names_are_isolated(tmp_path: Path) -> None:
    data = MEDIA.read_bytes()
    store = UploadStore(tmp_path)
    first = store.begin("same.mp4", len(data))
    second = store.begin("same.mp4", len(data))
    a = store.receive(first["upload_id"], io.BytesIO(data), len(data))
    b = store.receive(second["upload_id"], io.BytesIO(data), len(data))
    assert a["source_id"] != b["source_id"]
    assert store.source(a["source_id"]) != store.source(b["source_id"])
    assert store.source(a["source_id"]).read_bytes() == data
    with pytest.raises(UploadError, match="already"):
        store.receive(first["upload_id"], io.BytesIO(data), len(data))


@pytest.mark.parametrize("data", [b"", b"not media", MEDIA.read_bytes()[:100]])
def test_upload_refuses_truncated_or_invalid_media(tmp_path: Path, data: bytes) -> None:
    store = UploadStore(tmp_path)
    ticket = store.begin("source.mp4", MEDIA.stat().st_size)
    with pytest.raises(UploadError):
        store.receive(ticket["upload_id"], io.BytesIO(data), MEDIA.stat().st_size)
    with pytest.raises(UploadError):
        store.source(ticket["upload_id"])
    assert not list((tmp_path / "sources").glob("*/source.*"))


def test_upload_rejects_content_length_and_invalid_bytes(tmp_path: Path) -> None:
    store = UploadStore(tmp_path)
    ticket = store.begin("source.mp4", 10)
    with pytest.raises(UploadError, match="length"):
        store.receive(ticket["upload_id"], io.BytesIO(b"not video"), 9)
    with pytest.raises(UploadError, match="media"):
        store.receive(ticket["upload_id"], io.BytesIO(b"not video!"), 10)


@pytest.mark.parametrize(
    "filename,size",
    [
        ("../source.mp4", 10),
        ("C:\\source.mp4", 10),
        ("file.txt", 10),
        ("source.mp4", 0),
        ("source.mp4", True),
        ("source.mp4", 101),
    ],
)
def test_upload_rejects_names_and_size(tmp_path: Path, filename: str, size: int) -> None:
    store = UploadStore(tmp_path, max_bytes=100)
    with pytest.raises(UploadError):
        store.begin(filename, size)


def test_upload_capacity_is_reserved_and_interruption_is_not_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    monkeypatch.setattr(shutil, "disk_usage", lambda _: shutil._ntuple_diskusage(200, 50, 150))
    store = UploadStore(tmp_path, reserve_bytes=0)
    ticket = store.begin("source.mp4", 100)
    with pytest.raises(UploadError, match="space"):
        store.begin("other.mp4", 100)
    assert ticket["upload_id"]
    with pytest.raises(UploadError):
        UploadStore(tmp_path).source(ticket["upload_id"])


def test_upload_source_refuses_changed_bytes(tmp_path: Path) -> None:
    store = UploadStore(tmp_path)
    data = MEDIA.read_bytes()
    ticket = store.begin("source.mp4", len(data))
    source = store.receive(ticket["upload_id"], io.BytesIO(data), len(data))
    path = store.source(source["source_id"])
    path.write_bytes(b"changed")
    with pytest.raises(UploadError, match="changed"):
        store.source(source["source_id"])


def test_upload_http_contract_and_no_cross_origin_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hawedit.web as web

    monkeypatch.setattr(web, "UPLOAD_STORE", UploadStore(tmp_path))
    data = MEDIA.read_bytes()
    body = json.dumps({"filename": "new.mp4", "size": len(data)}).encode()
    request = (
        b"POST /api/uploads HTTP/1.1\r\nHost: localhost:8080\r\n"
        b"Content-Type: application/json\r\nContent-Length: "
        + str(len(body)).encode()
        + b"\r\n\r\n"
        + body
    )
    status, _, result = _handle_request(request)
    assert status == 201
    upload_id = json.loads(result)["upload_id"]
    status, _, result = _handle_request(
        f"PUT /api/uploads/{upload_id} HTTP/1.1\r\nHost: localhost:8080\r\n"
        f"Content-Length: {len(data)}\r\n\r\n".encode()
        + data
    )
    assert status == 201
    source_id = json.loads(result)["source_id"]
    assert web.UPLOAD_STORE is not None
    assert web.UPLOAD_STORE.source(source_id).read_bytes() == data
    status, _, _ = _handle_request(
        request.replace(
            b"Content-Type:",
            b"Origin: https://attacker.example\r\nContent-Type:",
        )
    )
    assert status == 403


def test_upload_http_rejects_unbounded_or_malformed_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hawedit.web as web

    monkeypatch.setattr(web, "UPLOAD_STORE", UploadStore(tmp_path))
    for headers, body in [
        (b"Content-Length: -1", b""),
        (b"Content-Length: 999999", b""),
        (b"Content-Length: 2", b"[]"),
        (b"Transfer-Encoding: chunked", b""),
    ]:
        status, _, _ = _handle_request(
            b"POST /api/uploads HTTP/1.1\r\nHost: localhost:8080\r\n"
            b"Content-Type: application/json\r\n" + headers + b"\r\n\r\n" + body
        )
        assert status == 400


def test_upload_http_refuses_ambiguous_lengths_and_duplicate_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hawedit.web as web

    monkeypatch.setattr(web, "UPLOAD_STORE", UploadStore(tmp_path))
    body = b'{"filename":"a.mp4","filename":"b.mp4","size":10}'
    status, _, _ = _handle_request(
        b"POST /api/uploads HTTP/1.1\r\nHost: localhost:8080\r\n"
        b"Content-Type: application/json\r\nContent-Length: "
        + str(len(body)).encode()
        + b"\r\n\r\n"
        + body
    )
    assert status == 400
    status, _, _ = _handle_request(
        b"PUT /api/uploads/"
        + b"a" * 32
        + b" HTTP/1.1\r\nHost: localhost:8080\r\nContent-Length: 1\r\nContent-Length: 2\r\n\r\nxx"
    )
    assert status == 400


def test_upload_corrupt_metadata_is_a_visible_refusal(tmp_path: Path) -> None:
    store = UploadStore(tmp_path)
    ticket = store.begin("source.mp4", 10)
    path = tmp_path / "tickets" / f"{ticket['upload_id']}.json"
    record = json.loads(path.read_text())
    record["expires_at"] = "not a clock"
    path.write_text(json.dumps(record))
    with pytest.raises(UploadError, match="record"):
        store.receive(ticket["upload_id"], io.BytesIO(b"not video!"), 10)


@pytest.mark.parametrize(
    "field,value",
    [
        ("suffix", []),
        ("state", {}),
        ("filename", None),
        ("filename", "../source.mp4"),
        ("filename", "source.txt"),
        ("expires_at", 10**400),
        ("expires_at", 0),
        ("expires_at", float("nan")),
    ],
)
def test_upload_malformed_record_fields_are_contextual_refusals(
    tmp_path: Path, field: str, value: object
) -> None:
    store = UploadStore(tmp_path)
    ticket = store.begin("source.mp4", 10)
    path = tmp_path / "tickets" / f"{ticket['upload_id']}.json"
    record = json.loads(path.read_text())
    record[field] = value
    path.write_text(json.dumps(record))
    restarted = UploadStore(tmp_path)
    with pytest.raises(UploadError, match="record"):
        restarted.receive(ticket["upload_id"], io.BytesIO(b"not video!"), 10)
    with pytest.raises(UploadError, match="record"):
        restarted.begin("another.mp4", 10)
    assert not list((tmp_path / "sources").iterdir())


@pytest.mark.parametrize(
    "method,path", [("POST", "/api/uploads"), ("PUT", "/api/uploads/" + "a" * 32)]
)
def test_upload_http_extreme_content_length_is_a_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, method: str, path: str
) -> None:
    import hawedit.web as web

    monkeypatch.setattr(web, "UPLOAD_STORE", UploadStore(tmp_path))
    status, _, body = _handle_request(
        f"{method} {path} HTTP/1.1\r\nHost: localhost:8080\r\n".encode()
        + b"Content-Type: application/json\r\nContent-Length: "
        + b"1" * 5000
        + b"\r\n\r\n"
    )
    assert status == 400
    assert "length" in json.loads(body)["error"].lower()


def test_upload_status_recovers_lost_response(tmp_path: Path) -> None:
    store = UploadStore(tmp_path)
    data = MEDIA.read_bytes()
    ticket = store.begin("source.mp4", len(data))
    before = store.status(ticket["upload_id"])
    assert before["state"] == "reserved" and "source" not in before
    source = store.receive(ticket["upload_id"], io.BytesIO(data), len(data))
    restarted = UploadStore(tmp_path)
    status = restarted.status(ticket["upload_id"])
    assert status["state"] == "ready" and status["source"] == source
    assert restarted.source(source["source_id"]).read_bytes() == data
    assert len(list((tmp_path / "sources").iterdir())) == 1
    path = restarted.source(source["source_id"])
    path.write_bytes(bytes([data[0] ^ 1]) + data[1:])
    with pytest.raises(UploadError, match="changed"):
        restarted.status(ticket["upload_id"])


def test_upload_status_recovers_committed_media_after_ticket_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hawedit.studio_uploads as uploads

    data = MEDIA.read_bytes()
    store = UploadStore(tmp_path)
    ticket = store.begin("source.mp4", len(data))
    atomic_write = write_text_atomic

    def fail_ready_ticket(path: Path, text: str) -> None:
        if path.parent.name == "tickets" and json.loads(text)["state"] == "ready":
            raise OSError("ticket storage unavailable")
        atomic_write(path, text)

    with monkeypatch.context() as fault:
        fault.setattr(uploads, "write_text_atomic", fail_ready_ticket)
        with pytest.raises(OSError, match="unavailable"):
            store.receive(ticket["upload_id"], io.BytesIO(data), len(data))
        # Repair is not acknowledged until its ticket can actually persist.
        with pytest.raises(OSError, match="unavailable"):
            UploadStore(tmp_path).status(ticket["upload_id"])
        import hawedit.web as web

        fault.setattr(web, "UPLOAD_STORE", UploadStore(tmp_path))
        code, _, body = _handle_request(
            f"GET /api/uploads/{ticket['upload_id']} HTTP/1.1\r\n"
            "Host: localhost:8080\r\n\r\n".encode()
        )
        assert code == 503 and "storage" in json.loads(body)["error"]
        assert "source" not in json.loads(body)
    restarted = UploadStore(tmp_path)
    status = restarted.status(ticket["upload_id"])
    assert status["state"] == "ready"
    assert status["source"]["source_id"] == ticket["upload_id"]
    assert restarted.source(ticket["upload_id"]).read_bytes() == data
    saved = json.loads((tmp_path / "tickets" / f"{ticket['upload_id']}.json").read_text())
    assert saved["state"] == "ready"
    assert len(list((tmp_path / "sources").iterdir())) == 1


@pytest.mark.parametrize("damage", ["filename", "sha256", "media", "oversized", "missing"])
def test_upload_status_refuses_mismatched_committed_evidence(tmp_path: Path, damage: str) -> None:
    store = UploadStore(tmp_path)
    data = MEDIA.read_bytes()
    ticket = store.begin("source.mp4", len(data))
    store.receive(ticket["upload_id"], io.BytesIO(data), len(data))
    ticket_path = tmp_path / "tickets" / f"{ticket['upload_id']}.json"
    record = json.loads(ticket_path.read_text())
    record["state"] = "receiving"
    ticket_path.write_text(json.dumps(record))
    manifest = tmp_path / "sources" / ticket["upload_id"] / "source.json"
    committed = json.loads(manifest.read_text())
    if damage == "media":
        (manifest.parent / "source.mp4").write_bytes(bytes([data[0] ^ 1]) + data[1:])
    elif damage == "oversized":
        manifest.write_text(" " * 8193)
    elif damage == "missing":
        manifest.unlink()
    else:
        committed[damage] = "different.mp4" if damage == "filename" else "0" * 64
        manifest.write_text(json.dumps(committed))
    with pytest.raises(UploadError):
        UploadStore(tmp_path).status(ticket["upload_id"])
    assert json.loads(ticket_path.read_text())["state"] == "receiving"
    with pytest.raises(UploadError):
        UploadStore(tmp_path).source(ticket["upload_id"])


def test_upload_status_distinguishes_live_and_interrupted_transfer(tmp_path: Path) -> None:
    store = UploadStore(tmp_path)
    data = MEDIA.read_bytes()
    ticket = store.begin("source.mp4", len(data))
    started = threading.Event()
    release = threading.Event()
    failures: list[BaseException] = []

    class DelayedReader:
        def __init__(self) -> None:
            self.stream = io.BytesIO(data)

        def read(self, size: int = -1, /) -> bytes:
            started.set()
            if not release.wait(10):
                raise TimeoutError("test transfer did not release")
            return self.stream.read(size)

    def receive() -> None:
        try:
            store.receive(ticket["upload_id"], DelayedReader(), len(data))
        except BaseException as exc:
            failures.append(exc)

    worker = threading.Thread(target=receive)
    worker.start()
    try:
        assert started.wait(10)
        live = store.status(ticket["upload_id"])
        assert live["state"] == "receiving" and "source" not in live
    finally:
        release.set()
        worker.join(10)
    assert not worker.is_alive() and not failures
    assert store.status(ticket["upload_id"])["state"] == "ready"
    abandoned = store.begin("abandoned.mp4", len(data))
    path = tmp_path / "tickets" / f"{abandoned['upload_id']}.json"
    record = json.loads(path.read_text())
    record["state"] = "receiving"
    path.write_text(json.dumps(record))
    status = UploadStore(tmp_path).status(abandoned["upload_id"])
    assert status["state"] == "interrupted" and "source" not in status
    assert "upload" in status["error"].lower()
    with pytest.raises(UploadError):
        UploadStore(tmp_path).source(abandoned["upload_id"])


def test_upload_http_status_is_guarded_and_contextual(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hawedit.web as web

    store = UploadStore(tmp_path)
    monkeypatch.setattr(web, "UPLOAD_STORE", store)
    ticket = store.begin("source.mp4", MEDIA.stat().st_size)
    request = (
        f"GET /api/uploads/{ticket['upload_id']} HTTP/1.1\r\nHost: localhost:8080\r\n\r\n".encode()
    )
    status, headers, body = _handle_request(request)
    assert status == 200 and json.loads(body)["state"] == "reserved"
    assert headers["cache-control"] == "no-store"
    for bad_header in (
        b"Host: attacker.example",
        b"Host: localhost:8080\r\nOrigin: https://attacker.example",
        b"Host: localhost:8080\r\nSec-Fetch-Site: cross-site",
    ):
        assert _handle_request(request.replace(b"Host: localhost:8080", bad_header))[0] == 403
    missing = request.replace(ticket["upload_id"].encode(), b"a" * 32)
    assert _handle_request(missing)[0] == 400
    data = MEDIA.read_bytes()
    store.receive(ticket["upload_id"], io.BytesIO(data), len(data))
    code, _, body = _handle_request(request)
    assert code == 200 and json.loads(body)["source"]["source_id"] == ticket["upload_id"]
    store.source(ticket["upload_id"]).unlink()
    code, _, body = _handle_request(request)
    assert code == 400 and "missing" in json.loads(body)["error"]


def test_upload_status_exposes_expired_and_failed_reservations(tmp_path: Path) -> None:
    store = UploadStore(tmp_path)
    ticket = store.begin("source.mp4", 10)
    path = tmp_path / "tickets" / f"{ticket['upload_id']}.json"
    record = json.loads(path.read_text())
    record["expires_at"] = 1
    path.write_text(json.dumps(record))
    status = store.status(ticket["upload_id"])
    assert status["state"] == "expired" and "source" not in status
    failed = store.begin("failed.mp4", 10)
    with pytest.raises(UploadError):
        store.receive(failed["upload_id"], io.BytesIO(b""), 10)
    status = UploadStore(tmp_path).status(failed["upload_id"])
    assert status["state"] == "failed" and "source" not in status
