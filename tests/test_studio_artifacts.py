"""Native manifest/snapshot and HTTP read-boundary regressions; not publication evidence."""

from __future__ import annotations

import base64
import hashlib
import http.client
import json
import os
import subprocess
import threading
import tomllib
import zipfile
from importlib import metadata
from pathlib import Path
from typing import Any

import pytest

from hawedit.measure import measure_clip
from hawedit.studio_artifacts import ArtifactError, open_preview
from test_web import _handle_request


@pytest.fixture(scope="module")
def measured_fixture() -> dict[str, Any]:
    return measure_clip(Path("tests/fixtures/kurdish-speech-3cuts.mp4")).to_dict()


def install_preview(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    measurement: dict[str, Any],
    *,
    job_id: str = "job-one",
) -> tuple[Path, Path, bytes]:
    import hawedit.web as web

    manager = web.JobManager(root / "jobs")
    job = root / "jobs" / job_id
    directory = job / "review" / "clip-one"
    directory.mkdir(parents=True)
    media = directory / "clip-one.mp4"
    payload = Path("tests/fixtures/kurdish-speech-3cuts.mp4").read_bytes()
    media.write_bytes(payload)
    (directory / "clip-one.measured.json").write_text(json.dumps(measurement), encoding="utf-8")
    (job / "report.json").write_text(
        json.dumps(
            {
                "episode_manifest": {
                    "clips": [{"clip_id": "clip-one", "delivery_dir": "review/clip-one"}]
                }
            }
        ),
        encoding="utf-8",
    )
    manager._jobs[job_id] = web.JobInfo(
        job_id, "source.mp4", "awaiting-review", "render", 6, 0, 1.0, 1.0, "review", clips=[]
    )
    monkeypatch.setattr(web, "JOB_MANAGER", manager)
    return job, media, payload


def request(
    path: str, *, method: str = "GET", headers: str = ""
) -> tuple[int, dict[str, str], bytes]:
    return _handle_request(
        f"{method} {path} HTTP/1.1\r\nHost: localhost:8080\r\n{headers}\r\n".encode("ascii")
    )


URL = "/api/jobs/job-one/clips/clip-one/preview"


def test_studio_font_packaging_and_sbom_cover_actual_font(tmp_path: Path) -> None:
    from hawedit.release import _spdx_sbom

    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    paths = set(data["tool"]["setuptools"]["data-files"]["share/hawedit/assets/fonts"])
    required = {
        "assets/fonts/Vazirmatn.ttf",
        "assets/fonts/Vazirmatn.ttf.provenance.json",
        "assets/fonts/Vazirmatn-COPYRIGHT.txt",
        "assets/fonts/OFL.txt",
    }
    assert required <= paths
    wheel = tmp_path / "studio-fonts.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "hawedit-0.1.0.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: hawedit\nVersion: 0.1.0\n",
        )
        for relative in paths:
            archive.write(relative, "hawedit-0.1.0.data/data/share/hawedit/" + relative)
    sbom = json.loads(
        _spdx_sbom(
            wheel,
            revision="a" * 40,
            epoch=1,
            wheel_sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(),
        )
    )
    packages = {item["name"]: item for item in sbom["packages"]}
    font = packages["Vazirmatn"]
    assert font["licenseDeclared"] == "OFL-1.1"
    assert font["checksums"] == [
        {
            "algorithm": "SHA256",
            "checksumValue": "696249a2c74b39ffdef55de4df2809c5b639d3ff80d618d8160a095d2fd49dca",
        }
    ]
    assert any(
        item["relationshipType"] == "CONTAINS" and item["relatedSpdxElement"] == font["SPDXID"]
        for item in sbom["relationships"]
    )


def test_studio_font_installed_record_and_missing_source_are_verified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hawedit.environment as environment
    from hawedit.studio_artifacts import font_bytes

    payload = Path("assets/fonts/Vazirmatn.ttf").read_bytes()
    asset_dir = tmp_path / "share/hawedit/assets/fonts"
    asset_dir.mkdir(parents=True)
    font = asset_dir / "Vazirmatn.ttf"
    font.write_bytes(payload)
    dist_dir = tmp_path / "lib/python/site-packages/hawedit-0.1.0.dist-info"
    dist_dir.mkdir(parents=True)
    digest = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).decode("ascii").rstrip("=")
    (dist_dir / "RECORD").write_text(
        f"../../../share/hawedit/assets/fonts/Vazirmatn.ttf,sha256={digest},{len(payload)}\n",
        encoding="utf-8",
    )
    distribution = metadata.PathDistribution(dist_dir)
    # Controlled discovery, real PathDistribution/RECORD authentication; not a clean install.
    monkeypatch.setattr(environment, "_runtime_hawedit_distribution", lambda: distribution)
    assert font_bytes(tmp_path / "lib") == payload
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "pyproject.toml").write_text("[project]\nname='hawedit'\n", encoding="utf-8")
    with pytest.raises(ArtifactError, match="storage"):
        font_bytes(checkout)
    font.write_bytes(b"altered")
    with pytest.raises(ArtifactError, match="storage"):
        font_bytes(tmp_path / "lib")


