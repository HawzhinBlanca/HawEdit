from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from hawedit.clip import Sv6d
from hawedit.path_b import PATH_B_MODEL, SceneReading
from hawedit.video_input import WindowFrames
from hawedit.visual_index import (
    RerankedHit,
    SceneWindow,
    VisualEmbedding,
    VisualHit,
)
from hawedit.visual_pipeline import FrameReader, VisualComposer, VisualPipelineError


def windows(count: int) -> tuple[SceneWindow, ...]:
    return tuple(
        SceneWindow(
            media_id="m",
            scene_index=i,
            window_index=0,
            in_ms=i * 1_000,
            out_ms=(i + 1) * 1_000,
            fps=2.0,
        )
        for i in range(count)
    )


class FakeEmbedder:
    model_id = "Qwen3-VL-Embedding-2B"

    def embed_frames(self, frames: WindowFrames) -> VisualEmbedding:
        value = (frames.window.scene_index + 1) / 100
        return VisualEmbedding(frames.window, (1.0, value), self.model_id)

    def embed_text(self, query: str) -> tuple[float, ...]:
        assert query == "گرنگ"
        return (1.0, 1.0)


class FakeReranker:
    def __init__(self, read_frames: FrameReader) -> None:
        self.read_frames = read_frames

    def rerank(self, query: str, hits: Sequence[VisualHit]) -> tuple[RerankedHit, ...]:
        assert query == "گرنگ"
        ordered = sorted(hits, key=lambda hit: hit.window.scene_index, reverse=True)
        return tuple(
            RerankedHit(
                window=hit.window,
                retrieval_similarity=hit.similarity,
                rerank_score=1.0 - rank / 100,
                rank=rank,
                model_id="Qwen3-VL-Reranker-2B",
            )
            for rank, hit in enumerate(ordered, 1)
        )


def sv6d(window: SceneWindow) -> Sv6d:
    at = f"{window.in_ms / 1000:.3f}s"
    return Sv6d(
        subject=f"subject {at}",
        aesthetics=f"aesthetics {at}",
        camera=f"camera {at}",
        editing=f"editing {at}",
        narrative=f"narrative {at}",
        retention=f"retention {at}",
    )


class FakeReader:
    def __init__(
        self,
        read_frames: FrameReader,
        score_window: Callable[[SceneWindow], float],
        seen: list[SceneWindow],
    ) -> None:
        self.read_frames = read_frames
        self.score_window = score_window
        self.seen = seen

    def read_scenes(self, items: Sequence[SceneWindow]) -> tuple[SceneReading, ...]:
        self.seen.extend(items)
        return tuple(
            SceneReading(item, sv6d(item), self.score_window(item), PATH_B_MODEL) for item in items
        )


def test_only_reranked_survivors_reach_videochat(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    extracted: list[str] = []

    def fake_extract(
        source: Path, window: SceneWindow, dest: Path, ffmpeg: Path | None
    ) -> WindowFrames:
        extracted.append(window.window_id)
        return WindowFrames(window, (dest / "frame.jpg", dest / "frame2.jpg"))

    monkeypatch.setattr("hawedit.visual_pipeline.extract_window_frames", fake_extract)
    seen: list[SceneWindow] = []
    composer = VisualComposer(
        FakeEmbedder(),
        FakeReranker,
        lambda read, score: FakeReader(read, score, seen),
        keep=5,
    )
    result = composer.discover(
        tmp_path / "m.mp4",
        windows(12),
        "گرنگ",
        tmp_path / "work",
        media_id="m",
    )

    assert len(extracted) == 12
    assert len(result.survivors) == 5
    assert tuple(window.window_id for window in seen) == tuple(
        hit.window.window_id for hit in result.survivors
    )
    assert {candidate.candidate_id for candidate in result.candidates} == {
        hit.window.window_id for hit in result.survivors
    }


def test_short_media_is_refused_instead_of_mislabeling_a_partial_top_five(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "hawedit.visual_pipeline.extract_window_frames",
        lambda source, window, dest, ffmpeg: WindowFrames(window, (dest / "a.jpg", dest / "b.jpg")),
    )
    composer = VisualComposer(
        FakeEmbedder(),
        FakeReranker,
        lambda read, score: FakeReader(read, score, []),
        keep=5,
    )
    with pytest.raises(VisualPipelineError, match="too short for Stage 2"):
        composer.discover(tmp_path / "m.mp4", windows(3), "گرنگ", tmp_path / "work", media_id="m")
