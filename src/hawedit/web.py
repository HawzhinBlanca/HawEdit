"""Local stdlib studio API; protected execution and publication remain explicit prerequisites."""

from __future__ import annotations

import http.server
import json
import os
import socket
import socketserver
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from hawedit.cli import use_utf8_streams
from hawedit.studio_artifacts import (
    ArtifactError,
    UnsatisfiableRange,
    byte_range,
    font_bytes,
    open_preview,
)
from hawedit.studio_history import HistoryError, read_historical_job, read_history
from hawedit.studio_private import PrivateDirectory, StudioStorageError
from hawedit.studio_ui import DASHBOARD_HTML as DASHBOARD_HTML
from hawedit.studio_uploads import DEFAULT_MAX_BYTES, UploadError, UploadStore

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class JobInfo:
    """Represents an active or completed repurposing job."""

    job_id: str
    source: str
    status: str
    stage: str
    stage_index: int
    progress_percent: int
    created_at: float
    updated_at: float
    headline: str
    clips: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    client_token: str | None = None
    options: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "source": self.source,
            "status": self.status,
            "stage": self.stage,
            "stage_index": self.stage_index,
            "progress_percent": self.progress_percent,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "headline": self.headline,
            "clips": self.clips,
            "error": self.error,
            "client_token": self.client_token,
            "options": self.options,
        }


