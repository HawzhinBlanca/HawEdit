from __future__ import annotations

import hashlib
import json
import os
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
    VideoUnderstanding,
)
from hawedit.video_input import VideoInputError, WindowFrames
from hawedit.visual_index import (
    RerankedHit,
    SceneWindow,
    VisualEmbedding,
    VisualHit,
)
from hawedit.visual_pipeline import (
    FrameReader,
    ReaderFactory,
    VisualComposer,
    VisualDiscoveryResult,
    VisualPipelineError,
)


def source_file(tmp_path: Path) -> Path:
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
        source_file(tmp_path),
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
        composer.discover(
            source_file(tmp_path), windows(3), "گرنگ", tmp_path / "work", media_id="m"
        )


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
        source_file(tmp_path), windows(12), "گرنگ", tmp_path / "work", media_id="m"
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
        source_file(tmp_path), windows(12), "گرنگ", tmp_path / "work", media_id="m"
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
    revisions: tuple[str | None, str | None] = (
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    ),
) -> tuple[CountingEmbedder, list[str], tuple[VisualDiscoveryResult, VisualDiscoveryResult]]:
    """Run `discover` twice over one work directory, optionally disturbing it in between."""
    extracted: list[str] = []

    def fake_extract(
        video: Path, window: SceneWindow, dest: Path, ffmpeg: Path | None = None
    ) -> WindowFrames:
        extracted.append(window.window_id)
        return WindowFrames(window, (dest / "frame.jpg", dest / "frame2.jpg"))

    monkeypatch.setattr("hawedit.visual_pipeline.extract_window_frames", fake_extract)
    source = source_file(tmp_path)
    work = tmp_path / "work"
    embedder = CountingEmbedder()

    def run(revision: str | None) -> VisualDiscoveryResult:
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
    # The readiness merge added `embedding_cache_hits`/`embedding_cache_misses` to the result,
    # and those are exactly the fields that must differ between a cold pass and a warm one - a
    # bare equality here now fails on the evidence that reuse worked. Compare everything else,
    # then assert the counters separately, which is a stronger statement than the original.
    counters = {"embedding_cache_hits", "embedding_cache_misses"}
    assert {k: v for k, v in first.to_dict().items() if k not in counters} == {
        k: v for k, v in second.to_dict().items() if k not in counters
    }, "the reused run produced a different result"
    assert (first.to_dict()["embedding_cache_hits"], first.to_dict()["embedding_cache_misses"]) == (
        0,
        12,
    ), "the first pass should have found nothing to reuse"
    assert (
        second.to_dict()["embedding_cache_hits"],
        second.to_dict()["embedding_cache_misses"],
    ) == (12, 0), "the second pass should have reused every window"


def test_a_different_checkpoint_revision_re_embeds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The control that matters most. Vectors from two checkpoints live in different embedding
    spaces, and mixing them makes every cosine similarity meaningless while looking fine — worse
    than the 880.7 s it saves. D-073 pinned the revisions; this makes the pin load-bearing.
    """
    embedder, _, _ = _discover_twice(
        monkeypatch,
        tmp_path,
        revisions=(
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        ),
    )

    assert len(embedder.calls) == 24, "a second checkpoint reused the first one's vectors"


def test_an_unidentified_checkpoint_never_licenses_a_reuse(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`None` means "not pinned". It must not license a reuse: vectors from a checkpoint nobody
    can name are not evidence that this run's weights produced them.

    This branch spelled "not pinned" as the empty string; the readiness merge refuses any
    revision that is not one lowercase 40-hex commit, and expresses "no identity, so no cache"
    as `None`. The property is unchanged and so is the count below - a disabled cache and a
    cache that never matches both re-embed every window. D-140.
    """
    embedder, _, _ = _discover_twice(monkeypatch, tmp_path, revisions=(None, None))

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

    cache = _EmbeddingCache(tmp_path / "embeddings", "Qwen3-VL-Embedding-2B", "a" * 40, "abc")
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


