"""The §3 Stage 2 embedder's refusals, all reachable without 4 GB of weights.

`models/` is git-ignored, so a CI runner has no checkpoint and the real forward pass lives in
`evidence/m5-2-embedder.md`. What is testable everywhere is the part that decides whether the
forward pass is even allowed to happen — the §7 role check, the declared-recipe check, and the
refusal to substitute a CPU for the GPU §6 specifies. Those are the checks that stop a wrong
number being produced, so those are the ones with tests.

The recipe fixtures below are written by hand rather than read from `models/`, so they pin the
*handling* of a recipe and keep working on a machine that has never downloaded one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hawedit.qwen_visual import (
    EMBEDDING_MODEL_ID,
    EmbedderUnavailable,
    QwenVisualEmbedder,
    QwenVisualReranker,
    read_pooling_recipe,
    read_score_tokens,
)
from hawedit.registry import WrongRole
from hawedit.video_input import WindowFrames
from hawedit.visual_index import SceneWindow, VisualHit, rerank_and_keep


def a_checkpoint(
    tmp_path: Path,
    pooling_mode: str = "lasttoken",
    dimension: int = 2048,
    prompt: str | None = "Represent the user's input.",
) -> Path:
    """A directory shaped like the checkpoint, carrying only what the recipe is read from."""
    (tmp_path / "1_Pooling").mkdir(parents=True, exist_ok=True)
    (tmp_path / "1_Pooling" / "config.json").write_text(
        json.dumps({"pooling_mode": pooling_mode, "embedding_dimension": dimension}),
        encoding="utf-8",
    )
    if prompt is not None:
        (tmp_path / "config_sentence_transformers.json").write_text(
            json.dumps({"default_prompt_name": "default", "prompts": {"default": prompt}}),
            encoding="utf-8",
        )
    return tmp_path


# --- the recipe comes from the checkpoint ---------------------------------------------------


def test_the_recipe_is_read_from_the_checkpoints_own_files(tmp_path: Path) -> None:
    recipe = read_pooling_recipe(a_checkpoint(tmp_path))
    assert (recipe.pooling_mode, recipe.dimension) == ("lasttoken", 2048)
    assert recipe.prompt == "Represent the user's input."


def test_a_checkpoint_that_does_not_state_its_pooling_is_refused(tmp_path: Path) -> None:
    """Guessing is how two runs produce vectors that are the right shape and incomparable."""
    with pytest.raises(EmbedderUnavailable, match="does not state how"):
        read_pooling_recipe(tmp_path)


def test_a_pooling_mode_this_module_does_not_implement_is_refused(tmp_path: Path) -> None:
    """The negative control on the recipe check.

    `mean` pooling would load, run, and return 2048 finite non-zero floats that pass every
    check `VisualEmbedding` makes — so nothing downstream could tell. Without this test the
    recipe would be read and then ignored, which is the same as not reading it.
    """
    with pytest.raises(EmbedderUnavailable, match="pools by 'mean'"):
        QwenVisualEmbedder(a_checkpoint(tmp_path, pooling_mode="mean"))


def test_the_declared_prompt_is_carried_even_without_the_sentence_transformers_file(
    tmp_path: Path,
) -> None:
    """The chat template injects this same string as its default system message, so the fallback
    has to be that string and not something reasonable-looking."""
    recipe = read_pooling_recipe(a_checkpoint(tmp_path, prompt=None))
    assert recipe.prompt == "Represent the user's input."


# --- §7 before any weights move -------------------------------------------------------------


def test_a_model_outside_section_7_never_reaches_the_loader(tmp_path: Path) -> None:
    with pytest.raises(Exception, match="not in BLUEPRINT §7"):
        QwenVisualEmbedder(a_checkpoint(tmp_path), model_id="clip-vit-huge")


def test_a_section_7_model_with_the_wrong_job_is_refused(tmp_path: Path) -> None:
    """Membership in §7 says the blueprint permits the model, not that it fits this slot.

    Audit finding #8's rule, applied here: `resolve_role` runs before the 4 GB load, so
    PySceneDetect cannot be handed in as the visual embedder.
    """
    with pytest.raises(WrongRole, match="cannot be used as the visual embedding model"):
        QwenVisualEmbedder(a_checkpoint(tmp_path), model_id="PySceneDetect")


def test_missing_weights_name_the_command_that_fetches_them(tmp_path: Path) -> None:
    absent = tmp_path / "not-downloaded"
    with pytest.raises(EmbedderUnavailable, match="fetch-models.sh"):
        QwenVisualEmbedder(absent)


def test_the_default_model_id_is_the_registry_id_for_the_embedder() -> None:
    """A drifting id would fail `resolve_role` at construction, but only for callers who use the
    default — this pins it directly."""
    from hawedit.registry import REGISTRY

    assert REGISTRY[EMBEDDING_MODEL_ID].role == "visual_embedding"


# --- the GPU is not optional ----------------------------------------------------------------


def test_asking_for_cuda_without_cuda_is_refused_rather_than_run_on_cpu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§6 puts Stage 2 on a GPU. A silent CPU fallback would change what every number measured
    afterwards is about — the same rule `asr.Hardware` enforces for throughput, and the same
    reason `render_clip` refuses an absent encoder instead of substituting x264.

    `torch.cuda.is_available` is answered directly so this runs on a GPU box too: deciding by
    what the machine happens to have would make the test vanish exactly where it matters.
    """
    torch = pytest.importorskip("torch", reason="the gpu extra is not installed")
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    embedder = QwenVisualEmbedder(a_checkpoint(tmp_path), device="cuda:0")
    with pytest.raises(EmbedderUnavailable, match="reports no CUDA"):
        embedder._load()