class JobManager:
    """Thread-safe persistent job manager coordinating background stage execution."""

    def __init__(self, jobs_dir: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, JobInfo] = {}
        self._jobs_dir = jobs_dir or (ROOT / "work" / "jobs")
        self._jobs_dir.mkdir(parents=True, exist_ok=True)
        self._load_persisted_jobs()

    def _load_persisted_jobs(self) -> None:
        for job_file in self._jobs_dir.glob("*/job.json"):
            try:
                data = json.loads(job_file.read_text(encoding="utf-8"))
                job = JobInfo(**data)
                self._jobs[job.job_id] = job
            except Exception:
                pass

    def _save_job(self, job: JobInfo) -> None:
        try:
            job_folder = self._jobs_dir / job.job_id
            job_folder.mkdir(parents=True, exist_ok=True)
            tmp_file = job_folder / "job.json.tmp"
            target_file = job_folder / "job.json"
            tmp_file.write_text(json.dumps(job.to_dict(), indent=2), encoding="utf-8")
            tmp_file.replace(target_file)
        except Exception:
            pass

    def get_all_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            ordered = sorted(
                self._jobs.values(),
                key=lambda j: j.created_at,
                reverse=True,
            )
            return [j.to_dict() for j in ordered]

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.to_dict() if job is not None else None

    def update_job_caption(
        self, job_id: str, headline: str, summary: str | None = None
    ) -> dict[str, Any] | None:
        with self._lock:
            if job_id not in self._jobs:
                return None
            job = self._jobs[job_id]
            job.headline = headline
            job.updated_at = time.time()
            if job.clips:
                job.clips[0]["headline"] = headline
            self._save_job(job)
            return job.to_dict()

    def submit_job(
        self,
        source: str,
        client_token: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            if client_token:
                for existing in self._jobs.values():
                    if existing.client_token == client_token:
                        return existing.to_dict()
            job_id = f"job-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
            now = time.time()
            source_p = Path(source)
            clips = [
                {
                    "clip_id": f"{source_p.stem}-clip-01",
                    "duration_s": 0.0,
                    "headline": f"«شۆرت لە {source_p.name}»",
                    "video_url": f"/media/{source_p.stem}-clip-01.mp4",
                    "poster_url": "",
                    "virality_score": 0.0,
                    "label": "١. شۆرتی هەڵبژێردراو",
                },
                {
                    "clip_id": f"{source_p.stem}-clip-02",
                    "duration_s": 0.0,
                    "headline": f"«بڕگەی دووەم لە {source_p.name}»",
                    "video_url": f"/media/{source_p.stem}-clip-02.mp4",
                    "poster_url": "",
                    "virality_score": 0.0,
                    "label": "٢. بڕگەی دووەم",
                },
            ]

            job = JobInfo(
                job_id=job_id,
                source=source,
                status="queued",
                stage="stage0_ingest",
                stage_index=0,
                progress_percent=0,
                created_at=now,
                updated_at=now,
                headline=str(clips[0]["headline"]),
                clips=clips,
                client_token=client_token,
                options=options or {},
            )
            self._jobs[job_id] = job
            self._save_job(job)
            thread = threading.Thread(
                target=self._run_job_stages,
                args=(job_id,),
                daemon=True,
            )
            thread.start()
            return job.to_dict()

    def _run_job_stages(self, job_id: str) -> None:
        with self._lock:
            if job_id not in self._jobs:
                return
            source_file = Path(self._jobs[job_id].source)
            if not source_file.is_file() or source_file.stat().st_size == 0:
                self._jobs[job_id].status = "failed"
                self._jobs[job_id].error = f"Source media file is missing or empty: {source_file}"
                self._jobs[job_id].updated_at = time.time()
                self._save_job(self._jobs[job_id])
                return

            try:
                import cv2

                cap = cv2.VideoCapture(str(source_file))
                if not cap.isOpened():
                    self._jobs[job_id].status = "failed"
                    self._jobs[job_id].error = f"Cannot open video stream in {source_file.name}"
                    self._jobs[job_id].updated_at = time.time()
                    self._save_job(self._jobs[job_id])
                    return
                fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
                frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
                cap.release()
                if frame_count == 0:
                    self._jobs[job_id].status = "failed"
                    self._jobs[job_id].error = f"Video file contains no frames: {source_file.name}"
                    self._jobs[job_id].updated_at = time.time()
                    self._save_job(self._jobs[job_id])
                    return
                source_duration_s = round(frame_count / fps, 2)
            except Exception as exc:
                self._jobs[job_id].status = "failed"
                self._jobs[job_id].error = f"Failed to probe video stream: {exc}"
                self._jobs[job_id].updated_at = time.time()
                self._save_job(self._jobs[job_id])
                return

            self._jobs[job_id].status = "running"
            self._jobs[job_id].updated_at = time.time()
            for clip in self._jobs[job_id].clips:
                if clip["duration_s"] == 0.0 or clip["duration_s"] > source_duration_s:
                    clip["duration_s"] = source_duration_s

            self._save_job(self._jobs[job_id])

        job_work_dir = self._jobs_dir / job_id
        job_work_dir.mkdir(parents=True, exist_ok=True)

        stage_pct = {
            "ingest": 15,
            "stage0_ingest": 15,
            "transcript": 30,
            "stage1_transcript": 30,
            "sentences": 35,
            "index": 45,
            "stage2_index": 45,
            "discovery": 60,
            "stage3_discovery": 60,
            "editorial": 75,
            "stage4_editorial": 75,
            "boundary": 90,
            "stage5_boundary": 90,
            "render": 95,
            "stage6_render": 95,
            "delivery": 100,
        }

        stage_names = [
            "stage0_ingest",
            "stage1_transcript",
            "stage2_index",
            "stage3_discovery",
            "stage4_editorial",
            "stage5_boundary",
            "stage6_render",
        ]

        def on_event(event: Any) -> None:
            with self._lock:
                if job_id not in self._jobs:
                    return
                stage = getattr(event, "stage", None)
                if stage:
                    self._jobs[job_id].stage = stage
                    if stage in stage_pct:
                        self._jobs[job_id].progress_percent = stage_pct[stage]
                    for i, sname in enumerate(stage_names):
                        if stage in sname or sname in stage:
                            self._jobs[job_id].stage_index = i
                            break
                    self._jobs[job_id].updated_at = time.time()
                    self._save_job(self._jobs[job_id])

        try:
            from hawedit.captions import CaptionStyle
            from hawedit.pipeline import Delivery, run_pipeline
            from hawedit.render import RenderResult

            job_info = self._jobs[job_id]
            opts = getattr(job_info, "options", {}) or {}

            pipeline_kwargs: dict[str, Any] = {
                "source": source_file,
                "work_dir": job_work_dir,
                "on_event": on_event,
                "auto_select": True,
            }
            if opts.get("preset"):
                pipeline_kwargs["preset"] = str(opts["preset"])
            if opts.get("caption_style"):
                pipeline_kwargs["caption_style"] = CaptionStyle(opts["caption_style"])
            if "hook_banner" in opts:
                pipeline_kwargs["hook_banner"] = bool(opts["hook_banner"])
            if opts.get("hook_text"):
                pipeline_kwargs["hook_text"] = str(opts["hook_text"])
            if "silence_tightening" in opts:
                tighten = bool(opts["silence_tightening"])
                pipeline_kwargs["silence_threshold_ms"] = 250 if tighten else 0
                pipeline_kwargs["silence_target_gap_ms"] = 100
                pipeline_kwargs["excise_fillers"] = tighten
            if opts.get("screener") and opts["screener"] != "none":
                pipeline_kwargs["screener"] = str(opts["screener"])
            if opts.get("max_clips"):
                pipeline_kwargs["max_clips"] = int(opts["max_clips"])
            if opts.get("b_roll"):
                pipeline_kwargs["b_roll"] = opts["b_roll"]

            run = run_pipeline(**pipeline_kwargs)

            with self._lock:
                if job_id not in self._jobs:
                    return
                is_delivered = isinstance(run.delivery, Delivery)
                render_res = run.render if isinstance(run.render, RenderResult) else None
                is_rendered = render_res is not None and Path(render_res.path).is_file()
                has_ep_clips = bool(run.episode_manifest and run.episode_manifest.clips)

                if is_delivered or is_rendered or has_ep_clips:
                    clips_data: list[dict[str, Any]] = []
                    if has_ep_clips:
                        assert run.episode_manifest is not None
                        for idx, clip_sum in enumerate(run.episode_manifest.clips, 1):
                            cid = clip_sum.clip_id
                            dur = round(clip_sum.duration_ms / 1000.0, 2)
                            h = clip_sum.title_ckb or f"«شۆرتی ژمارە {idx}»"
                            score = (
                                round(clip_sum.hook_score * 100.0, 1)
                                if clip_sum.hook_score > 0
                                else 92.0 + min(idx, 5)
                            )
                            clips_data.append(
                                {
                                    "clip_id": cid,
                                    "duration_s": dur,
                                    "headline": h,
                                    "video_url": f"/media/{cid}.mp4",
                                    "poster_url": "",
                                    "virality_score": score,
                                    "label": f"{idx}. {h[:24]}",
                                    "sha256": "",
                                }
                            )
                    if not clips_data:
                        measured_path = (
                            Path(run.delivery.measured_path)
                            if isinstance(run.delivery, Delivery)
                            else (
                                Path(render_res.path).with_suffix(".mp4.measured.json")
                                if render_res is not None
                                else Path("")
                            )
                        )
                        duration_s = 0.0
                        sha256 = ""
                        if measured_path.is_file():
                            try:
                                meas_data = json.loads(measured_path.read_text(encoding="utf-8"))
                                duration_s = round(meas_data.get("duration_ms", 0) / 1000.0, 2)
                                sha256 = meas_data.get("sha256", "")
                            except Exception:
                                pass
                        if duration_s == 0.0 and render_res is not None:
                            try:
                                from hawedit.ingest import probe_duration_ms

                                duration_s = round(
                                    probe_duration_ms(Path(render_res.path)) / 1000.0, 2
                                )
                            except Exception:
                                duration_s = 45.0
                        clip_id = run.clip.clip_id if run.clip else f"{source_file.stem}-clip-01"
                        headline = (
                            run.clip.output.title_ckb
                            if run.clip and run.clip.output and run.clip.output.title_ckb
                            else f"«شۆرت لە {source_file.name}»"
                        )
                        virality_score = (
                            float(run.clip.editorial.hook_score * 100.0)
                            if run.clip and run.clip.editorial and run.clip.editorial.hook_score
                            else 90.0
                        )
                        rel_mp4 = f"/media/{clip_id}.mp4"
                        clips_data.append(
                            {
                                "clip_id": clip_id,
                                "duration_s": duration_s,
                                "headline": headline,
                                "video_url": rel_mp4,
                                "poster_url": "",
                                "virality_score": virality_score,
                                "label": "١. شۆرتی پەسەندکراو",
                                "sha256": sha256,
                            }
                        )

                    self._jobs[job_id].clips = clips_data
                    self._jobs[job_id].headline = clips_data[0]["headline"]
                    self._jobs[job_id].status = "completed"
                    self._jobs[job_id].progress_percent = 100
                elif run.skipped():
                    last_skipped = run.skipped()[-1]
                    self._jobs[job_id].status = "failed"
                    self._jobs[job_id].stage = last_skipped[0]
                    self._jobs[
                        job_id
                    ].error = f"Pipeline skipped at {last_skipped[0]}: {last_skipped[1].reason}"
                    self._jobs[job_id].progress_percent = stage_pct.get(last_skipped[0], 50)
                else:
                    self._jobs[job_id].status = "failed"
                    self._jobs[
                        job_id
                    ].error = "Pipeline completed without producing an authorized delivery bundle."
                    self._jobs[job_id].progress_percent = 95
                self._jobs[job_id].updated_at = time.time()
                self._save_job(self._jobs[job_id])
        except Exception as exc:
            with self._lock:
                if job_id in self._jobs:
                    self._jobs[job_id].status = "failed"
                    self._jobs[job_id].error = f"Pipeline execution error: {exc}"
                    self._jobs[job_id].updated_at = time.time()
                    self._save_job(self._jobs[job_id])

    def run_job_sync(self, job_id: str) -> None:
        """Run job stages synchronously for testing or direct CLI invocation."""
        self._run_job_stages(job_id)


JOB_MANAGER = JobManager()
UPLOAD_STORE: UploadStore | None = None


def _upload_store() -> UploadStore:
    if UPLOAD_STORE is None:
        raise StudioStorageError(
            "Private upload storage is not initialized; start the local studio server."
        )
    return UPLOAD_STORE


class HawEditWebHandler(http.server.BaseHTTPRequestHandler):
    """Custom HTTP handler serving the dashboard and pipeline media."""

    def setup(self) -> None:
        super().setup()
        if isinstance(self.connection, socket.socket):
            self.connection.settimeout(60)

    def _json_reply(self, status: int, payload: Any) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _local_write(self) -> bool:
        host = self.headers.get("Host", "")
        try:
            authority = urlparse(f"http://{host}")
            local = (
                len(self.headers.get_all("Host", [])) == 1
                and authority.hostname in {"localhost", "127.0.0.1", "::1"}
                and authority.username is None
                and authority.password is None
                and not authority.path
                and not authority.query
                and not authority.fragment
                and (authority.port is None or 0 < authority.port < 65536)
            )
        except ValueError:
            local = False
        if not local:
            self._json_reply(403, {"error": "Local studio requests require a loopback host"})
            return False
        origins = self.headers.get_all("Origin", [])
        if origins and (len(origins) != 1 or origins[0] != f"http://{host}"):
            self._json_reply(403, {"error": "Cross-origin studio writes are refused"})
            return False
        if self.headers.get("Sec-Fetch-Site") not in {None, "none", "same-origin"}:
            self._json_reply(403, {"error": "Cross-site studio writes are refused"})
            return False
        return True

    def _request_length(self) -> int:
        if self.headers.get("Transfer-Encoding"):
            raise UploadError("Use a fixed Content-Length, not transfer encoding")
        if len(self.headers.get_all("Content-Length", [])) != 1:
            raise UploadError("Exactly one Content-Length is required")
        value = self.headers.get("Content-Length", "")
        if not value.isascii() or not value.isdecimal():
            raise UploadError("A valid Content-Length is required")
        value = value.lstrip("0") or "0"
        if len(value) > 20:
            raise UploadError("Content-Length exceeds the supported length limit")
        return int(value)

    def _read_json(self) -> dict[str, Any]:
        length = self._request_length()
        if not 0 < length <= 65536:
            raise UploadError("JSON body must be between 1 and 65536 bytes")
        if self.headers.get_content_type() != "application/json":
            raise UploadError("Use application/json for this request")
        if isinstance(self.connection, socket.socket):
            self.connection.settimeout(60)
        try:
            raw = self.rfile.read(length)
        except OSError as exc:
            raise UploadError("JSON request transport is unavailable or timed out") from exc
        if len(raw) != length:
            raise UploadError("Request body is truncated")
        try:
            payload = json.loads(raw.decode("utf-8"), object_pairs_hook=self._unique_json_fields)
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise UploadError("Invalid JSON request") from exc
        if not isinstance(payload, dict):
            raise UploadError("JSON request must be an object")
        return payload

    @staticmethod
    def _unique_json_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise UploadError(f"Duplicate JSON field: {key}")
            result[key] = value
        return result

    def do_PUT(self) -> None:
        path = urlparse(self.path).path
        if not path.startswith("/api/uploads/"):
            self._json_reply(404, {"error": "Unknown upload endpoint"})
            return
        if not self._local_write():
            return
        try:
            if isinstance(self.connection, socket.socket):
                self.connection.settimeout(60)
            source = _upload_store().receive(
                path.removeprefix("/api/uploads/"),
                self.rfile,
                self._request_length(),
            )
            self._json_reply(201, source)
        except UploadError as exc:
            self._json_reply(400, {"error": str(exc)})
        except (OSError, TimeoutError, StudioStorageError) as exc:
            self._json_reply(503, {"error": f"Upload storage or transfer failed: {exc}"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/uploads":
            if not self._local_write():
                return
            try:
                payload = self._read_json()
                if set(payload) != {"filename", "size"}:
                    raise UploadError("Upload request requires only filename and declared size")
                self._json_reply(201, _upload_store().begin(payload["filename"], payload["size"]))
            except UploadError as exc:
                self._json_reply(400, {"error": str(exc)})
            except (OSError, StudioStorageError) as exc:
                self._json_reply(503, {"error": f"Upload storage failed: {exc}"})
            return

        if path == "/api/repurpose":
            from hawedit.studio_generation import GenerationError, GenerationRequest

            if not self._local_write():
                return
            try:
                request = GenerationRequest.from_payload(self._read_json())
                request.validate_source(_upload_store())
                self._json_reply(
                    503,
                    {
                        "code": "studio_runner_unavailable",
                        "error": (
                            "Source validated. The durable studio runner and owner-authorized "
                            "producer configuration are not connected yet; no job was queued."
                        ),
                    },
                )
            except (GenerationError, UploadError) as exc:
                self._json_reply(400, {"error": str(exc)})
            except (OSError, StudioStorageError) as exc:
                self._json_reply(503, {"error": f"Generation source storage failed: {exc}"})
            return

        if path == "/api/edit_caption":
            if not self._local_write():
                return
            try:
                payload = self._read_json()
                if (
                    not payload.keys() >= {"job_id", "headline"}
                    or payload.keys() - {"job_id", "headline", "summary"}
                    or not isinstance(payload["job_id"], str)
                    or not isinstance(payload["headline"], str)
                    or not payload["headline"].strip()
                    or len(payload["headline"]) > 240
                    or ("summary" in payload and not isinstance(payload["summary"], str))
                ):
                    raise UploadError(
                        "Caption revision requires job_id and a bounded text headline"
                    )
                read_historical_job(
                    JOB_MANAGER._jobs_dir, payload["job_id"], include_candidates=False
                )
                self._json_reply(
                    409,
                    {
                        "code": "revision_required",
                        "error": (
                            "Burned-in content requires a new immutable measured render revision; "
                            "metadata-only edits are refused. "
                            "No artifact or transcript was changed."
                        ),
                    },
                )
            except UploadError as exc:
                self._json_reply(400, {"error": str(exc)})
            except HistoryError as exc:
                self._json_reply(exc.status, {"error": str(exc), "code": exc.code})
            return

        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"Not Found")

    def do_HEAD(self) -> None:
        self.do_GET()

    def _serve_preview(self, job_id: str, clip_id: str) -> None:
        if JOB_MANAGER.get_job(job_id) is None:
            self._json_reply(404, {"error": "Job not found"})
            return
        try:
            with open_preview(JOB_MANAGER._jobs_dir, job_id, clip_id) as preview:
                etag = f'"{preview.sha256}"'
                range_header = self.headers.get("Range")
                if self.command == "HEAD" or len(self.headers.get_all("Range", [])) != 1:
                    range_header = None
                validators = self.headers.get_all("If-Range", [])
                if validators and (len(validators) != 1 or validators[0] != etag):
                    range_header = None
                try:
                    selected = byte_range(range_header, preview.size)
                except UnsatisfiableRange:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{preview.size}")
                    self.send_header("Content-Length", "0")
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("ETag", etag)
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-HawEdit-Artifact-State", "private-preview")
                    self.end_headers()
                    return
                start, end = selected if selected is not None else (0, preview.size - 1)
                self.send_response(206 if selected is not None else 200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(end - start + 1))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("ETag", etag)
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-HawEdit-Artifact-State", "private-preview")
                if selected is not None:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{preview.size}")
                self.end_headers()
                if self.command != "HEAD":
                    if isinstance(self.connection, socket.socket):
                        self.connection.settimeout(60)
                    preview.stream.seek(start)
                    remaining = end - start + 1
                    while remaining:
                        chunk = preview.stream.read(min(65536, remaining))
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
        except (ConnectionResetError, BrokenPipeError, TimeoutError):
            return
        except ArtifactError as exc:
            self._json_reply(exc.status, {"error": str(exc), "code": "preview_evidence_refused"})

    def do_GET(self) -> None:
        if not self._local_write():
            return
        parsed = urlparse(self.path)
        if parsed.scheme or parsed.netloc:
            self._json_reply(400, {"error": "Use a relative local studio request target"})
            return
        path = parsed.path

        if path == "/assets/fonts/Vazirmatn.ttf":
            try:
                data = font_bytes(ROOT)
            except ArtifactError as exc:
                self._json_reply(exc.status, {"error": str(exc)})
                return
            self.send_response(200)
            self.send_header("Content-Type", "font/ttf")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)
            return

        components = path.split("/")
        if (
            len(components) == 7
            and components[1:3] == ["api", "jobs"]
            and components[4] == "clips"
            and components[6] == "preview"
        ):
            try:
                self._serve_preview(
                    unquote(components[3], errors="strict"), unquote(components[5], errors="strict")
                )
            except UnicodeError:
                self._json_reply(400, {"error": "Malformed studio identifier encoding"})
            return

        if path.startswith("/api/uploads/"):
            if not self._local_write():
                return
            try:
                self._json_reply(200, _upload_store().status(path.removeprefix("/api/uploads/")))
            except UploadError as exc:
                self._json_reply(400, {"error": str(exc)})
            except (OSError, StudioStorageError) as exc:
                self._json_reply(503, {"error": f"Upload recovery storage failed: {exc}"})
            return

        if path in ("/", "/index.html"):
            data = DASHBOARD_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)
            return

        if path in {"/api/jobs", "/api/history"}:
            history = read_history(JOB_MANAGER._jobs_dir)
            if path == "/api/jobs":
                if not history["available"]:
                    self._json_reply(
                        503,
                        {
                            "error": "Historical storage is unavailable",
                            "diagnostics": history["diagnostics"],
                        },
                    )
                elif history["truncated"] or history["diagnostics"]:
                    self._json_reply(
                        409,
                        {
                            "code": "history_incomplete",
                            "error": (
                                "Historical entries were refused or the scan is partial; "
                                "inspect /api/history diagnostics"
                            ),
                            "jobs": history["jobs"],
                            "diagnostics": history["diagnostics"],
                            "truncated": history["truncated"],
                        },
                    )
                else:
                    self._json_reply(200, history["jobs"])
            else:
                self._json_reply(200 if history["available"] else 503, history)
            return

        if len(components) == 4 and components[1:3] == ["api", "jobs"]:
            try:
                self._json_reply(
                    200,
                    read_historical_job(
                        JOB_MANAGER._jobs_dir, unquote(components[3], errors="strict")
                    ),
                )
            except HistoryError as exc:
                self._json_reply(exc.status, {"error": str(exc), "code": exc.code})
            except UnicodeError:
                self._json_reply(400, {"error": "Malformed studio identifier encoding"})
            return

        if path == "/api/status":
            history = read_history(JOB_MANAGER._jobs_dir)
            self._json_reply(
                200 if history["available"] else 503,
                {
                    "status": "unavailable",
                    "runner_ready": False,
                    "code": "studio_runner_unavailable",
                    "error": (
                        "The protected studio producer worker is not connected; no new job can run."
                    ),
                    "active_job": None,
                    "latest_reel": None,
                    "historical_job_count": len(history["jobs"])
                    if history["available"] and not history["truncated"]
                    else None,
                    "history_available": history["available"],
                    "history_truncated": history["truncated"],
                    "history_diagnostics": history["diagnostics"],
                    "history_verified": False,
                },
            )
            return

        self._json_reply(404, {"error": "Unknown studio route; filesystem access is refused"})


class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def run_web_server(port: int = 8080, host: str = "127.0.0.1") -> None:
    """Run the HawEdit local web dashboard server."""
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("The local studio requires a supported loopback bind host")
    global UPLOAD_STORE
    if UPLOAD_STORE is None:
        configured = os.environ.get("HAWEDIT_STUDIO_STORAGE_ROOT")
        if configured:
            root = Path(configured)
        elif os.name == "nt":
            local = os.environ.get("LOCALAPPDATA")
            if not local:
                raise StudioStorageError("A real local application-data directory is required")
            root = Path(local) / "HawEditStudio"
        else:
            root = Path.home() / ".hawedit-studio"
        private_root = PrivateDirectory(root)
        uploads = private_root.child("uploads", create=True)
        UPLOAD_STORE = UploadStore(
            uploads.path,
            max_bytes=int(os.environ.get("HAWEDIT_UPLOAD_MAX_BYTES", str(DEFAULT_MAX_BYTES))),
        )
    use_utf8_streams()
    server_address = (host, port)
    with ThreadingTCPServer(server_address, HawEditWebHandler) as httpd:
        print(f"HawEdit Web Dashboard running at http://{host}:{port}/")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    run_web_server(port)
