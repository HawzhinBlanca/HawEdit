"""Read-only historical projections; original flags cannot authorize work or publication."""

from __future__ import annotations

import hashlib
import math
import os
import stat
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
            getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
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


def _candidates(root: Path, job_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        report = read_studio_record(root, job_id, "report").document
        manifest = report.get("episode_manifest")
        if not isinstance(manifest, dict):
            raise HistoryError("A scoped private candidate manifest is required")
        rows = manifest.get("clips")
        if not isinstance(rows, list) or len(rows) > 1000:
            raise HistoryError("Private candidate manifest entries are invalid")
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
            clips.append(
                {
                    "clip_id": clip_id,
                    "headline": title,
                    "state": "unverified",
                    "duration_s": None,
                    "hook_score": None,
                    "sha256": None,
                    "preview_url": (
                        f"/api/jobs/{quote(job_id, safe='')}/clips/"
                        f"{quote(clip_id, safe='')}/preview"
                    ),
                    "preview_verified": False,
                    "publication_verified": False,
                }
            )
        return clips, []
    except (ArtifactError, HistoryError, ValueError) as exc:
        code = (
            "candidate_manifest_missing"
            if isinstance(exc, ArtifactError) and exc.status == 404
            else "candidate_manifest_refused"
        )
        return [], [
            _diagnostic(
                job_id,
                code,
                "Private candidate manifest is missing or invalid; original evidence is preserved",
            )
        ]


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
    clips, diagnostics = _candidates(jobs_root, job_id) if include_candidates else ([], [])
    return {
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