# =========================================================================================
# The reranker. §3 Stage 2: "Retrieve top 50 -> Qwen3-VL-Reranker-2B -> keep top 5-10."
#
# `rerank_and_keep` already enforces what a reranker may not do. These tests check that this
# reranker *produces* conforming output rather than depending on being caught — the score is
# injected, so the whole contract is exercised without 4 GB of weights.
# =========================================================================================


def a_reranker_checkpoint(tmp_path: Path, true_id: int = 9693, false_id: int = 2152) -> Path:
    (tmp_path / "1_LogitScore").mkdir(parents=True, exist_ok=True)
    (tmp_path / "1_LogitScore" / "config.json").write_text(
        json.dumps({"true_token_id": true_id, "false_token_id": false_id}), encoding="utf-8"
    )
    (tmp_path / "config_sentence_transformers.json").write_text(
        json.dumps(
            {
                "default_prompt_name": "query",
                "prompts": {"query": "Retrieve text relevant to the user's query."},
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def a_window(index: int, in_ms: int) -> SceneWindow:
    return SceneWindow(
        media_id="m", scene_index=index, window_index=0, in_ms=in_ms, out_ms=in_ms + 2_000, fps=1.0
    )


def hits_for(*windows: SceneWindow) -> tuple[VisualHit, ...]:
    """Retrieval output: descending similarity, dense 1-based ranks."""
    return tuple(
        VisualHit(window=w, similarity=0.9 - 0.1 * i, rank=i + 1) for i, w in enumerate(windows)
    )


def scored_reranker(
    tmp_path: Path, scores: dict[str, float], monkeypatch: pytest.MonkeyPatch
) -> QwenVisualReranker:
    """A real reranker with `score` answered from a table instead of by the model."""
    reranker = QwenVisualReranker(
        a_reranker_checkpoint(tmp_path),
        read_frames=lambda w: WindowFrames(window=w, paths=(Path("f0.jpg"), Path("f1.jpg"))),
    )
    monkeypatch.setattr(
        QwenVisualReranker, "score", lambda _self, _q, frames: scores[frames.window.window_id]
    )
    return reranker


def test_the_score_tokens_are_read_from_the_checkpoint(tmp_path: Path) -> None:
    tokens = read_score_tokens(a_reranker_checkpoint(tmp_path, true_id=1, false_id=2))
    assert (tokens.true_id, tokens.false_id) == (1, 2)


def test_a_checkpoint_that_does_not_name_its_score_tokens_is_refused(tmp_path: Path) -> None:
    """Hardcoding them would survive a tokenizer bump and rank footage by two arbitrary tokens,
    with every score still landing in [0, 1]."""
    with pytest.raises(EmbedderUnavailable, match="which tokens its score"):
        read_score_tokens(tmp_path)


def test_the_reranker_reorders_by_its_own_score(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The point of reranking: retrieval order must be allowed to change."""
    windows = [a_window(0, 0), a_window(1, 2_000), a_window(2, 4_000)]
    hits = hits_for(*windows)
    reranker = scored_reranker(
        tmp_path, {"m:s0:w0": 0.10, "m:s1:w0": 0.99, "m:s2:w0": 0.50}, monkeypatch
    )
    out = reranker.rerank("ڕۆژنامەوانی", hits)
    assert [h.window.scene_index for h in out] == [1, 2, 0]
    assert [h.rank for h in out] == [1, 2, 3]


def test_the_retrieval_score_is_carried_through_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`rerank_and_keep` refuses a reranker that restates the retrieval score, because that field
    is what makes "did reranking change anything?" answerable in §8.2. Produced correctly here,
    not merely survivable."""
    windows = [a_window(0, 0), a_window(1, 2_000)]
    hits = hits_for(*windows)
    original = {h.window.window_id: h.similarity for h in hits}
    injected = {"m:s0:w0": 0.2, "m:s1:w0": 0.77}
    reranker = scored_reranker(tmp_path, injected, monkeypatch)
    for hit in reranker.rerank("ڕۆژنامەوانی", hits):
        assert hit.retrieval_similarity == original[hit.window.window_id]
        # And `rerank_score` is the model's number, not a copy of the retrieval one. Asserting
        # merely that the two differ would pass by accident: the first draft of this test scored
        # a window 0.8 whose retrieval similarity was also 0.8, and went red for no defect.
        assert hit.rerank_score == injected[hit.window.window_id]


def test_output_survives_the_contract_rerank_and_keep_enforces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end against the real gatekeeper, not a paraphrase of it.

    `rerank_and_keep` checks for invented windows, duplicates, a short return and a restated
    retrieval score. Driving the real function is the only way to know this reranker satisfies
    all four at once.
    """
    from hawedit.visual_index import KEEP_MIN, VisualEmbedding, VisualIndex

    index = VisualIndex("m")
    windows = [a_window(i, i * 2_000) for i in range(KEEP_MIN)]
    for i, window in enumerate(windows):
        vector = tuple(1.0 if j == i else 0.0 for j in range(KEEP_MIN))
        index.add(VisualEmbedding(window=window, vector=vector, model_id=EMBEDDING_MODEL_ID))
    reranker = scored_reranker(
        tmp_path, {w.window_id: 0.1 * (i + 1) for i, w in enumerate(windows)}, monkeypatch
    )
    kept = rerank_and_keep(
        index,
        query_vector=(1.0,) * KEEP_MIN,
        query_text="ڕۆژنامەوانی",
        reranker=reranker,
        keep=KEEP_MIN,
        k=KEEP_MIN,
    )
    assert len(kept) == KEEP_MIN
    assert [h.rank for h in kept] == list(range(1, KEEP_MIN + 1))
    # Highest model score first — the table above scores the last window highest.
    assert kept[0].window.scene_index == KEEP_MIN - 1


def test_windows_the_model_scores_equally_keep_a_stable_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§8.2 counts Recall@K on this order, so a tie must not resolve differently between runs.

    Ties break by time then id — the same rule `VisualIndex.retrieve` uses, because two
    different tie-breaks in one pipeline is the same bug as none.
    """
    windows = [a_window(0, 4_000), a_window(1, 0), a_window(2, 2_000)]
    tied = {w.window_id: 0.5 for w in windows}
    reranker = scored_reranker(tmp_path, tied, monkeypatch)
    order = [h.window.in_ms for h in reranker.rerank("ڕۆژنامەوانی", hits_for(*windows))]
    assert order == [0, 2_000, 4_000]


def test_a_section_7_model_with_the_wrong_job_cannot_be_the_reranker(tmp_path: Path) -> None:
    with pytest.raises(WrongRole, match="cannot be used as the visual reranker"):
        QwenVisualReranker(
            a_reranker_checkpoint(tmp_path),
            read_frames=lambda w: WindowFrames(window=w, paths=(Path("f0.jpg"),)),
            model_id=EMBEDDING_MODEL_ID,
        )
