from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from hawedit.clip import Sv6d
from hawedit.path_b import (
    PATH_B_MODEL,
    PathBError,
    SceneReading,
    SceneReadings,
    UnreadableScene,
)
from hawedit.video_input import VideoInputError, WindowFrames
from hawedit.visual_index import (
    RerankedHit,
    SceneWindow,
    VisualEmbedding,
    VisualHit,
)
from hawedit.visual_pipeline import FrameReader, ReaderFactory, VisualComposer, VisualPipelineError


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

    def read_scenes(self, items: Sequence[SceneWindow]) -> SceneReadings:
        self.seen.extend(items)
        return SceneReadings(
            tuple(
                SceneReading(item, sv6d(item), self.score_window(item), PATH_B_MODEL)
                for item in items
            )
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


@pytest.mark.parametrize("failure", (VideoInputError("ffmpeg failed"), PathBError("bad reading")))
def test_component_failures_are_normalized_at_the_composer_boundary(
    failure: RuntimeError, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    reader_factory: ReaderFactory
    if isinstance(failure, VideoInputError):
        monkeypatch.setattr(
            "hawedit.visual_pipeline.extract_window_frames",
            lambda *_args: (_ for _ in ()).throw(failure),
        )

        def video_input_reader(
            read: FrameReader, score: Callable[[SceneWindow], float]
        ) -> FakeReader:
            return FakeReader(read, score, [])

        reader_factory = video_input_reader

    else:
        monkeypatch.setattr(
            "hawedit.visual_pipeline.extract_window_frames",
            lambda source, window, dest, ffmpeg: WindowFrames(
                window, (dest / "a.jpg", dest / "b.jpg")
            ),
        )

        class FailingReader:
            def read_scenes(self, items: Sequence[SceneWindow]) -> SceneReadings:
                raise failure

        def failing_reader(
            _read: FrameReader, _score: Callable[[SceneWindow], float]
        ) -> FailingReader:
            return FailingReader()

        reader_factory = failing_reader

    composer = VisualComposer(FakeEmbedder(), FakeReranker, reader_factory, keep=5)
    with pytest.raises(VisualPipelineError, match=type(failure).__name__) as caught:
        composer.discover(tmp_path / "m.mp4", windows(5), "گرنگ", tmp_path / "work", media_id="m")
    assert caught.value.__cause__ is failure


def test_gpu_phases_are_closed_before_the_next_model_is_constructed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    monkeypatch.setattr(
        "hawedit.visual_pipeline.extract_window_frames",
        lambda source, window, dest, ffmpeg: WindowFrames(window, (dest / "a.jpg", dest / "b.jpg")),
    )

    class LifecycleEmbedder(FakeEmbedder):
        def embed_frames(self, frames: WindowFrames) -> VisualEmbedding:
            events.append("embed")
            return super().embed_frames(frames)

        def embed_text(self, query: str) -> tuple[float, ...]:
            events.append("query")
            return super().embed_text(query)

        def close(self) -> None:
            events.append("close-embedder")

    class LifecycleReranker(FakeReranker):
        def rerank(self, query: str, hits: Sequence[VisualHit]) -> tuple[RerankedHit, ...]:
            events.append("rerank")
            return super().rerank(query, hits)

        def close(self) -> None:
            events.append("close-reranker")

    class LifecycleReader(FakeReader):
        def read_scenes(self, items: Sequence[SceneWindow]) -> SceneReadings:
            events.append("read")
            return super().read_scenes(items)

        def close(self) -> None:
            events.append("close-reader")

    def make_reranker(read: FrameReader) -> LifecycleReranker:
        assert events[-1] == "close-embedder"
        events.append("make-reranker")
        return LifecycleReranker(read)

    def make_reader(read: FrameReader, score: Callable[[SceneWindow], float]) -> LifecycleReader:
        assert events[-1] == "close-reranker"
        events.append("make-reader")
        return LifecycleReader(read, score, [])

    result = VisualComposer(LifecycleEmbedder(), make_reranker, make_reader, keep=5).discover(
        tmp_path / "m.mp4",
        windows(5),
        "\u06af\u0631\u0646\u06af",
        tmp_path / "work",
        media_id="m",
    )

    assert len(result.candidates) == 5
    assert events[-8:] == [
        "query",
        "close-embedder",
        "make-reranker",
        "rerank",
        "close-reranker",
        "make-reader",
        "read",
        "close-reader",
    ]
    assert events[-1] == "close-reader"


def test_cleanup_failure_does_not_replace_the_primary_model_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "hawedit.visual_pipeline.extract_window_frames",
        lambda source, window, dest, ffmpeg: WindowFrames(window, (dest / "a.jpg", dest / "b.jpg")),
    )
    primary = AssertionError("model invariant")

    class FailingEmbedder(FakeEmbedder):
        def embed_frames(self, frames: WindowFrames) -> VisualEmbedding:
            raise primary

        def close(self) -> None:
            raise OSError("CUDA cleanup failed")

    composer = VisualComposer(
        FailingEmbedder(),
        FakeReranker,
        lambda read, score: FakeReader(read, score, []),
        keep=5,
    )
    with pytest.raises(AssertionError) as caught:
        composer.discover(
            tmp_path / "m.mp4",
            windows(5),
            "\u06af\u0631\u0646\u06af",
            tmp_path / "work",
            media_id="m",
        )
    assert caught.value is primary
    assert caught.value.__notes__ == [
        "visual embedder cleanup failed (OSError): CUDA cleanup failed"
    ]


def test_cleanup_failure_after_success_is_a_composed_pipeline_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "hawedit.visual_pipeline.extract_window_frames",
        lambda source, window, dest, ffmpeg: WindowFrames(window, (dest / "a.jpg", dest / "b.jpg")),
    )

    class UnloadFailingEmbedder(FakeEmbedder):
        def close(self) -> None:
            raise OSError("driver refused release")

    composer = VisualComposer(
        UnloadFailingEmbedder(),
        FakeReranker,
        lambda read, score: FakeReader(read, score, []),
        keep=5,
    )
    with pytest.raises(VisualPipelineError, match="visual embedder cleanup failed") as caught:
        composer.discover(
            tmp_path / "m.mp4",
            windows(5),
            "\u06af\u0631\u0646\u06af",
            tmp_path / "work",
            media_id="m",
        )
    assert isinstance(caught.value.__cause__, OSError)