def test_a_store_that_fails_partway_leaves_no_readable_cache_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The staged write, which nothing distinguished from a direct one.

    Found SURVIVED by D-140's audit: replacing `staging.write_text(...); staging.replace(path)`
    with a direct `path.write_text(...)` left every test green, because no test had a write fail.
    The observable difference is *which file* holds the garbage — with a direct write the
    destination itself becomes a half-record that a concurrent reader can open.
    """
    from hawedit.visual_pipeline import _EmbeddingCache

    cache = _EmbeddingCache(tmp_path / "embeddings", "Qwen3-VL-Embedding-2B", "a" * 40, "abc")
    window = windows(1)[0]
    embedding = VisualEmbedding(window, (1.0, 0.5), "Qwen3-VL-Embedding-2B")
    # The readiness merge replaced `staging.write_text(...); staging.replace(path)` with a
    # NamedTemporaryFile staged in binary, fsynced, then `os.replace`d - so patching
    # `Path.write_text` no longer intercepts anything and the store would quietly succeed. The
    # property is unchanged and the failure is injected where publication now happens.
    def fail_to_publish(src: object, dst: object) -> None:
        raise OSError("no space left on device")

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "replace", fail_to_publish)
        with pytest.raises(VisualPipelineError, match="no space"):
            cache.store(embedding)

    staged = list((tmp_path / "embeddings").glob(".embedding-*"))
    assert staged == [], f"a failed store left its staging file behind: {staged}"

    published = list((tmp_path / "embeddings").glob("*.json"))
    assert published == [], (
        f"a failed store published a half-record a reader could open: {published}"
    )
    # The control: a store that does not fail publishes exactly one readable record, so this is
    # not measuring "nothing is ever written".
    cache.store(embedding)
    assert len(list((tmp_path / "embeddings").glob("*.json"))) == 1
    assert cache.load(window) is not None


# --- the six refusals on this module's boundary, none of which any test held ------------------
#
# Measured by mutation against a shadow copy of `src/hawedit`: neutralising each of the six one
# at a time left tests/test_visual_pipeline.py, tests/test_visual_index.py and
# tests/test_discovery.py green. The module's own score-provenance loop was among them.


def _frames(source: Path, window: SceneWindow, dest: Path, ffmpeg: Path | None) -> WindowFrames:
    return WindowFrames(window, (dest / "a.jpg", dest / "b.jpg"))


def _composer(
    reader_factory: Callable[[FrameReader, Callable[[SceneWindow], float]], VideoUnderstanding],
    keep: int = 5,
) -> VisualComposer:
    return VisualComposer(FakeEmbedder(), FakeReranker, reader_factory, keep=keep)


def test_an_empty_query_is_refused_before_the_text_encoder_sees_it(tmp_path: Path) -> None:
    """§3 Stage 2 is "Retrieve top 50 → rerank → keep top 5–10". With no query there is no
    retrieval, and five arbitrary windows would reach VideoChat3 labelled as query results.

    `FakeEmbedder.embed_text` asserts the query is the real one, so if this refusal ever moved
    below the encoder this test would fail on that assertion instead of passing quietly.
    """
    composer = _composer(lambda read, score: FakeReader(read, score, []))
    for query in ("", "   ", "\n\t"):
        with pytest.raises(VisualPipelineError, match="must not be empty"):
            composer.discover(
                source_file(tmp_path), windows(12), query, tmp_path / "work", media_id="m"
            )


def test_windows_belonging_to_another_media_are_refused(tmp_path: Path) -> None:
    """A mismatch means one film's scene plan was passed while composing another's — the
    embeddings would be real and the timestamps would address footage that is not there.
    """
    composer = _composer(lambda read, score: FakeReader(read, score, []))
    with pytest.raises(VisualPipelineError, match="were passed while composing"):
        composer.discover(
            source_file(tmp_path), windows(12), "گرنگ", tmp_path / "work", media_id="other"
        )


def test_a_window_id_reused_with_different_boundaries_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`SceneWindow.window_id` is `media:scene:window` — it does not include the boundaries.

    An adapter that re-derives a window from its indices can therefore produce the same id with
    a different time range, and the frame cache would hand back the pixels of the old range: the
    reranker scores 16,000..17,000 ms using the frames of 11,000..12,000 ms, and Stages 4 and 5
    cut on footage the model never saw.
    """
    monkeypatch.setattr("hawedit.visual_pipeline.extract_window_frames", _frames)

    class CollidingReader:
        def __init__(
            self, read_frames: FrameReader, score_window: Callable[[SceneWindow], float]
        ) -> None:
            self.read_frames = read_frames
            self.score_window = score_window

        def read_scenes(self, items: Sequence[SceneWindow]) -> SceneReadings:
            first = items[0]
            self.read_frames(first)
            impostor = SceneWindow(
                media_id=first.media_id,
                scene_index=first.scene_index,
                window_index=first.window_index,
                in_ms=first.in_ms + 5_000,
                out_ms=first.out_ms + 5_000,
                fps=first.fps,
            )
            assert impostor.window_id == first.window_id
            self.read_frames(impostor)
            raise AssertionError("the cache should have refused the second call")

    composer = _composer(lambda read, score: CollidingReader(read, score))
    with pytest.raises(VisualPipelineError, match="reused with different boundaries"):
        composer.discover(
            source_file(tmp_path), windows(12), "گرنگ", tmp_path / "work", media_id="m"
        )


