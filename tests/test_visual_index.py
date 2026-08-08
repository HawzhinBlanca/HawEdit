"""§3 Stage 2 — the visual index, tested ahead of the models that will fill it.

    **Visual:** `Qwen3-VL-Embedding-2B`, one embedding per scene. Reference settings run
    ~1 fps with a maximum of 64 frames, so segment before embedding. Retrieve top 50 →
    `Qwen3-VL-Reranker-2B` → keep top 5–10.

Four sentences, and every one of them is a silent failure when it is broken. A scene embedded
past the 64-frame ceiling still yields a vector of the right shape; a gap between windows is
footage no visual query can ever reach; a zero vector ranks last against everything forever;
a reranker that returns five items of the right type, one of which it invented, is indistin-
guishable from a good one unless somebody checks membership. Same class every time: the shape
of an answer accepted without its content.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from itertools import pairwise

import pytest

from hawedit.registry import ModelNotInRegistry, WrongRole
from hawedit.visual_index import (
    KEEP_MAX,
    KEEP_MIN,
    MAX_FRAMES_PER_WINDOW,
    REFERENCE_FPS,
    RETRIEVE_K,
    RerankedHit,
    SceneWindow,
    VisualEmbedding,
    VisualHit,
    VisualIndex,
    VisualIndexError,
    assert_window_coverage,
    plan_scene_windows,
    rerank_and_keep,
)

EMBEDDER = "Qwen3-VL-Embedding-2B"
RERANKER = "Qwen3-VL-Reranker-2B"

# 64 frames at 1 fps is 64 seconds. This is the whole arithmetic of the ceiling.
MAX_WINDOW_MS = 64_000


def a_window(
    in_ms: int = 0,
    out_ms: int = 64_000,
    *,
    media_id: str = "m1",
    scene_index: int = 0,
    window_index: int = 0,
    fps: float = REFERENCE_FPS,
) -> SceneWindow:
    return SceneWindow(
        media_id=media_id,
        scene_index=scene_index,
        window_index=window_index,
        in_ms=in_ms,
        out_ms=out_ms,
        fps=fps,
    )


def an_embedding(
    window: SceneWindow | None = None,
    vector: Sequence[float] = (1.0, 0.0, 0.0),
    model_id: str = EMBEDDER,
) -> VisualEmbedding:
    return VisualEmbedding(
        window=window if window is not None else a_window(),
        vector=tuple(vector),
        model_id=model_id,
    )


# =========================================================================================
# SceneWindow — the 64-frame ceiling, as arithmetic rather than as a comment
# =========================================================================================


def test_a_window_of_exactly_sixty_four_seconds_holds_exactly_sixty_four_frames() -> None:
    window = a_window(0, MAX_WINDOW_MS)
    assert window.frame_count == MAX_FRAMES_PER_WINDOW
    assert window.duration_ms == MAX_WINDOW_MS


def test_one_millisecond_past_the_ceiling_is_refused() -> None:
    """The reference settings are '~1 fps with a maximum of 64 frames'. Both at once.

    A 65th frame means one of the two gave way, and neither may: sampling 65 frames breaks
    the maximum, and holding 64 across a longer window breaks the rate. The refusal is what
    forces the caller to segment, which is what §3 asks for in the same sentence.
    """
    with pytest.raises(ValueError, match="64"):
        a_window(0, MAX_WINDOW_MS + 1)


def test_a_long_window_cannot_buy_itself_room_by_lowering_the_frame_rate() -> None:
    """The silent failure this module exists to prevent.

    A 180 s scene at 0.35 fps is 63 frames — under the ceiling, and a perfectly ordinary
    embedding comes back. But `~1 fps` is the setting the published retrieval numbers were
    measured at, and nothing downstream can see that this vector was sampled at a third of
    it. The window is wrong and every score computed from it is wrong by an unknown amount.
    """
    with pytest.raises(ValueError, match="fps"):
        a_window(0, 180_000, fps=0.35)


def test_a_zero_length_window_is_refused() -> None:
    with pytest.raises(ValueError, match="no length"):
        a_window(5_000, 5_000)


def test_a_backwards_window_is_refused() -> None:
    with pytest.raises(ValueError, match="no length"):
        a_window(5_000, 4_000)


def test_negative_indices_are_refused() -> None:
    with pytest.raises(ValueError, match="scene_index"):
        a_window(scene_index=-1)
    with pytest.raises(ValueError, match="window_index"):
        a_window(window_index=-1)


def test_the_window_id_names_media_scene_and_window() -> None:
    window = a_window(media_id="ep12", scene_index=3, window_index=1)
    assert window.window_id == "ep12:s3:w1"


# =========================================================================================
# plan_scene_windows — segment before embedding, and cover everything
# =========================================================================================


def test_a_video_with_no_cuts_shorter_than_the_ceiling_is_one_window() -> None:
    windows = plan_scene_windows("m1", duration_ms=30_000, shot_cuts_ms=())
    assert len(windows) == 1
    assert windows[0].span == (0, 30_000)
    assert windows[0].scene_index == 0
    assert windows[0].window_index == 0


def test_a_scene_longer_than_the_ceiling_is_split_not_downsampled() -> None:
    """§3: 'so segment before embedding'. Three windows, every one at the reference rate."""
    windows = plan_scene_windows("m1", duration_ms=180_000, shot_cuts_ms=())
    assert len(windows) == 3
    assert all(w.fps == REFERENCE_FPS for w in windows)
    assert all(w.frame_count <= MAX_FRAMES_PER_WINDOW for w in windows)
    assert [w.window_index for w in windows] == [0, 1, 2]
    assert {w.scene_index for w in windows} == {0}


def test_the_split_is_even_so_no_window_is_a_runt() -> None:
    """A 64 s window followed by a 1 s window would embed a single frame as a whole scene.

    Its vector is the right shape and means almost nothing, and it competes for retrieval
    slots on equal terms with windows built from 64 frames.
    """
    windows = plan_scene_windows("m1", duration_ms=MAX_WINDOW_MS + 1_000, shot_cuts_ms=())
    assert len(windows) == 2
    durations = [w.duration_ms for w in windows]
    assert max(durations) - min(durations) <= 1, durations


def test_windows_tile_the_media_with_no_gap_and_no_overlap() -> None:
    windows = plan_scene_windows(
        "m1", duration_ms=400_000, shot_cuts_ms=(12_000, 90_000, 91_500, 300_000)
    )
    assert windows[0].in_ms == 0
    assert windows[-1].out_ms == 400_000
    for previous, nxt in pairwise(windows):
        assert nxt.in_ms == previous.out_ms, f"{previous.window_id} -> {nxt.window_id}"


def test_every_cut_starts_a_new_scene_index() -> None:
    windows = plan_scene_windows("m1", duration_ms=30_000, shot_cuts_ms=(10_000, 20_000))
    assert [w.scene_index for w in windows] == [0, 1, 2]
    assert [w.span for w in windows] == [(0, 10_000), (10_000, 20_000), (20_000, 30_000)]


def test_window_index_restarts_within_each_scene() -> None:
    """`window_index` counts within a scene; `scene_index` counts scenes. Not one counter."""
    windows = plan_scene_windows("m1", duration_ms=200_000, shot_cuts_ms=(100_000,))
    by_scene: dict[int, list[int]] = {}
    for window in windows:
        by_scene.setdefault(window.scene_index, []).append(window.window_index)
    assert by_scene == {0: [0, 1], 1: [0, 1]}


def test_a_cut_at_zero_is_refused() -> None:
    """`ingest.detect_shots` drops the first scene start for exactly this reason: the file
    beginning is not a cut. A zero here means the caller passed raw scene starts."""
    with pytest.raises(VisualIndexError, match="0"):
        plan_scene_windows("m1", duration_ms=30_000, shot_cuts_ms=(0, 10_000))


def test_a_cut_at_or_past_the_duration_is_refused() -> None:
    with pytest.raises(VisualIndexError, match="duration"):
        plan_scene_windows("m1", duration_ms=30_000, shot_cuts_ms=(30_000,))
    with pytest.raises(VisualIndexError, match="duration"):
        plan_scene_windows("m1", duration_ms=30_000, shot_cuts_ms=(31_000,))


def test_a_duplicate_cut_is_refused() -> None:
    with pytest.raises(VisualIndexError, match="twice"):
        plan_scene_windows("m1", duration_ms=30_000, shot_cuts_ms=(10_000, 10_000))


def test_cuts_out_of_order_are_sorted_rather_than_refused() -> None:
    scrambled = plan_scene_windows("m1", duration_ms=30_000, shot_cuts_ms=(20_000, 10_000))
    ordered = plan_scene_windows("m1", duration_ms=30_000, shot_cuts_ms=(10_000, 20_000))
    assert scrambled == ordered


def test_a_zero_duration_media_is_refused() -> None:
    with pytest.raises(VisualIndexError, match="duration"):
        plan_scene_windows("m1", duration_ms=0, shot_cuts_ms=())


def test_the_planner_output_passes_its_own_coverage_check() -> None:
    windows = plan_scene_windows(
        "m1", duration_ms=500_000, shot_cuts_ms=(7_000, 8_000, 240_000, 499_000)
    )
    assert_window_coverage(windows, media_id="m1", duration_ms=500_000)


# =========================================================================================
# assert_window_coverage — the net for windows arriving as JSON from another stage
# =========================================================================================


def test_coverage_detects_a_gap() -> None:
    """A gap is footage no visual query can retrieve. §3 Stage 3 unions the paths precisely
    so that nothing is invisible to both; a hole here makes a moment invisible to Path B and
    nothing reports it."""
    windows = (
        a_window(0, 10_000, scene_index=0),
        a_window(12_000, 30_000, scene_index=1),
    )
    with pytest.raises(VisualIndexError, match="gap"):
        assert_window_coverage(windows, media_id="m1", duration_ms=30_000)


def test_coverage_detects_an_overlap() -> None:
    windows = (
        a_window(0, 12_000, scene_index=0),
        a_window(10_000, 30_000, scene_index=1),
    )
    with pytest.raises(VisualIndexError, match="overlap"):
        assert_window_coverage(windows, media_id="m1", duration_ms=30_000)


def test_coverage_detects_a_short_tail() -> None:
    windows = (a_window(0, 29_000),)
    with pytest.raises(VisualIndexError, match="ends at"):
        assert_window_coverage(windows, media_id="m1", duration_ms=30_000)


def test_coverage_detects_a_foreign_media_id() -> None:
    windows = (a_window(0, 30_000, media_id="other"),)
    with pytest.raises(VisualIndexError, match="media"):
        assert_window_coverage(windows, media_id="m1", duration_ms=30_000)


def test_coverage_refuses_an_empty_plan() -> None:
    with pytest.raises(VisualIndexError, match="no windows"):
        assert_window_coverage((), media_id="m1", duration_ms=30_000)


# =========================================================================================
# VisualEmbedding — §7 provenance, and a vector that can actually be compared
# =========================================================================================


def test_an_embedding_model_outside_the_registry_is_refused() -> None:
    with pytest.raises(ModelNotInRegistry):
        an_embedding(model_id="openai/clip-vit-large")


def test_a_registry_model_in_the_wrong_role_is_refused() -> None:
    """Being in §7 says the blueprint permits the model, not that it fits this slot."""
    with pytest.raises(WrongRole):
        an_embedding(model_id=RERANKER)
    with pytest.raises(WrongRole):
        an_embedding(model_id="PySceneDetect")


def test_a_nan_in_the_vector_is_refused() -> None:
    """NaN makes every comparison against it False, so the scene sinks to last place in every
    query and never appears again. A silent, permanent, invisible exclusion."""
    with pytest.raises(ValueError, match="finite"):
        an_embedding(vector=(1.0, math.nan, 0.0))


def test_an_infinity_in_the_vector_is_refused() -> None:
    with pytest.raises(ValueError, match="finite"):
        an_embedding(vector=(1.0, math.inf, 0.0))


def test_a_zero_vector_is_refused() -> None:
    """A zero vector has no direction: cosine similarity against it is undefined, and the
    convenient answer — 0.0 — is a *measurement* this system does not have. Unmeasured is
    refused, never scored."""
    with pytest.raises(ValueError, match="direction"):
        an_embedding(vector=(0.0, 0.0, 0.0))


def test_an_empty_vector_is_refused() -> None:
    with pytest.raises(ValueError, match="empty"):
        an_embedding(vector=())


# =========================================================================================
# VisualIndex — retrieval is arithmetic, and arithmetic can be tested without weights
# =========================================================================================


def _index_of(n: int, media_id: str = "m1") -> VisualIndex:
    """`n` windows tiling `n` × 10 s, each embedded pointing slightly differently."""
    index = VisualIndex(media_id)
    for i in range(n):
        window = SceneWindow(
            media_id=media_id,
            scene_index=i,
            window_index=0,
            in_ms=i * 10_000,
            out_ms=(i + 1) * 10_000,
            fps=REFERENCE_FPS,
        )
        # Rotating in the first quadrant: window 0 is closest to (1, 0), and similarity to
        # (1, 0) falls monotonically with i, so the expected ranking is known exactly.
        angle = (i / max(n, 2)) * (math.pi / 2)
        index.add(an_embedding(window, vector=(math.cos(angle), math.sin(angle))))
    return index


def test_a_duplicate_window_is_refused() -> None:
    index = VisualIndex("m1")
    index.add(an_embedding(a_window(0, 10_000)))
    with pytest.raises(VisualIndexError, match="already"):
        index.add(an_embedding(a_window(0, 10_000)))


def test_an_embedding_from_another_media_is_refused() -> None:
    index = VisualIndex("m1")
    with pytest.raises(VisualIndexError, match="media"):
        index.add(an_embedding(a_window(0, 10_000, media_id="m2")))


def test_a_dimension_mismatch_is_refused_on_add() -> None:
    index = VisualIndex("m1")
    index.add(an_embedding(a_window(0, 10_000, scene_index=0), vector=(1.0, 0.0)))
    with pytest.raises(VisualIndexError, match="dimension"):
        index.add(an_embedding(a_window(10_000, 20_000, scene_index=1), vector=(1.0, 0.0, 0.0)))


def test_two_sampling_rates_in_one_index_are_refused() -> None:
    """The rate is not a detail of how a window was read — it changes what the vector says.

    Measured on the real fixture, the *same* 0–4162 ms span embedded three ways
    (`evidence/m5-2-sampling-rate.md`): 1 vs 2 fps sit **0.117** apart in cosine distance,
    1 vs 4 fps **0.057**, 2 vs 4 fps **0.034**. Three visually distinct scenes sit
    **0.186–0.224** apart. So the rate alone is up to 63% of the distance between different
    footage, and in a mixed index a window can outrank a more relevant one for having been
    sampled differently. `plan_scene_windows` already takes one rate per media, so the honest
    path was uniform; nothing enforced it, which is what let the M5.2 evidence index be built
    at 4 fps without anything saying so.
    """
    index = VisualIndex("m1")
    index.add(an_embedding(a_window(0, 10_000, scene_index=0, fps=1.0), vector=(1.0, 0.0)))
    with pytest.raises(VisualIndexError, match="sampled at 2.0 fps"):
        index.add(an_embedding(a_window(10_000, 20_000, scene_index=1, fps=2.0), vector=(0.0, 1.0)))


def test_one_sampling_rate_above_the_reference_is_accepted_throughout() -> None:
    """The positive control, and the remedy the refusal above names.

    Without this the guard could be satisfied by refusing every rate but 1 fps — which would
    also refuse D-049's fix for short scenes, where a 1400 ms window at 1 fps is a single frame
    with no temporal structure at all. A whole index at 4 fps is legal; a mixed one is not.
    """
    index = VisualIndex("m1")
    for scene in range(3):
        index.add(
            an_embedding(
                a_window(scene * 10_000, scene * 10_000 + 10_000, scene_index=scene, fps=2.0),
                vector=(1.0, float(scene)),
            )
        )
    assert len(index) == 3


def test_a_dimension_mismatch_is_refused_on_query() -> None:
    index = _index_of(3)
    with pytest.raises(VisualIndexError, match="dimension"):
        index.retrieve((1.0, 0.0, 0.0))


def test_retrieval_orders_by_similarity_with_dense_one_based_ranks() -> None:
    index = _index_of(6)
    hits = index.retrieve((1.0, 0.0))
    assert [h.rank for h in hits] == [1, 2, 3, 4, 5, 6]
    assert [h.window.scene_index for h in hits] == [0, 1, 2, 3, 4, 5]
    similarities = [h.similarity for h in hits]
    assert similarities == sorted(similarities, reverse=True)


def test_retrieval_keeps_at_most_k() -> None:
    index = _index_of(60)
    assert len(index.retrieve((1.0, 0.0))) == RETRIEVE_K
    assert RETRIEVE_K == 50
    assert len(index.retrieve((1.0, 0.0), k=5)) == 5


def test_retrieval_on_an_empty_index_returns_nothing_rather_than_raising() -> None:
    assert VisualIndex("m1").retrieve((1.0, 0.0)) == ()


def test_ties_are_broken_by_time_so_the_order_is_reproducible() -> None:
    """Two identical scenes must not swap places between runs; §8.2 counts Recall@K on the
    order this returns."""
    index = VisualIndex("m1")
    for i in range(4):
        index.add(
            an_embedding(
                SceneWindow(
                    media_id="m1",
                    scene_index=i,
                    window_index=0,
                    in_ms=i * 10_000,
                    out_ms=(i + 1) * 10_000,
                    fps=REFERENCE_FPS,
                ),
                vector=(1.0, 0.0),
            )
        )
    hits = index.retrieve((1.0, 0.0))
    assert [h.window.in_ms for h in hits] == [0, 10_000, 20_000, 30_000]


def test_a_non_finite_query_is_refused() -> None:
    index = _index_of(3)
    with pytest.raises(VisualIndexError, match="finite"):
        index.retrieve((math.nan, 0.0))


def test_a_zero_query_is_refused() -> None:
    index = _index_of(3)
    with pytest.raises(VisualIndexError, match="direction"):
        index.retrieve((0.0, 0.0))


# =========================================================================================
# rerank_and_keep — 'Retrieve top 50 → reranker → keep top 5–10'
# =========================================================================================


class FakeReranker:
    """Stands in for `Qwen3-VL-Reranker-2B` (BLOCKED.md #2, #6).

    It records what it was handed, which is the only way to test the half of the contract
    that is about the *call* rather than the result.
    """

    def __init__(self, transform: str = "reverse") -> None:
        self.transform = transform
        self.seen: tuple[VisualHit, ...] = ()

    def rerank(self, query: str, hits: Sequence[VisualHit]) -> tuple[RerankedHit, ...]:
        self.seen = tuple(hits)
        chosen = list(reversed(hits)) if self.transform == "reverse" else list(hits)
        if self.transform == "invent":
            chosen[0] = VisualHit(
                window=a_window(999_000, 999_500, scene_index=99),
                similarity=0.99,
                rank=1,
            )
        if self.transform == "duplicate":
            chosen[1] = chosen[0]
        if self.transform == "drop":
            chosen = chosen[:2]
        out: list[RerankedHit] = []
        for position, hit in enumerate(chosen, start=1):
            similarity = 0.123 if self.transform == "fabricate" else hit.similarity
            out.append(
                RerankedHit(
                    window=hit.window,
                    retrieval_similarity=similarity,
                    rerank_score=1.0 / position,
                    rank=position,
                    model_id=RERANKER,
                )
            )
        return tuple(out)


def test_the_happy_path_retrieves_fifty_and_keeps_seven() -> None:
    index = _index_of(60)
    reranker = FakeReranker()
    kept = rerank_and_keep(index, (1.0, 0.0), "کوردی", reranker, keep=7)
    assert len(reranker.seen) == RETRIEVE_K, "the reranker must see the whole top 50"
    assert [h.rank for h in kept] == [1, 2, 3, 4, 5, 6, 7]
    assert all(h.model_id == RERANKER for h in kept)


def test_keeping_fewer_than_five_is_refused() -> None:
    index = _index_of(60)
    with pytest.raises(VisualIndexError, match="5"):
        rerank_and_keep(index, (1.0, 0.0), "q", FakeReranker(), keep=KEEP_MIN - 1)


def test_keeping_more_than_ten_is_refused() -> None:
    index = _index_of(60)
    with pytest.raises(VisualIndexError, match="10"):
        rerank_and_keep(index, (1.0, 0.0), "q", FakeReranker(), keep=KEEP_MAX + 1)


def test_the_reranker_is_handed_the_retrieved_set_not_a_prefiltered_one() -> None:
    """Reranking a set that is not the top 50 changes what the numbers mean, and the output
    looks identical either way."""
    index = _index_of(60)
    reranker = FakeReranker()
    rerank_and_keep(index, (1.0, 0.0), "q", reranker, keep=5)
    expected = index.retrieve((1.0, 0.0))
    assert reranker.seen == expected


def test_a_reranker_that_invents_a_window_is_refused() -> None:
    """Five results of the right type, one of them a scene that is not in this video."""
    index = _index_of(60)
    with pytest.raises(VisualIndexError, match="not among"):
        rerank_and_keep(index, (1.0, 0.0), "q", FakeReranker("invent"), keep=5)


def test_a_reranker_that_returns_the_same_window_twice_is_refused() -> None:
    index = _index_of(60)
    with pytest.raises(VisualIndexError, match="twice"):
        rerank_and_keep(index, (1.0, 0.0), "q", FakeReranker("duplicate"), keep=5)


def test_a_reranker_returning_fewer_than_keep_is_refused() -> None:
    index = _index_of(60)
    with pytest.raises(VisualIndexError, match="returned 2"):
        rerank_and_keep(index, (1.0, 0.0), "q", FakeReranker("drop"), keep=5)


def test_a_reranker_that_rewrites_the_retrieval_score_is_refused() -> None:
    """`retrieval_similarity` is carried through, never restated. It is the evidence that
    lets §8.2 ask whether reranking changed anything; a reranker that supplies its own has
    erased the comparison."""
    index = _index_of(60)
    with pytest.raises(VisualIndexError, match="retrieval"):
        rerank_and_keep(index, (1.0, 0.0), "q", FakeReranker("fabricate"), keep=5)


def test_an_index_below_the_survivor_floor_is_refused_rather_than_shortened() -> None:
    """D-037 clause 4, restored (D-066). It considered returning whatever exists and rejected it.

    §8.2 counts Recall@K on this list, so three results in a column that says five is a number
    that does not mean what the column says. A three-window index is the *fixture*, not the
    product — a 40-minute episode is roughly 75 windows at 2 fps — so the refusal costs nothing
    real and the alternative silently mislabels every downstream metric.

    This test replaced one asserting `len(kept) == 3`, written when the guard was reverted to
    `min(keep, len(reranked))` with no superseding decision while `PROGRESS.md` still certified
    the refusal. The docstring two lines above the change still said the reranker "may not drop
    below the survivor count".
    """
    index = _index_of(3)
    with pytest.raises(VisualIndexError, match="too short for Stage 2's survivor slice"):
        rerank_and_keep(index, (1.0, 0.0), "q", FakeReranker(), keep=5)


def test_the_refusal_is_made_before_the_reranker_is_asked_to_run() -> None:
    """The negative control on where the check sits: a GPU pass costs seconds per window.

    A reranker that raises if called at all still lets the refusal through, which proves the
    index size is checked before any scoring — not after paying for it.
    """

    class _Explode:
        model_id = RERANKER

        def rerank(self, query: str, hits: object) -> tuple[RerankedHit, ...]:
            raise AssertionError("the reranker was called on an index below the survivor floor")

    with pytest.raises(VisualIndexError, match="too short for Stage 2's survivor slice"):
        rerank_and_keep(_index_of(3), (1.0, 0.0), "q", _Explode(), keep=5)


def test_an_index_at_the_floor_is_accepted_and_returns_exactly_the_survivor_count() -> None:
    """The positive control. A guard that refused every index would pass both tests above."""
    kept = rerank_and_keep(_index_of(5), (1.0, 0.0), "q", FakeReranker(), keep=5)
    assert len(kept) == 5
    assert [hit.rank for hit in kept] == [1, 2, 3, 4, 5]


def test_a_reranked_hit_from_the_wrong_role_is_refused() -> None:
    with pytest.raises(WrongRole):
        RerankedHit(
            window=a_window(),
            retrieval_similarity=0.5,
            rerank_score=0.9,
            rank=1,
            model_id=EMBEDDER,
        )


def test_a_reranked_hit_rank_is_one_based() -> None:
    with pytest.raises(ValueError, match="1-based"):
        RerankedHit(
            window=a_window(),
            retrieval_similarity=0.5,
            rerank_score=0.9,
            rank=0,
            model_id=RERANKER,
        )
