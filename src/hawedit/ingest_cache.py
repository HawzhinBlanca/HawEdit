"""Observed Stage0 byte bindings and non-destructive recovery, not approval authority."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import time
import uuid
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, distribution, version
from pathlib import Path
from typing import Any, BinaryIO

from hawedit.atomic_fs import rename_directory_noreplace
from hawedit.captions import ffprobe_for, find_ffmpeg
from hawedit.ingest import IngestError, IngestResult, probe_stream
from hawedit.wsl_setup import package_digest

_METADATA_LIMIT = 16 * 1024**2
_MARKER_LIMIT = 64 * 1024
_READ_SECONDS = 600.0
_LIBRARIES = (
    "numpy",
    "torch",
    "silero-vad",
    "onnxruntime",
    "scenedetect",
    "opencv-python",
    "opencv-python-headless",
)


class IngestCacheError(IngestError):
    """Cache verification or preservation failed; no stale bytes may reach ASR."""


def _stamp(info: os.stat_result) -> tuple[int, int, int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        info.st_nlink,
    )


def _plain(path: Path, *, directory: bool = False, single_link: bool = True) -> os.stat_result:
    info = path.lstat()
    valid = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if (
        not valid
        or bool(getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)
        or (not directory and single_link and info.st_nlink != 1)
    ):
        raise IngestCacheError("Ingest cache refuses linked or nonregular storage")
    return info


@dataclass
class _Opened:
    path: Path
    handle: BinaryIO
    before: os.stat_result
    held: os.stat_result
    single_link: bool

    def check(self) -> None:
        if _stamp(os.fstat(self.handle.fileno())) != _stamp(self.held) or _stamp(
            _plain(self.path, single_link=self.single_link)
        ) != _stamp(self.before):
            raise IngestCacheError("Ingest cache bytes or file identity changed during inspection")

    def read(self, limit: int) -> bytes:
        if self.before.st_size > limit:
            raise ValueError("Ingest cache metadata exceeds its byte limit")
        self.handle.seek(0)
        data = self.handle.read(limit + 1)
        self.check()
        if len(data) != self.before.st_size:
            raise IngestCacheError("Ingest cache metadata changed during reading")
        return data

    def digest(self, destination: BinaryIO | None = None) -> str:
        digest = hashlib.sha256()
        deadline = time.monotonic() + _READ_SECONDS
        self.handle.seek(0)
        count = 0
        while chunk := self.handle.read(1024**2):
            if time.monotonic() > deadline:
                raise IngestCacheError("Ingest cache regular-file read exceeded its deadline")
            count += len(chunk)
            digest.update(chunk)
            if destination is not None:
                destination.write(chunk)
        self.check()
        if count != self.before.st_size:
            raise IngestCacheError("Ingest cache byte count changed during inspection")
        return digest.hexdigest()


@contextmanager
def _open(path: Path, *, single_link: bool = True) -> Iterator[_Opened]:
    before = _plain(path, single_link=single_link)
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0),
    )
    try:
        handle = os.fdopen(descriptor, "rb")
    except BaseException:
        os.close(descriptor)
        raise
    with handle:
        held = os.fstat(handle.fileno())

        # Windows CRT/path ctime and executable mode bits differ; retain both full baselines.
        def common(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
            return (
                info.st_dev,
                info.st_ino,
                stat.S_IFMT(info.st_mode),
                info.st_size,
                info.st_mtime_ns,
                info.st_nlink,
            )

        if common(before) != common(held):
            raise IngestCacheError("Ingest cache file identity changed while opening")
        opened = _Opened(path, handle, before, held, single_link)
        opened.check()
        yield opened
        opened.check()


def _fingerprint(path: Path) -> dict[str, str]:
    resolved = path.resolve(strict=True)
    with _open(resolved, single_link=False) as opened:
        return {"path": str(resolved), "sha256": opened.digest()}


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError("Ingest cache JSON repeats a field")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ValueError(f"Ingest cache JSON contains nonfinite {value}")


def _json(data: bytes) -> dict[str, Any]:
    result: object = json.loads(data, object_pairs_hook=_pairs, parse_constant=_constant)
    if not isinstance(result, dict):
        raise ValueError("Ingest cache metadata must be an object")
    return result


def _write(path: Path, data: bytes) -> None:
    _plain(path.parent, directory=True)
    try:
        before = _plain(path)
    except FileNotFoundError:
        before = None
    staging = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    descriptor = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        after = _plain(path)
    except FileNotFoundError:
        after = None
    if (before is None) != (after is None) or (
        before is not None and after is not None and _stamp(before) != _stamp(after)
    ):
        raise IngestCacheError("Ingest cache destination changed before atomic write")
    staging.replace(path)


class IngestCache:
    """Verify actual inputs and preserve known cache members before normal regeneration."""

    def __init__(
        self,
        source: Path,
        work_dir: Path,
        media_id: str,
        source_sha256: str,
        ffmpeg: Path | None,
    ) -> None:
        self.source = source
        self.work_dir = Path(os.path.abspath(work_dir))
        _plain(self.work_dir, directory=True)
        self.stage = self.work_dir / "stage0"
        self.paths = {
            "audio.wav": self.stage / "audio.wav",
            "proxy.mp4": self.stage / "proxy.mp4",
            "ingest.json": self.stage / "ingest.json",
            "stage0_ingest.done": self.work_dir / "stage0_ingest.done",
            "audio.wav.provenance.json": self.stage / "audio.wav.provenance.json",
            "proxy.mp4.provenance.json": self.stage / "proxy.mp4.provenance.json",
        }
        if source.resolve() in {path.resolve() for path in self.paths.values()}:
            raise IngestCacheError("Source video collides with an owned Stage0 cache output")
        selected = ffmpeg if ffmpeg is not None else find_ffmpeg()
        if selected is None:
            raise IngestCacheError("no ffmpeg available; run hawedit-ffmpeg-setup")
        self.ffmpeg = selected
        self.media_id = media_id
        self.source_sha256 = source_sha256
        self.reason: str | None = None
        self._root_identity = (
            _plain(self.work_dir, directory=True).st_dev,
            _plain(self.work_dir, directory=True).st_ino,
        )
        try:
            self.binding = self._binding()
        except (OSError, PackageNotFoundError) as exc:
            raise IngestCacheError("Selected ingest tool or VAD identity is unavailable") from exc

    def _namespace(self) -> None:
        root = _plain(self.work_dir, directory=True)
        if (root.st_dev, root.st_ino) != self._root_identity:
            raise IngestCacheError("Ingest cache work directory identity changed")
        with suppress(FileNotFoundError):
            _plain(self.stage, directory=True)

    def _binding(self) -> dict[str, Any]:
        libraries: dict[str, str | None] = {}
        for name in _LIBRARIES:
            try:
                libraries[name] = version(name)
            except PackageNotFoundError:
                libraries[name] = None
        vad = Path(str(distribution("silero-vad").locate_file("silero_vad/data/silero_vad.onnx")))
        return {
            "source_sha256": self.source_sha256,
            "source": str(self.source.resolve(strict=True)),
            "media_id": self.media_id,
            "producer_source_sha256": package_digest(),
            "libraries": libraries,
            "vad_model_sha256": _fingerprint(vad)["sha256"],
            "tools": {
                "ffmpeg": _fingerprint(self.ffmpeg),
                "ffprobe": _fingerprint(ffprobe_for(self.ffmpeg)),
            },
        }

    def _readers(self, stack: ExitStack, *, include_checkpoint: bool = True) -> dict[str, _Opened]:
        self._namespace()
        readers: dict[str, _Opened] = {}
        for name, path in self.paths.items():
            if name == "stage0_ingest.done" and not include_checkpoint:
                continue
            with suppress(FileNotFoundError):
                readers[name] = stack.enter_context(_open(path))
        return readers

    def load(self) -> IngestResult | None:
        with ExitStack() as stack:
            readers = self._readers(stack)
            if not readers:
                return None
            if set(readers) != set(self.paths):
                self.reason = "incomplete ingest cache has missing bound members"
                return None
            try:
                marker = _json(readers["stage0_ingest.done"].read(_MARKER_LIMIT))
                metadata = marker.get("metadata")
                if (
                    not isinstance(metadata, dict)
                    or type(metadata.get("cache_schema")) is not int
                    or metadata["cache_schema"] != 2
                ):
                    raise ValueError("legacy ingest checkpoint lacks derived byte bindings")
                if (
                    type(marker.get("schema")) is not int
                    or marker["schema"] != 1
                    or marker.get("stage_name") != "stage0_ingest"
                    or marker.get("input_hashes") != {"source_sha256": self.source_sha256}
                    or metadata.get("binding") != self.binding
                ):
                    raise ValueError("ingest source or producer/tool configuration changed")
                actual = {
                    name: reader.digest()
                    for name, reader in readers.items()
                    if name != "stage0_ingest.done"
                }
                if metadata.get("outputs") != actual:
                    raise ValueError("ingest metadata or derived media bytes changed")
                result = IngestResult.from_dict(_json(readers["ingest.json"].read(_METADATA_LIMIT)))
                self._record(result)
                probe_stream(
                    self.paths["proxy.mp4"], "stream=index", ffmpeg=self.ffmpeg, video_only=True
                )
                probe_stream(self.paths["audio.wav"], "stream=index", ffmpeg=self.ffmpeg)
                if self._binding() != self.binding:
                    raise IngestCacheError("Ingest producer context changed while verifying cache")
                for reader in readers.values():
                    reader.check()
                self._namespace()
                return result
            except (ValueError, TypeError, KeyError, RecursionError) as exc:
                self.reason = str(exc)
                return None

    def _record(self, result: IngestResult) -> None:
        if (
            result.media_id != self.media_id
            or result.source_sha256 != self.source_sha256
            or Path(result.source).resolve() != self.source.resolve()
            or Path(os.path.abspath(result.audio_path)) != self.paths["audio.wav"]
            or Path(os.path.abspath(result.proxy_path)) != self.paths["proxy.mp4"]
            or result.diarization is not None
        ):
            raise ValueError("Ingest measurement identity or scoped output paths differ")

    def preserve(self) -> Path:
        """Copy only known files; never move unrelated owner data or erase partial attempts."""
        try:
            root = self.work_dir / "stage0-recovery"
            self._namespace()
            root.mkdir(mode=0o700, exist_ok=True)
            _plain(root, directory=True)
            nonce = uuid.uuid4().hex
            staging, final = root / f"pending-{nonce}", root / f"recovery-{nonce}"
            staging.mkdir(mode=0o700)
            hashes: dict[str, str] = {}
            with ExitStack() as stack:
                readers = self._readers(stack)
                for name, reader in readers.items():
                    descriptor = os.open(
                        staging / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
                    )
                    with os.fdopen(descriptor, "wb") as handle:
                        hashes[name] = reader.digest(handle)
                        handle.flush()
                        os.fsync(handle.fileno())
                for reader in readers.values():
                    reader.check()
                self._namespace()
                _write(
                    staging / "recovery.json",
                    json.dumps(
                        {
                            "schema": 1,
                            "reason": self.reason,
                            "files": hashes,
                            "current_binding": self.binding,
                        },
                        sort_keys=True,
                        indent=2,
                    ).encode(),
                )
                # Move only this new owned staging leaf, inside the verified recovery root.
                for target in (staging, final):
                    target.resolve().relative_to(root.resolve(strict=True))
                _plain(root, directory=True)
                _plain(staging, directory=True)
                rename_directory_noreplace(staging, final)
                for reader in readers.values():
                    reader.check()
            return final
        except (OSError, IngestCacheError) as exc:
            raise IngestCacheError(
                "Ingest cache preservation failed; original files retained"
            ) from exc

    def save(self, result: IngestResult) -> None:
        try:
            self._record(result)
        except ValueError as exc:
            raise IngestCacheError("Fresh ingest source or base-result identity changed") from exc
        self._namespace()
        if self._binding() != self.binding:
            raise IngestCacheError("Ingest producer/tool context changed during generation")
        _write(self.paths["ingest.json"], result.to_json().encode())
        with ExitStack() as stack:
            readers = self._readers(stack, include_checkpoint=False)
            outputs = {
                name: reader.digest()
                for name, reader in readers.items()
                if name != "stage0_ingest.done"
            }
            if set(outputs) != set(self.paths) - {"stage0_ingest.done"}:
                raise IngestCacheError("Fresh ingest is missing required derived files")
            marker = {
                "schema": 1,
                "stage_name": "stage0_ingest",
                "completed_at": datetime.now(UTC).isoformat(),
                "input_hashes": {"source_sha256": self.source_sha256},
                "metadata": {
                    "audio_path": result.audio_path,
                    "cache_schema": 2,
                    "binding": self.binding,
                    "outputs": outputs,
                },
            }
            _write(
                self.paths["stage0_ingest.done"],
                json.dumps(marker, sort_keys=True, indent=2).encode(),
            )
        self._namespace()

    def invalidate_extractions(self) -> None:
        """After retention, ensure the inner extractor cannot reuse an invalidated context."""
        self._namespace()
        for name in ("audio.wav.provenance.json", "proxy.mp4.provenance.json"):
            _write(self.paths[name], b"{}\n")
