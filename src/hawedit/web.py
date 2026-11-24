"""Local stdlib studio API; protected execution and publication remain explicit prerequisites."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import http.server
import importlib
import inspect
import json
import os
import re
import socket
import socketserver
import stat
import sys
import threading
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final
from urllib.parse import quote, unquote, urlparse

from hawedit.atomic_fs import write_text_atomic
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
from hawedit.studio_youtube import YouTubeImports
from hawedit.transcripts import validate_media_id

ROOT = Path(__file__).resolve().parents[2]
PROTECTED_STUDIO_ENV: Final = "HAWEDIT_PROTECTED_STUDIO"

_V8_STYLE_PRESETS: Final[frozenset[str]] = frozenset(
    {"viral_gold", "crimson_punch", "executive_cyan", "luxury_minimal", "broadcast_news"}
)
_V8_DIRECTORS: Final[frozenset[str]] = frozenset({"gemini", "local-omni", "offline"})
_V8_SUB_ENGINES: Final[frozenset[str]] = frozenset({"skia", "libass"})
_HEX_COLOR_RE: Final[re.Pattern[str]] = re.compile(r"^#[0-9A-Fa-f]{6}\Z")
_SOURCE_ID_RE: Final[re.Pattern[str]] = re.compile(r"^[a-f0-9]{32}\Z")
_CLIENT_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}\Z")
_SAFE_FILENAME_PART_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}\Z")
_V8_OPTION_KEYS: Final[frozenset[str]] = frozenset(
    {
        "engine",
        "style_preset",
        "director",
        "sub_engine",
        "condense",
        "cold_open",
        "max_clips",
        "brand_accent_hex",
        "speaker_source_id",
        "correction_source_id",
        "transcript_corrections",
        "cloud_consent_token",
        "subtitle_languages",
        "dub_languages",
        "speaker_name_ckb",
        "speaker_role_ckb",
        "end_card_title_ckb",
        "end_card_handle",
        "use_omni_asr",
    }
)
_V8_ARTIFACT_KINDS: Final[dict[str, tuple[str, str]]] = {
    "mp4": ("mp4", "video/mp4"),
    "social_zip": ("social_zip", "application/zip"),
    "srt": ("srt", "application/x-subrip; charset=utf-8"),
    "edl": ("edl", "text/plain; charset=utf-8"),
    "otio": ("otio", "application/json; charset=utf-8"),
    "cover": ("cover", "image/png"),
    "cover.png": ("cover", "image/png"),
    "director": ("director_json", "application/json; charset=utf-8"),
    "director_json": ("director_json", "application/json; charset=utf-8"),
    "director.json": ("director_json", "application/json; charset=utf-8"),
    "grill": ("grill_json", "application/json; charset=utf-8"),
    "grill_json": ("grill_json", "application/json; charset=utf-8"),
    "grill.json": ("grill_json", "application/json; charset=utf-8"),
}
_V8_ALLOWED_FILE_SUFFIXES: Final[tuple[tuple[str, str], ...]] = (
    (".v8.mp4", "video/mp4"),
    (".v8.srt", "application/x-subrip; charset=utf-8"),
    (".v8.edl", "text/plain; charset=utf-8"),
    (".v8.social.zip", "application/zip"),
    (".v8.otio", "application/json; charset=utf-8"),
    (".v8.cover.png", "image/png"),
    (".grill.json", "application/json; charset=utf-8"),
    (".director.json", "application/json; charset=utf-8"),
    ("blind-review.html", "text/html; charset=utf-8"),
    ("client-review.html", "text/html; charset=utf-8"),
)
_V8_SMALL_ARTIFACT_LIMIT: Final[int] = 32 * 1024 * 1024
_V8_ETAG_CACHE_MAX: Final[int] = 256
_V8_ETAG_LOCK = threading.Lock()
_V8_ETAG_CACHE: dict[tuple[int, int, int, int], str] = {}
_MAX_IN_MEMORY_COMPLETED_JOBS: Final[int] = 100
_SSE_KEEPALIVE_INTERVAL_S: Final[float] = 15.0


def _validate_bounded_opt_text(value: object, name: str, *, max_len: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string or null")
    stripped = value.strip()
    if not stripped:
        return None
    if len(stripped) > max_len or any(ord(ch) < 32 for ch in stripped):
        raise ValueError(f"{name} must be bounded text without control characters")
    return stripped


def _extract_repurpose_engine(payload: Mapping[str, Any]) -> str | None:
    top_engine = payload.get("engine")
    raw_opts = payload.get("options")
    opt_engine = raw_opts.get("engine") if isinstance(raw_opts, Mapping) else None
    if top_engine is not None and opt_engine is not None and top_engine != opt_engine:
        raise ValueError("Conflicting engine values between top-level payload and options")
    selected = top_engine if top_engine is not None else opt_engine
    if selected is None:
        return None
    if not isinstance(selected, str) or selected not in {"v8", "legacy"}:
        raise ValueError("Unsupported engine; use 'v8' or 'legacy'")
    return selected


def _parse_v8_repurpose_payload(payload: Mapping[str, Any]) -> tuple[str, str, dict[str, Any]]:
    """Strictly validate a V8 /api/repurpose request payload (D-392)."""
    if "source" in payload:
        raise ValueError(
            "Use a finalized source_id, not a filename or server path; server paths are refused"
        )
    if "transcript_path" in payload or (
        isinstance(payload.get("options"), Mapping) and "transcript_path" in payload["options"]
    ):
        raise ValueError(
            "Server transcript_path is refused; upload media and run with use_omni_asr=true"
        )
    allowed_top = {"schema", "source_id", "client_token", "options"} | _V8_OPTION_KEYS
    unknown_top = set(payload) - allowed_top
    if unknown_top:
        raise ValueError(f"Unsupported V8 repurpose fields: {', '.join(sorted(unknown_top))}")
    if type(payload.get("schema")) is not int or payload.get("schema") != 1:
        raise ValueError("Unsupported generation schema; use schema 1")
    source_id = payload.get("source_id")
    if not isinstance(source_id, str) or not _SOURCE_ID_RE.fullmatch(source_id):
        raise ValueError(
            "Use a finalized source_id, not a filename or server path; server paths are refused"
        )
    client_token = payload.get("client_token")
    if not isinstance(client_token, str) or not _CLIENT_TOKEN_RE.fullmatch(client_token):
        raise ValueError("client_token must be 16-128 ASCII identifier characters")

    merged: dict[str, Any] = {}
    raw_options = payload.get("options")
    if raw_options is not None:
        if not isinstance(raw_options, dict) or any(not isinstance(k, str) for k in raw_options):
            raise ValueError("Studio options must be an object with string fields")
        unknown_opts = set(raw_options) - _V8_OPTION_KEYS
        if unknown_opts:
            raise ValueError(f"Unsupported V8 studio options: {', '.join(sorted(unknown_opts))}")
        merged.update(raw_options)

    for key in _V8_OPTION_KEYS:
        if key in payload:
            if key in merged and merged[key] != payload[key]:
                raise ValueError(f"Conflicting values for V8 option '{key}'")
            merged[key] = payload[key]

    style_preset = merged.get("style_preset", "viral_gold")
    if not isinstance(style_preset, str) or style_preset not in _V8_STYLE_PRESETS:
        raise ValueError(
            f"Unsupported style_preset {style_preset!r}; choose one of {sorted(_V8_STYLE_PRESETS)}"
        )
    director = merged.get("director", "offline")
    if not isinstance(director, str) or director not in _V8_DIRECTORS:
        raise ValueError(
            f"Unsupported director {director!r}; choose one of {sorted(_V8_DIRECTORS)}"
        )
    if director == "gemini" and merged.get("cloud_consent_token") != client_token:
        raise ValueError("Gemini requires cloud consent for this job")
    sub_engine = merged.get("sub_engine", "skia")
    if not isinstance(sub_engine, str) or sub_engine not in _V8_SUB_ENGINES:
        raise ValueError(
            f"Unsupported sub_engine {sub_engine!r}; choose one of {sorted(_V8_SUB_ENGINES)}"
        )

    condense = merged.get("condense", True)
    if type(condense) is not bool:
        raise ValueError("condense must be a boolean")
    cold_open = merged.get("cold_open", True)
    if type(cold_open) is not bool:
        raise ValueError("cold_open must be a boolean")

    max_clips = merged.get("max_clips", 3)
    if type(max_clips) is not int or not (1 <= max_clips <= 10):
        raise ValueError("max_clips must be an integer between 1 and 10")

    brand_accent_hex = _validate_bounded_opt_text(
        merged.get("brand_accent_hex"), "brand_accent_hex", max_len=16
    )
    if brand_accent_hex is not None and not _HEX_COLOR_RE.fullmatch(brand_accent_hex):
        raise ValueError("brand_accent_hex must be a #RRGGBB hex color")

    speaker_name_ckb = _validate_bounded_opt_text(
        merged.get("speaker_name_ckb"), "speaker_name_ckb", max_len=120
    )
    speaker_role_ckb = _validate_bounded_opt_text(
        merged.get("speaker_role_ckb"), "speaker_role_ckb", max_len=120
    )
    if speaker_role_ckb and not speaker_name_ckb:
        raise ValueError("A speaker credit role requires a speaker name")
    if speaker_name_ckb and merged.get("speaker_source_id") != source_id:
        raise ValueError("Confirm the speaker credit for this source")
    end_card_title_ckb = _validate_bounded_opt_text(
        merged.get("end_card_title_ckb"), "end_card_title_ckb", max_len=120
    )
    end_card_handle = _validate_bounded_opt_text(
        merged.get("end_card_handle"), "end_card_handle", max_len=80
    )

    if "use_omni_asr" in merged:
        use_omni_asr = merged["use_omni_asr"]
        if type(use_omni_asr) is not bool:
            raise ValueError("use_omni_asr must be a boolean")
    else:
        use_omni_asr = True

    normalized: dict[str, Any] = {
        "engine": "v8",
        "style_preset": style_preset,
        "director": director,
        "sub_engine": sub_engine,
        "condense": condense,
        "cold_open": cold_open,
        "max_clips": max_clips,
        "brand_accent_hex": brand_accent_hex,
        "speaker_name_ckb": speaker_name_ckb,
        "speaker_role_ckb": speaker_role_ckb,
        "end_card_title_ckb": end_card_title_ckb,
        "end_card_handle": end_card_handle,
        "use_omni_asr": use_omni_asr,
    }
    corrections = merged.get("transcript_corrections", [])
    if not isinstance(corrections, list) or len(corrections) > 32:
        raise ValueError("Expected at most 32 transcript corrections")
    if corrections:
        if merged.get("correction_source_id") != source_id:
            raise ValueError("Confirm transcript corrections for this source")
        from hawedit.v8.schema import WordRepair

        checked = []
        indices = set()
        for row in corrections:
            if not isinstance(row, dict):
                raise ValueError("Expected a transcript correction")
            repair = WordRepair.from_dict(row)
            if (
                max(len(repair.original), len(repair.repaired)) > 100
                or repair.reason != "native editor"
                or repair.word_index in indices
            ):
                raise ValueError("Invalid or duplicate transcript correction")
            indices.add(repair.word_index)
            checked.append(repair.to_dict())
        normalized["transcript_corrections"] = checked
        normalized["correction_source_id"] = source_id
    for option_name in ("subtitle_languages", "dub_languages"):
        tracks = merged.get(option_name, [])
        if (
            not isinstance(tracks, list)
            or len(tracks) > 2
            or any(v not in ("ar", "en") for v in tracks)
        ):
            raise ValueError(f"{option_name} must list Arabic or English language codes")
        if tracks:
            normalized[option_name] = list(dict.fromkeys(tracks))
    if director == "gemini":
        normalized["cloud_consent_token"] = client_token
    if speaker_name_ckb:
        normalized["speaker_source_id"] = source_id
    return source_id, client_token, normalized


def _plain_fs_entry(info: os.stat_result, *, directory: bool) -> None:
    reparse = sys.platform == "win32" and bool(
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )
    valid = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if reparse or not valid or (not directory and info.st_nlink != 1):
        raise ArtifactError("Linked or non-regular artifact path is refused", status=409)


def _validate_safe_rel_parts(parts: tuple[str, ...]) -> tuple[str, ...]:
    if not parts or len(parts) > 4:
        raise ArtifactError("Invalid artifact path scope", status=400)
    for part in parts:
        if not part or part in {".", ".."} or not _SAFE_FILENAME_PART_RE.fullmatch(part):
            raise ArtifactError("Path traversal or unsafe artifact segment refused", status=400)
    return parts


def _resolve_safe_job_file(jobs_root: Path, job_id: str, rel_parts: tuple[str, ...]) -> Path:
    try:
        validate_media_id(job_id)
    except ValueError as exc:
        raise ArtifactError("Invalid studio job identifier", status=400) from exc
    clean_parts = _validate_safe_rel_parts(rel_parts)
    root = jobs_root.absolute()
    try:
        _plain_fs_entry(root.lstat(), directory=True)
        current = root / job_id
        _plain_fs_entry(current.lstat(), directory=True)
        for index, part in enumerate(clean_parts):
            current = current / part
            _plain_fs_entry(current.lstat(), directory=index < len(clean_parts) - 1)
    except FileNotFoundError as exc:
        raise ArtifactError("Requested studio artifact was not found", status=404) from exc
    except OSError as exc:
        raise ArtifactError("Studio artifact storage is unavailable", status=503) from exc
    return current


def _read_safe_job_file_bytes(
    jobs_root: Path, job_id: str, rel_parts: tuple[str, ...], *, max_bytes: int
) -> tuple[bytes, str]:
    target = _resolve_safe_job_file(jobs_root, job_id, rel_parts)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        before = target.lstat()
        with os.fdopen(os.open(target, flags), "rb") as stream:
            opened = os.fstat(stream.fileno())
            _plain_fs_entry(opened, directory=False)
            if (before.st_dev, before.st_ino, before.st_size) != (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
            ):
                raise ArtifactError("Artifact changed while opening", status=409)
            if opened.st_size > max_bytes:
                raise ArtifactError("Artifact exceeds download limit", status=413)
            data = stream.read(max_bytes + 1)
            if len(data) != opened.st_size:
                raise ArtifactError("Artifact changed while reading", status=409)
    except ArtifactError:
        raise
    except FileNotFoundError as exc:
        raise ArtifactError("Requested studio artifact was not found", status=404) from exc
    except OSError as exc:
        raise ArtifactError("Studio artifact storage is unavailable", status=503) from exc
    return data, hashlib.sha256(data).hexdigest()


def _content_type_for_v8_filename(filename: str) -> str | None:
    lower = filename.lower()
    for suffix, ctype in _V8_ALLOWED_FILE_SUFFIXES:
        if lower == suffix or lower.endswith(suffix):
            return ctype
    return None


def _job_relative_parts(job_dir: Path, path_value: object) -> tuple[str, ...] | None:
    if path_value is None:
        return None
    raw = Path(str(path_value))
    if not raw.is_file():
        return None
    try:
        rel = raw.resolve().relative_to(job_dir.resolve())
    except ValueError:
        return None
    parts = tuple(rel.parts)
    try:
        return _validate_safe_rel_parts(parts)
    except ArtifactError:
        return None


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def _build_v8_episode_config(config_cls: Any, opts: Mapping[str, Any]) -> Any:
    """Construct V8EpisodeConfig matching its declared fields without silent drops."""
    speaker_name = opts.get("speaker_name_ckb")
    speaker_role = opts.get("speaker_role_ckb")
    speaker_bio = (speaker_name, speaker_role) if speaker_name else None
    end_title = opts.get("end_card_title_ckb")
    end_handle = opts.get("end_card_handle")
    end_card = (end_title, None, end_handle) if end_title else None

    candidates: dict[str, Any] = {
        "style_preset": str(opts.get("style_preset", "viral_gold")),
        "director": str(opts.get("director", "offline")),
        "director_backend": str(opts.get("director", "offline")),
        "sub_engine": str(opts.get("sub_engine", "skia")),
        "condense": bool(opts.get("condense", True)),
        "cold_open": bool(opts.get("cold_open", True)),
        "max_clips": int(opts.get("max_clips", 3)),
        "brand_accent_hex": opts.get("brand_accent_hex"),
        "subtitle_languages": tuple(opts.get("subtitle_languages", ())),
        "dub_languages": tuple(opts.get("dub_languages", ())),
        "speaker_bio": speaker_bio,
        "speaker_name_ckb": speaker_name,
        "speaker_role_ckb": speaker_role,
        "end_card": end_card,
        "end_card_title_ckb": end_title,
        "end_card_handle": end_handle,
    }
    if opts.get("transcript_corrections"):
        from hawedit.v8.schema import WordRepair

        candidates["transcript_corrections"] = tuple(
            WordRepair.from_dict(r) for r in opts["transcript_corrections"]
        )
    if isinstance(config_cls, type) and dataclasses.is_dataclass(config_cls):
        field_names = {f.name for f in dataclasses.fields(config_cls)}
        kwargs = {k: v for k, v in candidates.items() if k in field_names}
        return config_cls(**kwargs)
    return config_cls(**candidates)


def protected_studio_enabled(
    env: Mapping[str, str] | None = None,
    *,
    protected: bool | None = None,
) -> bool:
    """Return True when protected host admission (503 stub) is requested (A3, D-337)."""
    if protected is not None:
        return bool(protected)
    environ = os.environ if env is None else env
    raw = environ.get(PROTECTED_STUDIO_ENV, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


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


def _read_measured_summary(path: Path) -> tuple[float, str]:
    if not path.is_file():
        return 0.0, ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 0.0, ""
    if not isinstance(data, dict):
        return 0.0, ""
    file_info = data.get("file")
    video_info = data.get("video")
    duration_ms = (
        video_info.get("duration_ms", 0)
        if isinstance(video_info, dict)
        else data.get("duration_ms", 0)
    )
    sha256 = file_info.get("sha256", "") if isinstance(file_info, dict) else data.get("sha256", "")
    duration_s = (
        round(float(duration_ms) / 1000.0, 2) if isinstance(duration_ms, int | float) else 0.0
    )
    return duration_s, str(sha256) if isinstance(sha256, str) else ""


class JobManager:
    """Thread-safe persistent job manager coordinating background stage execution."""

    def __init__(self, jobs_dir: Path | None = None, *, create_dir: bool = True) -> None:
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._exec_lock = threading.Lock()
        self._jobs: dict[str, JobInfo] = {}
        self._live_jobs: set[str] = set()
        self._desktop_jobs: set[str] = set()
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._stages: dict[str, list[dict[str, str]]] = {}
        self._jobs_dir = jobs_dir or (ROOT / "work" / "jobs")
        if create_dir:
            self._jobs_dir.mkdir(parents=True, exist_ok=True)
        if self._jobs_dir.is_dir():
            self._load_persisted_jobs()

    def _load_persisted_jobs(self) -> None:
        for job_file in self._jobs_dir.glob("*/job.json"):
            try:
                data = json.loads(job_file.read_text(encoding="utf-8"))
                job = JobInfo(**data)
                if job.status in {"queued", "running"}:
                    job.status = "interrupted"
                    if not job.error:
                        job.error = "Interrupted by studio server restart"
                self._jobs[job.job_id] = job
            except (OSError, ValueError, TypeError):
                continue

    def _save_job(self, job: JobInfo) -> None:
        job_folder = self._jobs_dir / job.job_id
        job_folder.mkdir(parents=True, exist_ok=True)
        target_file = job_folder / "job.json"
        write_text_atomic(target_file, json.dumps(job.to_dict(), indent=2))

    def _prune_completed_locked(self) -> None:
        completed_ids = [
            jid for jid, info in self._jobs.items() if info.status not in {"queued", "running"}
        ]
        if len(completed_ids) <= _MAX_IN_MEMORY_COMPLETED_JOBS:
            return
        completed_ids.sort(key=lambda jid: self._jobs[jid].updated_at)
        evict_count = len(completed_ids) - _MAX_IN_MEMORY_COMPLETED_JOBS
        for stale_id in completed_ids[:evict_count]:
            self._jobs.pop(stale_id, None)
            self._live_jobs.discard(stale_id)
            self._desktop_jobs.discard(stale_id)
            self._events.pop(stale_id, None)
            self._stages.pop(stale_id, None)

    def _append_event_locked(self, job_id: str, event_name: str, data: dict[str, Any]) -> None:
        bucket = self._events.setdefault(job_id, [])
        bucket.append({"seq": len(bucket) + 1, "event": event_name, "data": data})
        self._cond.notify_all()

    def is_live_job(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._live_jobs

    def get_live_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            if job_id not in self._live_jobs or job_id not in self._jobs:
                return None
            job = self._jobs[job_id]
            data = job.to_dict()
            data["historical"] = False
            data["stages"] = list(self._stages.get(job_id, []))
            data["publication_verified"] = False
            review_url = next(
                (
                    clip.get("review_sheet_url")
                    for clip in job.clips
                    if isinstance(clip, dict) and clip.get("review_sheet_url")
                ),
                None,
            )
            if review_url is not None:
                data["review_sheet_url"] = review_url
            return data

    def active_job(self) -> dict[str, Any] | None:
        with self._lock:
            for job_id in reversed(list(self._live_jobs)):
                job = self._jobs.get(job_id)
                if job is not None and job.status in {"queued", "running"}:
                    return {
                        "job_id": job.job_id,
                        "status": job.status,
                        "stage": job.stage,
                        "progress_percent": job.progress_percent,
                    }
            return None

    def latest_completed_reel(self) -> dict[str, Any] | None:
        with self._lock:
            for job_id in reversed(list(self._live_jobs)):
                job = self._jobs.get(job_id)
                if job is not None and job.status == "completed" and job.clips:
                    clip = job.clips[0]
                    return {
                        "job_id": job.job_id,
                        "clip_id": clip.get("clip_id"),
                        "preview_url": clip.get("preview_url"),
                        "headline": clip.get("headline"),
                    }
            return None

    def read_events_since(
        self, job_id: str, after_seq: int, *, timeout: float = 1.0
    ) -> tuple[list[dict[str, Any]], bool]:
        """Return (new_events, is_terminal) waiting up to timeout while job is active."""
        with self._cond:
            bucket = self._events.get(job_id, [])
            job = self._jobs.get(job_id)
            if len(bucket) <= after_seq and (
                job is not None and job.status in {"queued", "running"}
            ):
                self._cond.wait(timeout=timeout)
                bucket = self._events.get(job_id, [])
                job = self._jobs.get(job_id)
            events = [dict(item) for item in bucket[after_seq:]]
            terminal = job is None or job.status not in {"queued", "running"}
            return events, terminal

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

    def _start_worker(self, job_id: str) -> None:
        thread = threading.Thread(
            target=self._run_job_stages,
            args=(job_id,),
            daemon=True,
        )
        thread.start()

    def submit_job(
        self,
        source: str,
        client_token: str | None = None,
        options: dict[str, Any] | None = None,
        *,
        start_worker: bool = True,
        desktop_mode: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            if client_token:
                for existing in self._jobs.values():
                    if existing.client_token == client_token:
                        return existing.to_dict()
            job_id = f"job-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
            now = time.time()
            source_p = Path(source)
            clips: list[dict[str, Any]] = (
                []
                if desktop_mode
                else [
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
            )

            job = JobInfo(
                job_id=job_id,
                source=source,
                status="queued",
                stage="stage0_ingest",
                stage_index=0,
                progress_percent=0,
                created_at=now,
                updated_at=now,
                headline=f"«شۆرت لە {source_p.name}»",
                clips=clips,
                client_token=client_token,
                options=options or {},
            )
            self._jobs[job_id] = job
            self._live_jobs.add(job_id)
            if desktop_mode:
                self._desktop_jobs.add(job_id)
            self._stages[job_id] = []
            self._append_event_locked(
                job_id,
                "queued",
                {
                    "job_id": job_id,
                    "status": "queued",
                    "stage": "stage0_ingest",
                    "progress_percent": 0,
                },
            )
            self._save_job(job)
        if start_worker:
            self._start_worker(job_id)
        return job.to_dict()

    def _run_job_stages(self, job_id: str) -> None:
        with self._exec_lock:
            self._run_job_stages_unlocked(job_id)

    def _run_job_stages_unlocked(self, job_id: str) -> None:
        with self._lock:
            if job_id not in self._jobs:
                return
            source_file = Path(self._jobs[job_id].source)

        probe_error: str | None = None
        source_duration_s = 0.0
        if not source_file.is_file() or source_file.stat().st_size == 0:
            probe_error = f"Source media file is missing or empty: {source_file}"
        else:
            try:
                import cv2

                cap = cv2.VideoCapture(str(source_file))
                try:
                    if not cap.isOpened():
                        probe_error = f"Cannot open video stream in {source_file.name}"
                    else:
                        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
                        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
                        if frame_count == 0:
                            probe_error = f"Video file contains no frames: {source_file.name}"
                        else:
                            source_duration_s = round(frame_count / fps, 2)
                finally:
                    cap.release()
            except Exception as exc:
                probe_error = f"Failed to probe video stream: {exc}"

        with self._lock:
            if job_id not in self._jobs:
                return
            if probe_error is not None:
                self._jobs[job_id].status = "failed"
                self._jobs[job_id].error = probe_error
                self._jobs[job_id].updated_at = time.time()
                self._append_event_locked(
                    job_id,
                    "failed",
                    {
                        "job_id": job_id,
                        "status": "failed",
                        "error": self._jobs[job_id].error,
                    },
                )
                self._save_job(self._jobs[job_id])
                self._prune_completed_locked()
                return

            self._jobs[job_id].status = "running"
            self._jobs[job_id].updated_at = time.time()
            for clip in self._jobs[job_id].clips:
                if clip["duration_s"] == 0.0 or clip["duration_s"] > source_duration_s:
                    clip["duration_s"] = source_duration_s
            self._append_event_locked(
                job_id,
                "stage",
                {
                    "job_id": job_id,
                    "stage": "ingest",
                    "state": "started",
                    "progress_percent": 0,
                },
            )
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
                state_raw = getattr(event, "state", None)
                state_val = str(getattr(state_raw, "value", state_raw) or "")
                if stage:
                    self._jobs[job_id].stage = stage
                    if stage in stage_pct:
                        self._jobs[job_id].progress_percent = stage_pct[stage]
                    for i, sname in enumerate(stage_names):
                        if stage in sname or sname in stage:
                            self._jobs[job_id].stage_index = i
                            break
                    rows = self._stages.setdefault(job_id, [])
                    updated_row = {"stage": stage, "state": state_val or "started"}
                    existing_idx = next(
                        (idx for idx, row in enumerate(rows) if row["stage"] == stage),
                        None,
                    )
                    if existing_idx is not None:
                        rows[existing_idx] = updated_row
                    else:
                        rows.append(updated_row)
                    self._jobs[job_id].updated_at = time.time()
                    self._append_event_locked(
                        job_id,
                        "stage",
                        {
                            "job_id": job_id,
                            "stage": stage,
                            "state": updated_row["state"],
                            "progress_percent": self._jobs[job_id].progress_percent,
                            "reason": getattr(event, "reason", None),
                        },
                    )
                    self._save_job(self._jobs[job_id])

        try:
            from hawedit.captions import CaptionStyle
            from hawedit.pipeline import Delivery, _build_and_run, build_parser, run_pipeline
            from hawedit.render import RenderResult
            from hawedit.studio_generation import _option_argv

            with self._lock:
                job_info = self._jobs[job_id]
                opts = dict(getattr(job_info, "options", {}) or {})
                is_desktop = job_id in self._desktop_jobs

            if opts.get("engine") == "v8":
                self._run_v8_episode_job(job_id, source_file, job_work_dir, opts)
                return

            if is_desktop:
                effective_opts: dict[str, Any] = {"max_clips": 5, **opts}
                argv = [
                    str(source_file),
                    f"--work-dir={job_work_dir}",
                    f"--media-id={job_id}",
                    "--reels",
                    *_option_argv(effective_opts),
                ]
                parsed_args = build_parser().parse_args(argv)
                if getattr(parsed_args, "validate_asr", None) is None:
                    parsed_args.validate_asr = False
                run = _build_and_run(parsed_args, on_event=on_event)
            else:
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

                write_text_atomic(
                    job_work_dir / "report.json",
                    json.dumps(run.to_dict(), ensure_ascii=False, indent=2),
                )

                if is_delivered or is_rendered or has_ep_clips:
                    clips_data: list[dict[str, Any]] = []
                    if has_ep_clips:
                        assert run.episode_manifest is not None
                        for idx, clip_sum in enumerate(run.episode_manifest.clips, 1):
                            cid = clip_sum.clip_id
                            meas_path = (
                                job_work_dir / clip_sum.delivery_dir / f"{cid}.measured.json"
                            )
                            meas_dur, sha256 = _read_measured_summary(meas_path)
                            dur = meas_dur or round(clip_sum.duration_ms / 1000.0, 2)
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
                                    "preview_url": f"/api/jobs/{job_id}/clips/{cid}/preview",
                                    "preview_verified": bool(sha256 and dur > 0),
                                    "poster_url": "",
                                    "virality_score": score,
                                    "label": f"{idx}. {h[:24]}",
                                    "sha256": sha256,
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
                        duration_s, sha256 = _read_measured_summary(measured_path)
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
                        clips_data.append(
                            {
                                "clip_id": clip_id,
                                "duration_s": duration_s,
                                "headline": headline,
                                "video_url": f"/media/{clip_id}.mp4",
                                "preview_url": f"/api/jobs/{job_id}/clips/{clip_id}/preview",
                                "preview_verified": bool(sha256 and duration_s > 0),
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
                self._append_event_locked(
                    job_id,
                    self._jobs[job_id].status,
                    {
                        "job_id": job_id,
                        "status": self._jobs[job_id].status,
                        "stage": self._jobs[job_id].stage,
                        "progress_percent": self._jobs[job_id].progress_percent,
                        "error": self._jobs[job_id].error,
                        "clips": self._jobs[job_id].clips,
                    },
                )
                self._save_job(self._jobs[job_id])
                self._prune_completed_locked()
        except Exception as exc:
            with self._lock:
                if job_id in self._jobs:
                    self._jobs[job_id].status = "failed"
                    self._jobs[job_id].error = f"Pipeline execution error: {exc}"
                    self._jobs[job_id].updated_at = time.time()
                    self._append_event_locked(
                        job_id,
                        "failed",
                        {
                            "job_id": job_id,
                            "status": "failed",
                            "error": self._jobs[job_id].error,
                        },
                    )
                    self._save_job(self._jobs[job_id])
                    self._prune_completed_locked()

    def _run_v8_episode_job(
        self,
        job_id: str,
        source_file: Path,
        job_work_dir: Path,
        opts: Mapping[str, Any],
    ) -> None:
        """Execute a V8 Lean Director multi-reel episode compile job (D-392)."""

        def _record_stage(stage: str, state: str, progress: int, stage_index: int) -> None:
            with self._lock:
                if job_id not in self._jobs:
                    return
                self._jobs[job_id].stage = stage
                self._jobs[job_id].stage_index = stage_index
                self._jobs[job_id].progress_percent = progress
                rows = self._stages.setdefault(job_id, [])
                updated_row = {"stage": stage, "state": state}
                existing_idx = next(
                    (idx for idx, row in enumerate(rows) if row["stage"] == stage),
                    None,
                )
                if existing_idx is not None:
                    rows[existing_idx] = updated_row
                else:
                    rows.append(updated_row)
                self._jobs[job_id].updated_at = time.time()
                self._append_event_locked(
                    job_id,
                    "stage",
                    {
                        "job_id": job_id,
                        "stage": stage,
                        "state": state,
                        "progress_percent": progress,
                    },
                )
                self._save_job(self._jobs[job_id])

        try:
            _record_stage("stage0_ingest", "completed", 15, 0)
            _record_stage("v8_episode_compile", "started", 35, 3)

            episode_mod = importlib.import_module("hawedit.v8.episode")
            v8_config_cls = episode_mod.V8EpisodeConfig
            compile_v8_episode = episode_mod.compile_v8_episode

            v8_out_dir = job_work_dir / "v8"
            v8_out_dir.mkdir(parents=True, exist_ok=True)
            ep_config = _build_v8_episode_config(v8_config_cls, opts)

            use_omni_asr = bool(opts.get("use_omni_asr", True))
            compile_kwargs: dict[str, Any] = {
                "transcript_path": None,
                "use_omni_asr": use_omni_asr,
                "config": ep_config,
            }
            try:
                sig = inspect.signature(compile_v8_episode)
                if "on_progress" in sig.parameters:
                    compile_kwargs["on_progress"] = lambda stage, state, pct: _record_stage(
                        stage, state, pct, 4
                    )
            except (TypeError, ValueError):
                pass

            ep_result = compile_v8_episode(source_file, v8_out_dir, **compile_kwargs)

            review_rel = _job_relative_parts(
                job_work_dir, getattr(ep_result, "review_html_path", None)
            )
            encoded_job_id = quote(job_id, safe="")
            review_sheet_url = (
                f"/api/jobs/{encoded_job_id}/artifacts/"
                f"{'/'.join(quote(part, safe='') for part in review_rel)}"
                if review_rel is not None
                else None
            )

            clips_data: list[dict[str, Any]] = []
            manifest_clips: list[dict[str, Any]] = []
            v8_clip_artifacts: dict[str, dict[str, str]] = {}
            v8_clip_meta: dict[str, dict[str, Any]] = {}

            for idx, item in enumerate(getattr(ep_result, "clips", ()), 1):
                pack = item.delivery_pack
                cid = str(item.clip_id)
                validate_media_id(cid)
                encoded_cid = quote(cid, safe="")

                artifact_sources: dict[str, object] = {
                    "mp4": getattr(pack, "mp4_path", None),
                    "srt": getattr(pack, "srt_path", None),
                    "social_zip": getattr(pack, "social_zip_path", None),
                    "edl": getattr(pack, "edl_path", None),
                    "otio": getattr(pack, "otio_path", None),
                    "cover": getattr(pack, "cover_png_path", None),
                    "director_json": getattr(pack, "director_json_path", None),
                    "grill_json": getattr(pack, "grill_json_path", None),
                }
                rel_map: dict[str, str] = {}
                for kind, raw_path in artifact_sources.items():
                    rel_parts = _job_relative_parts(job_work_dir, raw_path)
                    if rel_parts is not None:
                        rel_map[kind] = "/".join(rel_parts)

                mp4_path_obj = Path(str(pack.mp4_path)) if getattr(pack, "mp4_path", None) else None
                mp4_sha256 = (
                    _sha256_file(mp4_path_obj)
                    if mp4_path_obj is not None and mp4_path_obj.is_file()
                    else ""
                )
                hook_title = str(
                    getattr(item, "hook_title_ckb", "")
                    or getattr(pack, "hook_title_ckb", "")
                    or f"«شۆرتی ژمارە {idx}»"
                )
                duration_s = round(
                    float(
                        getattr(
                            item,
                            "duration_s",
                            float(getattr(pack, "duration_ms", 0)) / 1000.0,
                        )
                    ),
                    2,
                )
                face_share = round(
                    float(getattr(item, "face_share", getattr(pack, "face_share", 0.0))),
                    4,
                )
                grill_passed_raw = getattr(
                    item, "grill_passed", getattr(pack, "grill_passed", None)
                )
                grill_passed = bool(grill_passed_raw) if grill_passed_raw is not None else False
                grill_summary = str(
                    getattr(item, "grill_summary", "") or getattr(pack, "grill_summary", "")
                )

                download_urls: dict[str, str] = {}
                for dl_kind in (
                    "mp4",
                    "social_zip",
                    "srt",
                    "edl",
                    "otio",
                    "director_json",
                    "grill_json",
                ):
                    if dl_kind in rel_map:
                        download_urls[dl_kind] = (
                            f"/api/jobs/{encoded_job_id}/clips/{encoded_cid}/artifacts/{dl_kind}"
                        )

                preview_url = f"/api/jobs/{encoded_job_id}/clips/{encoded_cid}/preview"
                cover_url = (
                    f"/api/jobs/{encoded_job_id}/clips/{encoded_cid}/cover.png"
                    if "cover" in rel_map
                    else ""
                )

                clips_data.append(
                    {
                        "clip_id": cid,
                        "headline": hook_title,
                        "hook_title_ckb": hook_title,
                        "duration_s": duration_s,
                        "face_share": face_share,
                        "grill_passed": grill_passed,
                        "grill_summary": grill_summary,
                        "editorial_reason": getattr(item, "editorial_reason", ""),
                        "source_quotes": list(getattr(item, "source_quotes", ())),
                        "preview_url": preview_url,
                        "preview_verified": bool(mp4_sha256 and duration_s > 0),
                        "cover_url": cover_url,
                        "download_urls": download_urls,
                        "review_sheet_url": review_sheet_url,
                        "sha256": mp4_sha256,
                        "video_url": preview_url,
                        "label": f"{idx}. {hook_title[:28]}",
                    }
                )
                v8_clip_artifacts[cid] = rel_map
                v8_clip_meta[cid] = {
                    "editorial_reason": clips_data[-1]["editorial_reason"],
                    "source_quotes": clips_data[-1]["source_quotes"],
                    "hook_title_ckb": hook_title,
                    "duration_s": duration_s,
                    "face_share": face_share,
                    "grill_passed": grill_passed,
                    "grill_summary": grill_summary,
                    "sha256": mp4_sha256,
                }
                mp4_rel_str = rel_map.get("mp4", "v8")
                mp4_dir = "/".join(mp4_rel_str.split("/")[:-1]) if "/" in mp4_rel_str else "v8"
                manifest_clips.append(
                    {
                        "clip_id": cid,
                        "delivery_dir": mp4_dir or "v8",
                        "title_ckb": hook_title,
                    }
                )

            report_doc: dict[str, Any] = {
                "engine": "v8",
                "episode_manifest": {"clips": manifest_clips},
                "v8_episode": {
                    "clips": v8_clip_artifacts,
                    "clip_meta": v8_clip_meta,
                    "review_sheet": "/".join(review_rel) if review_rel is not None else None,
                    "all_grills_passed": bool(getattr(ep_result, "all_grills_passed", False)),
                    "total_wall_s": float(getattr(ep_result, "total_wall_s", 0.0)),
                },
            }
            write_text_atomic(
                job_work_dir / "report.json",
                json.dumps(report_doc, ensure_ascii=False, indent=2),
            )

            _record_stage("v8_episode_compile", "completed", 95, 6)

            with self._lock:
                if job_id not in self._jobs:
                    return
                if clips_data:
                    self._jobs[job_id].clips = clips_data
                    self._jobs[job_id].headline = clips_data[0]["headline"]
                    self._jobs[job_id].status = "completed"
                    self._jobs[job_id].stage = "delivery"
                    self._jobs[job_id].stage_index = 6
                    self._jobs[job_id].progress_percent = 100
                else:
                    self._jobs[job_id].status = "failed"
                    self._jobs[job_id].error = "V8 episode compiler produced no clips."
                    self._jobs[job_id].progress_percent = 95
                self._jobs[job_id].updated_at = time.time()
                self._append_event_locked(
                    job_id,
                    self._jobs[job_id].status,
                    {
                        "job_id": job_id,
                        "status": self._jobs[job_id].status,
                        "stage": self._jobs[job_id].stage,
                        "progress_percent": self._jobs[job_id].progress_percent,
                        "error": self._jobs[job_id].error,
                        "clips": self._jobs[job_id].clips,
                    },
                )
                self._save_job(self._jobs[job_id])
                self._prune_completed_locked()
        except Exception as exc:
            with self._lock:
                if job_id in self._jobs:
                    self._jobs[job_id].status = "failed"
                    self._jobs[job_id].error = f"V8 episode execution error: {exc}"
                    self._jobs[job_id].updated_at = time.time()
                    self._append_event_locked(
                        job_id,
                        "failed",
                        {
                            "job_id": job_id,
                            "status": "failed",
                            "error": self._jobs[job_id].error,
                        },
                    )
                    self._save_job(self._jobs[job_id])
                    self._prune_completed_locked()

    def run_job_sync(self, job_id: str) -> None:
        """Run job stages synchronously for testing or direct CLI invocation."""
        self._run_job_stages(job_id)


JOB_MANAGER = JobManager(create_dir=False)
UPLOAD_STORE: UploadStore | None = None
YOUTUBE_IMPORTS = YouTubeImports()


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

        if path in {"/api/youtube/import", "/api/youtube/status"}:
            if not self._local_write():
                return
            try:
                data = self._read_json()
                if set(data) != {"url"} or not isinstance(data["url"], str):
                    raise ValueError("Supply one YouTube video URL")
                status = YOUTUBE_IMPORTS.request(
                    _upload_store(), data["url"], start=path.endswith("/import")
                )
                self._json_reply(202 if status["state"] == "importing" else 200, status)
            except (ValueError, UploadError) as exc:
                self._json_reply(400, {"error": str(exc)})
            except (OSError, StudioStorageError) as exc:
                self._json_reply(503, {"error": str(exc)})
            return

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
                payload = self._read_json()
                engine = _extract_repurpose_engine(payload)
                if engine == "v8":
                    source_id, client_token, v8_opts = _parse_v8_repurpose_payload(payload)
                    source_path = _upload_store().source(source_id)
                    if protected_studio_enabled():
                        self._json_reply(
                            503,
                            {
                                "code": "studio_runner_unavailable",
                                "error": (
                                    "Source validated. The durable studio runner and "
                                    "owner-authorized producer configuration are not "
                                    "connected yet; no job was queued."
                                ),
                            },
                        )
                        return
                    job = JOB_MANAGER.submit_job(
                        str(source_path),
                        client_token=client_token,
                        options={**v8_opts, "episode_source_id": source_id},
                        desktop_mode=True,
                    )
                    self._json_reply(
                        202,
                        {
                            "job_id": job["job_id"],
                            "status": job["status"],
                            "engine": "v8",
                            "events_url": f"/api/jobs/{job['job_id']}/events",
                        },
                    )
                    return

                legacy_payload = payload
                if engine == "legacy":
                    legacy_payload = {k: v for k, v in payload.items() if k != "engine"}
                    if isinstance(legacy_payload.get("options"), dict):
                        legacy_payload["options"] = {
                            k: v for k, v in legacy_payload["options"].items() if k != "engine"
                        }
                request = GenerationRequest.from_payload(legacy_payload)
                source_path, _ = request.validate_source(_upload_store())
                if protected_studio_enabled():
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
                    return
                job = JOB_MANAGER.submit_job(
                    str(source_path),
                    client_token=request.client_token,
                    options=dict(request.options),
                    desktop_mode=True,
                )
                self._json_reply(
                    202,
                    {
                        "job_id": job["job_id"],
                        "status": job["status"],
                        "events_url": f"/api/jobs/{job['job_id']}/events",
                    },
                )
            except (GenerationError, UploadError, ValueError) as exc:
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

    def _serve_v8_doctor(self) -> None:
        try:
            doctor_mod = importlib.import_module("hawedit.v8.doctor")
            report = doctor_mod.run_v8_doctor()
            payload = report.to_dict() if hasattr(report, "to_dict") else dict(report)
            self._json_reply(200, payload)
        except Exception as exc:
            self._json_reply(503, {"error": f"V8 preflight doctor unavailable: {exc}"})

    def _serve_v8_presets(self) -> None:
        try:
            styles_mod = importlib.import_module("hawedit.v8.styles")
            presets = list(styles_mod.list_client_style_presets())
            self._json_reply(200, {"presets": presets})
        except Exception as exc:
            self._json_reply(503, {"error": f"V8 client style presets unavailable: {exc}"})

    def _v8_report_data(self, job_id: str) -> dict[str, Any] | None:
        try:
            raw, _ = _read_safe_job_file_bytes(
                JOB_MANAGER._jobs_dir, job_id, ("report.json",), max_bytes=4 * 1024 * 1024
            )
            doc = json.loads(raw.decode("utf-8"))
        except Exception:
            return None
        if not isinstance(doc, dict):
            return None
        v8_ep = doc.get("v8_episode")
        return dict(v8_ep) if isinstance(v8_ep, dict) else None

    def _stream_safe_v8_artifact(
        self,
        job_id: str,
        rel_parts: tuple[str, ...],
        *,
        content_type: str = "video/mp4",
        as_preview: bool = False,
        download_name: str | None = None,
    ) -> None:
        target = _resolve_safe_job_file(JOB_MANAGER._jobs_dir, job_id, rel_parts)
        flags = (
            os.O_RDONLY
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
        )
        try:
            before = target.lstat()
            with os.fdopen(os.open(target, flags), "rb") as stream:
                opened = os.fstat(stream.fileno())
                _plain_fs_entry(opened, directory=False)
                if (before.st_dev, before.st_ino, before.st_size) != (
                    opened.st_dev,
                    opened.st_ino,
                    opened.st_size,
                ):
                    raise ArtifactError("Video artifact changed while opening", status=409)
                size = opened.st_size
                if size <= 0:
                    raise ArtifactError("Video artifact is empty", status=409)
                cache_key = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
                with _V8_ETAG_LOCK:
                    cached_etag = _V8_ETAG_CACHE.get(cache_key)
                if cached_etag is None:
                    hasher = hashlib.sha256()
                    while chunk := stream.read(1024 * 1024):
                        hasher.update(chunk)
                    cached_etag = f'"{hasher.hexdigest()}"'
                    with _V8_ETAG_LOCK:
                        if len(_V8_ETAG_CACHE) >= _V8_ETAG_CACHE_MAX:
                            _V8_ETAG_CACHE.clear()
                        _V8_ETAG_CACHE[cache_key] = cached_etag
                etag = cached_etag

                range_header = self.headers.get("Range")
                if self.command == "HEAD" or len(self.headers.get_all("Range", [])) != 1:
                    range_header = None
                validators = self.headers.get_all("If-Range", [])
                if validators and (len(validators) != 1 or validators[0] != etag):
                    range_header = None
                try:
                    selected = byte_range(range_header, size)
                except UnsatisfiableRange:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("ETag", etag)
                    self.send_header("Cache-Control", "no-store")
                    if as_preview:
                        self.send_header("X-HawEdit-Artifact-State", "private-preview")
                    self.end_headers()
                    return
                start, end = selected if selected is not None else (0, size - 1)
                self.send_response(206 if selected is not None else 200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(end - start + 1))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("ETag", etag)
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                if as_preview:
                    self.send_header("X-HawEdit-Artifact-State", "private-preview")
                if download_name:
                    self.send_header(
                        "Content-Disposition", f'attachment; filename="{download_name}"'
                    )
                if selected is not None:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.end_headers()
                if self.command != "HEAD":
                    if isinstance(self.connection, socket.socket):
                        self.connection.settimeout(60)
                    stream.seek(start)
                    remaining = end - start + 1
                    while remaining:
                        chunk = stream.read(min(65536, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
        except (ConnectionResetError, BrokenPipeError, TimeoutError):
            return
        except ArtifactError as exc:
            self._json_reply(exc.status, {"error": str(exc), "code": "preview_evidence_refused"})
        except FileNotFoundError:
            self._json_reply(404, {"error": "Requested video artifact was not found"})
        except OSError:
            self._json_reply(503, {"error": "Video artifact storage is unavailable"})

    def _serve_v8_bytes(
        self,
        data: bytes,
        etag_hex: str,
        content_type: str,
        *,
        download_name: str | None = None,
    ) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("ETag", f'"{etag_hex}"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _serve_v8_review_sheet(self, raw_job_id: str) -> None:
        try:
            job_id = unquote(raw_job_id, errors="strict")
            validate_media_id(job_id)
        except (UnicodeError, ValueError):
            self._json_reply(400, {"error": "Malformed studio job identifier"})
            return
        v8_meta = self._v8_report_data(job_id)
        candidates: list[tuple[str, ...]] = []
        if v8_meta and isinstance(v8_meta.get("review_sheet"), str):
            candidates.append(tuple(v8_meta["review_sheet"].split("/")))
        candidates.extend([("v8", "client-review.html"), ("client-review.html",)])
        last_exc: ArtifactError | None = None
        for rel_parts in candidates:
            if not rel_parts or rel_parts[-1] != "client-review.html":
                continue
            try:
                data, digest = _read_safe_job_file_bytes(
                    JOB_MANAGER._jobs_dir, job_id, rel_parts, max_bytes=_V8_SMALL_ARTIFACT_LIMIT
                )
                parent_parts = rel_parts[:-1]
                base_suffix = (
                    "/".join(quote(part, safe="") for part in parent_parts) + "/"
                    if parent_parts
                    else ""
                )
                base_href = f"/api/jobs/{quote(job_id, safe='')}/artifacts/{base_suffix}"
                html_text = data.decode("utf-8", errors="replace")
                base_tag = f'<base href="{base_href}">'
                if "<head>" in html_text and "<base " not in html_text:
                    html_text = html_text.replace("<head>", f"<head>\n  {base_tag}", 1)
                    data = html_text.encode("utf-8")
                    digest = hashlib.sha256(data).hexdigest()
                self._serve_v8_bytes(data, digest, "text/html; charset=utf-8")
                return
            except ArtifactError as exc:
                last_exc = exc
                if exc.status != 404:
                    break
        status = last_exc.status if last_exc is not None else 404
        msg = str(last_exc) if last_exc is not None else "Client review sheet not found"
        self._json_reply(status, {"error": msg})

    def _serve_v8_clip_artifact(
        self, raw_job_id: str, raw_clip_id: str, raw_kind: str, *, as_preview: bool = False
    ) -> None:
        try:
            job_id = unquote(raw_job_id, errors="strict")
            clip_id = unquote(raw_clip_id, errors="strict")
            kind_key = unquote(raw_kind, errors="strict").strip().lower()
            validate_media_id(job_id)
            validate_media_id(clip_id)
        except (UnicodeError, ValueError):
            self._json_reply(400, {"error": "Malformed studio identifier encoding"})
            return
        spec = _V8_ARTIFACT_KINDS.get(kind_key)
        if spec is None:
            self._json_reply(400, {"error": f"Unsupported V8 artifact kind: {kind_key!r}"})
            return
        canonical_kind, content_type = spec
        v8_meta = self._v8_report_data(job_id)
        clips_map = v8_meta.get("clips") if isinstance(v8_meta, dict) else None
        clip_artifacts = clips_map.get(clip_id) if isinstance(clips_map, dict) else None
        rel_str = clip_artifacts.get(canonical_kind) if isinstance(clip_artifacts, dict) else None
        if not isinstance(rel_str, str) or not rel_str:
            self._json_reply(404, {"error": "Requested V8 clip artifact was not found"})
            return
        rel_parts = tuple(rel_str.split("/"))
        if canonical_kind in {"mp4", "social_zip"}:
            self._stream_safe_v8_artifact(
                job_id,
                rel_parts,
                content_type=content_type,
                as_preview=as_preview,
                download_name=None if as_preview else rel_parts[-1],
            )
            return
        try:
            data, digest = _read_safe_job_file_bytes(
                JOB_MANAGER._jobs_dir, job_id, rel_parts, max_bytes=_V8_SMALL_ARTIFACT_LIMIT
            )
            dl_name = None if canonical_kind == "cover" else rel_parts[-1]
            self._serve_v8_bytes(data, digest, content_type, download_name=dl_name)
        except ArtifactError as exc:
            self._json_reply(exc.status, {"error": str(exc)})

    def _serve_v8_job_artifact(self, raw_job_id: str, raw_segments: list[str]) -> None:
        try:
            job_id = unquote(raw_job_id, errors="strict")
            validate_media_id(job_id)
            rel_parts = tuple(unquote(seg, errors="strict") for seg in raw_segments)
            _validate_safe_rel_parts(rel_parts)
        except (UnicodeError, ValueError, ArtifactError) as exc:
            self._json_reply(400, {"error": f"Refused unsafe artifact path: {exc}"})
            return
        content_type = _content_type_for_v8_filename(rel_parts[-1])
        if content_type is None:
            self._json_reply(400, {"error": "Artifact extension is not allowed"})
            return
        if content_type in {"video/mp4", "application/zip"}:
            self._stream_safe_v8_artifact(
                job_id, rel_parts, content_type=content_type, download_name=rel_parts[-1]
            )
            return
        try:
            data, digest = _read_safe_job_file_bytes(
                JOB_MANAGER._jobs_dir, job_id, rel_parts, max_bytes=_V8_SMALL_ARTIFACT_LIMIT
            )
            dl_name = (
                None if content_type in {"image/png", "text/html; charset=utf-8"} else rel_parts[-1]
            )
            self._serve_v8_bytes(data, digest, content_type, download_name=dl_name)
        except ArtifactError as exc:
            self._json_reply(exc.status, {"error": str(exc)})

    def _serve_preview(self, job_id: str, clip_id: str) -> None:
        job_doc = JOB_MANAGER.get_job(job_id)
        opts = job_doc.get("options") if isinstance(job_doc, dict) else None
        is_v8_job = isinstance(opts, dict) and opts.get("engine") == "v8"
        if is_v8_job:
            self._serve_v8_clip_artifact(job_id, clip_id, "mp4", as_preview=True)
            return
        if job_doc is None:
            try:
                validate_media_id(job_id)
            except ValueError:
                self._json_reply(400, {"error": "Malformed studio identifier encoding"})
                return
            if self._v8_report_data(job_id) is not None:
                self._serve_v8_clip_artifact(job_id, clip_id, "mp4", as_preview=True)
                return
            self._json_reply(404, {"error": "Job not found"})
            return
        if self._v8_report_data(job_id) is not None:
            self._serve_v8_clip_artifact(job_id, clip_id, "mp4", as_preview=True)
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

        if path == "/api/v8/doctor":
            self._serve_v8_doctor()
            return

        if path == "/api/v8/presets":
            self._serve_v8_presets()
            return

        components = path.split("/")
        if (
            len(components) == 5
            and components[1:3] == ["api", "jobs"]
            and components[4] == "events"
        ):
            self._serve_job_events(components[3])
            return

        if (
            len(components) == 5
            and components[1:3] == ["api", "jobs"]
            and components[4] == "review.html"
        ):
            self._serve_v8_review_sheet(components[3])
            return

        if (
            len(components) >= 6
            and components[1:3] == ["api", "jobs"]
            and components[4] == "artifacts"
        ):
            self._serve_v8_job_artifact(components[3], components[5:])
            return

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

        if (
            len(components) == 7
            and components[1:3] == ["api", "jobs"]
            and components[4] == "clips"
            and components[6] == "cover.png"
        ):
            self._serve_v8_clip_artifact(components[3], components[5], "cover")
            return

        if (
            len(components) == 8
            and components[1:3] == ["api", "jobs"]
            and components[4] == "clips"
            and components[6] == "artifacts"
        ):
            self._serve_v8_clip_artifact(components[3], components[5], components[7])
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
            if history["available"] and isinstance(history.get("jobs"), list):
                history["jobs"] = [
                    JOB_MANAGER.get_live_job(str(row["job_id"])) or row for row in history["jobs"]
                ]
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
                job_id = unquote(components[3], errors="strict")
                validate_media_id(job_id)
                live = JOB_MANAGER.get_live_job(job_id)
                if live is not None:
                    self._json_reply(200, live)
                    return
                self._json_reply(200, read_historical_job(JOB_MANAGER._jobs_dir, job_id))
            except HistoryError as exc:
                self._json_reply(exc.status, {"error": str(exc), "code": exc.code})
            except (UnicodeError, ValueError):
                self._json_reply(400, {"error": "Malformed studio identifier encoding"})
            return

        if path == "/api/status":
            history = read_history(JOB_MANAGER._jobs_dir)
            if protected_studio_enabled():
                payload: dict[str, Any] = {
                    "status": "unavailable",
                    "runner_ready": False,
                    "code": "studio_runner_unavailable",
                    "error": (
                        "The protected studio producer worker is not connected; no new job can run."
                    ),
                    "active_job": None,
                    "latest_reel": None,
                }
            else:
                active = JOB_MANAGER.active_job()
                payload = {
                    "status": "running" if active is not None else "ready",
                    "runner_ready": True,
                    "active_job": active,
                    "latest_reel": JOB_MANAGER.latest_completed_reel(),
                }
            payload.update(
                {
                    "historical_job_count": len(history["jobs"])
                    if history["available"] and not history["truncated"]
                    else None,
                    "history_available": history["available"],
                    "history_truncated": history["truncated"],
                    "history_diagnostics": history["diagnostics"],
                    "history_verified": False,
                }
            )
            self._json_reply(200 if history["available"] else 503, payload)
            return

        self._json_reply(404, {"error": "Unknown studio route; filesystem access is refused"})

    def _serve_job_events(self, raw_job_id: str) -> None:
        try:
            job_id = unquote(raw_job_id, errors="strict")
            validate_media_id(job_id)
        except (UnicodeError, ValueError):
            self._json_reply(400, {"error": "Malformed studio identifier encoding"})
            return
        is_live = JOB_MANAGER.is_live_job(job_id)
        hist: dict[str, Any] | None = None
        if not is_live:
            try:
                hist = read_historical_job(JOB_MANAGER._jobs_dir, job_id, include_candidates=False)
            except HistoryError as exc:
                self._json_reply(exc.status, {"error": str(exc), "code": exc.code})
                return

        self.close_connection = True
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command == "HEAD":
            return

        try:
            if not is_live and hist is not None:
                frame = (
                    f"id: 1\nevent: {hist['status']}\n"
                    f"data: {json.dumps(hist, ensure_ascii=False)}\n\n"
                ).encode()
                self.wfile.write(frame)
                self.wfile.flush()
                return

            cursor = 0
            last_write = time.monotonic()
            while True:
                events, terminal = JOB_MANAGER.read_events_since(job_id, cursor, timeout=1.0)
                for item in events:
                    frame = (
                        f"id: {item['seq']}\nevent: {item['event']}\n"
                        f"data: {json.dumps(item['data'], ensure_ascii=False)}\n\n"
                    ).encode()
                    self.wfile.write(frame)
                    self.wfile.flush()
                    cursor = int(item["seq"])
                    last_write = time.monotonic()
                if terminal:
                    break
                if not events and (time.monotonic() - last_write) >= _SSE_KEEPALIVE_INTERVAL_S:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    last_write = time.monotonic()
        except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
            return


class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def run_web_server(
    port: int = 8080,
    host: str = "127.0.0.1",
    *,
    protected_studio: bool | None = None,
) -> None:
    """Run the HawEdit local web dashboard server."""
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("The local studio requires a supported loopback bind host")
    if protected_studio is not None:
        os.environ[PROTECTED_STUDIO_ENV] = "1" if protected_studio else "0"
    global JOB_MANAGER, UPLOAD_STORE
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
        if JOB_MANAGER._jobs_dir == ROOT / "work" / "jobs":
            JOB_MANAGER = JobManager(private_root.child("jobs", create=True).path)
    use_utf8_streams()
    server_address = (host, port)
    with ThreadingTCPServer(server_address, HawEditWebHandler) as httpd:
        print(f"HawEdit Web Dashboard running at http://{host}:{port}/")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")


def _parse_web_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the HawEdit local web dashboard server.")
    parser.add_argument("positional_port", nargs="?", type=int)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--protected-studio", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    parsed = _parse_web_args()
    selected_port = parsed.port if parsed.port is not None else (parsed.positional_port or 8080)
    run_web_server(
        selected_port,
        host=parsed.host,
        protected_studio=True if parsed.protected_studio else None,
    )