def test_a_score_requested_for_a_non_survivor_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Only reranked survivors have a score. Asking for one outside that set raises `KeyError`,
    a type `pipeline.py:1207-1221` does not catch — it handles `VisualPipelineError` and records
    a StageSkipped, so a bare KeyError takes the whole run down after Stage 2, which is the most
    expensive stage in this pipeline.
    """
    monkeypatch.setattr("hawedit.visual_pipeline.extract_window_frames", _frames)

    class StrangerReader:
        def __init__(
            self, read_frames: FrameReader, score_window: Callable[[SceneWindow], float]
        ) -> None:
            self.read_frames = read_frames
            self.score_window = score_window

        def read_scenes(self, items: Sequence[SceneWindow]) -> SceneReadings:
            stranger = SceneWindow(
                media_id="m", scene_index=99, window_index=0, in_ms=0, out_ms=1_000, fps=2.0
            )
            self.score_window(stranger)
            raise AssertionError("scoring a non-survivor should have been refused")

    composer = _composer(lambda read, score: StrangerReader(read, score))
    with pytest.raises(VisualPipelineError, match="non-survivor"):
        composer.discover(
            source_file(tmp_path), windows(12), "گرنگ", tmp_path / "work", media_id="m"
        )


# The sixth refusal — `accounted != set(scores)`, "Path B candidates do not exactly match the
# reranked survivors" — has no test here on purpose, and the reason is worth recording rather
# than leaving as an apparent omission.
#
# Both directions of the mismatch are refused before that line is reached. A reader that DROPS a
# survivor is refused by `path_b.py:251` ("the model omitted readings for [...]; silently dropping
# scenes destroys visual recall"), measured by writing that test and watching PathBError arrive
# instead. A reader that ADDS one is refused by the non-survivor score check above, because the
# extra window has no entry in `scores`. So the guard is defence in depth against a state no
# legal caller can construct: unreachable rather than untested, which is a different thing and
# should not be papered over with a test that fabricates the state directly.


def test_a_path_b_score_that_is_not_the_reranker_score_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The check the module exists to perform.

    `Candidate.score` becomes `MergedCandidate.visual_score`, which is what the §5 sidecar
    publishes and what §8.2's per-path metrics are computed from. A number that did not come
    from the reranker travelling under that name is precisely what this loop refuses — and
    removing the loop raised nothing any test noticed.
    """
    monkeypatch.setattr("hawedit.visual_pipeline.extract_window_frames", _frames)

    class InventiveReader:
        def __init__(
            self, read_frames: FrameReader, score_window: Callable[[SceneWindow], float]
        ) -> None:
            self.read_frames = read_frames
            self.score_window = score_window

        def read_scenes(self, items: Sequence[SceneWindow]) -> SceneReadings:
            return SceneReadings(
                tuple(SceneReading(item, sv6d(item), 0.5, PATH_B_MODEL) for item in items)
            )

    composer = _composer(lambda read, score: InventiveReader(read, score))
    with pytest.raises(VisualPipelineError, match="is not its reranker score"):
        composer.discover(
            source_file(tmp_path), windows(12), "گرنگ", tmp_path / "work", media_id="m"
        )


def test_composed_visual_run_deletes_every_cached_source_frame(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    private_dirs: list[Path] = []

    def fake_extract(
        source: Path, window: SceneWindow, dest: Path, ffmpeg: Path | None
    ) -> WindowFrames:
        owner = dest / ".owned-attempt"
        owner.mkdir(parents=True)
        paths = (owner / "frame-0.jpg", owner / "frame-1.jpg")
        for path in paths:
            path.write_bytes(b"private source pixel")
        identity = os.lstat(owner)
        private_dirs.append(owner)
        return WindowFrames(
            window,
            paths,
            _owner_dir=owner,
            _owner_identity=(identity.st_dev, identity.st_ino),
        )

    monkeypatch.setattr("hawedit.visual_pipeline.extract_window_frames", fake_extract)
    composer = VisualComposer(
        FakeEmbedder(),
        FakeReranker,
        lambda read, score: FakeReader(read, score, []),
        keep=5,
    )

    result = composer.discover(
        tmp_path / "m.mp4",
        windows(5),
        "\u06af\u0631\u0646\u06af",
        tmp_path / "work",
        media_id="m",
    )

    assert len(result.candidates) == 5
    assert len(private_dirs) == 5
    assert all(not path.exists() for path in private_dirs)


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


def _cached_discovery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    revisions: tuple[str, str] = ("a" * 40, "a" * 40),
    between: Callable[[Path], None] | None = None,
) -> tuple[CountingEmbedder, list[str], VisualDiscoveryResult, VisualDiscoveryResult]:
    extracted: list[str] = []

    def fake_extract(
        source: Path, window: SceneWindow, dest: Path, ffmpeg: Path | None
    ) -> WindowFrames:
        extracted.append(window.window_id)
        return WindowFrames(window, (dest / "frame.jpg", dest / "frame2.jpg"))

    monkeypatch.setattr("hawedit.visual_pipeline.extract_window_frames", fake_extract)
    source = source_file(tmp_path)
    work = tmp_path / "work"
    embedder = CountingEmbedder()

    def run(revision: str | None) -> VisualDiscoveryResult:
        return VisualComposer(
            embedder,
            FakeReranker,
            lambda read, score: FakeReader(read, score, []),
            keep=5,
            embedding_revision=revision,
        ).discover(source, windows(5), "گرنگ", work, media_id="m")

    first = run(revisions[0])
    if between is not None:
        between(work)
    second = run(revisions[1])
    return embedder, extracted, first, second