def test_studio_server_refuses_nonlocal_binding_before_listen() -> None:
    from hawedit.web import run_web_server

    with pytest.raises(ValueError, match="loopback"):
        run_web_server(port=0, host="https://attacker.invalid")


@pytest.mark.parametrize("method", ["GET", "HEAD"])
@pytest.mark.parametrize(
    "path",
    [
        "/README.md",
        "/work/",
        "/src/hawedit/web.py",
        "/assets/fonts/",
        "/../README.md",
        "/%2e%2e/README.md",
        "/work/private-billing.sqlite",
        "/tests/fixtures/kurdish-speech-3cuts.mp4",
    ],
)
def test_studio_refuses_unlisted_filesystem_routes(method: str, path: str) -> None:
    status, headers, body = request(path, method=method)
    assert status == 404
    assert "Directory listing" not in body.decode("utf-8")
    assert headers["cache-control"] == "no-store"
    if method == "HEAD":
        assert body == b""


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_studio_unscoped_media_is_refused(method: str) -> None:
    status, _, body = request("/media/kurdish-speech-3cuts.mp4", method=method)
    assert status == 404 and b"ftyp" not in body


@pytest.mark.parametrize("legacy_status", ["queued", "running", "completed", "failed"])
def test_studio_status_never_fabricates_readiness_or_reel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, legacy_status: str
) -> None:
    import hawedit.web as web

    manager = web.JobManager(tmp_path / "jobs")
    manager._jobs["old"] = web.JobInfo(
        "old", "old.mp4", legacy_status, "render", 6, 100, 1, 1, "old"
    )
    folder = manager._jobs_dir / "old"
    folder.mkdir()
    (folder / "job.json").write_text(json.dumps(manager._jobs["old"].to_dict()), encoding="utf-8")
    monkeypatch.setattr(web, "JOB_MANAGER", manager)
    status, _, body = request("/api/status")
    document = json.loads(body)
    assert status == 200 and document["status"] == "unavailable"
    assert document["runner_ready"] is False and document["latest_reel"] is None
    assert document["historical_job_count"] == 1 and document["active_job"] is None
    assert b"48.14" not in body and b"audit_passed" not in body


def test_studio_local_font_is_pinned_and_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hawedit.web as web

    status, headers, body = request("/assets/fonts/Vazirmatn.ttf")
    assert status == 200 and headers["content-type"] == "font/ttf"
    assert (
        hashlib.sha256(body).hexdigest()
        == "696249a2c74b39ffdef55de4df2809c5b639d3ff80d618d8160a095d2fd49dca"
    )
    _, head, head_body = request("/assets/fonts/Vazirmatn.ttf", method="HEAD")
    assert head_body == b"" and int(head["content-length"]) == len(body)
    assert (
        "fonts.googleapis.com" not in web.DASHBOARD_HTML
        and "fonts.gstatic.com" not in web.DASHBOARD_HTML
    )
    assert "/assets/fonts/Vazirmatn.ttf" in web.DASHBOARD_HTML
    directory = tmp_path / "assets" / "fonts"
    directory.mkdir(parents=True)
    (directory / "Vazirmatn.ttf").write_bytes(b"altered font")
    monkeypatch.setattr(web, "ROOT", tmp_path)
    refused, _, bad_body = request("/assets/fonts/Vazirmatn.ttf")
    assert refused == 503 and b"altered font" not in bad_body


