from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from hawedit.clip import Sv6d
from hawedit.path_b import PATH_B_MODEL, SceneReading, SceneReadings, UnreadableScene
from hawedit.video_input import WindowFrames
from hawedit.visual_index import (
    RerankedHit,
    SceneWindow,
    VisualEmbedding,
    VisualHit,
)
from hawedit.visual_pipeline import (
    FrameReader,
    VisualComposer,
    VisualDiscoveryResult,
    VisualPipelineError,
)


def a_source(tmp_path: Path) -> Path:
    """A stand-in for the media file.

    It has to exist: `discover` reads the source's SHA-256 to key the per-window embedding cache
    (D-140), and every window it would embed comes out of this file anyway — failing here is
    earlier and clearer than failing inside ffmpeg, which is where an absent source landed
    before. These tests monkeypatch the extraction, so the bytes are never decoded.
    """
    source = tmp_path / "m.mp4"
    source.write_bytes(b"not a real video, and never decoded")
    return source


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
        a_source(tmp_path),
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
        composer.discover(a_source(tmp_path), windows(3), "گرنگ", tmp_path / "work", media_id="m")


# --- D-118: an unreadable survivor is reported, not fatal, and still accounted for -------------


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
        a_source(tmp_path), windows(12), "گرنگ", tmp_path / "work", media_id="m"
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
        a_source(tmp_path), windows(12), "گرنگ", tmp_path / "work", media_id="m"
    )
    assert result.unreadable == ()
    assert result.to_dict()["unreadable"] == []


# --- D-140: Stage 2's visual half is the most expensive stage, and it was redone every run ---
#
# Measured on `ZAR38MinTest.mp4` with the real `Qwen3-VL-Embedding-2B` on a 3090 Ti: 641 windows
# planned, **1,374 ms per window warm** (3,207 ms including the first forward pass), so
# **880.7 s** extrapolated — and a second pass re-embedded all of them while ffmpeg rewrote all
# 81 sampled jpgs. Two passes over one work directory now measure **12 embedder calls then 0**,
# 16.49 s then 0.14 s, with the cached vectors bit-identical.


class CountingEmbedder(FakeEmbedder):
    """`FakeEmbedder`, recording which windows it was actually asked to embed."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def embed_frames(self, frames: WindowFrames) -> VisualEmbedding:
        self.calls.append(frames.window.window_id)
        return super().embed_frames(frames)


def _discover_twice(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    between: Callable[[Path], None] | None = None,
    revisions: tuple[str, str] = ("rev-1", "rev-1"),
) -> tuple[CountingEmbedder, list[str], tuple[VisualDiscoveryResult, VisualDiscoveryResult]]:
    """Run `discover` twice over one work directory, optionally disturbing it in between."""
    extracted: list[str] = []

    def fake_extract(
        video: Path, window: SceneWindow, dest: Path, ffmpeg: Path | None = None
    ) -> WindowFrames:
        extracted.append(window.window_id)
        return WindowFrames(window, (dest / "frame.jpg", dest / "frame2.jpg"))

    monkeypatch.setattr("hawedit.visual_pipeline.extract_window_frames", fake_extract)
    source = a_source(tmp_path)
    work = tmp_path / "work"
    embedder = CountingEmbedder()

    def run(revision: str) -> VisualDiscoveryResult:
        composer = VisualComposer(
            embedder,
            FakeReranker,
            lambda read, score: FakeReader(read, score, []),
            keep=5,
            embedding_revision=revision,
        )
        return composer.discover(source, windows(12), "گرنگ", work, media_id="m")

    first = run(revisions[0])
    if between is not None:
        between(work)
    second = run(revisions[1])
    return embedder, extracted, (first, second)


def test_a_second_pass_reuses_every_embedding_and_extracts_no_frames(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The defect: 641 windows at 1,374 ms each, re-embedded on every run.

    Frames are asserted too, because a cached window needs no ffmpeg either — that is where the
    measured 95.1 ms/window goes, and a cache that still extracted would keep paying it.
    """
    embedder, extracted, (first, second) = _discover_twice(monkeypatch, tmp_path)

    assert len(embedder.calls) == 12, "the first pass must embed every window"
    assert embedder.calls == extracted[:12]
    assert len(extracted) == 12, f"the second pass extracted frames again: {extracted[12:]}"
    assert first.to_dict() == second.to_dict(), "the reused run produced a different result"


