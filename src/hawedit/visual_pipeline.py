"""The composed Stage 2 → Path B visual pipeline.

This module owns the joins that individual model adapters deliberately do not: extract every
scene once, embed it, retrieve the top 50, rerank every retrieved hit, keep 5–10, and show
*only those survivors* to VideoChat3. Media with fewer scenes than the requested survivor count
is refused explicitly rather than mislabeled as a top-5 result. A score on a Path B reading is
accepted only when it is the exact reranker score for that same window.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

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
    ) -> None:
        self.embedder = embedder
        self.reranker_factory = reranker_factory
        self.reader_factory = reader_factory
        self.keep = keep
        self.retrieve_k = retrieve_k

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
        index.add_all(self.embedder.embed_frames(read_frames(window)) for window in windows)
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