@pytest.mark.parametrize(
    "range_header,expected_status,start,end",
    [
        ("bytes=0-99", 206, 0, 99),
        ("bytes=100-", 206, 100, None),
        ("bytes=-50", 206, -50, None),
        ("bytes=0-999999", 206, 0, None),
        ("bytes=999999-", 416, None, None),
        ("bytes=-0", 416, None, None),
        ("bytes=99-1", 200, 0, None),
        ("bytes=0-1,3-4", 200, 0, None),
        ("bytes=1e2-200", 200, 0, None),
        ("items=0-1", 200, 0, None),
    ],
)
def test_studio_artifact_scope_and_ranges(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    measured_fixture: dict[str, Any],
    range_header: str,
    expected_status: int,
    start: int | None,
    end: int | None,
) -> None:
    _, _, payload = install_preview(tmp_path, monkeypatch, measured_fixture)
    status, headers, body = request(URL, headers=f"Range: {range_header}\r\n")
    assert status == expected_status and headers["accept-ranges"] == "bytes"
    assert headers["etag"] == '"' + hashlib.sha256(payload).hexdigest() + '"'
    assert headers["x-hawedit-artifact-state"] == "private-preview"
    assert headers["cache-control"] == "no-store"
    if status == 416:
        assert headers["content-range"] == f"bytes */{len(payload)}" and body == b""
    else:
        assert start is not None
        assert body == payload[start : None if end is None else end + 1]
        assert int(headers["content-length"]) == len(body)
        if status == 206:
            real_start = start if start >= 0 else len(payload) + start
            real_end = end if end is not None else len(payload) - 1
            assert headers["content-range"] == f"bytes {real_start}-{real_end}/{len(payload)}"


def test_studio_preview_head_if_range_and_duplicate_ranges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, measured_fixture: dict[str, Any]
) -> None:
    _, _, payload = install_preview(tmp_path, monkeypatch, measured_fixture)
    status, headers, body = request(URL, method="HEAD", headers="Range: bytes=0-9\r\n")
    assert status == 200 and body == b"" and int(headers["content-length"]) == len(payload)
    for value, expected in (
        (headers["etag"], 206),
        ('"stale"', 200),
        ("W/" + headers["etag"], 200),
    ):
        code, _, actual = request(URL, headers=f"Range: bytes=0-9\r\nIf-Range: {value}\r\n")
        assert code == expected and actual == (payload[:10] if expected == 206 else payload)
    code, _, actual = request(URL, headers="Range: bytes=0-9\r\nRange: bytes=20-29\r\n")
    assert code == 200 and actual == payload


@pytest.mark.parametrize(
    "change",
    [
        "media",
        "measurement",
        "manifest",
        "duplicate",
        "escape",
        "missing",
        "bool-duration",
        "deep-json",
    ],
)
def test_studio_preview_refuses_changed_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, measured_fixture: dict[str, Any], change: str
) -> None:
    job, media, payload = install_preview(tmp_path, monkeypatch, measured_fixture)
    if change == "media":
        media.write_bytes(b"x" * len(payload))
    elif change in {"measurement", "bool-duration"}:
        changed = json.loads(json.dumps(measured_fixture))
        if change == "measurement":
            changed["file"]["sha256"] = "0" * 64
        else:
            changed["video"]["duration_ms"] = True
        media.with_suffix(".measured.json").write_text(json.dumps(changed), encoding="utf-8")
    elif change == "manifest":
        (job / "report.json").write_text('{"episode_manifest":{"clips":[]}}', encoding="utf-8")
    elif change == "duplicate":
        row = {"clip_id": "clip-one", "delivery_dir": "review/clip-one"}
        (job / "report.json").write_text(
            json.dumps({"episode_manifest": {"clips": [row, row]}}), encoding="utf-8"
        )
    elif change == "escape":
        (job / "report.json").write_text(
            '{"episode_manifest":{"clips":[{"clip_id":"clip-one","delivery_dir":"../review"}]}}',
            encoding="utf-8",
        )
    elif change == "deep-json":
        (job / "report.json").write_text("[" * 16384 + "0" + "]" * 16384, encoding="utf-8")
    else:
        media.unlink()
    status, _, body = request(URL)
    assert status in {404, 409} and payload not in body and str(tmp_path).encode() not in body


def test_studio_preview_snapshot_survives_source_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, measured_fixture: dict[str, Any]
) -> None:
    job, media, payload = install_preview(tmp_path, monkeypatch, measured_fixture)
    with open_preview(job.parent, job.name, "clip-one") as preview:
        media.write_bytes(b"x" * len(payload))
        assert preview.stream.read() == payload
        assert preview.duration_ms == measured_fixture["video"]["duration_ms"]
    with (
        pytest.raises(ArtifactError, match="evidence"),
        open_preview(job.parent, job.name, "clip-one"),
    ):
        pytest.fail("Altered bytes must not be previewable")


