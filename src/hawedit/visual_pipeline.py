"""The composed Stage 2 → Path B visual pipeline.

This module owns the joins that individual model adapters deliberately do not: extract every
scene once, embed it, retrieve the top 50, rerank every retrieved hit, keep 5–10, and show
*only those survivors* to VideoChat3. Media with fewer scenes than the requested survivor count
is refused explicitly rather than mislabeled as a top-5 result. A score on a Path B reading is
accepted only when it is the exact reranker score for that same window.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import tempfile
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from hawedit import video_input
from hawedit.discovery import Candidate
from hawedit.path_b import PathBError, UnreadableScene, VideoUnderstanding, discover_visual
from hawedit.qwen_visual import EmbedderUnavailable
from hawedit.video_input import VideoInputError, WindowFrames, extract_window_frames
from hawedit.visual_index import (
    RETRIEVE_K,
    RerankedHit,
    SceneWindow,
    VisualEmbedding,
    VisualIndex,
    VisualIndexError,
    VisualReranker,
    rerank_and_keep,
)

__all__ = [
    "FrameReader",
    "ReaderFactory",
    "VisualComposer",
    "VisualDiscoveryResult",
    "VisualEmbedder",
    "VisualPipelineError",
]


class VisualPipelineError(RuntimeError):
    """The composed visual path lost identity or score provenance."""


_CACHE_SCHEMA = 1
_CACHE_READ_LIMIT = 8 * 1024 * 1024
_REVISION = re.compile(r"[0-9a-f]{40}")


def _is_reparse(metadata: os.stat_result) -> bool:
    return bool(getattr(metadata, "st_file_attributes", 0) & 0x400)


def _same_file(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        left.st_size,
        left.st_mtime_ns,
        left.st_nlink,
    ) == (
        right.st_dev,
        right.st_ino,
        right.st_size,
        right.st_mtime_ns,
        right.st_nlink,
    )


def _bound_regular_bytes(path: Path, *, limit: int) -> bytes | None:
    """Read one optional cache record without following a link or accepting an unstable file."""
    try:
        before_path = os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError:
        return None
    if (
        not stat.S_ISREG(before_path.st_mode)
        or _is_reparse(before_path)
        or before_path.st_nlink != 1
        or before_path.st_size > limit
    ):
        return None
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return None
    try:
        before_fd = os.fstat(descriptor)
        if not _same_file(before_path, before_fd):
            return None
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(descriptor, min(1 << 20, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after_fd = os.fstat(descriptor)
        try:
            after_path = os.lstat(path)
        except OSError:
            return None
        if len(payload) > limit or not _same_file(before_fd, after_fd):
            return None
        if not _same_file(after_fd, after_path):
            return None
        return payload
    finally:
        os.close(descriptor)


def _source_digest(path: Path) -> str:
    """Hash the exact stable source bytes that cached scene vectors describe."""
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        before_path = os.lstat(path)
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise VisualPipelineError(
            f"visual source could not be opened for cache identity: {exc}"
        ) from exc
    try:
        before_fd = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before_fd.st_mode)
            or _is_reparse(before_path)
            or not _same_file(before_path, before_fd)
        ):
            raise VisualPipelineError("visual source changed or is not one stable regular file")
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, 1 << 20):
            digest.update(chunk)
        after_fd = os.fstat(descriptor)
        try:
            after_path = os.lstat(path)
        except OSError as exc:
            raise VisualPipelineError(
                "visual source disappeared while its identity was read"
            ) from exc
        if not _same_file(before_fd, after_fd) or not _same_file(after_fd, after_path):
            raise VisualPipelineError("visual source changed while its cache identity was read")
        return digest.hexdigest()
    finally:
        os.close(descriptor)


def _canonical_json(document: object) -> bytes:
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


class _EmbeddingCache:
    """Atomic per-window vectors, bound to source, window, model, and checkpoint revision."""

    def __init__(self, root: Path, model_id: str, revision: str, source_sha256: str) -> None:
        if _REVISION.fullmatch(revision) is None:
            raise VisualPipelineError("embedding cache requires one lowercase 40-hex revision")
        self.root = root
        self.model_id = model_id
        self.revision = revision
        self.source_sha256 = source_sha256
        self.hits = 0
        self.misses = 0

    def _path(self, window: SceneWindow) -> Path:
        identity = _canonical_json(window.to_dict())
        return self.root / f"{hashlib.sha256(identity).hexdigest()}.json"

    def _body(self, window: SceneWindow, vector: tuple[float, ...]) -> dict[str, object]:
        return {
            "schema": _CACHE_SCHEMA,
            "window": window.to_dict(),
            "model_id": self.model_id,
            "revision": self.revision,
            "source_sha256": self.source_sha256,
            # `TEMPORAL_PATCH_FRAMES` decides how many of the delivered frames survive to the
            # model, so it changes the vector and belongs in the key. Measured on the real
            # 38-minute file: `zar38:s2:w0` (60,000-77,500 ms at 2 fps) yields 34 frames at a
            # patch of 2 and 32 at 4 — different pixels, different embedding — with every other
            # key here byte-identical. Without it a run at one patch size silently reuses the
            # other's vectors. D-140.
            "temporal_patch_frames": video_input.TEMPORAL_PATCH_FRAMES,
            "vector": list(vector),
        }

    def _document(self, window: SceneWindow, vector: tuple[float, ...]) -> dict[str, object]:
        body = self._body(window, vector)
        return {**body, "record_sha256": hashlib.sha256(_canonical_json(body)).hexdigest()}

    def load(self, window: SceneWindow) -> VisualEmbedding | None:
        payload = _bound_regular_bytes(self._path(window), limit=_CACHE_READ_LIMIT)
        if payload is None:
            self.misses += 1
            return None
        try:
            stored = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.misses += 1
            return None
        if not isinstance(stored, dict) or set(stored) != {
            "schema",
            "window",
            "model_id",
            "revision",
            "source_sha256",
            "temporal_patch_frames",
            "vector",
            "record_sha256",
        }:
            self.misses += 1
            return None
        vector = stored.get("vector")
        if (
            not isinstance(vector, list)
            or not vector
            or len(vector) > 65_536
            or any(
                isinstance(value, bool) or not isinstance(value, int | float) for value in vector
            )
        ):
            self.misses += 1
            return None
        numeric = tuple(float(value) for value in vector)
        expected = self._document(window, numeric)
        if stored != expected:
            self.misses += 1
            return None
        try:
            embedding = VisualEmbedding(window, numeric, self.model_id)
        except (TypeError, ValueError):
            self.misses += 1
            return None
        self.hits += 1
        return embedding

    def store(self, embedding: VisualEmbedding) -> None:
        if embedding.model_id != self.model_id:
            raise VisualPipelineError(
                f"embedding cache expected model {self.model_id!r}, got {embedding.model_id!r}"
            )
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            document = _canonical_json(self._document(embedding.window, embedding.vector)) + b"\n"
            temporary: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="wb", dir=self.root, prefix=".embedding-", suffix=".tmp", delete=False
                ) as stream:
                    temporary = Path(stream.name)
                    stream.write(document)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self._path(embedding.window))
                temporary = None
            finally:
                if temporary is not None:
                    with suppress(FileNotFoundError):
                        temporary.unlink()
        except OSError as exc:
            raise VisualPipelineError(f"embedding cache could not publish a record: {exc}") from exc


def _cleanup_note(label: str, exc: BaseException) -> str:
    detail = " ".join(str(exc).split())
    if len(detail) > 384:
        detail = f"{detail[:383]}…"
    return f"{label} cleanup failed ({type(exc).__name__}): {detail or 'no detail'}"


@contextmanager
def _release_after(component: object, label: str) -> Iterator[None]:
    """Close one GPU phase without ever replacing its primary failure.

    Adapters remain reusable: their `close()` methods unload weights and the next call reloads
    through the same verified checkpoint boundary. Injected protocol implementations need not
    implement `close`, which preserves the small test/integration seam.
    """
    closer = getattr(component, "close", None)
    try:
        yield
    except BaseException as primary:
        if callable(closer):
            try:
                closer()
            except BaseException as cleanup:
                primary.add_note(_cleanup_note(label, cleanup))
        raise
    else:
        if callable(closer):
            try:
                closer()
            except Exception as exc:
                raise VisualPipelineError(_cleanup_note(label, exc)) from exc


class VisualEmbedder(Protocol):
    model_id: str

    def embed_frames(self, frames: WindowFrames) -> VisualEmbedding: ...

    def embed_text(self, query: str) -> tuple[float, ...]: ...


FrameReader = Callable[[SceneWindow], WindowFrames]
RerankerFactory = Callable[[FrameReader], VisualReranker]
ReaderFactory = Callable[[FrameReader, Callable[[SceneWindow], float]], VideoUnderstanding]


@dataclass(frozen=True, slots=True)
class VisualDiscoveryResult:
    """Auditable output of retrieval, reranking, and local scene reading."""

    media_id: str
    query: str
    indexed_windows: int
    retrieved: int
    survivors: tuple[RerankedHit, ...]
    candidates: tuple[Candidate, ...]
    # Survivors Path B reached and could not turn into a reading. Reported rather than dropped:
    # "six candidates" and "seven, one of which vanished" are different facts, and §8.2 counts
    # Recall@K on this list. D-156.
    unreadable: tuple[UnreadableScene, ...] = ()
    embedding_cache_hits: int = 0
    embedding_cache_misses: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "media_id": self.media_id,
            "query": self.query,
            "indexed_windows": self.indexed_windows,
            "retrieved": self.retrieved,
            "survivors": [
                {
                    "window": hit.window.to_dict(),
                    "retrieval_similarity": hit.retrieval_similarity,
                    "rerank_score": hit.rerank_score,
                    "rank": hit.rank,
                    "model_id": hit.model_id,
                }
                for hit in self.survivors
            ],
            "candidate_ids": [candidate.candidate_id for candidate in self.candidates],
            # Emitted even when empty, so "nothing was unreadable" is readable and cannot be
            # confused with a build that does not record it (D-110's rule).
            "unreadable": [scene.to_dict() for scene in self.unreadable],
            "embedding_cache_hits": self.embedding_cache_hits,
            "embedding_cache_misses": self.embedding_cache_misses,
        }


class _FrameCache:
    def __init__(
        self,
        source: Path,
        work_dir: Path,
        ffmpeg: Path | None,
    ) -> None:
        self.source = source
        self.work_dir = work_dir
        self.ffmpeg = ffmpeg
        self._frames: dict[str, WindowFrames] = {}

    def __call__(self, window: SceneWindow) -> WindowFrames:
        existing = self._frames.get(window.window_id)
        if existing is not None:
            if existing.window != window:
                raise VisualPipelineError(
                    f"window id {window.window_id!r} was reused with different boundaries"
                )
            return existing
        frames = extract_window_frames(
            self.source,
            window,
            self.work_dir / window.window_id.replace(":", "_"),
            self.ffmpeg,
        )
        self._frames[window.window_id] = frames
        return frames

    def close(self) -> None:
        failures: list[str] = []
        for window_id, frames in reversed(tuple(self._frames.items())):
            try:
                frames.cleanup()
            except VideoInputError as exc:
                failures.append(f"{window_id}: {type(exc).__name__}: {exc}")
        self._frames.clear()
        if failures:
            raise VideoInputError("; ".join(failures))


class VisualComposer:
    """Compose Qwen retrieval/reranking with VideoChat3 over the survivor set only."""

    def __init__(
        self,
        embedder: VisualEmbedder,
        reranker_factory: RerankerFactory,
        reader_factory: ReaderFactory,
        *,
        keep: int = 7,
        retrieve_k: int = RETRIEVE_K,
        embedding_revision: str | None = None,
    ) -> None:
        self.embedder = embedder
        self.reranker_factory = reranker_factory
        self.reader_factory = reader_factory
        self.keep = keep
        self.retrieve_k = retrieve_k
        if embedding_revision is not None and _REVISION.fullmatch(embedding_revision) is None:
            raise ValueError("embedding_revision must be one lowercase 40-hex commit SHA")
        self.embedding_revision = embedding_revision

    def discover(
        self,
        source: Path,
        windows: Sequence[SceneWindow],
        query: str,
        work_dir: Path,
        *,
        media_id: str,
        ffmpeg: Path | None = None,
    ) -> VisualDiscoveryResult:
        try:
            return self._discover(
                source,
                windows,
                query,
                work_dir,
                media_id=media_id,
                ffmpeg=ffmpeg,
            )
        except VisualPipelineError:
            raise
        except (EmbedderUnavailable, PathBError, VideoInputError, VisualIndexError) as exc:
            raise VisualPipelineError(
                f"visual pipeline component {type(exc).__name__} refused this media: {exc}"
            ) from exc

    def _discover(
        self,
        source: Path,
        windows: Sequence[SceneWindow],
        query: str,
        work_dir: Path,
        *,
        media_id: str,
        ffmpeg: Path | None = None,
    ) -> VisualDiscoveryResult:
        if not query.strip():
            raise VisualPipelineError("visual retrieval query must not be empty")
        foreign = sorted({window.media_id for window in windows} - {media_id})
        if foreign:
            raise VisualPipelineError(
                f"visual windows for {foreign!r} were passed while composing {media_id!r}"
            )
        if not windows:
            return VisualDiscoveryResult(media_id, query, 0, 0, (), ())

        cache = (
            _EmbeddingCache(
                work_dir / "embeddings",
                self.embedder.model_id,
                self.embedding_revision,
                _source_digest(source),
            )
            if self.embedding_revision is not None
            else None
        )
        read_frames = _FrameCache(source, work_dir / "frames", ffmpeg)
        with _release_after(read_frames, "visual frame cache"):
            return self._discover_with_frames(windows, query, media_id, read_frames, cache)

    def _discover_with_frames(
        self,
        windows: Sequence[SceneWindow],
        query: str,
        media_id: str,
        read_frames: _FrameCache,
        cache: _EmbeddingCache | None,
    ) -> VisualDiscoveryResult:
        index = VisualIndex(media_id)
        with _release_after(self.embedder, "visual embedder"):

            def embedding_for(window: SceneWindow) -> VisualEmbedding:
                if cache is not None:
                    cached = cache.load(window)
                    if cached is not None:
                        return cached
                fresh = self.embedder.embed_frames(read_frames(window))
                if cache is not None:
                    cache.store(fresh)
                return fresh

            index.add_all(embedding_for(window) for window in windows)
            query_vector = self.embedder.embed_text(query)
        reranker = self.reranker_factory(read_frames)
        with _release_after(reranker, "visual reranker"):
            try:
                survivors = rerank_and_keep(
                    index,
                    query_vector,
                    query,
                    reranker,
                    keep=self.keep,
                    k=self.retrieve_k,
                )
            except VisualIndexError as exc:
                raise VisualPipelineError(f"visual retrieval refused this media: {exc}") from exc

        scores = {hit.window.window_id: hit.rerank_score for hit in survivors}

        def score_window(window: SceneWindow) -> float:
            try:
                return scores[window.window_id]
            except KeyError as exc:
                raise VisualPipelineError(
                    f"VideoChat3 requested a score for non-survivor {window.window_id!r}"
                ) from exc

        reader = self.reader_factory(read_frames, score_window)
        with _release_after(reader, "VideoChat3 reader"):
            discovery = discover_visual(
                tuple(hit.window for hit in survivors), reader, media_id=media_id
            )
        candidates = discovery.candidates
        # Every survivor is either a candidate or a named refusal — still exact, so a scene
        # cannot go missing between the reranker and Stage 4, which is what this guard was for.
        accounted = {candidate.candidate_id for candidate in candidates} | {
            scene.window_id for scene in discovery.unreadable
        }
        if accounted != set(scores):
            raise VisualPipelineError(
                "Path B candidates do not exactly match the reranked survivors"
            )
        for candidate in candidates:
            expected = scores[candidate.candidate_id]
            if candidate.score is None or not math.isclose(
                candidate.score, expected, rel_tol=1e-9, abs_tol=1e-12
            ):
                raise VisualPipelineError(
                    f"Path B score {candidate.score!r} for {candidate.candidate_id!r} is not "
                    f"its reranker score {expected!r}"
                )

        return VisualDiscoveryResult(
            media_id=media_id,
            query=query,
            indexed_windows=len(index),
            retrieved=min(len(index), self.retrieve_k),
            survivors=survivors,
            candidates=candidates,
            unreadable=discovery.unreadable,
            embedding_cache_hits=cache.hits if cache is not None else 0,
            embedding_cache_misses=cache.misses if cache is not None else 0,
        )