# --- D-156: an unreadable survivor is reported, not fatal, and still accounted for -------------


def test_an_unreadable_survivor_is_carried_into_the_result_not_dropped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The composer's exactness guard was "candidates == survivors", which a refusal breaks.

    It is now "candidates ∪ unreadable == survivors" — still exact, so a scene cannot go
    missing between the reranker and Stage 4, which is what the guard was for. The refusal
    reaches `to_dict`, because a result that quietly holds four candidates for five survivors
    is the silent case this module exists to prevent.
    """

    def fake_extract(
        source: Path, window: SceneWindow, dest: Path, ffmpeg: Path | None
    ) -> WindowFrames:
        return WindowFrames(window, (dest / "frame.jpg", dest / "frame2.jpg"))

    monkeypatch.setattr("hawedit.visual_pipeline.extract_window_frames", fake_extract)

    class RefusesTheFirst:
        def __init__(
            self, read_frames: object, score_window: Callable[[SceneWindow], float]
        ) -> None:
            self.score_window = score_window

        def read_scenes(self, items: Sequence[SceneWindow]) -> SceneReadings:
            first, *rest = items
            return SceneReadings(
                tuple(
                    SceneReading(item, sv6d(item), self.score_window(item), PATH_B_MODEL)
                    for item in rest
                ),
                (
                    UnreadableScene(
                        window_id=first.window_id,
                        in_ms=first.in_ms,
                        out_ms=first.out_ms,
                        reason="PathBError: the model returned no usable line for ['subject', …]",
                    ),
                ),
            )

    composer = VisualComposer(
        FakeEmbedder(), FakeReranker, lambda read, score: RefusesTheFirst(read, score), keep=5
    )
    result = composer.discover(
        tmp_path / "m.mp4", windows(12), "گرنگ", tmp_path / "work", media_id="m"
    )

    assert len(result.survivors) == 5
    assert len(result.candidates) == 4
    assert len(result.unreadable) == 1
    emitted = result.to_dict()
    assert emitted["unreadable"] == [
        {
            "window_id": result.unreadable[0].window_id,
            "in_ms": result.unreadable[0].in_ms,
            "out_ms": result.unreadable[0].out_ms,
            "reason": result.unreadable[0].reason,
        }
    ]
    assert emitted["candidate_ids"] == [c.candidate_id for c in result.candidates]


def test_a_run_with_nothing_unreadable_still_says_so(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The control (D-110's rule). Emitting the key only when non-empty makes its absence
    unreadable — a clean run and a build that does not record refusals look identical."""

    def fake_extract(
        source: Path, window: SceneWindow, dest: Path, ffmpeg: Path | None
    ) -> WindowFrames:
        return WindowFrames(window, (dest / "frame.jpg", dest / "frame2.jpg"))

    monkeypatch.setattr("hawedit.visual_pipeline.extract_window_frames", fake_extract)
    composer = VisualComposer(
        FakeEmbedder(), FakeReranker, lambda read, score: FakeReader(read, score, []), keep=5
    )
    result = composer.discover(
        tmp_path / "m.mp4", windows(12), "گرنگ", tmp_path / "work", media_id="m"
    )
    assert result.unreadable == ()
    assert result.to_dict()["unreadable"] == []
