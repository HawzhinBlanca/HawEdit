"""Tests for V9 Module D (D-392): First-Class V8 Integration in Studio UI & Web API."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import hawedit.web as web
from hawedit.studio_history import read_history
from hawedit.studio_ui import DASHBOARD_HTML
from hawedit.studio_uploads import UploadStore
from studio_test_storage import create_private_test_root
from test_studio_ui import markup
from test_web import _handle_request

FIXTURE_VIDEO = Path("tests/fixtures/kurdish-speech-3cuts.mp4")


@pytest.fixture(name="tmp_path")
def _private_tmp_path(tmp_path: Path) -> Path:
    return create_private_test_root(tmp_path)


def _upload_fixture(tmp_path: Path) -> tuple[UploadStore, str]:
    store = UploadStore(tmp_path / "uploads")
    data = FIXTURE_VIDEO.read_bytes()
    ticket = store.begin("episode.mp4", len(data))
    source = store.receive(ticket["upload_id"], io.BytesIO(data), len(data))
    return store, source["source_id"]


def _http_get(
    path: str, *, host: str = "localhost:8080", extra_headers: str = ""
) -> tuple[int, dict[str, str], bytes]:
    raw = f"GET {path} HTTP/1.1\r\nHost: {host}\r\n{extra_headers}\r\n".encode("ascii")
    return _handle_request(raw)


def _http_head(path: str, *, host: str = "localhost:8080") -> tuple[int, dict[str, str], bytes]:
    raw = f"HEAD {path} HTTP/1.1\r\nHost: {host}\r\n\r\n".encode("ascii")
    return _handle_request(raw)


def _http_post(
    path: str, payload: dict[str, Any], *, host: str = "localhost:8080"
) -> tuple[int, dict[str, str], bytes]:
    body = json.dumps(payload).encode("utf-8")
    raw = (
        f"POST {path} HTTP/1.1\r\nHost: {host}\r\n"
        f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n"
    ).encode("ascii") + body
    return _handle_request(raw)


def _v8_payload(source_id: str, **overrides: Any) -> dict[str, Any]:
    options: dict[str, Any] = {
        "engine": "v8",
        "style_preset": "crimson_punch",
        "director": "offline",
        "sub_engine": "skia",
        "condense": True,
        "cold_open": True,
        "max_clips": 2,
        "brand_accent_hex": "#FF2E63",
        "speaker_name_ckb": "هاوژین",
        "speaker_role_ckb": "پێشکەشکار",
        "end_card_title_ckb": "بۆ ڤیدیۆی زیاتر فۆڵۆمان بکە",
        "end_card_handle": "@hawedit",
        "use_omni_asr": False,
    }
    options.update(overrides)
    return {
        "schema": 1,
        "source_id": source_id,
        "client_token": "v8-client-token-0001",
        "options": options,
    }


def _install_stub_doctor(monkeypatch: pytest.MonkeyPatch, report_dict: dict[str, Any]) -> None:
    mod = types.ModuleType("hawedit.v8.doctor")

    class _StubReport:
        def to_dict(self) -> dict[str, Any]:
            return report_dict

    def _run_v8_doctor() -> _StubReport:
        return _StubReport()

    mod.run_v8_doctor = _run_v8_doctor  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "hawedit.v8.doctor", mod)


def _install_stub_styles(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = types.ModuleType("hawedit.v8.styles")
    presets = (
        {
            "name": "viral_gold",
            "display_name": "Viral Gold",
            "description": "High-energy yellow pills",
            "active_pill_hex": "#FFD700",
            "power_pill_hex": "#B8FF2E",
            "progress_bar_hex": "#FFD700",
            "swatches": ["#FFD700", "#B8FF2E", "#FFD700"],
            "allow_camera_moves": True,
            "max_camera_scale": 1.14,
        },
        {
            "name": "crimson_punch",
            "display_name": "Crimson Punch",
            "description": "Creator red contrast pills",
            "active_pill_hex": "#FF2E63",
            "power_pill_hex": "#FFD700",
            "progress_bar_hex": "#FF2E63",
            "swatches": ["#FF2E63", "#FFD700", "#FF2E63"],
            "allow_camera_moves": True,
            "max_camera_scale": 1.15,
        },
        {
            "name": "executive_cyan",
            "display_name": "Executive Cyan",
            "description": "Clean business cyan pills",
            "active_pill_hex": "#00D4FF",
            "power_pill_hex": "#FFFFFF",
            "progress_bar_hex": "#00D4FF",
            "swatches": ["#00D4FF", "#FFFFFF", "#00D4FF"],
            "allow_camera_moves": True,
            "max_camera_scale": 1.08,
        },
        {
            "name": "luxury_minimal",
            "display_name": "Luxury Minimal",
            "description": "Champagne gold hairline pills",
            "active_pill_hex": "#161820",
            "power_pill_hex": "#F5C451",
            "progress_bar_hex": "#F5C451",
            "swatches": ["#161820", "#F5C451", "#F5C451"],
            "allow_camera_moves": True,
            "max_camera_scale": 1.08,
        },
        {
            "name": "broadcast_news",
            "display_name": "Broadcast News",
            "description": "100% locked tripod broadcast",
            "active_pill_hex": "#102446",
            "power_pill_hex": "#FFD700",
            "progress_bar_hex": "#1D4ED8",
            "swatches": ["#102446", "#FFD700", "#1D4ED8"],
            "allow_camera_moves": False,
            "max_camera_scale": 1.00,
        },
    )

    def _list_presets() -> tuple[dict[str, Any], ...]:
        return presets

    mod.list_client_style_presets = _list_presets  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "hawedit.v8.styles", mod)


@dataclass(frozen=True)
class _StubV8EpisodeConfig:
    director: str = "offline"
    sub_engine: str = "skia"
    max_clips: int = 3
    condense: bool = False
    cold_open: bool = False
    style_preset: str = "viral_gold"
    brand_accent_hex: str | None = None
    speaker_name_ckb: str | None = None
    speaker_role_ckb: str | None = None
    end_card_title_ckb: str | None = None
    end_card_handle: str | None = None


@dataclass(frozen=True)
class _StubDeliveryPack:
    clip_id: str
    mp4_path: Path
    srt_path: Path
    edl_path: Path
    otio_path: Path
    cover_png_path: Path
    director_json_path: Path
    grill_json_path: Path | None
    duration_ms: int
    face_share: float
    hook_title_ckb: str
    grill_passed: bool | None
    grill_summary: str


@dataclass(frozen=True)
class _StubClipItem:
    rank: int
    clip_id: str
    delivery_pack: _StubDeliveryPack
    grill_passed: bool
    grill_summary: str
    hook_title_ckb: str
    duration_s: float
    face_share: float


@dataclass(frozen=True)
class _StubEpisodeResult:
    media_id: str
    source_mp4: Path
    out_dir: Path
    clips: tuple[_StubClipItem, ...]
    review_html_path: Path
    total_wall_s: float
    all_grills_passed: bool


def test_v8_doctor_endpoint_returns_structured_report(monkeypatch: pytest.MonkeyPatch) -> None:
    sample_report = {
        "ready_for_production": True,
        "elapsed_ms": 42.5,
        "gpu_note": "RTX 5070 Ti + RTX 4060 Ti",
        "counts": {"ok": 6, "warn": 1, "fail": 0},
        "checks": [
            {
                "name": "gpu_nvenc",
                "status": "ok",
                "summary": "h264_nvenc ready",
                "details": {},
                "elapsed_ms": 5.0,
            },
            {
                "name": "ffmpeg_rtl",
                "status": "ok",
                "summary": "HarfBuzz + FriBidi ok",
                "details": {},
                "elapsed_ms": 4.0,
            },
            {
                "name": "skia_harfbuzz",
                "status": "ok",
                "summary": "Skia + Vazirmatn ok",
                "details": {},
                "elapsed_ms": 3.0,
            },
            {
                "name": "wsl_asr",
                "status": "ok",
                "summary": "8000 & 8001 healthy",
                "details": {},
                "elapsed_ms": 8.0,
            },
            {
                "name": "gemini_director",
                "status": "ok",
                "summary": "GEMINI_API_KEY set",
                "details": {},
                "elapsed_ms": 1.0,
            },
            {
                "name": "local_omni_director",
                "status": "warn",
                "summary": "LM Studio offline",
                "details": {},
                "elapsed_ms": 20.0,
            },
            {
                "name": "disk_space",
                "status": "ok",
                "summary": "180 GB free",
                "details": {},
                "elapsed_ms": 1.5,
            },
        ],
        "checks_by_name": {"gpu_nvenc": {"status": "ok"}},
    }
    _install_stub_doctor(monkeypatch, sample_report)

    status, headers, body = _http_get("/api/v8/doctor")
    assert status == 200
    assert "application/json" in headers["content-type"]
    data = json.loads(body.decode("utf-8"))
    assert data["ready_for_production"] is True
    assert len(data["checks"]) == 7
    assert {row["name"] for row in data["checks"]} == {
        "gpu_nvenc",
        "ffmpeg_rtl",
        "skia_harfbuzz",
        "wsl_asr",
        "gemini_director",
        "local_omni_director",
        "disk_space",
    }

    # Host boundary enforced on doctor route
    bad_status, _, _ = _http_get("/api/v8/doctor", host="evil.example")
    assert bad_status == 403


def test_v8_doctor_endpoint_fails_loud_when_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    broken = types.ModuleType("hawedit.v8.doctor")

    def _boom() -> None:
        raise RuntimeError("nvidia-smi crashed")

    broken.run_v8_doctor = _boom  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "hawedit.v8.doctor", broken)

    status, _, body = _http_get("/api/v8/doctor")
    assert status == 503
    assert "nvidia-smi crashed" in json.loads(body.decode("utf-8"))["error"]


def test_v8_presets_endpoint_lists_all_five_client_presets(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_stub_styles(monkeypatch)

    status, headers, body = _http_get("/api/v8/presets")
    assert status == 200
    assert "application/json" in headers["content-type"]
    data = json.loads(body.decode("utf-8"))
    presets = data["presets"]
    assert [p["name"] for p in presets] == [
        "viral_gold",
        "crimson_punch",
        "executive_cyan",
        "luxury_minimal",
        "broadcast_news",
    ]
    for preset in presets:
        assert preset["display_name"]
        assert preset["description"]
        assert len(preset["swatches"]) == 3
        assert all(hex_c.startswith("#") and len(hex_c) == 7 for hex_c in preset["swatches"])


def test_v8_repurpose_executes_episode_serves_all_artifacts_and_blocks_traversal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HAWEDIT_PROTECTED_STUDIO", raising=False)
    store, source_id = _upload_fixture(tmp_path)
    manager = web.JobManager(tmp_path / "jobs")
    monkeypatch.setattr(web, "UPLOAD_STORE", store)
    monkeypatch.setattr(web, "JOB_MANAGER", manager)
    monkeypatch.setattr(manager, "_start_worker", lambda _jid: None)

    captured: dict[str, Any] = {}

    def _fake_compile_v8_episode(
        source: Path,
        out_dir: Path,
        *,
        transcript_path: Path | None = None,
        use_omni_asr: bool = False,
        config: _StubV8EpisodeConfig | None = None,
    ) -> _StubEpisodeResult:
        captured["source"] = source
        captured["out_dir"] = out_dir
        captured["transcript_path"] = transcript_path
        captured["use_omni_asr"] = use_omni_asr
        captured["config"] = config

        out_dir.mkdir(parents=True, exist_ok=True)
        cid = "ep-clip-01"
        mp4 = out_dir / f"{cid}.v8.mp4"
        srt = out_dir / f"{cid}.v8.srt"
        edl = out_dir / f"{cid}.v8.edl"
        otio = out_dir / f"{cid}.v8.otio"
        cover = out_dir / f"{cid}.v8.cover.png"
        director_json = out_dir / f"{cid}.director.json"
        grill_json = out_dir / f"{cid}.grill.json"
        review_html = out_dir / "client-review.html"

        mp4.write_bytes(FIXTURE_VIDEO.read_bytes())
        srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nسڵاو کوردستان\n", encoding="utf-8")
        edl.write_text("TITLE: ep-clip-01\nFCM: NON-DROP FRAME\n", encoding="utf-8")
        otio.write_text('{"OTIO_SCHEMA": "Timeline.1", "name": "ep-clip-01"}', encoding="utf-8")
        cover.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        director_json.write_text('{"hook_title_ckb": "نهێنی AI لە کوردستان"}', encoding="utf-8")
        grill_json.write_text('{"passed": true, "double_cuts": []}', encoding="utf-8")
        review_html.write_text(
            "<!DOCTYPE html><html lang='ckb' dir='rtl'><body>Review</body></html>", encoding="utf-8"
        )

        pack = _StubDeliveryPack(
            clip_id=cid,
            mp4_path=mp4,
            srt_path=srt,
            edl_path=edl,
            otio_path=otio,
            cover_png_path=cover,
            director_json_path=director_json,
            grill_json_path=grill_json,
            duration_ms=41200,
            face_share=0.96,
            hook_title_ckb="نهێنی AI لە کوردستان",
            grill_passed=True,
            grill_summary="0 double-cuts · -14.0 LUFS · 96% face",
        )
        item = _StubClipItem(
            rank=1,
            clip_id=cid,
            delivery_pack=pack,
            grill_passed=True,
            grill_summary=pack.grill_summary,
            hook_title_ckb=pack.hook_title_ckb,
            duration_s=41.2,
            face_share=0.96,
        )
        return _StubEpisodeResult(
            media_id="ep-01",
            source_mp4=source,
            out_dir=out_dir,
            clips=(item,),
            review_html_path=review_html,
            total_wall_s=12.4,
            all_grills_passed=True,
        )

    ep_mod = types.ModuleType("hawedit.v8.episode")
    ep_mod.V8EpisodeConfig = _StubV8EpisodeConfig  # type: ignore[attr-defined]
    ep_mod.compile_v8_episode = _fake_compile_v8_episode  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "hawedit.v8.episode", ep_mod)

    status, _, body = _http_post("/api/repurpose", _v8_payload(source_id))
    assert status == 202, body.decode("utf-8", "replace")
    reply = json.loads(body.decode("utf-8"))
    job_id = reply["job_id"]
    assert reply["engine"] == "v8"
    assert reply["events_url"] == f"/api/jobs/{job_id}/events"

    manager.run_job_sync(job_id)

    # Confirm V8EpisodeConfig received all client options accurately
    cfg = captured["config"]
    assert isinstance(cfg, _StubV8EpisodeConfig)
    assert cfg.style_preset == "crimson_punch"
    assert cfg.director == "offline"
    assert cfg.sub_engine == "skia"
    assert cfg.condense is True
    assert cfg.cold_open is True
    assert cfg.max_clips == 2
    assert cfg.brand_accent_hex == "#FF2E63"
    assert cfg.speaker_name_ckb == "هاوژین"
    assert cfg.speaker_role_ckb == "پێشکەشکار"
    assert cfg.end_card_title_ckb == "بۆ ڤیدیۆی زیاتر فۆڵۆمان بکە"
    assert cfg.end_card_handle == "@hawedit"

    # Confirm GET /api/jobs/<job_id> returns rich V8 clip metadata
    job_status, _, job_raw = _http_get(f"/api/jobs/{job_id}")
    assert job_status == 200
    job_doc = json.loads(job_raw.decode("utf-8"))
    assert job_doc["status"] == "completed"
    expected_review_url = f"/api/jobs/{job_id}/artifacts/v8/client-review.html"
    assert job_doc["review_sheet_url"] == expected_review_url
    assert len(job_doc["clips"]) == 1
    clip = job_doc["clips"][0]
    assert clip["clip_id"] == "ep-clip-01"
    assert clip["grill_passed"] is True
    assert "0 double-cuts" in clip["grill_summary"]
    assert clip["hook_title_ckb"] == "نهێنی AI لە کوردستان"
    assert clip["duration_s"] == 41.2
    assert clip["face_share"] == 0.96
    assert clip["preview_url"] == f"/api/jobs/{job_id}/clips/ep-clip-01/preview"
    assert clip["cover_url"] == f"/api/jobs/{job_id}/clips/ep-clip-01/cover.png"
    assert clip["review_sheet_url"] == expected_review_url
    assert set(clip["download_urls"]) == {
        "mp4",
        "srt",
        "edl",
        "otio",
        "director_json",
        "grill_json",
    }

    # Confirm history reader accepts persisted V8 job cleanly with zero diagnostics
    history = read_history(manager._jobs_dir)
    assert history["available"] is True
    assert history["diagnostics"] == []
    assert len(history["jobs"]) == 1

    # Confirm HEAD & GET & Range on preview endpoint
    expected_mp4 = FIXTURE_VIDEO.read_bytes()
    expected_sha = hashlib.sha256(expected_mp4).hexdigest()
    head_code, head_headers, head_body = _http_head(clip["preview_url"])
    assert head_code == 200 and head_body == b""
    assert head_headers["content-type"] == "video/mp4"
    assert head_headers["x-hawedit-artifact-state"] == "private-preview"
    assert head_headers["etag"] == f'"{expected_sha}"'

    range_code, range_headers, range_body = _http_get(
        clip["preview_url"], extra_headers="Range: bytes=0-15\r\n"
    )
    assert range_code == 206
    assert range_body == expected_mp4[:16]
    assert range_headers["content-range"].startswith("bytes 0-15/")

    # Confirm cover PNG, review sheet, and every download URL serves safely
    cover_code, cover_headers, cover_body = _http_get(clip["cover_url"])
    assert cover_code == 200
    assert cover_headers["content-type"] == "image/png"
    assert cover_body.startswith(b"\x89PNG")

    rev_code, rev_headers, rev_body = _http_get(clip["review_sheet_url"])
    assert rev_code == 200
    assert "text/html" in rev_headers["content-type"]
    assert b"Review" in rev_body

    for kind, expected_ct, expected_snippet in (
        ("mp4", "video/mp4", b"ftyp"),
        ("srt", "application/x-subrip", "سڵاو".encode()),
        ("edl", "text/plain", b"TITLE: ep-clip-01"),
        ("otio", "application/json", b"Timeline.1"),
        ("director_json", "application/json", b"hook_title_ckb"),
        ("grill_json", "application/json", b'"passed": true'),
    ):
        dl_code, dl_headers, dl_body = _http_get(clip["download_urls"][kind])
        assert dl_code == 200, kind
        assert expected_ct in dl_headers["content-type"]
        assert expected_snippet in dl_body

    # Direct allowlisted job artifact route works for valid V8 files
    direct_code, _, direct_body = _http_get(f"/api/jobs/{job_id}/artifacts/v8/ep-clip-01.v8.srt")
    assert direct_code == 200 and "سڵاو".encode() in direct_body

    # Path traversal, hidden files, forbidden extensions, and unknown kinds MUST be refused
    for bad_path in (
        f"/api/jobs/{job_id}/artifacts/../../pyproject.toml",
        f"/api/jobs/{job_id}/artifacts/..%2F..%2Fpyproject.toml",
        f"/api/jobs/{job_id}/artifacts/.env",
        f"/api/jobs/{job_id}/artifacts/v8/secret.py",
        f"/api/jobs/{job_id}/clips/ep-clip-01/artifacts/not_a_kind",
        f"/api/jobs/{job_id}/clips/..%2Foutside/cover.png",
        "/api/jobs/..%2Foutside/review.html",
    ):
        bad_code, _, _ = _http_get(bad_path)
        assert bad_code in {400, 404, 409}, f"{bad_path} unexpectedly returned {bad_code}"


@pytest.mark.parametrize(
    "bad_override",
    [
        {"style_preset": "neon_unknown"},
        {"director": "magic_ai"},
        {"sub_engine": "canvas"},
        {"condense": "yes"},
        {"cold_open": 1},
        {"max_clips": 0},
        {"max_clips": 99},
        {"max_clips": True},
        {"brand_accent_hex": "gold"},
        {"brand_accent_hex": "#123"},
        {"transcript_path": "notes.txt"},
        {"transcript_path": "/etc/secret.json"},
        {"use_omni_asr": "true"},
        {"unknown_v8_flag": 1},
    ],
)
def test_v8_repurpose_strictly_rejects_invalid_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad_override: dict[str, Any]
) -> None:
    monkeypatch.delenv("HAWEDIT_PROTECTED_STUDIO", raising=False)
    store, source_id = _upload_fixture(tmp_path)
    manager = web.JobManager(tmp_path / "jobs")
    monkeypatch.setattr(web, "UPLOAD_STORE", store)
    monkeypatch.setattr(web, "JOB_MANAGER", manager)

    status, _, body = _http_post("/api/repurpose", _v8_payload(source_id, **bad_override))
    assert status == 400, f"Expected 400 for {bad_override}, got {status}: {body!r}"
    assert manager.get_all_jobs() == []


def test_v8_repurpose_respects_protected_studio_and_fails_loud_on_compiler_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, source_id = _upload_fixture(tmp_path)
    manager = web.JobManager(tmp_path / "jobs")
    monkeypatch.setattr(web, "UPLOAD_STORE", store)
    monkeypatch.setattr(web, "JOB_MANAGER", manager)

    # 1. Protected studio returns 503 and queues nothing
    monkeypatch.setenv("HAWEDIT_PROTECTED_STUDIO", "1")
    code503, _, body503 = _http_post("/api/repurpose", _v8_payload(source_id))
    assert code503 == 503
    assert json.loads(body503.decode("utf-8"))["code"] == "studio_runner_unavailable"
    assert manager.get_all_jobs() == []

    # 2. When V8 compiler raises, job fails loudly (zero silent fallback)
    monkeypatch.delenv("HAWEDIT_PROTECTED_STUDIO", raising=False)
    monkeypatch.setattr(manager, "_start_worker", lambda _jid: None)
    broken_ep = types.ModuleType("hawedit.v8.episode")
    broken_ep.V8EpisodeConfig = _StubV8EpisodeConfig  # type: ignore[attr-defined]

    def _fail_compile(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("WSL OmniASR offline on 127.0.0.1:8000")

    broken_ep.compile_v8_episode = _fail_compile  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "hawedit.v8.episode", broken_ep)

    code202, _, body202 = _http_post("/api/repurpose", _v8_payload(source_id))
    assert code202 == 202
    job_id = json.loads(body202.decode("utf-8"))["job_id"]
    manager.run_job_sync(job_id)

    failed_job = manager.get_job(job_id)
    assert failed_job is not None
    assert failed_job["status"] == "failed"
    assert "WSL OmniASR offline" in str(failed_job["error"])


def test_v8_repurpose_accepts_top_level_engine_and_legacy_engine_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HAWEDIT_PROTECTED_STUDIO", raising=False)
    store, source_id = _upload_fixture(tmp_path)
    manager = web.JobManager(tmp_path / "jobs")
    monkeypatch.setattr(web, "UPLOAD_STORE", store)
    monkeypatch.setattr(web, "JOB_MANAGER", manager)
    monkeypatch.setattr(manager, "_start_worker", lambda _jid: None)

    # Top-level engine="v8" + top-level style_preset works
    top_v8 = {
        "schema": 1,
        "source_id": source_id,
        "client_token": "v8-top-level-token-01",
        "engine": "v8",
        "style_preset": "broadcast_news",
        "director": "gemini",
        "max_clips": 3,
    }
    code, _, raw = _http_post("/api/repurpose", top_v8)
    assert code == 202, raw.decode("utf-8", "replace")
    jid = json.loads(raw.decode("utf-8"))["job_id"]
    job = manager.get_job(jid)
    assert job is not None
    assert job["options"]["engine"] == "v8"
    assert job["options"]["style_preset"] == "broadcast_news"
    assert job["options"]["director"] == "gemini"

    # Explicit engine="legacy" delegates cleanly to legacy GenerationRequest
    legacy_req = {
        "schema": 1,
        "source_id": source_id,
        "client_token": "legacy-explicit-token-01",
        "engine": "legacy",
        "options": {"preset": "viral", "max_clips": 3},
    }
    l_code, _, l_raw = _http_post("/api/repurpose", legacy_req)
    assert l_code == 202, l_raw.decode("utf-8", "replace")
    l_jid = json.loads(l_raw.decode("utf-8"))["job_id"]
    l_job = manager.get_job(l_jid)
    assert l_job is not None
    assert l_job["options"].get("engine") is None
    assert l_job["options"]["preset"] == "viral"


def test_studio_ui_html_exposes_all_v8_controls_health_strip_and_grill_badges() -> None:
    doc = markup()
    # All element IDs remain strictly unique
    ids = [attrs["id"] for _, attrs in doc.elements if "id" in attrs]
    assert len(ids) == len(set(ids))

    # V8 Preflight Health Strip
    assert doc.element("v8HealthStrip")[0] == "div"
    assert "api('/api/v8/doctor')" in DASHBOARD_HTML
    assert "GPU / NVENC" in DASHBOARD_HTML
    assert "Skia + HarfBuzz" in DASHBOARD_HTML
    assert "WSL ASR" in DASHBOARD_HTML

    # V8 Creative Director Controls
    assert doc.element("optEngine")[0] == "select"
    assert '<option value="v8" selected>' in DASHBOARD_HTML
    assert doc.element("stylePresetGrid")[0] == "div"
    assert "api('/api/v8/presets')" in DASHBOARD_HTML
    for preset_name in (
        "viral_gold",
        "crimson_punch",
        "executive_cyan",
        "luxury_minimal",
        "broadcast_news",
    ):
        assert preset_name in DASHBOARD_HTML
    assert doc.element("optDirector")[0] == "select"
    assert doc.element("optSubEngine")[0] == "select"
    assert doc.element("optCondense")[1]["type"] == "checkbox"
    assert doc.element("optColdOpen")[1]["type"] == "checkbox"

    # Collapsible Client Brand Kit
    assert doc.element("clientBrandKit")[0] == "details"
    assert "open" not in doc.element("clientBrandKit")[1]
    for brand_id in (
        "optBrandAccent",
        "optSpeakerName",
        "optSpeakerRole",
        "optEndCardTitle",
        "optEndCardHandle",
    ):
        assert doc.element(brand_id)[0] == "input"

    # Clip results forensic badges, cover thumbnail, and agency downloads
    assert doc.element("grillBadge")[0] == "span"
    assert doc.element("clipCoverImg")[0] == "img"
    assert doc.element("clipDownloads")[0] == "div"
    assert "GRILL PASSED ✓" in DASHBOARD_HTML
    assert "GRILL FAILED" in DASHBOARD_HTML
    for label in ("'MP4'", "'SRT'", "'EDL'", "'OTIO'", "'Cover'", "'Review Sheet'"):
        assert label in DASHBOARD_HTML

    # Security & offline invariants preserved
    assert "innerHTML" not in DASHBOARD_HTML
    assert "setInterval" not in DASHBOARD_HTML


def test_v9_audit_fixes_review_links_restart_history_etag_and_security(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regressions for ponytail-audit #1, #2, #4, #6, #8, #9, #10, #15."""
    monkeypatch.delenv("HAWEDIT_PROTECTED_STUDIO", raising=False)
    store, source_id = _upload_fixture(tmp_path)

    # Fix #9: create_dir=False does not create missing folders on init
    lazy_dir = tmp_path / "never_created_on_init"
    _lazy_mgr = web.JobManager(lazy_dir, create_dir=False)
    assert not lazy_dir.exists()

    manager = web.JobManager(tmp_path / "jobs")
    monkeypatch.setattr(web, "UPLOAD_STORE", store)
    monkeypatch.setattr(web, "JOB_MANAGER", manager)
    monkeypatch.setattr(manager, "_start_worker", lambda _jid: None)

    # Fix #2: even a real existing .json file on disk is refused as transcript_path
    secret_json = tmp_path / "secret.json"
    secret_json.write_text('{"secret": true}', encoding="utf-8")
    code400, _, body400 = _http_post(
        "/api/repurpose", _v8_payload(source_id, transcript_path=str(secret_json))
    )
    assert code400 == 400
    assert "transcript_path" in json.loads(body400.decode("utf-8"))["error"]

    # Run a V8 job emitting progress + real relative links in client-review.html
    progress_seen: list[tuple[str, str, int]] = []

    def _fake_compile_with_progress(
        source: Path,
        out_dir: Path,
        *,
        transcript_path: Path | None = None,
        use_omni_asr: bool = False,
        config: _StubV8EpisodeConfig | None = None,
        on_progress: Any = None,
    ) -> _StubEpisodeResult:
        assert transcript_path is None
        if callable(on_progress):
            on_progress("v8_clip_1_of_1", "started", 40)
            progress_seen.append(("v8_clip_1_of_1", "started", 40))
        out_dir.mkdir(parents=True, exist_ok=True)
        cid = "ep-clip-01"
        mp4 = out_dir / f"{cid}.v8.mp4"
        srt = out_dir / f"{cid}.v8.srt"
        edl = out_dir / f"{cid}.v8.edl"
        otio = out_dir / f"{cid}.v8.otio"
        cover = out_dir / f"{cid}.v8.cover.png"
        director_json = out_dir / f"{cid}.director.json"
        grill_json = out_dir / f"{cid}.grill.json"
        review_html = out_dir / "client-review.html"

        mp4.write_bytes(FIXTURE_VIDEO.read_bytes())
        srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nسڵاو\n", encoding="utf-8")
        edl.write_text("TITLE: ep-clip-01\n", encoding="utf-8")
        otio.write_text('{"OTIO_SCHEMA": "Timeline.1"}', encoding="utf-8")
        cover.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        director_json.write_text('{"clip_id": "ep-clip-01"}', encoding="utf-8")
        grill_json.write_text('{"passed": true}', encoding="utf-8")
        review_html.write_text(
            "<!DOCTYPE html><html><head><title>Review</title></head><body>"
            f'<video poster="{cid}.v8.cover.png"><source src="{cid}.v8.mp4"></video>'
            f'<a href="{cid}.v8.srt">SRT</a></body></html>',
            encoding="utf-8",
        )
        if callable(on_progress):
            on_progress("v8_clip_1_of_1", "completed", 90)
            progress_seen.append(("v8_clip_1_of_1", "completed", 90))
        pack = _StubDeliveryPack(
            clip_id=cid,
            mp4_path=mp4,
            srt_path=srt,
            edl_path=edl,
            otio_path=otio,
            cover_png_path=cover,
            director_json_path=director_json,
            grill_json_path=grill_json,
            duration_ms=32000,
            face_share=0.98,
            hook_title_ckb="سەردێڕی تاقیکاری",
            grill_passed=True,
            grill_summary="PASSED",
        )
        item = _StubClipItem(
            rank=1,
            clip_id=cid,
            delivery_pack=pack,
            grill_passed=True,
            grill_summary="PASSED",
            hook_title_ckb="سەردێڕی تاقیکاری",
            duration_s=32.0,
            face_share=0.98,
        )
        return _StubEpisodeResult(
            media_id="ep-01",
            source_mp4=source,
            out_dir=out_dir,
            clips=(item,),
            review_html_path=review_html,
            total_wall_s=2.0,
            all_grills_passed=True,
        )

    ep_mod = types.ModuleType("hawedit.v8.episode")
    ep_mod.V8EpisodeConfig = _StubV8EpisodeConfig  # type: ignore[attr-defined]
    ep_mod.compile_v8_episode = _fake_compile_with_progress  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "hawedit.v8.episode", ep_mod)

    status, _, body = _http_post("/api/repurpose", _v8_payload(source_id))
    assert status == 202
    job_id = json.loads(body.decode("utf-8"))["job_id"]
    manager.run_job_sync(job_id)

    # Fix #10: intermediate clip progress callback invoked
    assert len(progress_seen) == 2

    # Fix #1: review_sheet_url resolves relative links to HTTP 200; /review.html injects <base>
    rev_url = f"/api/jobs/{job_id}/artifacts/v8/client-review.html"
    r_code, _, r_body = _http_get(rev_url)
    assert r_code == 200 and b"ep-clip-01.v8.mp4" in r_body
    rel_mp4_code, _, _ = _http_get(f"/api/jobs/{job_id}/artifacts/v8/ep-clip-01.v8.mp4")
    rel_cov_code, _, _ = _http_get(f"/api/jobs/{job_id}/artifacts/v8/ep-clip-01.v8.cover.png")
    assert rel_mp4_code == 200 and rel_cov_code == 200

    legacy_rev_code, _, legacy_rev_body = _http_get(f"/api/jobs/{job_id}/review.html")
    assert legacy_rev_code == 200
    assert f'<base href="/api/jobs/{job_id}/artifacts/v8/">'.encode() in legacy_rev_body

    # Fix #8: Range requests populate & reuse _V8_ETAG_CACHE
    web._V8_ETAG_CACHE.clear()
    preview_url = f"/api/jobs/{job_id}/clips/ep-clip-01/preview"
    c1, h1, _ = _http_get(preview_url, extra_headers="Range: bytes=0-15\r\n")
    assert c1 == 206 and len(web._V8_ETAG_CACHE) == 1
    c2, h2, _ = _http_get(preview_url, extra_headers="Range: bytes=16-31\r\n")
    assert c2 == 206 and h1["etag"] == h2["etag"]

    # Fix #4: Simulate server restart; historical V8 job retains UI links
    restarted = web.JobManager(tmp_path / "jobs")
    monkeypatch.setattr(web, "JOB_MANAGER", restarted)
    assert not restarted.is_live_job(job_id)

    h_code, _, h_raw = _http_get(f"/api/jobs/{job_id}")
    assert h_code == 200
    hist = json.loads(h_raw.decode("utf-8"))
    assert hist["historical"] is True
    assert hist["review_sheet_url"] == rev_url
    hclip = hist["clips"][0]
    assert hclip["cover_url"] == f"/api/jobs/{job_id}/clips/ep-clip-01/cover.png"
    assert hclip["grill_passed"] is True
    assert hclip["face_share"] == 0.98
    assert hclip["duration_s"] == 32.0
    assert set(hclip["download_urls"]) >= {"mp4", "srt", "edl", "otio"}

    # Preview still works after restart even if job is absent from in-memory _jobs
    restarted._jobs.clear()
    p_code, _, _ = _http_head(preview_url)
    assert p_code == 200

    # Fix #6: Persisted "running" job reloads as "interrupted" without modifying disk bytes
    zombie_dir = tmp_path / "jobs" / "zombie-job-01"
    zombie_dir.mkdir(parents=True)
    zombie_file = zombie_dir / "job.json"
    zombie_payload = {
        "job_id": "zombie-job-01",
        "source": str(FIXTURE_VIDEO),
        "status": "running",
        "stage": "stage0_ingest",
        "stage_index": 0,
        "progress_percent": 15,
        "created_at": 100.0,
        "updated_at": 100.0,
        "headline": "test",
        "clips": [],
        "error": None,
        "client_token": "zombie-token-0001",
        "options": {},
    }
    zombie_file.write_text(json.dumps(zombie_payload), encoding="utf-8")
    before_bytes = zombie_file.read_bytes()
    reloaded = web.JobManager(tmp_path / "jobs")
    zjob = reloaded.get_job("zombie-job-01")
    assert zjob is not None and zjob["status"] == "interrupted"
    assert zombie_file.read_bytes() == before_bytes

    # Fix #15: _prune_completed_locked bounds completed in-memory jobs to cap
    monkeypatch.setattr(web, "_MAX_IN_MEMORY_COMPLETED_JOBS", 2)
    with reloaded._lock:
        for i in range(5):
            jid = f"done-{i}"
            reloaded._jobs[jid] = web.JobInfo(
                job_id=jid,
                source="x.mp4",
                status="completed",
                stage="delivery",
                stage_index=6,
                progress_percent=100,
                created_at=float(i),
                updated_at=float(i),
                headline="h",
            )
            reloaded._events[jid] = [{"seq": 1, "event": "completed", "data": {}}]
        reloaded._prune_completed_locked()
        remaining = [
            jid for jid, info in reloaded._jobs.items() if info.status not in {"queued", "running"}
        ]
        assert len(remaining) == 2
        assert len(reloaded._events) <= 2
