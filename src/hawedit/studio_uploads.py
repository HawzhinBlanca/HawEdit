"""Two-phase local uploads: only finalized, probed bytes become runnable sources.

Original filenames are display metadata, never storage paths. Each reservation is isolated;
a ready record is committed only after the bytes and probe record have been atomically
published. An interrupted reservation cannot be resolved as a source.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Protocol

from hawedit.atomic_fs import rename_directory_noreplace
from hawedit.captions import ffprobe_for, find_ffmpeg
from hawedit.studio_private import PrivateDirectory, StudioStorageError, write_text_atomic

DEFAULT_MAX_BYTES = 32 * 1024**3
_DEMUXERS = {
    ".mp4": ("mov",),
    ".mov": ("mov",),
    ".m4v": ("mov", "m4v"),
    ".mkv": ("matroska", "webm"),
    ".webm": ("matroska", "webm"),
    ".avi": ("avi",),
    ".ts": ("mpegts",),
}
SUPPORTED_CONTAINERS = frozenset(_DEMUXERS)
_ID = re.compile(r"[a-f0-9]{32}\Z")


class UploadError(ValueError):
    """An upload cannot safely become a source; safe to report to the local creator."""


class ByteReader(Protocol):
    def read(self, size: int = -1, /) -> bytes: ...


def _filename_suffix(filename: object) -> str:
    if (
        not isinstance(filename, str)
        or not filename.strip()
        or len(filename) > 240
        or any(char in filename for char in ("/", "\\", ":", "\x00"))
        or any(ord(char) < 32 for char in filename)
    ):
        raise UploadError("Use a filename, not a server path")
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_CONTAINERS:
        raise UploadError("Unsupported video container")
    return suffix


def _probe(media: Path) -> dict[str, int]:
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        raise UploadError("Media probing unavailable; run hawedit-ffmpeg-setup")
    demuxers = _DEMUXERS[_filename_suffix(media.name)]
    restrictions = [
        "-protocol_whitelist",
        "file",
        "-format_whitelist",
        ",".join(demuxers),
    ]
    try:
        result = subprocess.run(
            [
                str(ffprobe_for(ffmpeg)),
                "-v",
                "error",
                *restrictions,
                "-show_entries",
                "format=duration,format_name:stream=codec_type,width,height",
                "-of",
                "json",
                str(media),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        data = json.loads(result.stdout)
        if not set(data["format"]["format_name"].split(",")).intersection(demuxers):
            raise ValueError("Media container does not match the supported filename")
        video = next(stream for stream in data["streams"] if stream["codec_type"] == "video")
        width, height = int(video["width"]), int(video["height"])
        duration_s = float(data["format"]["duration"])
        if width <= 0 or height <= 0 or not math.isfinite(duration_s) or duration_s <= 0:
            raise ValueError("No usable video dimensions or duration")
        # Metadata alone is not enough: prove a video frame can actually decode.
        decoded = subprocess.run(
            [
                str(ffmpeg),
                "-v",
                "error",
                "-nostdin",
                "-threads",
                "1",
                *restrictions,
                "-i",
                str(media),
                "-map",
                "0:v:0",
                "-frames:v",
                "1",
                "-f",
                "framehash",
                "-",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        frames = list(csv.reader(io.StringIO(decoded.stdout)))
        if not any(
            len(row) == 6 and re.fullmatch(r"[a-f0-9]{64}", row[-1].strip()) and int(row[4]) > 0
            for row in frames
        ):
            raise ValueError("No decoded video frame")
        return {"width": width, "height": height, "duration_ms": round(duration_s * 1000)}
    except (
        OSError,
        subprocess.SubprocessError,
        ValueError,
        KeyError,
        TypeError,
        StopIteration,
    ) as exc:
        raise UploadError(
            "Invalid or unsupported media; a readable video stream is required"
        ) from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class UploadStore:
    """A single-server upload store with bounded reservations and atomic finalization."""

    def __init__(
        self,
        root: Path,
        *,
        max_bytes: int = DEFAULT_MAX_BYTES,
        reserve_bytes: int = 1024**3,
        reservation_seconds: int = 24 * 3600,
    ) -> None:
        if max_bytes <= 0 or reserve_bytes < 0 or reservation_seconds <= 0:
            raise ValueError("Invalid upload storage limits")
        self._storage = PrivateDirectory(root)
        self.root = self._storage.path
        self.max_bytes = max_bytes
        self.reserve_bytes = reserve_bytes
        self.reservation_seconds = reservation_seconds
        self._lock = threading.Lock()
        self._active: set[str] = set()
        self._containers = {
            name: self._storage.child(name, create=True)
            for name in ("tickets", "incoming", "sources")
        }

    def _verify(self) -> None:
        self._storage.verify()
        if self.root != self._storage.path:
            raise StudioStorageError("Studio upload root binding changed")
        for directory in self._containers.values():
            directory.verify()

    def _ticket_path(self, upload_id: str) -> Path:
        if not _ID.fullmatch(upload_id):
            raise UploadError("Unknown upload ID")
        return self.root / "tickets" / f"{upload_id}.json"

    def _record(self, upload_id: str, *, committed: bool = False) -> dict[str, Any]:
        self._verify()
        try:
            path = self._ticket_path(upload_id)
            directory = self._containers["tickets"]
            if committed:
                directory = self._containers["sources"].child(upload_id)
                path = directory.path / "source.json"
            before = directory.member_identity(path.name)
            with path.open("rb") as stream:
                payload = stream.read(8193)
            if directory.member_identity(path.name) != before:
                raise UploadError("Upload record identity changed while reading")
            self._verify()
            if len(payload) > 8192:
                raise UploadError("Invalid upload record")
            try:
                record = json.loads(payload)
            except ValueError as exc:
                raise UploadError("Invalid upload record JSON") from exc
            if not isinstance(record, dict) or record.get("upload_id") != upload_id:
                raise UploadError("Invalid upload record")
            if type(record.get("size")) is not int or not 0 < record["size"] <= self.max_bytes:
                raise UploadError("Invalid upload size record")
            try:
                suffix = _filename_suffix(record.get("filename"))
            except UploadError as exc:
                raise UploadError("Invalid upload filename record") from exc
            if record.get("suffix") != suffix:
                raise UploadError("Invalid upload container record")
            state = record.get("state")
            if not isinstance(state, str) or state not in {
                "reserved",
                "receiving",
                "ready",
                "failed",
            }:
                raise UploadError("Invalid upload state record")
            expires = record.get("expires_at")
            if (
                isinstance(expires, bool)
                or not isinstance(expires, int | float)
                or not math.isfinite(expires)
                or expires <= 0
            ):
                raise UploadError("Invalid upload reservation record")
            if record["state"] == "ready":
                if record.get("source_id") != upload_id or not isinstance(
                    record.get("sha256"), str
                ):
                    raise UploadError("Invalid finalized source record")
                if not re.fullmatch(r"[a-f0-9]{64}", record["sha256"]):
                    raise UploadError("Invalid finalized source digest")
                for key in ("width", "height", "duration_ms"):
                    if type(record.get(key)) is not int or record[key] <= 0:
                        raise UploadError("Invalid finalized source measurement")
            return record
        except StudioStorageError as exc:
            raise UploadError("Upload record private storage is unsafe or unavailable") from exc
        except (OSError, UnicodeError, OverflowError) as exc:
            raise UploadError("Upload record is missing or unreadable") from exc

    def _write(self, record: dict[str, Any]) -> None:
        self._verify()
        write_text_atomic(self._ticket_path(record["upload_id"]), json.dumps(record))
        self._verify()

    def _reserved(self) -> int:
        self._verify()
        total = 0
        for path in (self.root / "tickets").glob("*.json"):
            record = self._record(path.stem)
            if (
                record.get("state") in {"reserved", "receiving"}
                and record.get("expires_at", 0) > time.time()
            ):
                total += record["size"]
        return total

    def begin(self, filename: str, size: int) -> dict[str, Any]:
        suffix = _filename_suffix(filename)
        if type(size) is not int or not 0 < size <= self.max_bytes:
            raise UploadError(f"Declared size must be between 1 and {self.max_bytes} bytes")
        with self._lock:
            if size + self._reserved() + self.reserve_bytes > shutil.disk_usage(self.root).free:
                raise UploadError("Insufficient free storage space for this upload")
            upload_id = uuid.uuid4().hex
            record = {
                "upload_id": upload_id,
                "filename": filename,
                "size": size,
                "suffix": suffix,
                "state": "reserved",
                "created_at": time.time(),
                "expires_at": time.time() + self.reservation_seconds,
            }
            self._write(record)
        return {"upload_id": upload_id, "size": size, "expires_at": record["expires_at"]}

    def receive(self, upload_id: str, stream: ByteReader, content_length: int) -> dict[str, Any]:
        with self._lock:
            record = self._record(upload_id)
            if record.get("state") != "reserved":
                raise UploadError("Upload already consumed; request a new upload ID")
            if record.get("expires_at", 0) <= time.time():
                raise UploadError("Upload reservation expired; request a new upload ID")
            if type(content_length) is not int or content_length != record["size"]:
                raise UploadError("Content length does not match the declared upload size")
            if content_length + self.reserve_bytes > shutil.disk_usage(self.root).free:
                raise UploadError("Insufficient free storage space for this upload")
            record["state"] = "receiving"
            self._write(record)
            self._active.add(upload_id)
        staging = self.root / "incoming" / upload_id
        target = self.root / "sources" / upload_id
        stage: PrivateDirectory | None = None
        owned: dict[str, tuple[int, int, int]] = {}
        try:
            self._verify()
            stage = self._containers["incoming"].child(upload_id, create=True, exclusive=True)
            media = staging / f"source{record['suffix']}"
            digest = hashlib.sha256()
            remaining = content_length
            with stage.open_new_file(media.name) as output:
                owned[media.name] = stage.member_identity(media.name)
                while remaining:
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise UploadError("Upload interrupted before its declared length")
                    self._verify()
                    stage.verify()
                    if stage.member_identity(media.name) != owned[media.name]:
                        raise StudioStorageError("Studio upload staging media identity changed")
                    output.write(chunk)
                    digest.update(chunk)
                    remaining -= len(chunk)
                output.flush()
                os.fsync(output.fileno())
            stage.verify()
            self._verify()
            measurement = _probe(media)
            stage.verify()
            self._verify()
            record.update(
                {
                    "source_id": upload_id,
                    "sha256": digest.hexdigest(),
                    **measurement,
                    "state": "ready",
                }
            )
            write_text_atomic(staging / "source.json", json.dumps(record))
            owned["source.json"] = stage.member_identity("source.json")
            stage.verify()
            self._verify()
            rename_directory_noreplace(staging, target)
            self._containers["sources"].sync()
            self._verify()
            with self._lock:
                self._write(record)
            return self.describe(upload_id)
        except BaseException:
            with self._lock:
                record["state"] = "failed"
                self._write(record)
            # A moved/published/lost namespace is not permission to clean a replacement.
            if stage is not None:
                try:
                    self._verify()
                    stage.verify()
                    for name, identity in owned.items():
                        stage.remove_owned(name, identity)
                    stage.verify()
                    stage.path.rmdir()
                except (OSError, StudioStorageError):
                    pass
            raise
        finally:
            with self._lock:
                self._active.discard(upload_id)

    def status(self, upload_id: str) -> dict[str, Any]:
        """Recover an uncertain response, verifying committed bytes before acknowledgement."""
        with self._lock:
            record = self._record(upload_id)
            result: dict[str, Any] = {
                key: record[key] for key in ("upload_id", "filename", "size", "expires_at")
            }
            if upload_id in self._active:
                return {**result, "state": "receiving"}
            target = self.root / "sources" / upload_id
            if record["state"] == "ready" or target.exists():
                if record["state"] not in {"receiving", "failed", "ready"}:
                    raise UploadError("Committed source has no matching transfer record")
                committed = self._record(upload_id, committed=True)
                if committed["state"] != "ready":
                    raise UploadError("Committed source is not finalized")
                bound = ("upload_id", "filename", "size", "suffix", "created_at", "expires_at")
                if any(committed.get(key) != record.get(key) for key in bound):
                    raise UploadError("Committed source does not match its reservation record")
                if record["state"] == "ready" and committed != record:
                    raise UploadError("Committed source metadata changed after upload")
                for key in ("source_id", "sha256", "width", "height", "duration_ms"):
                    if key in record and record[key] != committed[key]:
                        raise UploadError("Committed source evidence changed after upload")
                self._validated_source(committed)
                if record["state"] != "ready":
                    self._write(committed)
                return {**result, "state": "ready", "source": self.describe(upload_id)}
            if record["state"] == "receiving":
                return {
                    **result,
                    "state": "interrupted",
                    "error": "Upload interrupted; request a new upload ID and upload again",
                }
            if record["state"] == "failed":
                return {
                    **result,
                    "state": "failed",
                    "error": "Upload failed; request a new upload ID and upload again",
                }
            if record["expires_at"] <= time.time():
                return {
                    **result,
                    "state": "expired",
                    "error": "Upload reservation expired; request a new upload ID",
                }
            return {**result, "state": "reserved"}

    def describe(self, source_id: str) -> dict[str, Any]:
        record = self._record(source_id)
        if record.get("state") != "ready":
            raise UploadError("Source is not finalized; upload it again")
        return {
            key: record[key]
            for key in (
                "source_id",
                "filename",
                "size",
                "sha256",
                "duration_ms",
                "width",
                "height",
            )
        }

    def source(self, source_id: str) -> Path:
        record = self._record(source_id)
        if record["state"] != "ready":
            raise UploadError("Source is not finalized; upload it again")
        return self._validated_source(record)

    def _validated_source(self, record: dict[str, Any]) -> Path:
        self._verify()
        source_id: str = record["source_id"]
        path = self.root / "sources" / source_id / f"source{record['suffix']}"
        try:
            directory = self._containers["sources"].child(source_id)
            before = directory.member_identity(path.name)
            if (
                directory.check_file(path.name).st_size != record["size"]
                or _sha256(path) != record["sha256"]
            ):
                raise UploadError("Source bytes changed after upload; upload it again")
            if directory.member_identity(path.name) != before:
                raise UploadError("Source identity changed while reading")
            self._verify()
        except StudioStorageError as exc:
            raise UploadError("Source private storage is unsafe or unavailable") from exc
        except OSError as exc:
            raise UploadError("Source bytes are missing or unreadable") from exc
        return path
