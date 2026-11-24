"""Actual private upload/outbox boundaries; no model, paid call or release claim."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import pickle
import socket
import stat
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

import pytest

from hawedit.captions import find_ffmpeg
from hawedit.studio_private import write_text_atomic
from hawedit.studio_submissions import StudioStorageError, SubmissionStore
from hawedit.studio_uploads import UploadError, UploadStore
from hawedit.windows_security import assert_private_windows_path
from studio_test_storage import create_private_test_root, make_private_directory, seed_private_file
from test_studio_private import directory_alias
from test_web import _handle_request

MEDIA = Path(__file__).parent / "fixtures/kurdish-speech-3cuts.mp4"


def test_studio_upload_shared_root_is_preserved_and_refused(tmp_path: Path) -> None:
    root = tmp_path / "ordinary"
    root.mkdir(mode=0o755)
    marker = root / "original-owner-data"
    marker.write_bytes(b"original owner bytes")
    before = root.stat().st_mode
    with pytest.raises(StudioStorageError, match="private"):
        UploadStore(root)
    assert root.stat().st_mode == before
    assert marker.read_bytes() == b"original owner bytes"
    assert sorted(path.name for path in root.iterdir()) == [marker.name]


def test_studio_upload_linked_ticket_is_preserved(tmp_path: Path) -> None:
    root = create_private_test_root(tmp_path)
    store = UploadStore(root)
    ticket = store.begin("episode.mp4", MEDIA.stat().st_size)
    path = root / "tickets" / f"{ticket['upload_id']}.json"
    before = path.read_bytes()
    outside = tmp_path / "retained-original-ticket"
    os.link(path, outside)
    with pytest.raises((UploadError, StudioStorageError), match="private|linked"):
        store.begin("another.mp4", MEDIA.stat().st_size)
    assert outside.read_bytes() == path.read_bytes() == before
    assert len(list((root / "tickets").iterdir())) == 1


def test_studio_upload_container_replacement_refuses(tmp_path: Path) -> None:
    root = create_private_test_root(tmp_path)
    store = UploadStore(root)
    ticket = store.begin("episode.mp4", MEDIA.stat().st_size)
    retained = tmp_path / "retained-sources"
    assert (root / "sources").resolve().is_relative_to(tmp_path.resolve())
    assert retained.resolve().is_relative_to(tmp_path.resolve())
    (root / "sources").rename(retained)
    make_private_directory(root / "sources")
    before = (root / "tickets" / f"{ticket['upload_id']}.json").read_bytes()
    with pytest.raises(StudioStorageError, match="identity|private"):
        store.status(ticket["upload_id"])
    assert (root / "tickets" / f"{ticket['upload_id']}.json").read_bytes() == before
    assert not list(retained.iterdir())


def test_studio_upload_failure_cleanup_cannot_follow_replaced_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hawedit.studio_uploads as uploads

    root = create_private_test_root(tmp_path)
    store = UploadStore(root)
    ticket = store.begin("episode.mp4", MEDIA.stat().st_size)
    staging = root / "incoming" / ticket["upload_id"]
    retained = root / "incoming" / "retained-original-transfer"
    outside = tmp_path / "owner-originals"
    outside.mkdir()
    media = outside / "source.mp4"
    manifest = outside / "source.json"
    media.write_bytes(b"unrelated owner media must never be removed")
    manifest.write_bytes(b"unrelated owner manifest must never be removed")
    before = (media.read_bytes(), manifest.read_bytes())
    probe = uploads._probe

    def probe_then_replace(path: Path) -> dict[str, int]:
        measured = probe(path)
        assert measured["duration_ms"] > 0
        assert staging.resolve().is_relative_to(root.resolve())
        assert retained.resolve().is_relative_to(root.resolve())
        staging.rename(retained)
        directory_alias(staging, outside)
        raise UploadError("deliberate post-probe transfer failure")

    monkeypatch.setattr(uploads, "_probe", probe_then_replace)
    with (
        MEDIA.open("rb") as stream,
        pytest.raises((UploadError, StudioStorageError, OSError)),
    ):
        store.receive(ticket["upload_id"], stream, MEDIA.stat().st_size)
    assert (media.read_bytes(), manifest.read_bytes()) == before
    assert (
        hashlib.sha256((retained / "source.mp4").read_bytes()).digest()
        == hashlib.sha256(MEDIA.read_bytes()).digest()
    )
    assert not (root / "sources" / ticket["upload_id"]).exists()


def test_studio_submission_shared_root_is_preserved_and_refused(tmp_path: Path) -> None:
    root = tmp_path / "ordinary"
    root.mkdir(mode=0o755)
    marker = root / "original-owner-data"
    marker.write_bytes(b"original owner bytes")
    before = root.stat().st_mode
    with pytest.raises(StudioStorageError, match="private"):
        SubmissionStore(root / "submissions.sqlite")
    assert root.stat().st_mode == before
    assert marker.read_bytes() == b"original owner bytes"
    assert not (root / "submissions.sqlite").exists()


def test_studio_submission_missing_database_is_not_recreated(tmp_path: Path) -> None:
    root = create_private_test_root(tmp_path)
    store = SubmissionStore(root / "submissions.sqlite")
    assert store.path.resolve().is_relative_to(root.resolve())
    store.path.unlink()
    with pytest.raises(StudioStorageError):
        store.pending()
    assert not store.path.exists()


def test_studio_storage_error_preserves_legacy_pickle_and_catchers() -> None:
    # Captured from the real old module-qualified class before its relocation.
    legacy = base64.b64decode(
        "gASVXAAAAAAAAACMGmhhd2VkaXQuc3R1ZGlvX3N1Ym1pc3Npb25zlIwSU3R1ZGlvU3RvcmFn"
        "ZUVycm9ylJOUjCBsZWdhY3kgdGVzdC1vbmx5IHN0b3JhZ2UgcmVmdXNhbJSFlFKULg=="
    )
    restored = pickle.loads(legacy)
    assert type(restored) is StudioStorageError
    assert isinstance(restored, RuntimeError)
    assert str(restored) == "legacy test-only storage refusal"
    assert type(pickle.loads(pickle.dumps(restored))) is StudioStorageError


def test_studio_private_atomic_metadata_is_private(tmp_path: Path) -> None:
    root = create_private_test_root(tmp_path)
    path = root / "record.json"
    write_text_atomic(path, '{"actual":"private metadata"}')
    write_text_atomic(path, '{"actual":"updated private metadata"}')
    assert path.read_bytes() == b'{"actual":"updated private metadata"}'
    assert sorted(item.name for item in root.iterdir()) == [path.name]
    if os.name == "nt":
        assert_private_windows_path(root, require_protected=True)
        assert_private_windows_path(path, require_protected=False)
    else:
        assert hasattr(os, "geteuid")
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert path.stat().st_uid == os.geteuid()


def test_studio_private_atomic_metadata_refuses_linked_target(tmp_path: Path) -> None:
    root = create_private_test_root(tmp_path)
    path = root / "record.json"
    seed_private_file(path, b"preserve original owner evidence")
    outside = tmp_path / "original-owner-evidence"
    os.link(path, outside)
    with pytest.raises(StudioStorageError, match="linked"):
        write_text_atomic(path, "must never replace this target")
    assert path.read_bytes() == outside.read_bytes() == b"preserve original owner evidence"
    assert sorted(item.name for item in root.iterdir()) == [path.name]


def test_studio_upload_refuses_external_playlist_container(tmp_path: Path) -> None:
    root = create_private_test_root(tmp_path)
    outside = tmp_path / "external-owner-segment.ts"
    subprocess.run(
        [
            str(find_ffmpeg()),
            "-v",
            "error",
            "-nostdin",
            "-i",
            str(MEDIA),
            "-c",
            "copy",
            "-f",
            "mpegts",
            str(outside),
        ],
        capture_output=True,
        check=True,
        timeout=30,
    )
    before = outside.read_bytes()
    assert before
    playlist = (
        "#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:60\n"
        "#EXTINF:30.0,\n" + outside.as_uri() + "\n#EXT-X-ENDLIST\n"
    ).encode("utf-8")
    store = UploadStore(root)
    ticket = store.begin("disguised-supported-container.mp4", len(playlist))
    with pytest.raises(UploadError, match="container|media"):
        store.receive(ticket["upload_id"], io.BytesIO(playlist), len(playlist))
    assert outside.read_bytes() == before
    assert not list((root / "sources").iterdir())


def test_studio_upload_refuses_mismatched_container(tmp_path: Path) -> None:
    root = create_private_test_root(tmp_path)
    transport_stream = tmp_path / "actual-mpegts.ts"
    subprocess.run(
        [
            str(find_ffmpeg()),
            "-v",
            "error",
            "-nostdin",
            "-i",
            str(MEDIA),
            "-c",
            "copy",
            "-f",
            "mpegts",
            str(transport_stream),
        ],
        capture_output=True,
        check=True,
        timeout=30,
    )
    data = transport_stream.read_bytes()
    assert data
    store = UploadStore(root)
    ticket = store.begin("not-an-mp4.mp4", len(data))
    with pytest.raises(UploadError, match="container|media"):
        store.receive(ticket["upload_id"], io.BytesIO(data), len(data))
    assert transport_stream.read_bytes() == data
    assert not list((root / "sources").iterdir())


@pytest.mark.parametrize(
    ("suffix", "muxer"),
    [
        (".mp4", "mp4"),
        (".mov", "mov"),
        (".m4v", "mp4"),
        (".mkv", "matroska"),
        (".webm", "webm"),
        (".avi", "avi"),
        (".ts", "mpegts"),
    ],
)
def test_studio_upload_accepts_actual_supported_containers(
    tmp_path: Path,
    suffix: str,
    muxer: str,
) -> None:
    root = create_private_test_root(tmp_path)
    media = tmp_path / ("actual-container" + suffix)
    codecs = ["-c", "copy"]
    if suffix == ".webm":
        codecs = ["-c:v", "libvpx-vp9", "-c:a", "libopus", "-threads", "1"]
    subprocess.run(
        [
            str(find_ffmpeg()),
            "-v",
            "error",
            "-nostdin",
            "-i",
            str(MEDIA),
            *codecs,
            "-f",
            muxer,
            str(media),
        ],
        capture_output=True,
        check=True,
        timeout=30,
    )
    data = media.read_bytes()
    assert data
    store = UploadStore(root)
    ticket = store.begin("creator-video" + suffix, len(data))
    source = store.receive(ticket["upload_id"], io.BytesIO(data), len(data))
    assert store.status(ticket["upload_id"])["state"] == "ready"
    assert source["duration_ms"] > 0
    assert source["width"] > 0 and source["height"] > 0
    assert store.source(source["source_id"]).read_bytes() == media.read_bytes() == data


@pytest.mark.parametrize("route", ["begin", "put", "status", "generation"])
def test_studio_http_unconfigured_upload_storage_refuses(
    monkeypatch: pytest.MonkeyPatch,
    route: str,
) -> None:
    import hawedit.web as web

    monkeypatch.setattr(web, "UPLOAD_STORE", None)
    identifier = "a" * 32
    method, path, body = "POST", "/api/uploads", b'{"filename":"source.mp4","size":10}'
    if route == "put":
        method, path, body = "PUT", f"/api/uploads/{identifier}", b"not video!"
    elif route == "status":
        method, path, body = "GET", f"/api/uploads/{identifier}", b""
    elif route == "generation":
        path = "/api/repurpose"
        body = json.dumps(
            {
                "schema": 1,
                "source_id": identifier,
                "client_token": "actual-test-only-token",
                "options": {},
            }
        ).encode()
    status, _, response = _handle_request(
        f"{method} {path} HTTP/1.1\r\nHost: localhost:8080\r\n"
        f"Content-Length: {len(body)}\r\nContent-Type: application/json\r\n\r\n".encode()
        + body
    )
    assert status == 503
    assert "storage" in json.loads(response)["error"].lower()
    assert "source_id" not in json.loads(response)
    assert web.UPLOAD_STORE is None


def test_studio_http_lost_upload_root_refuses_without_recreation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hawedit.web as web

    root = create_private_test_root(tmp_path)
    store = UploadStore(root)
    monkeypatch.setattr(web, "UPLOAD_STORE", store)
    ticket = store.begin("source.mp4", 10)
    retained = tmp_path / "retained-private-owner-data"
    root.rename(retained)
    status, _, response = _handle_request(
        f"GET /api/uploads/{ticket['upload_id']} HTTP/1.1\r\nHost: localhost:8080\r\n\r\n".encode()
    )
    assert status == 503
    assert "storage" in json.loads(response)["error"].lower()
    assert not root.exists()
    assert (retained / "tickets" / f"{ticket['upload_id']}.json").is_file()


@pytest.mark.parametrize("configured", [False, True])
def test_studio_native_server_uploads_use_private_startup_storage(
    tmp_path: Path,
    configured: bool,
) -> None:
    # Execute the actual startup/handler in a child; no worker, model or legacy submission.
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    env = dict(os.environ, PYTHONUNBUFFERED="1", LOCALAPPDATA=str(tmp_path), HOME=str(tmp_path))
    env.pop("HAWEDIT_STUDIO_STORAGE_ROOT", None)
    env.pop("HAWEDIT_UPLOAD_MAX_BYTES", None)
    root = tmp_path / ("HawEditStudio" if os.name == "nt" else ".hawedit-studio")
    if configured:
        root = tmp_path / "configured-private-studio"
        env["HAWEDIT_STUDIO_STORAGE_ROOT"] = str(root)
    program = (
        "import sys; from pathlib import Path; import hawedit.web as w; "
        "assert w.UPLOAD_STORE is None; "
        "w.JOB_MANAGER = w.JobManager(Path(sys.argv[2])); "
        "w.run_web_server(int(sys.argv[1]))"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", program, str(port), str(tmp_path / "test-only-history")],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 20
        while True:
            assert process.poll() is None, "Native studio startup failed"
            try:
                with urlopen(base + "/", timeout=1) as response:
                    assert response.status == 200 and b"HawEdit" in response.read()
                break
            except URLError:
                assert time.monotonic() < deadline, "Native studio startup timed out"
                time.sleep(0.05)
        data = MEDIA.read_bytes()
        payload = json.dumps({"filename": "real-selected-video.mp4", "size": len(data)}).encode()
        with urlopen(
            Request(
                base + "/api/uploads", data=payload, headers={"Content-Type": "application/json"}
            ),
            timeout=10,
        ) as response:
            assert response.status == 201
            upload_id = json.load(response)["upload_id"]
        with urlopen(
            Request(base + f"/api/uploads/{upload_id}", data=data, method="PUT"), timeout=30
        ) as response:
            assert response.status == 201
            source = json.load(response)
        with urlopen(base + f"/api/uploads/{upload_id}", timeout=10) as response:
            status = json.load(response)
            assert status["state"] == "ready"
            assert status["source"] == source
            assert status["source"]["source_id"] == upload_id
        uploads = UploadStore(root / "uploads")
        media = uploads.source(source["source_id"])
        assert media.read_bytes() == data
        if os.name == "nt":
            assert_private_windows_path(root, require_protected=True)
            assert_private_windows_path(media, require_protected=False)
        else:
            assert stat.S_IMODE(root.stat().st_mode) == 0o700
            assert stat.S_IMODE(media.stat().st_mode) == 0o600
    finally:
        if process.poll() is None:
            process.terminate()  # Exact test-owned child only; never a console control event.
        process.wait(timeout=15)
