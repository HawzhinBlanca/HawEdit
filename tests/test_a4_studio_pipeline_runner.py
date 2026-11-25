"""Tests for A4 (D-338): Studio repurpose queue, SSE progress, and preview serving."""

from __future__ import annotations

import io
import json
import re
import threading
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

import pytest

from hawedit.clip import DiscoveryPath
from hawedit.discovery import Candidate
from hawedit.events import RunEvent, RunState
from hawedit.pipeline import Delivery, PipelineRun, run_pipeline
from hawedit.studio_uploads import UploadStore
from studio_test_storage import create_private_test_root
from test_a2_one_command_reels import FIXTURE, _StubJudge, _two_clip_transcript
from test_studio_generation import payload as gen_payload
from test_web import _handle_request


@pytest.fixture(name="tmp_path")
def _private_tmp_path(tmp_path: Path) -> Path:
    return create_private_test_root(tmp_path)


def _upload_fixture(tmp_path: Path) -> tuple[UploadStore, str]:
    store = UploadStore(tmp_path / "uploads")
    data = FIXTURE.read_bytes()
    ticket = store.begin("episode.mp4", len(data))
    source = store.receive(ticket["upload_id"], io.BytesIO(data), len(data))
    return store, source["source_id"]


def _post_repurpose(
    body: bytes,
    *,
    host: str = "localhost:8080",
) -> tuple[int, dict[str, str], bytes]:
    req = (
        f"POST /api/repurpose HTTP/1.1\r\nHost: {host}\r\n"
        f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n"
    ).encode("ascii") + body
    return _handle_request(req)


def test_studio_status_reports_ready_in_desktop_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hawedit.web as web

    monkeypatch.delenv("HAWEDIT_PROTECTED_STUDIO", raising=False)
    manager = web.JobManager(tmp_path / "jobs")
    monkeypatch.setattr(web, "JOB_MANAGER", manager)

    code, _, body = _handle_request(b"GET /api/status HTTP/1.1\r\nHost: localhost:8080\r\n\r\n")
    assert code == 200
    status = json.loads(body.decode("utf-8"))
    assert status["status"] == "ready"
    assert status["runner_ready"] is True
    assert status["active_job"] is None
    assert status["latest_reel"] is None
    assert "code" not in status

    submitted = manager.submit_job(str(FIXTURE), start_worker=False)
    code2, _, body2 = _handle_request(b"GET /api/status HTTP/1.1\r\nHost: localhost:8080\r\n\r\n")
    assert code2 == 200
    active_status = json.loads(body2.decode("utf-8"))
    assert active_status["status"] == "running"
    assert active_status["runner_ready"] is True
    assert active_status["active_job"] is not None
    assert active_status["active_job"]["job_id"] == submitted["job_id"]


def test_repurpose_queues_real_pipeline_job_with_zero_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hawedit.pipeline as pipeline_mod
    import hawedit.web as web

    monkeypatch.delenv("HAWEDIT_PROTECTED_STUDIO", raising=False)
    store, source_id = _upload_fixture(tmp_path)
    manager = web.JobManager(tmp_path / "jobs")
    monkeypatch.setattr(web, "UPLOAD_STORE", store)
    monkeypatch.setattr(web, "JOB_MANAGER", manager)

    started_calls: list[dict[str, Any]] = []
    block_worker = threading.Event()
    monkeypatch.setattr(
        manager,
        "_start_worker",
        lambda jid: started_calls.append({"job_id": jid}),
    )

    body = json.dumps(gen_payload(source_id, preset="viral", max_clips=10)).encode("utf-8")
    code, _, raw = _post_repurpose(body)
    assert code == 202, raw.decode("utf-8", "replace")
    reply = json.loads(raw.decode("utf-8"))
    assert reply["job_id"]
    assert reply["status"] in {"queued", "running"}
    assert reply["events_url"] == f"/api/jobs/{reply['job_id']}/events"
    assert started_calls == [{"job_id": reply["job_id"]}]
    assert _post_repurpose(body, host="attacker.example")[0] == 403

    captured_args: dict[str, Any] = {}

    def spy_build_and_run(args: Any, on_event: Any = None) -> PipelineRun:
        captured_args["args"] = args
        captured_args["on_event"] = on_event
        block_worker.set()
        job_dir = manager._jobs_dir / reply["job_id"]
        return PipelineRun(
            media_id="ep",
            source=str(args.source),
            work_dir=str(job_dir),
            delivery=Delivery(
                srt_path=str(job_dir / "a.srt"),
                edl_path=str(job_dir / "a.edl"),
                editing_json_path=str(job_dir / "a.json"),
                measured_path=str(job_dir / "a.measured.json"),
                edit_plan_path=str(job_dir / "a.edit_plan.json"),
            ),
        )

    monkeypatch.setattr(pipeline_mod, "_build_and_run", spy_build_and_run)
    manager.run_job_sync(reply["job_id"])
    args = captured_args["args"]
    assert args.reels is True
    assert args.max_clips == 10
    assert args.strict_runtime is False
    assert args.validate_asr is False


