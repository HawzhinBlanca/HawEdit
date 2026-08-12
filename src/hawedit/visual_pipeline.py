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
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from hawedit import video_input
from hawedit.discovery import Candidate
from hawedit.path_b import UnreadableScene, VideoUnderstanding, discover_visual
from hawedit.video_input import WindowFrames, extract_window_frames
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
    "VisualComposer",
    "VisualDiscoveryResult",
    "VisualEmbedder",
    "VisualPipelineError",
]


class VisualPipelineError(RuntimeError):
    """The composed visual path lost identity or score provenance."""


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
    # Recall@K on this list. D-118.
    unreadable: tuple[UnreadableScene, ...] = ()

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
        }


def _file_digest(path: Path) -> str:
    """SHA-256 of a file, streamed. Measured in D-132: 0.1 s for the real 82 MB source."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class _EmbeddingCache:
    """Per-window embeddings on disk, so Stage 2 resumes instead of restarting.

    Stage 2's visual half is the most expensive thing in this pipeline. Measured on
    `ZAR38MinTest.mp4` with the real `Qwen3-VL-Embedding-2B` on a 3090 Ti: it plans **641
    windows** at **3,207 ms each** — **2,055.9 s** extrapolated, 34 minutes — plus 95.1 ms of
    ffmpeg per window, and a second pass **rewrote all 81 sampled jpgs**. None of it was reused:
    `discover` built a fresh in-memory `_FrameCache` per call and embedded every window
    unconditionally. D-132 made Stage 0 re-runnable and D-136 Stage 1; this is the third and
    largest. D-140.

    One file per window, so a run killed at window 400 keeps 400. Reuse is verified rather than
    assumed, on everything that changes the vector:

    * the **window** — id, bounds, fps and frame count, so a replanned window re-embeds;
    * the **model id and revision** — a different checkpoint produces a different embedding
      space, and mixing two would make every similarity meaningless while looking fine. D-073
      pinned the revisions for exactly this reason and D-136 made the producer part of the key;
    * the **source digest**, because a window is a time range and the same range of a different
      recording is different footage;
    * `TEMPORAL_PATCH_FRAMES`, which decides how many of the delivered frames survive to the
      model. Added by adversarial pass 32, which measured this list being wrong: it claimed
      "everything that changes the vector" while naming only the first three. On the real file,
      `zar38:s2:w0` (60,000–77,500 ms at 2 fps) yields **34** frames at a patch of 2 and **32**
      at 4 — different pixels, different embedding — with every other key above byte-identical,
      and `discover` consults this cache *before* extracting anything, so nothing downstream
      could notice. The window's own `frame_count` does not cover it: it is the **planned** 35,
      a number neither extraction produced.

    What is still outside the key is the ffmpeg invocation itself — a change to the filters or
    the output quality would produce different pixels under an unchanged fingerprint. That is
    code rather than data, it is not fingerprinted anywhere in this repo's on-disk caches, and
    the honest statement is that this key covers the settings, not the implementation.

    Any mismatch, unreadable file or malformed vector re-embeds — the expensive answer, never the
    wrong one. `load` compares the whole record, so records written before a key existed simply
    fail to match and are re-embedded once.
    """

    def __init__(self, root: Path, model_id: str, revision: str, source_sha256: str) -> None:
        self.root = root
        self.model_id = model_id
        self.revision = revision
        self.source_sha256 = source_sha256

    def _path(self, window: SceneWindow) -> Path:
        return self.root / f"{window.window_id.replace(':', '_')}.json"

    def _record(self, window: SceneWindow, vector: tuple[float, ...]) -> dict[str, object]:
        return {
            "window": window.to_dict(),
            "model_id": self.model_id,
            "revision": self.revision,
            "source_sha256": self.source_sha256,
            # Which of the window's frames actually reach the model. `extract_window_frames`
            # trims the delivered frames to a multiple of this, and D-190 defines it as `max()`
            # over the §7 checkpoints' declared `temporal_patch_size` — so it moves when the
            # model set moves, with no edit to this file. Read from the module that does the
            # trimming, not re-imported, so the fingerprint is the value actually applied.
            "temporal_patch_frames": video_input.TEMPORAL_PATCH_FRAMES,
            "vector": list(vector),
        }

    def load(self, window: SceneWindow) -> VisualEmbedding | None:
        if not self.revision:
            # An unidentified checkpoint never licenses a reuse. The docstring said so and the
            # first version of this code did not: an empty revision compared equal to itself, so
            # unpinned weights happily reused their own unnamed vectors — caught by the test
            # written for the rule rather than for the code. D-132's "absent evidence is not
            # evidence of a match", one key over.
            return None
        path = self._path(window)
        if not path.is_file():
            return None
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(stored, dict):
            return None
        vector = stored.get("vector")
        if not isinstance(vector, list) or not vector:
            return None
        expected = self._record(window, tuple(float(v) for v in vector))
        if stored != expected:
            return None
        try:
            # `VisualEmbedding` refuses an empty, zero or non-finite vector, and a cached one has
            # to clear the same bar as a fresh one — the cache is a store, not an exemption.
            return VisualEmbedding(window, tuple(float(v) for v in vector), self.model_id)
        except (TypeError, ValueError):
            return None

    def store(self, embedding: VisualEmbedding) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path(embedding.window)
        # Written through a temporary file: a run killed mid-write must leave no half-record for
        # the next one to parse. D-132's ordering.
        staging = path.with_suffix(".json.tmp")
        staging.write_text(
            json.dumps(self._record(embedding.window, embedding.vector), indent=2) + "\n",
            encoding="utf-8",
        )
        staging.replace(path)


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
        embedding_revision: str = "",
    ) -> None:
        self.embedder = embedder
        self.reranker_factory = reranker_factory
        self.reader_factory = reader_factory
        self.keep = keep
        self.retrieve_k = retrieve_k
        # Which checkpoint produced the cached vectors. Empty means "not identified", and
        # `_EmbeddingCache` then never matches — a run whose weights nobody pinned re-embeds
        # rather than reusing vectors from an unknown model (D-073's pins, D-136's producer key).
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
        if not query.strip():
            raise VisualPipelineError("visual retrieval query must not be empty")
        foreign = sorted({window.media_id for window in windows} - {media_id})
        if foreign:
            raise VisualPipelineError(
                f"visual windows for {foreign!r} were passed while composing {media_id!r}"
            )
        if not windows:
            return VisualDiscoveryResult(media_id, query, 0, 0, (), ())

        read_frames = _FrameCache(source, work_dir / "frames", ffmpeg)
        index = VisualIndex(media_id)
        cache = _EmbeddingCache(
            work_dir / "embeddings",
            self.embedder.model_id,
            self.embedding_revision,
            _file_digest(source),
        )

        def embedding_for(window: SceneWindow) -> VisualEmbedding:
            cached = cache.load(window)
            if cached is not None:
                return cached
            # Frames are only extracted for windows that still need embedding. A cached window
            # costs no ffmpeg either, which is where the 95.1 ms/window goes; survivors get their
            # frames later through the same `read_frames`, for the reranker and the reader.
            fresh = self.embedder.embed_frames(read_frames(window))
            cache.store(fresh)
            return fresh

        index.add_all(embedding_for(window) for window in windows)
        query_vector = self.embedder.embed_text(query)
        reranker = self.reranker_factory(read_frames)
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
        )
