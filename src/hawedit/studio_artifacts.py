"""Manifest-bound private preview snapshots, never publication authorization."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from hawedit.environment import EnvironmentAuditError, resolve_installed_hawedit_data
from hawedit.measure import ClipMeasurement
from hawedit.studio_uploads import DEFAULT_MAX_BYTES
from hawedit.transcripts import validate_media_id

FONT_SHA256 = "696249a2c74b39ffdef55de4df2809c5b639d3ff80d618d8160a095d2fd49dca"
_RECORD_LIMIT = 2 * 1024**2
_MEMORY_LIMIT = 8 * 1024**2
_SNAPSHOTS = threading.BoundedSemaphore(1)


class ArtifactError(RuntimeError):
    def __init__(self, message: str, *, status: int = 409) -> None:
        super().__init__(message)
        self.status = status


class UnsatisfiableRange(ValueError):
    """A valid single byte range cannot select bytes in this representation."""


@dataclass(frozen=True, slots=True)
class PreviewSnapshot:
    stream: tempfile.SpooledTemporaryFile[bytes]
    size: int
    sha256: str
    duration_ms: int


@dataclass(frozen=True, slots=True)
class RecordSnapshot:
    document: dict[str, Any]
    sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class CandidateArtifactEvidence:
    size_bytes: int
    sha256: str
    duration_ms: int
    artifact_path: str


def _parts(value: object) -> tuple[str, ...]:
    if not isinstance(value, str) or len(value.encode("utf-8")) > 1024:
        raise ArtifactError("Artifact scope evidence is invalid")
    parts = tuple(value.split("/"))
    try:
        for part in parts:
            validate_media_id(part)
    except ValueError as exc:
        raise ArtifactError("Artifact scope evidence is invalid") from exc
    return parts


def _metadata(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        getattr(info, "st_birthtime_ns", info.st_ctime_ns) if os.name == "nt" else info.st_ctime_ns,
        info.st_nlink,
    )


def _plain(info: os.stat_result, *, directory: bool) -> None:
    reparse = bool(getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    valid = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if reparse or not valid or (not directory and info.st_nlink != 1):
        raise ArtifactError("Linked or non-regular artifact evidence is refused")


def _scoped(root: Path, parts: tuple[str, ...]) -> Path:
    path = root.absolute()
    _plain(path.lstat(), directory=True)
    for index, part in enumerate(parts):
        path = path / part
        _plain(path.lstat(), directory=index < len(parts) - 1)
    return path


@contextmanager
def _regular(root: Path, parts: tuple[str, ...]) -> Iterator[tuple[BinaryIO, Path, os.stat_result]]:
    path = _scoped(root, parts)
    before = path.lstat()
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        _plain(opened, directory=False)
        if _metadata(before) != _metadata(opened):
            raise ArtifactError("Artifact evidence changed while opening")
        yield stream, path, opened
        if _metadata(opened) != _metadata(os.fstat(stream.fileno())):
            raise ArtifactError("Artifact evidence changed while reading")
        current = _scoped(root, parts).lstat()
        if _metadata(opened) != _metadata(current):
            raise ArtifactError("Artifact evidence changed while reading")


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ArtifactError("Duplicate JSON artifact evidence is refused")
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    raise ArtifactError("Nonfinite JSON artifact evidence is refused")


def _record_snapshot(
    root: Path, parts: tuple[str, ...]
) -> tuple[RecordSnapshot, Path, os.stat_result]:
    with _regular(root, parts) as (stream, path, info):
        if not 0 < info.st_size <= _RECORD_LIMIT:
            raise ArtifactError("Artifact record evidence exceeds the size limit")
        data = stream.read(_RECORD_LIMIT + 1)
        if len(data) != info.st_size:
            raise ArtifactError("Artifact record evidence changed while reading")
        try:
            document = json.loads(
                data.decode("utf-8"), object_pairs_hook=_unique, parse_constant=_nonfinite
            )
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise ArtifactError("Malformed JSON artifact evidence is refused") from exc
        if not isinstance(document, dict):
            raise ArtifactError("Artifact record evidence must be an object")
    return RecordSnapshot(document, hashlib.sha256(data).hexdigest(), len(data)), path, info


def _record(root: Path, parts: tuple[str, ...]) -> tuple[dict[str, Any], Path, os.stat_result]:
    record, path, info = _record_snapshot(root, parts)
    return record.document, path, info


def read_studio_record(jobs_root: Path, job_id: str, kind: str) -> RecordSnapshot:
    """Read a stable bounded job/report snapshot, not an arbitrary filesystem path."""
    try:
        validate_media_id(job_id)
        if kind not in {"job", "report"}:
            raise ArtifactError("Unsupported studio record kind")
        record, _, _ = _record_snapshot(jobs_root, (job_id, f"{kind}.json"))
        return record
    except FileNotFoundError as exc:
        raise ArtifactError("Studio record is missing", status=404) from exc
    except OSError as exc:
        raise ArtifactError("Studio record storage is unavailable", status=503) from exc
    except ValueError as exc:
        raise ArtifactError("Studio record scope is invalid") from exc


def _clip_directory(report: dict[str, Any], clip_id: str) -> tuple[str, ...]:
    manifest = report.get("episode_manifest")
    if not isinstance(manifest, dict) or not isinstance(manifest.get("clips"), list):
        raise ArtifactError("A private candidate manifest is required", status=404)
    rows = manifest["clips"]
    if len(rows) > 1000:
        raise ArtifactError("Candidate manifest evidence exceeds the entry limit")
    ids: set[str] = set()
    selected = None
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("clip_id"), str):
            raise ArtifactError("Candidate manifest evidence is invalid")
        current = row["clip_id"]
        validate_media_id(current)
        if current in ids:
            raise ArtifactError("Duplicate candidate manifest evidence is refused")
        ids.add(current)
        if current == clip_id:
            selected = _parts(row.get("delivery_dir"))
    if selected is None:
        raise ArtifactError("Candidate is not listed in the job manifest", status=404)
    return selected


def _measurement_evidence(record: dict[str, Any]) -> tuple[int, str, int]:
    measurement = ClipMeasurement.from_dict(record)
    size, digest = measurement.file.size_bytes, measurement.file.sha256
    duration = measurement.video.duration_ms
    if (
        type(measurement.schema) is not int
        or measurement.schema != 1
        or type(size) is not int
        or not 0 < size <= DEFAULT_MAX_BYTES
        or not isinstance(digest, str)
        or re.fullmatch("[0-9a-f]{64}", digest) is None
        or type(duration) is not int
        or duration <= 0
    ):
        raise ArtifactError("Candidate measurement evidence is invalid")
    return size, digest, duration


def inspect_review_candidate(
    work_dir: Path, clip_id: str, media_path: Path
) -> CandidateArtifactEvidence:
    """Bind ready projection to stable private files; not fresh media or review approval."""
    try:
        validate_media_id(clip_id)
        root = work_dir.absolute()
        parts = ("review", clip_id, f"{clip_id}.mp4")
        if media_path.absolute() != root.joinpath(*parts):
            raise ArtifactError("Candidate artifact is outside its exact private review scope")
        record, measurement_path, measurement_info = _record_snapshot(
            root, ("review", clip_id, f"{clip_id}.measured.json")
        )
        size, digest, duration = _measurement_evidence(record.document)
        hasher = hashlib.sha256()
        copied = 0
        deadline = time.monotonic() + 60
        with _regular(root, parts) as (stream, _, info):
            if info.st_size != size:
                raise ArtifactError("Candidate bytes do not match measurement evidence")
            while chunk := stream.read(min(1024**2, size - copied + 1)):
                copied += len(chunk)
                if copied > size or time.monotonic() > deadline:
                    raise ArtifactError("Candidate evidence exceeds inspection bounds")
                hasher.update(chunk)
        if copied != size or hasher.hexdigest() != digest:
            raise ArtifactError("Candidate bytes do not match measurement evidence")
        repeated, _, current = _record_snapshot(
            root, tuple(measurement_path.relative_to(root).parts)
        )
        if repeated.sha256 != record.sha256 or _metadata(current) != _metadata(measurement_info):
            raise ArtifactError("Candidate measurement changed during inspection")
        return CandidateArtifactEvidence(size, digest, duration, "/".join(parts))
    except ArtifactError:
        raise
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError, AttributeError) as exc:
        raise ArtifactError("Candidate artifact evidence is invalid") from exc
    except OSError as exc:
        raise ArtifactError("Candidate evidence storage is unavailable") from exc


@contextmanager
def open_preview(jobs_root: Path, job_id: str, clip_id: str) -> Iterator[PreviewSnapshot]:
    """Copy/hash one declared private MP4 before serving any bytes; no filename search."""
    if not _SNAPSHOTS.acquire(timeout=5):
        raise ArtifactError("Preview preparation is busy; retry shortly", status=503)
    prepared = False
    try:
        validate_media_id(job_id)
        validate_media_id(clip_id)
        root = jobs_root.absolute()
        report, report_path, report_info = _record(root, (job_id, "report.json"))
        directory = (job_id, *_clip_directory(report, clip_id))
        record, measurement_path, measurement_info = _record(
            root, (*directory, f"{clip_id}.measured.json")
        )
        size, digest, duration = _measurement_evidence(record)
        job_root = root / job_id
        if shutil.disk_usage(job_root).free < max(0, size - _MEMORY_LIMIT) + 16 * 1024**2:
            raise ArtifactError("Insufficient storage for a verified preview snapshot", status=503)
        # Serve the hash-verified copy, not an original that can change after validation.
        with tempfile.SpooledTemporaryFile(
            max_size=_MEMORY_LIMIT, mode="w+b", dir=str(job_root)
        ) as snapshot:
            hasher = hashlib.sha256()
            deadline = time.monotonic() + 60
            copied = 0
            with _regular(root, (*directory, f"{clip_id}.mp4")) as (source, _, info):
                if info.st_size != size:
                    raise ArtifactError("Candidate bytes do not match measurement evidence")
                while chunk := source.read(min(1024**2, size - copied + 1)):
                    copied += len(chunk)
                    if copied > size or time.monotonic() > deadline:
                        raise ArtifactError("Candidate evidence exceeds preview preparation bounds")
                    hasher.update(chunk)
                    snapshot.write(chunk)
            if copied != size or hasher.hexdigest() != digest:
                raise ArtifactError("Candidate bytes do not match measurement evidence")
            for path, original in (
                (report_path, report_info),
                (measurement_path, measurement_info),
            ):
                current = _scoped(root, tuple(path.relative_to(root).parts)).lstat()
                if _metadata(current) != _metadata(original):
                    raise ArtifactError("Candidate evidence changed during preview preparation")
            snapshot.seek(0)
            prepared = True
            yield PreviewSnapshot(snapshot, size, digest, duration)
    except ArtifactError:
        raise
    except FileNotFoundError as exc:
        raise ArtifactError("Requested preview evidence is missing", status=404) from exc
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError, AttributeError) as exc:
        raise ArtifactError("Candidate artifact evidence is invalid") from exc
    except OSError as exc:
        if prepared:
            raise
        raise ArtifactError("Preview evidence storage is unavailable", status=503) from exc
    finally:
        _SNAPSHOTS.release()


def font_bytes(root: Path) -> bytes:
    try:
        if not (root / "pyproject.toml").is_file() and not (root / "assets").exists():
            installed = resolve_installed_hawedit_data("share/hawedit/assets/fonts/Vazirmatn.ttf")
            root = installed.parents[2]
        with _regular(root, ("assets", "fonts", "Vazirmatn.ttf")) as (stream, _, info):
            if not 0 < info.st_size <= _RECORD_LIMIT:
                raise ArtifactError("Local font evidence exceeds the asset limit", status=503)
            data = stream.read(_RECORD_LIMIT + 1)
            if len(data) != info.st_size or hashlib.sha256(data).hexdigest() != FONT_SHA256:
                raise ArtifactError(
                    "Local font evidence does not match shipped provenance", status=503
                )
        return data
    except (OSError, EnvironmentAuditError) as exc:
        raise ArtifactError("Local font storage is unavailable", status=503) from exc


def byte_range(value: str | None, size: int) -> tuple[int, int] | None:
    """Ignore unsupported/malformed ranges; distinguish valid unsatisfiable ranges."""
    if value is None or len(value) > 256:
        return None
    match = re.fullmatch(r"bytes=([0-9]*)-([0-9]*)", value.strip())
    if match is None or not any(match.groups()):
        return None
    first, last = match.groups()
    if not first:
        suffix = int(last)
        if suffix == 0:
            raise UnsatisfiableRange
        return max(0, size - suffix), size - 1
    start = int(first)
    end = int(last) if last else size - 1
    if last and end < start:
        return None
    if start >= size:
        raise UnsatisfiableRange
    return start, min(end, size - 1)