def test_protected_studio_mode_preserves_503_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hawedit.web as web

    monkeypatch.setenv("HAWEDIT_PROTECTED_STUDIO", "1")
    store, source_id = _upload_fixture(tmp_path)
    manager = web.JobManager(tmp_path / "jobs")
    monkeypatch.setattr(web, "UPLOAD_STORE", store)
    monkeypatch.setattr(web, "JOB_MANAGER", manager)

    code, _, raw_status = _handle_request(
        b"GET /api/status HTTP/1.1\r\nHost: localhost:8080\r\n\r\n"
    )
    assert code == 200
    status = json.loads(raw_status.decode("utf-8"))
    assert status["status"] == "unavailable"
    assert status["runner_ready"] is False
    assert status["code"] == "studio_runner_unavailable"

    body = json.dumps(gen_payload(source_id, preset="viral")).encode("utf-8")
    post_code, _, post_raw = _post_repurpose(body)
    assert post_code == 503
    assert json.loads(post_raw.decode("utf-8"))["code"] == "studio_runner_unavailable"
    assert manager.get_all_jobs() == []


def test_job_events_sse_streams_stage_updates_and_closes_on_terminal_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hawedit.pipeline as pipeline_mod
    import hawedit.web as web

    monkeypatch.delenv("HAWEDIT_PROTECTED_STUDIO", raising=False)
    store, source_id = _upload_fixture(tmp_path)
    manager = web.JobManager(tmp_path / "jobs")
    monkeypatch.setattr(web, "UPLOAD_STORE", store)
    monkeypatch.setattr(web, "JOB_MANAGER", manager)

    def fake_build_and_run(args: Any, on_event: Any = None) -> PipelineRun:
        work = Path(args.work_dir)
        on_event(RunEvent("ep", 1, 10, "ingest", RunState.STARTED))
        on_event(RunEvent("ep", 2, 20, "ingest", RunState.COMPLETED))
        on_event(RunEvent("ep", 3, 30, "transcript", RunState.STARTED))
        on_event(RunEvent("ep", 4, 40, "delivery", RunState.COMPLETED))
        return PipelineRun(
            media_id="ep",
            source=str(args.source),
            work_dir=str(work),
            delivery=Delivery(
                srt_path=str(work / "c.srt"),
                edl_path=str(work / "c.edl"),
                editing_json_path=str(work / "c.json"),
                measured_path=str(work / "c.measured.json"),
                edit_plan_path=str(work / "c.edit_plan.json"),
            ),
        )

    monkeypatch.setattr(pipeline_mod, "_build_and_run", fake_build_and_run)

    with web.ThreadingTCPServer(("127.0.0.1", 0), web.HawEditWebHandler) as server:
        port = int(server.server_address[1])
        srv_thread = threading.Thread(target=server.serve_forever, daemon=True)
        srv_thread.start()
        try:
            conn = HTTPConnection("127.0.0.1", port, timeout=5)
            body = json.dumps(gen_payload(source_id, preset="viral")).encode("utf-8")
            conn.request(
                "POST",
                "/api/repurpose",
                body=body,
                headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{port}"},
            )
            post_resp = conn.getresponse()
            assert post_resp.status == 202
            job_id = json.loads(post_resp.read().decode("utf-8"))["job_id"]
            conn.close()

            sse_conn = HTTPConnection("127.0.0.1", port, timeout=5)
            sse_conn.request(
                "GET",
                f"/api/jobs/{job_id}/events",
                headers={"Host": f"127.0.0.1:{port}"},
            )
            sse_resp = sse_conn.getresponse()
            assert sse_resp.status == 200
            assert "text/event-stream" in sse_resp.getheader("Content-Type", "")
            raw_stream = sse_resp.read().decode("utf-8")
            sse_conn.close()
        finally:
            server.shutdown()
            srv_thread.join(timeout=2)

    assert "event: stage" in raw_stream
    assert '"stage": "ingest"' in raw_stream
    assert "event: completed" in raw_stream