def test_a_different_checkpoint_revision_re_embeds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The control that matters most. Vectors from two checkpoints live in different embedding
    spaces, and mixing them makes every cosine similarity meaningless while looking fine — worse
    than the 880.7 s it saves. D-073 pinned the revisions; this makes the pin load-bearing.
    """
    embedder, _, _ = _discover_twice(monkeypatch, tmp_path, revisions=("rev-1", "rev-2"))

    assert len(embedder.calls) == 24, "a second checkpoint reused the first one's vectors"


def test_an_unidentified_checkpoint_never_licenses_a_reuse(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An empty revision means "not pinned". It must not match itself: vectors from a checkpoint
    nobody can name are not evidence that this run's weights produced them."""
    embedder, _, _ = _discover_twice(monkeypatch, tmp_path, revisions=("", ""))

    assert len(embedder.calls) == 24, "unpinned weights reused their own unidentified vectors"


def test_a_replaced_source_re_embeds(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A window is a *time range*. The same range of a different recording is different footage,
    so reusing there would embed one video and describe another."""

    def replace_source(_work: Path) -> None:
        (tmp_path / "m.mp4").write_bytes(b"a different recording entirely")

    embedder, _, _ = _discover_twice(monkeypatch, tmp_path, between=replace_source)

    assert len(embedder.calls) == 24, "a replaced source served the old video's embeddings"


def test_a_changed_frame_trim_re_embeds(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Adversarial pass 32 refuted the cache docstring's own claim on real footage.

    It said reuse was verified "on everything that changes the vector" and keyed on three things:
    the window, the checkpoint, the source. `extract_window_frames` trims the delivered frames to
    a multiple of `TEMPORAL_PATCH_FRAMES`, and D-190 defines that as `max()` over the §7
    checkpoints' declared `temporal_patch_size` — so it moves when the model set moves, without
    anyone editing it.

    Measured on `ZAR38MinTest.mp4`, window `zar38:s2:w0` (60,000–77,500 ms at 2 fps): **34**
    frames at a patch of 2, **32** at 4, different pixel digests, and a byte-identical key. The
    window's own `frame_count` does not cover it — that is the *planned* 35, which neither
    extraction produced. `discover` reads this cache before extracting anything, so the stale
    vector was served with nothing downstream in a position to notice.
    """

    def widen_the_temporal_patch(_work: Path) -> None:
        monkeypatch.setattr("hawedit.video_input.TEMPORAL_PATCH_FRAMES", 4)

    embedder, _, _ = _discover_twice(monkeypatch, tmp_path, between=widen_the_temporal_patch)

    assert len(embedder.calls) == 24, (
        "a different frame trim served the vectors built from the old frame set"
    )


def test_the_frame_trim_is_recorded_in_the_cache_entry(tmp_path: Path) -> None:
    """Assert the artifact, not the behaviour above: the fingerprint is *in* the written file.

    `load` compares the whole record, so a key that is silently absent would make every entry
    from an older release match a newer one — which is the shape of the defect, one level down.
    """
    import json

    from hawedit.visual_index import TEMPORAL_PATCH_FRAMES
    from hawedit.visual_pipeline import _EmbeddingCache

    cache = _EmbeddingCache(tmp_path / "embeddings", "Qwen3-VL-Embedding-2B", "rev-1", "abc")
    window = windows(1)[0]
    cache.store(VisualEmbedding(window, (0.1, 0.2, 0.3), "Qwen3-VL-Embedding-2B"))

    written = json.loads(next((tmp_path / "embeddings").glob("*.json")).read_text(encoding="utf-8"))
    assert written["temporal_patch_frames"] == TEMPORAL_PATCH_FRAMES, written
    # The control: the entry it just wrote is one this cache accepts, so the assertion above is
    # about the key's presence and not about a record no reader would take anyway.
    assert cache.load(window) is not None


def test_a_truncated_cache_entry_re_embeds_only_that_window(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Half-written JSON is every sidecar's realistic failure mode, and it falls through to
    embedding — the expensive answer, never the wrong one.

    Only that window: a cache that gave up wholesale on one bad file would re-embed all twelve,
    which is correct and throws away 11 windows of work for nothing.

    **What this cannot check, and the first version of this test wrongly asserted it could:** a
    hand-edited *vector* that still parses and still satisfies the embedding invariants is
    indistinguishable from a legitimate one. The record verifies what *produced* the vector —
    window, model, revision, source — because the vector's own content cannot be validated
    without re-embedding it, which is the cost the cache exists to avoid. Any checksum stored
    beside it would be derived from the same file and re-derivable by whoever edited it. D-140
    records the limitation rather than pretending otherwise.
    """

    def truncate_one(work: Path) -> None:
        entries = sorted((work / "embeddings").glob("*.json"))
        assert len(entries) == 12, entries
        entries[0].write_text('{"window": {"med', encoding="utf-8")

    embedder, _, _ = _discover_twice(monkeypatch, tmp_path, between=truncate_one)

    assert len(embedder.calls) == 13, embedder.calls


def test_a_cached_vector_must_still_clear_the_embedding_invariants(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`VisualEmbedding` refuses a zero or non-finite vector because a NaN sinks a scene below
    everything in every query without a trace. A cached vector has to clear the same bar — the
    cache is a store, not an exemption.
    """

    def zero_one_vector(work: Path) -> None:
        entry = sorted((work / "embeddings").glob("*.json"))[0]
        stored = json.loads(entry.read_text(encoding="utf-8"))
        stored["vector"] = [0.0, 0.0]
        entry.write_text(json.dumps(stored), encoding="utf-8")

    embedder, _, _ = _discover_twice(monkeypatch, tmp_path, between=zero_one_vector)

    assert len(embedder.calls) == 13, "a zero vector was served from the cache"


def test_the_cache_writes_one_file_per_window_so_a_killed_run_keeps_its_work(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The resumability property, stated as the file layout it depends on. A single combined file
    written at the end would keep nothing from a run killed at window 400 of 641.
    """
    _discover_twice(monkeypatch, tmp_path)
    entries = sorted((tmp_path / "work" / "embeddings").glob("*.json"))

    assert len(entries) == 12, entries
    assert not list((tmp_path / "work" / "embeddings").glob("*.tmp")), (
        "a staging file survived, so a killed run can leave a half-record"
    )
    ids = {json.loads(path.read_text(encoding="utf-8"))["window"]["window_id"] for path in entries}
    assert len(ids) == 12, "two windows share a cache file"


def test_a_store_that_fails_partway_leaves_no_readable_cache_file(tmp_path: Path) -> None:
    """The staged write, which nothing distinguished from a direct one.

    Found SURVIVED by D-140's audit: replacing `staging.write_text(...); staging.replace(path)`
    with a direct `path.write_text(...)` left every test green, because no test had a write fail.
    The observable difference is *which file* holds the garbage — with a direct write the
    destination itself becomes a half-record that a concurrent reader can open.
    """
    from hawedit.visual_pipeline import _EmbeddingCache

    cache = _EmbeddingCache(tmp_path / "embeddings", "Qwen3-VL-Embedding-2B", "rev-1", "abc")
    window = windows(1)[0]
    embedding = VisualEmbedding(window, (1.0, 0.5), "Qwen3-VL-Embedding-2B")
    real_write = Path.write_text

    def fail_after_writing_half(self: Path, data: str, *args: object, **kwargs: object) -> int:
        real_write(self, data[: len(data) // 2], encoding="utf-8")
        raise OSError("no space left on device")

    original = Path.write_text
    Path.write_text = fail_after_writing_half  # type: ignore[method-assign]
    try:
        with pytest.raises(OSError, match="no space"):
            cache.store(embedding)
    finally:
        Path.write_text = original  # type: ignore[method-assign]

    published = list((tmp_path / "embeddings").glob("*.json"))
    assert published == [], (
        f"a failed store published a half-record a reader could open: {published}"
    )
    # The control: a store that does not fail publishes exactly one readable record, so this is
    # not measuring "nothing is ever written".
    cache.store(embedding)
    assert len(list((tmp_path / "embeddings").glob("*.json"))) == 1
    assert cache.load(window) is not None
