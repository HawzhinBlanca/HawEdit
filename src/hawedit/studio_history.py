"""Read-only historical projections; original flags cannot authorize work or publication."""

from __future__ import annotations

import hashlib
import math
import os
import re
import stat
import sys
import time
from pathlib import Path, PureWindowsPath
from typing import Any, cast
from urllib.parse import quote

from hawedit.studio_artifacts import ArtifactError, read_studio_record
from hawedit.transcripts import validate_media_id

__all__ = ["HistoryError", "read_historical_job", "read_history"]

_REQUIRED = {
    "job_id",
    "source",
    "status",
    "stage",
    "stage_index",
    "progress_percent",
    "created_at",
    "updated_at",
    "headline",
    "clips",
}
_OPTIONAL = {"error", "client_token", "options"}
_STATES = {
    "queued",
    "running",
    "awaiting-review",
    "partially-completed",
    "completed",
    "failed",
    "cancelled",
    "interrupted",
    "unverified-historical",
}


class HistoryError(RuntimeError):
    def __init__(self, message: str, *, status: int = 409) -> None:
        super().__init__(message)
        self.status = status
        self.code = "history_storage_unavailable" if status == 503 else "history_record_refused"


def _root(root: Path) -> None:
    try:
        info = root.lstat()
        if not stat.S_ISDIR(info.st_mode) or (
            sys.platform == "win32"
            and getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise HistoryError("Historical storage must be an unlinked directory", status=503)
    except OSError as exc:
        raise HistoryError("Historical storage is unavailable", status=503) from exc


def _text(value: object, *, limit: int = 4096) -> str:
    if not isinstance(value, str) or len(value) > limit or "\x00" in value:
        raise HistoryError("Historical text fields are invalid")
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise HistoryError("Historical text fields must be valid Unicode") from exc
    return value


def _timestamp(value: object) -> float:
    if type(value) not in {int, float}:
        raise HistoryError("Historical timestamps must be finite nonnegative numbers")
    try:
        number = float(cast(int | float, value))
    except OverflowError as exc:
        raise HistoryError("Historical timestamp exceeds the numeric bound") from exc
    if not math.isfinite(number) or number < 0:
        raise HistoryError("Historical timestamps must be finite nonnegative numbers")
    return number


def _validate_record(data: dict[str, Any], job_id: str) -> None:
    if not data.keys() >= _REQUIRED or data.keys() - (_REQUIRED | _OPTIONAL):
        raise HistoryError("Historical record has missing or unsupported fields")
    if data["job_id"] != job_id:
        raise HistoryError("Historical record does not match its job directory")
    if not isinstance(data["status"], str) or data["status"] not in _STATES:
        raise HistoryError("Historical job state is unsupported")
    for key in ("source", "headline", "stage"):
        _text(data[key])
    if not data["source"] or not data["stage"]:
        raise HistoryError("Historical source and stage must be nonempty")
    for key in ("stage_index", "progress_percent"):
        if type(data[key]) is not int or not 0 <= data[key] <= 100:
            raise HistoryError("Historical progress fields are invalid")
    for key in ("created_at", "updated_at"):
        _timestamp(data[key])
    if (
        not isinstance(data["clips"], list)
        or len(data["clips"]) > 1000
        or any(not isinstance(clip, dict) for clip in data["clips"])
        or not isinstance(data.get("options", {}), dict)
    ):
        raise HistoryError("Historical clip/options fields are invalid")
    if data.get("error") is not None:
        _text(data["error"], limit=16384)
    if data.get("client_token") is not None:
        _text(data["client_token"], limit=128)


def _diagnostic(job_id: str | None, code: str, message: str) -> dict[str, Any]:
    return {"job_id": job_id, "code": code, "message": message}


def _candidates(
    root: Path, job_id: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    try:
        report = read_studio_record(root, job_id, "report").document
        manifest = report.get("episode_manifest")
        if not isinstance(manifest, dict):
            raise HistoryError("A scoped private candidate manifest is required")
        rows = manifest.get("clips")
        if not isinstance(rows, list) or len(rows) > 1000:
            raise HistoryError("Private candidate manifest entries are invalid")
        encoded_job_id = quote(job_id, safe="")
        v8_ep = report.get("v8_episode") if report.get("engine") == "v8" else None
        v8_clips_map = v8_ep.get("clips") if isinstance(v8_ep, dict) else None
        v8_meta_map = v8_ep.get("clip_meta") if isinstance(v8_ep, dict) else None
        review_sheet_url: str | None = None
        if isinstance(v8_ep, dict) and isinstance(v8_ep.get("review_sheet"), str):
            raw_review = _text(v8_ep["review_sheet"], limit=512)
            review_parts = [p for p in raw_review.split("/") if p]
            if review_parts and all(p not in {".", ".."} for p in review_parts):
                review_sheet_url = (
                    f"/api/jobs/{encoded_job_id}/artifacts/"
                    f"{'/'.join(quote(p, safe='') for p in review_parts)}"
                )
        ids: set[str] = set()
        clips = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("clip_id"), str):
                raise HistoryError("Private candidate ID is invalid")
            clip_id = row["clip_id"]
            validate_media_id(clip_id)
            if clip_id in ids:
                raise HistoryError("Private candidate IDs must be unique")
            ids.add(clip_id)
            directory = _text(row.get("delivery_dir"), limit=1024)
            for part in directory.split("/"):
                validate_media_id(part)
            title = row.get("title_ckb")
            if title is not None:
                _text(title)
            encoded_cid = quote(clip_id, safe="")
            clip_entry: dict[str, Any] = {
                "clip_id": clip_id,
                "headline": title,
                "state": "unverified",
                "duration_s": None,
                "hook_score": None,
                "sha256": None,
                "preview_url": (f"/api/jobs/{encoded_job_id}/clips/{encoded_cid}/preview"),
                "preview_verified": False,
                "publication_verified": False,
            }
            if isinstance(v8_clips_map, dict) and isinstance(v8_clips_map.get(clip_id), dict):
                rel_map = v8_clips_map[clip_id]
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
                    if isinstance(rel_map.get(dl_kind), str) and rel_map[dl_kind]:
                        download_urls[dl_kind] = (
                            f"/api/jobs/{encoded_job_id}/clips/{encoded_cid}/artifacts/{dl_kind}"
                        )
                clip_entry["download_urls"] = download_urls
                if isinstance(rel_map.get("cover"), str) and rel_map["cover"]:
                    clip_entry["cover_url"] = (
                        f"/api/jobs/{encoded_job_id}/clips/{encoded_cid}/cover.png"
                    )
                if review_sheet_url is not None:
                    clip_entry["review_sheet_url"] = review_sheet_url
            if isinstance(v8_meta_map, dict) and isinstance(v8_meta_map.get(clip_id), dict):
                meta = v8_meta_map[clip_id]
                if isinstance(meta.get("editorial_reason"), str):
                    clip_entry["editorial_reason"] = _text(meta["editorial_reason"])
                quotes = meta.get("source_quotes")
                if isinstance(quotes, list):
                    clip_entry["source_quotes"] = [
                        q
                        for q in quotes
                        if isinstance(q, dict)
                        and type(q.get("in_ms")) is int
                        and type(q.get("out_ms")) is int
                        and isinstance(q.get("quote"), str)
                        and isinstance(q.get("words", []), list)
                        and all(
                            isinstance(w, dict)
                            and type(w.get("index")) is int
                            and isinstance(w.get("original"), str)
                            for w in q.get("words", [])
                        )
                    ]
                if isinstance(meta.get("hook_title_ckb"), str):
                    clip_entry["hook_title_ckb"] = _text(meta["hook_title_ckb"])
                if type(meta.get("duration_s")) in {int, float} and math.isfinite(
                    float(meta["duration_s"])
                ):
                    clip_entry["duration_s"] = round(float(meta["duration_s"]), 2)
                if type(meta.get("face_share")) in {int, float} and math.isfinite(
                    float(meta["face_share"])
                ):
                    clip_entry["face_share"] = round(float(meta["face_share"]), 4)
                if type(meta.get("grill_passed")) is bool:
                    clip_entry["grill_passed"] = meta["grill_passed"]
                if isinstance(meta.get("grill_summary"), str):
                    clip_entry["grill_summary"] = _text(meta["grill_summary"])
                if isinstance(meta.get("sha256"), str) and meta["sha256"]:
                    clip_entry["sha256"] = _text(meta["sha256"], limit=128)
                    if clip_entry["duration_s"] and clip_entry["duration_s"] > 0:
                        clip_entry["preview_verified"] = True
            clips.append(clip_entry)
        return clips, [], review_sheet_url
    except (ArtifactError, HistoryError, ValueError) as exc:
        code = (
            "candidate_manifest_missing"
            if isinstance(exc, ArtifactError) and exc.status == 404
            else "candidate_manifest_refused"
        )
        return (
            [],
            [
                _diagnostic(
                    job_id,
                    code,
                    "Private candidate manifest is missing or invalid; "
                    "original evidence is preserved",
                )
            ],
            None,
        )


def read_historical_job(
    jobs_root: Path, job_id: str, *, include_candidates: bool = True
) -> dict[str, Any]:
    _root(jobs_root)
    try:
        validate_media_id(job_id)
    except ValueError as exc:
        raise HistoryError("Invalid historical job ID", status=400) from exc
    try:
        record = read_studio_record(jobs_root, job_id, "job")
    except ArtifactError as exc:
        raise HistoryError(str(exc), status=exc.status) from exc
    data = record.document
    _validate_record(data, job_id)
    recorded_status = data["status"]
    recovery = recorded_status in {"queued", "running", "interrupted"}
    terminal = recorded_status in {"failed", "cancelled", "interrupted"}
    status = "interrupted" if recovery else recorded_status if terminal else "unverified-historical"
    clips, diagnostics, review_sheet_url = (
        _candidates(jobs_root, job_id) if include_candidates else ([], [], None)
    )
    record_out: dict[str, Any] = {
        "job_id": job_id,
        "source": PureWindowsPath(data["source"]).name,
        "headline": data["headline"],
        "status": status,
        "recorded_status": recorded_status,
        "historical": True,
        "record_sha256": record.sha256,
        "record_bytes": record.size_bytes,
        "created_at": _timestamp(data["created_at"]),
        "updated_at": _timestamp(data["updated_at"]),
        "recorded_stage": data["stage"],
        "stage": None,
        "progress_percent": None,
        "work_progress": None,
        "stages": [],
        "clips": clips,
        "diagnostics": diagnostics,
        "publication_verified": False,
        "published_count": 0,
        "recovery_required": recovery,
        "recorded_error_present": bool(data.get("error")),
        "code": "legacy_recovery_required" if recovery else "historical_evidence_unverified",
        "error": "Recovery reconciliation is required before retrying this historical job"
        if recovery
        else None,
    }
    source_id = data.get("options", {}).get("episode_source_id")
    if (
        include_candidates
        and isinstance(source_id, str)
        and re.fullmatch("[a-f0-9]{32}", source_id)
    ):
        record_out["options"] = {"episode_source_id": source_id}
    if review_sheet_url is not None:
        record_out["review_sheet_url"] = review_sheet_url
    return record_out


def read_history(jobs_root: Path, *, max_entries: int = 1000) -> dict[str, Any]:
    """Bound enumeration and expose refused entries; never rewrite or re-enqueue originals."""
    if type(max_entries) is not int or not 1 <= max_entries <= 1000:
        raise ValueError("History entry limit must be an integer from 1 to 1000")
    jobs: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    result = {
        "schema": 1,
        "available": True,
        "truncated": False,
        "jobs": jobs,
        "diagnostics": diagnostics,
    }
    deadline, read_bytes = time.monotonic() + 5, 0
    try:
        _root(jobs_root)
        with os.scandir(jobs_root) as entries:
            for index, entry in enumerate(entries):
                if index >= max_entries or read_bytes >= 8 * 1024**2 or time.monotonic() > deadline:
                    result["truncated"] = True
                    diagnostics.append(
                        _diagnostic(
                            None,
                            "history_scan_limit",
                            "Historical scan is partial; history reduction requires owner approval",
                        )
                    )
                    break
                job_id: str | None = None
                try:
                    validate_media_id(entry.name)
                    job_id = entry.name
                    if not entry.is_dir(follow_symlinks=False):
                        raise HistoryError(
                            "Unrecognized historical storage entry is preserved but refused"
                        )
                    try:
                        record_size = (jobs_root / job_id / "job.json").lstat().st_size
                        read_bytes += min(max(0, record_size), 2 * 1024**2)
                    except OSError:
                        read_bytes += 2 * 1024**2
                    job = read_historical_job(jobs_root, job_id, include_candidates=False)
                    jobs.append(job)
                except (HistoryError, ValueError, OSError) as exc:
                    code = exc.code if isinstance(exc, HistoryError) else "history_record_refused"
                    diagnostic = _diagnostic(
                        job_id,
                        code,
                        "Historical entry is missing, malformed or linked; "
                        "original bytes are preserved",
                    )
                    diagnostic["entry_sha256"] = hashlib.sha256(
                        entry.name.encode("utf-8", errors="surrogatepass")
                    ).hexdigest()
                    diagnostics.append(diagnostic)
    except (HistoryError, OSError):
        result["available"] = False
        diagnostics.append(
            _diagnostic(
                None,
                "history_storage_unavailable",
                "Historical storage is unavailable; no complete history is asserted",
            )
        )
    jobs.sort(key=lambda job: (job["created_at"], job["job_id"]), reverse=True)
    return result