def test_delivered_studio_clips_serve_verified_preview_and_keep_sse_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hawedit.pipeline as pipeline_mod
    import hawedit.web as web

    assert "EventSource" in web.DASHBOARD_HTML
    assert "/events" in web.DASHBOARD_HTML
    assert "setInterval" not in web.DASHBOARD_HTML
    assert '<option value="10">' in web.DASHBOARD_HTML
    assert "[1, 2, 3, 5, 10]" in web.DASHBOARD_HTML

    monkeypatch.delenv("HAWEDIT_PROTECTED_STUDIO", raising=False)
    store, source_id = _upload_fixture(tmp_path)
    manager = web.JobManager(tmp_path / "jobs")
    monkeypatch.setattr(web, "UPLOAD_STORE", store)
    monkeypatch.setattr(web, "JOB_MANAGER", manager)
    monkeypatch.setattr(manager, "_start_worker", lambda _jid: None)

    body = json.dumps(gen_payload(source_id, preset="viral", max_clips=10)).encode("utf-8")
    code, _, raw = _post_repurpose(body)
    assert code == 202
    job_id = json.loads(raw.decode("utf-8"))["job_id"]

    def real_delivery_build_and_run(args: Any, on_event: Any = None) -> PipelineRun:
        work = Path(args.work_dir)
        transcript = _two_clip_transcript("ep")
        candidates = [
            Candidate("c1", "ep", 100, 1_500, DiscoveryPath.VERBAL, rank=1, score=0.92),
            Candidate("c2", "ep", 2_000, 4_100, DiscoveryPath.VERBAL, rank=2, score=0.89),
        ]
        return run_pipeline(
            Path(args.source),
            work,
            media_id="ep",
            transcript=transcript,
            discover=lambda _n: candidates,
            judge=_StubJudge(),
            auto_select=True,
            judge_top_n=2,
            min_clip_ms=1_000,
            max_clips=2,
            min_separation_ms=100,
            on_event=on_event,
        )

    monkeypatch.setattr(pipeline_mod, "_build_and_run", real_delivery_build_and_run)
    manager.run_job_sync(job_id)

    job_code, _, job_raw = _handle_request(
        f"GET /api/jobs/{job_id} HTTP/1.1\r\nHost: localhost:8080\r\n\r\n".encode("ascii")
    )
    assert job_code == 200
    job_doc = json.loads(job_raw.decode("utf-8"))
    assert job_doc["status"] == "completed"
    assert len(job_doc["clips"]) == 2
    clip_id = job_doc["clips"][0]["clip_id"]

    preview_path = f"/api/jobs/{job_id}/clips/{clip_id}/preview"
    head_code, head_headers, head_body = _handle_request(
        f"HEAD {preview_path} HTTP/1.1\r\nHost: localhost:8080\r\n\r\n".encode("ascii")
    )
    assert head_code == 200 and head_body == b""
    assert head_headers.get("x-hawedit-artifact-state") == "private-preview"
    assert head_headers.get("content-type") == "video/mp4"
    assert re.fullmatch(r'"[a-f0-9]{64}"', head_headers.get("etag", ""))

    get_code, _, mp4_bytes = _handle_request(
        f"GET {preview_path} HTTP/1.1\r\nHost: localhost:8080\r\n\r\n".encode("ascii")
    )
    assert get_code == 200 and b"ftyp" in mp4_bytes[:32]

    bad_preview = f"/api/jobs/{job_id}/clips/../outside/preview"
    bad_code, _, _ = _handle_request(
        f"GET {bad_preview} HTTP/1.1\r\nHost: localhost:8080\r\n\r\n".encode("ascii")
    )
    assert bad_code in {400, 404, 409}