def test_second_visual_pass_reuses_every_window_embedding(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    embedder, extracted, first, second = _cached_discovery(monkeypatch, tmp_path)

    assert len(embedder.calls) == 5
    assert len(extracted) == 5
    assert first.embedding_cache_hits == 0
    assert first.embedding_cache_misses == 5
    assert second.embedding_cache_hits == 5
    assert second.embedding_cache_misses == 0
    assert second.to_dict()["embedding_cache_hits"] == 5
    assert len(list((tmp_path / "work" / "embeddings").glob("*.json"))) == 5
    assert not list((tmp_path / "work" / "embeddings").glob("*.tmp"))


def test_checkpoint_revision_change_re_embeds_every_window(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    embedder, _, _, second = _cached_discovery(
        monkeypatch, tmp_path, revisions=("a" * 40, "b" * 40)
    )

    assert len(embedder.calls) == 10
    assert second.embedding_cache_hits == 0
    assert second.embedding_cache_misses == 5


def test_replaced_source_re_embeds_every_window(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def replace_source(_work: Path) -> None:
        (tmp_path / "m.mp4").write_bytes(b"different source bytes")

    embedder, _, _, second = _cached_discovery(monkeypatch, tmp_path, between=replace_source)

    assert len(embedder.calls) == 10
    assert second.embedding_cache_hits == 0
    assert second.embedding_cache_misses == 5


def test_truncated_cache_record_re_embeds_only_that_window(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def truncate_one(work: Path) -> None:
        records = sorted((work / "embeddings").glob("*.json"))
        assert len(records) == 5
        records[0].write_text('{"schema":', encoding="utf-8")

    embedder, _, _, second = _cached_discovery(monkeypatch, tmp_path, between=truncate_one)

    assert len(embedder.calls) == 6
    assert second.embedding_cache_hits == 4
    assert second.embedding_cache_misses == 1


def test_cache_record_refuses_boolean_vector_even_with_a_matching_digest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def insert_boolean(work: Path) -> None:
        record = sorted((work / "embeddings").glob("*.json"))[0]
        stored = json.loads(record.read_text(encoding="utf-8"))
        stored["vector"] = [True, 0.5]
        body = {key: value for key, value in stored.items() if key != "record_sha256"}
        canonical = json.dumps(
            body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        stored["record_sha256"] = hashlib.sha256(canonical).hexdigest()
        record.write_text(json.dumps(stored), encoding="utf-8")

    embedder, _, _, second = _cached_discovery(monkeypatch, tmp_path, between=insert_boolean)

    assert len(embedder.calls) == 6
    assert second.embedding_cache_hits == 4
    assert second.embedding_cache_misses == 1


def test_failed_cache_publish_leaves_no_shared_temporary_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "hawedit.visual_pipeline.os.replace",
        lambda *_args: (_ for _ in ()).throw(OSError("disk full")),
    )
    monkeypatch.setattr(
        "hawedit.visual_pipeline.extract_window_frames",
        lambda source, window, dest, ffmpeg: WindowFrames(
            window, (dest / "frame.jpg", dest / "frame2.jpg")
        ),
    )
    composer = VisualComposer(
        CountingEmbedder(),
        FakeReranker,
        lambda read, score: FakeReader(read, score, []),
        keep=5,
        embedding_revision="a" * 40,
    )

    with pytest.raises(VisualPipelineError, match="could not publish"):
        composer.discover(
            source_file(tmp_path), windows(5), "گرنگ", tmp_path / "work", media_id="m"
        )

    cache_dir = tmp_path / "work" / "embeddings"
    assert not list(cache_dir.glob("*.json"))
    assert not list(cache_dir.glob("*.tmp"))


def test_cache_revision_must_be_an_exact_pinned_commit() -> None:
    with pytest.raises(ValueError, match="40-hex"):
        VisualComposer(
            FakeEmbedder(),
            FakeReranker,
            lambda read, score: FakeReader(read, score, []),
            embedding_revision="main",
        )