@pytest.mark.parametrize("target", ["media", "report", "measurement", "directory"])
def test_studio_preview_refuses_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, measured_fixture: dict[str, Any], target: str
) -> None:
    job, media, _ = install_preview(tmp_path, monkeypatch, measured_fixture)
    if target == "directory":
        outside = tmp_path / "outside"
        outside.mkdir()
        link = job / "linked"
        if os.name == "nt":
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                check=True,
                capture_output=True,
                timeout=10,
            )
        else:
            link.symlink_to(outside, target_is_directory=True)
        (job / "report.json").write_text(
            '{"episode_manifest":{"clips":[{"clip_id":"clip-one","delivery_dir":"linked"}]}}',
            encoding="utf-8",
        )
    else:
        original = {
            "media": media,
            "report": job / "report.json",
            "measurement": media.with_suffix(".measured.json"),
        }[target]
        os.link(original, tmp_path / f"linked-{target}")
    status, _, _ = request(URL)
    assert status == 409


@pytest.mark.parametrize(
    "path", [URL, "/api/jobs", "/api/status", "/assets/fonts/Vazirmatn.ttf", "/"]
)
def test_studio_reads_require_local_origin(path: str) -> None:
    for headers in (
        "Host: attacker.invalid\r\n",
        "Host: localhost:8080\r\nOrigin: https://attacker.invalid\r\n",
        "Host: localhost:8080\r\nHost: attacker.invalid\r\n",
        "Host: localhost:8080\r\nSec-Fetch-Site: cross-site\r\n",
    ):
        status, _, body = _handle_request(f"GET {path} HTTP/1.1\r\n{headers}\r\n".encode("ascii"))
        assert status == 403 and b"ftyp" not in body


@pytest.mark.parametrize(
    "headers",
    [
        "Sec-Fetch-Site: same-site\r\n",
        "Sec-Fetch-Site: invalid\r\n",
        "Origin: http://localhost:8080\r\nOrigin: https://attacker.invalid\r\n",
    ],
)
def test_studio_reads_refuse_ambiguous_or_neighbor_origins(headers: str) -> None:
    status, _, _ = request("/api/status", headers=headers)
    assert status == 403


def test_studio_preview_real_loopback_seeking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, measured_fixture: dict[str, Any]
) -> None:
    import hawedit.web as web

    _, _, payload = install_preview(tmp_path, monkeypatch, measured_fixture)
    with web.ThreadingTCPServer(("127.0.0.1", 0), web.HawEditWebHandler) as server:
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            connection = http.client.HTTPConnection(
                "127.0.0.1", server.server_address[1], timeout=10
            )
            connection.request("GET", URL, headers={"Range": "bytes=16-63"})
            response = connection.getresponse()
            assert response.status == 206 and response.read() == payload[16:64]
            connection.close()
        finally:
            server.shutdown()
            thread.join(timeout=10)
            assert not thread.is_alive()


def test_studio_preview_busy_and_disconnect_release_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, measured_fixture: dict[str, Any]
) -> None:
    job, _, _ = install_preview(tmp_path, monkeypatch, measured_fixture)
    with open_preview(job.parent, job.name, "clip-one"):
        status, _, body = request(URL)
        assert status == 503 and b"busy" in body
    with (
        pytest.raises(BrokenPipeError, match="consumer disconnected"),
        open_preview(job.parent, job.name, "clip-one"),
    ):
        raise BrokenPipeError("consumer disconnected")
    assert request(URL)[0] == 200


def test_studio_preview_large_decoded_snapshot_cleans_disk_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, measured_fixture: dict[str, Any]
) -> None:
    from hawedit.captions import find_ffmpeg

    job, media, _ = install_preview(tmp_path, monkeypatch, measured_fixture)
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None
    subprocess.run(
        [
            str(ffmpeg),
            "-v",
            "error",
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=640x360:rate=25",
            "-i",
            "tests/fixtures/kurdish-speech-3cuts.mp4",
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-vf",
            "noise=alls=100:allf=t",
            "-t",
            "3",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-qp",
            "0",
            "-threads",
            "1",
            "-c:a",
            "aac",
            str(media),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    assert media.stat().st_size > 8 * 1024**2
    measurement = measure_clip(media)
    media.with_suffix(".measured.json").write_text(measurement.to_json(), encoding="utf-8")
    before = set(job.iterdir())
    with open_preview(job.parent, job.name, "clip-one") as preview:
        assert getattr(preview.stream, "_rolled", False)
        assert hashlib.sha256(preview.stream.read()).hexdigest() == measurement.file.sha256
    assert set(job.iterdir()) == before
