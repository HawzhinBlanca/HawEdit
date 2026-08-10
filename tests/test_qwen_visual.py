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
from contextlib import contextmanager, nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from hawedit.qwen_visual import (
    EMBEDDING_MODEL_ID,
    BinaryScoreTokens,
    EmbedderUnavailable,
    PoolingRecipe,
    QwenVisualEmbedder,
    QwenVisualReranker,
    load_processor_and_model,
    read_pooling_prompt,
    read_pooling_recipe,
    read_score_tokens,
)
from hawedit.registry import WrongRole
from hawedit.video_input import TimestampsOutsideWindow, WindowFrames
from hawedit.visual_index import SceneWindow, VisualEmbedding, VisualHit, rerank_and_keep


def a_checkpoint(
    tmp_path: Path,
    pooling_mode: str = "lasttoken",
    dimension: int = 2048,
    prompt: str | None = "Represent the user's input.",
) -> Path:
    """A directory shaped like the checkpoint, carrying only what the recipe is read from."""
    (tmp_path / "config.json").write_text(json.dumps({"model_type": "qwen3_vl"}), encoding="utf-8")
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


def test_qwen_adapters_release_loaded_gpu_state_idempotently(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    released: list[str] = []
    monkeypatch.setattr("hawedit.qwen_visual.release_cuda_model_memory", released.append)
    checkpoint = a_checkpoint(tmp_path)
    embedder = QwenVisualEmbedder(checkpoint, device="cuda:1")
    embedder._loaded = (object(), object())
    embedder._recipe = PoolingRecipe("lasttoken", 2048, "prompt")

    def unused_reader(_window: SceneWindow) -> WindowFrames:
        raise AssertionError("close must not read frames")

    reranker = QwenVisualReranker(checkpoint, unused_reader, device="cuda:1")
    reranker._loaded = (object(), object())
    reranker._direction = object()
    reranker._tokens = BinaryScoreTokens(1, 2)
    reranker._instruct = "instruction"

    embedder.close()
    embedder.close()
    reranker.close()
    reranker.close()

    assert released == ["cuda:1", "cuda:1"]
    assert embedder._loaded is None
    assert embedder._recipe is None
    assert reranker._loaded is None
    assert reranker._direction is None
    assert reranker._tokens is None
    assert reranker._instruct is None


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
    embedder = QwenVisualEmbedder(a_checkpoint(tmp_path, pooling_mode="mean"))
    with pytest.raises(EmbedderUnavailable, match="pools by 'mean'"):
        embedder._cache_verified_recipe(embedder.model_dir)


def test_the_declared_prompt_is_carried_even_without_the_sentence_transformers_file(
    tmp_path: Path,
) -> None:
    """The chat template injects this same string as its default system message, so the fallback
    has to be that string and not something reasonable-looking."""
    recipe = read_pooling_recipe(a_checkpoint(tmp_path, prompt=None))
    assert recipe.prompt == "Represent the user's input."


def test_malformed_pooling_recipe_is_a_domain_refusal(tmp_path: Path) -> None:
    checkpoint = a_checkpoint(tmp_path)
    (checkpoint / "1_Pooling" / "config.json").write_text("{", encoding="utf-8")
    with pytest.raises(EmbedderUnavailable, match="cannot read verified checkpoint pooling"):
        read_pooling_recipe(checkpoint)


def test_malformed_prompt_recipe_is_not_hidden_by_the_embedder_fallback(tmp_path: Path) -> None:
    checkpoint = a_checkpoint(tmp_path)
    (checkpoint / "config_sentence_transformers.json").write_text("{", encoding="utf-8")
    with pytest.raises(EmbedderUnavailable, match="cannot read verified checkpoint prompt"):
        read_pooling_recipe(checkpoint)


@pytest.mark.parametrize(
    "payload",
    [
        {"prompts": []},
        {"prompts": False},
        {"prompts": "not-an-object"},
        {"prompts": {}, "default_prompt_name": 0},
        {"prompts": {}, "default_prompt_name": False},
    ],
)
def test_false_valued_prompt_schema_violations_are_not_treated_as_absence(
    tmp_path: Path, payload: object
) -> None:
    checkpoint = a_checkpoint(tmp_path)
    (checkpoint / "config_sentence_transformers.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    with pytest.raises(EmbedderUnavailable, match="non-object 'prompts'|non-string prompt name"):
        read_pooling_prompt(checkpoint)


def test_embedder_does_not_cache_a_recipe_before_verified_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint = a_checkpoint(tmp_path, prompt="attacker-controlled instruction")
    embedder = QwenVisualEmbedder(checkpoint, device="cpu")
    with pytest.raises(EmbedderUnavailable, match="before verified model load"):
        _ = embedder.recipe

    a_checkpoint(tmp_path, prompt="Represent the user's input.")

    def verified_stub(_model_dir: Path, _device: str, **kwargs: Any) -> tuple[object, object]:
        callback = kwargs["_after_verify"]
        assert callable(callback)
        callback(checkpoint)
        return object(), object()

    monkeypatch.setattr("hawedit.qwen_visual.load_processor_and_model", verified_stub)
    embedder._load()
    assert embedder.recipe.prompt == "Represent the user's input."


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


def test_missing_weights_are_lazy_at_construction_and_refused_at_runtime(tmp_path: Path) -> None:
    absent = tmp_path / "not-downloaded"
    embedder = QwenVisualEmbedder(absent)

    assert embedder.model_dir == absent
    with pytest.raises(EmbedderUnavailable, match="hawedit-fetch-models"):
        embedder.embed_text("کوردی")


def test_the_default_model_id_is_the_registry_id_for_the_embedder() -> None:
    """A drifting id would fail `resolve_role` at construction, but only for callers who use the
    default — this pins it directly."""
    from hawedit.registry import REGISTRY

    assert REGISTRY[EMBEDDING_MODEL_ID].role == "visual_embedding"


def test_model_config_is_refused_before_any_gpu_or_transformers_loader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CVE guard has to precede even runtime discovery, not merely AutoModel."""
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "model_type": "qwen3_vl",
                "_attn_implementation_internal": "attacker/kernel",
            }
        ),
        encoding="utf-8",
    )
    # test_models intentionally reloads hawedit.models to exercise installed-path discovery;
    # RuntimeError avoids binding this cross-file assertion to the pre-reload class identity.
    monkeypatch.setattr(
        "hawedit.qwen_visual.verified_checkpoint_access",
        lambda _model_id, model_dir: nullcontext(model_dir),
    )
    with pytest.raises(RuntimeError, match="CVE-2026-4372"):
        load_processor_and_model(tmp_path, "cuda:0")


@pytest.mark.parametrize("model_type", ["xclip", "lightglue"])
def test_visual_loader_uses_the_qwen_model_type_allowlist(
    tmp_path: Path, model_type: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "config.json").write_text(json.dumps({"model_type": model_type}), encoding="utf-8")
    monkeypatch.setattr(
        "hawedit.qwen_visual.verified_checkpoint_access",
        lambda _model_id, model_dir: nullcontext(model_dir),
    )
    with pytest.raises(RuntimeError, match="unapproved"):
        load_processor_and_model(tmp_path, "cuda:0")


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
    monkeypatch.setattr(
        "hawedit.qwen_visual.verified_checkpoint_access",
        lambda _model_id, model_dir: nullcontext(model_dir),
    )
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    embedder = QwenVisualEmbedder(a_checkpoint(tmp_path), device="cuda:0")
    with pytest.raises(EmbedderUnavailable, match="reports no CUDA"):
        embedder._load()


def test_checkpoint_integrity_is_proven_before_torch_or_transformers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "config.json").write_text(json.dumps({"model_type": "qwen3_vl"}), encoding="utf-8")

    def refuse(*_args: object) -> None:
        raise RuntimeError("integrity sentinel")

    monkeypatch.setattr("hawedit.qwen_visual.verified_checkpoint_access", refuse)
    with pytest.raises(RuntimeError, match="integrity sentinel"):
        load_processor_and_model(tmp_path, "cuda:0")


def test_integrity_then_safe_config_precede_verified_recipe_parsing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []

    @contextmanager
    def integrity(*_args: object) -> Any:
        events.append("integrity")
        yield tmp_path

    def safe_config(*_args: object) -> None:
        assert events == ["integrity"]
        events.append("safe-config")

    def recipe(_verified_dir: Path) -> None:
        assert events == ["integrity", "safe-config"]
        events.append("recipe")
        raise RuntimeError("recipe sentinel")

    monkeypatch.setattr("hawedit.qwen_visual.verified_checkpoint_access", integrity)
    monkeypatch.setattr("hawedit.qwen_visual.assert_transformers_config_safe", safe_config)
    with pytest.raises(RuntimeError, match="recipe sentinel"):
        load_processor_and_model(tmp_path, "cuda:0", _after_verify=recipe)
    assert events == ["integrity", "safe-config", "recipe"]


def test_verified_checkpoint_binding_is_held_through_every_constructor_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hawedit.qwen_visual as qwen_module

    active = False
    events: list[str] = []

    @contextmanager
    def access(_model_id: str, model_dir: Path) -> Any:
        nonlocal active
        active = True
        events.append("verified")
        try:
            yield model_dir
        finally:
            active = False

    def safe_config(model_dir: Path, _allowed: object) -> None:
        assert active and model_dir == tmp_path
        events.append("safe-config")

    def recipe(model_dir: Path) -> None:
        assert active and model_dir == tmp_path
        events.append("recipe")

    def backend(model_dir: Path, _device: str, **_kwargs: object) -> tuple[object, object]:
        assert active and model_dir == tmp_path
        events.append("from-pretrained")
        return object(), object()

    monkeypatch.setattr(qwen_module, "verified_checkpoint_access", access)
    monkeypatch.setattr(qwen_module, "assert_transformers_config_safe", safe_config)
    monkeypatch.setattr(qwen_module, "_load_verified_processor_and_model", backend)

    load_processor_and_model(tmp_path, "cpu", _after_verify=recipe)
    assert not active
    assert events == ["verified", "safe-config", "recipe", "from-pretrained"]


def test_embedder_backend_failures_become_domain_refusals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    embedder = QwenVisualEmbedder(a_checkpoint(tmp_path))
    failure = RuntimeError("CUDA out of memory")
    monkeypatch.setattr(embedder, "_load", lambda: (_ for _ in ()).throw(failure))
    window = a_window(0, 0)

    with pytest.raises(EmbedderUnavailable, match="CUDA out of memory") as caught:
        embedder.embed_frames(WindowFrames(window, (Path("f0.jpg"), Path("f1.jpg"))))
    assert caught.value.__cause__ is failure


def test_embed_window_deletes_extracted_source_pixels_after_embedding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = a_window(0, 0)
    private = tmp_path / "private-frames"
    private.mkdir()
    paths = (private / "f0.jpg", private / "f1.jpg")
    for path in paths:
        path.write_bytes(b"source pixel")
    metadata = private.stat()
    frames = WindowFrames(
        window,
        paths,
        _owner_dir=private,
        _owner_identity=(metadata.st_dev, metadata.st_ino),
    )
    checkpoint = tmp_path / "checkpoint"
    checkpoint.mkdir()
    embedder = QwenVisualEmbedder(a_checkpoint(checkpoint), device="cpu")
    monkeypatch.setattr("hawedit.qwen_visual.extract_window_frames", lambda *_args: frames)
    monkeypatch.setattr(
        embedder,
        "embed_frames",
        lambda value: VisualEmbedding(value.window, (1.0, 0.0), EMBEDDING_MODEL_ID),
    )

    result = embedder.embed_window(tmp_path / "source.mp4", window, tmp_path / "work")

    assert result.window == window
    assert not private.exists()


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


def test_malformed_score_recipe_is_a_domain_refusal(tmp_path: Path) -> None:
    checkpoint = a_reranker_checkpoint(tmp_path)
    (checkpoint / "1_LogitScore" / "config.json").write_text("{", encoding="utf-8")
    with pytest.raises(EmbedderUnavailable, match="cannot read verified checkpoint score"):
        read_score_tokens(checkpoint)


def test_reranker_does_not_cache_tokens_or_prompt_before_verified_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint = a_reranker_checkpoint(tmp_path, true_id=777, false_id=666)
    prompt_file = checkpoint / "config_sentence_transformers.json"
    prompt_file.write_text(
        json.dumps({"default_prompt_name": "query", "prompts": {"query": "attacker prompt"}}),
        encoding="utf-8",
    )
    reranker = QwenVisualReranker(checkpoint, read_frames=lambda _window: two_frames())
    with pytest.raises(EmbedderUnavailable, match="before verified model load"):
        _ = reranker.tokens
    with pytest.raises(EmbedderUnavailable, match="before verified model load"):
        _ = reranker.instruct

    a_reranker_checkpoint(tmp_path, true_id=1, false_id=2)

    def verified_stub(_model_dir: Path, _device: str, **kwargs: Any) -> tuple[object, object]:
        callback = kwargs["_after_verify"]
        assert callable(callback)
        callback(checkpoint)
        return object(), object()

    monkeypatch.setattr("hawedit.qwen_visual.load_processor_and_model", verified_stub)
    reranker._load()
    assert (reranker.tokens.true_id, reranker.tokens.false_id) == (1, 2)
    assert reranker.instruct == "Retrieve text relevant to the user's query."


def test_reranker_backend_failures_become_domain_refusals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reranker = QwenVisualReranker(
        a_reranker_checkpoint(tmp_path),
        read_frames=lambda window: WindowFrames(window, (Path("f0.jpg"), Path("f1.jpg"))),
    )
    failure = RuntimeError("CUDA kernel launch failed")
    monkeypatch.setattr(reranker, "_load", lambda: (_ for _ in ()).throw(failure))

    with pytest.raises(EmbedderUnavailable, match="CUDA kernel launch failed") as caught:
        reranker.score("گرنگ", WindowFrames(a_window(0, 0), (Path("f0.jpg"), Path("f1.jpg"))))
    assert caught.value.__cause__ is failure


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


# =========================================================================================
# What actually reaches the processor, tested without weights.
#
# An adversarial pass over M5.2 mutated seven guards one at a time and asked whether the gate
# noticed. Five survived: dropping `video_metadata` from either model (the whole D-049 fix),
# dropping the timestamp assertion, flipping `add_generation_prompt`, and replacing D-051's
# float32 score formula with a constant. Every headline fix of three iterations was silently
# revertible, because the tests covered refusals reachable without weights and nothing covered
# the *wiring* — which arguments actually arrive.
#
# The stubs below close that. The processor stub is not invented behaviour: it reproduces what
# the real one was measured to do — timestamps inside the window when `video_metadata` arrives
# as a top-level argument, and the 24-fps fallback `<0.0 seconds><0.1 seconds>` when it does
# not. So a mutation that drops the argument fails here for the same reason it fails on real
# weights.
# =========================================================================================


class StubProcessor:
    """Mimics the measured behaviour of a Qwen3-VL processor's chat template."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.text = ""

    def apply_chat_template(self, conversation: Any, **kwargs: Any) -> dict[str, Any]:
        import torch

        self.calls.append(kwargs)
        metadata = kwargs.get("video_metadata")
        if metadata:
            duration = float(metadata[0]["duration"])
            stamps = f"<0.0 seconds><{duration * 0.6:.3f} seconds>"
        else:
            # Exactly what the real processor produced for a 4162 ms window, assuming 24 fps.
            stamps = "<0.0 seconds><0.1 seconds>"
        self.text = f"<|vision_start|>{stamps}<|video_pad|>"
        return {"input_ids": torch.tensor([[1, 2, 3]])}

    def decode(self, _ids: Any) -> str:
        return self.text


class StubModel:
    """A fixed hidden state and a tiny `lm_head`, so the score is arithmetic we know."""

    def __init__(self, hidden: Any, weight: Any) -> None:
        self.lm_head = SimpleNamespace(weight=SimpleNamespace(data=weight))
        self._hidden = hidden
        self.forward_kwargs: dict[str, Any] = {}

    def __call__(self, **kwargs: Any) -> Any:
        self.forward_kwargs = kwargs
        return SimpleNamespace(hidden_states=[self._hidden])


def stubbed(
    obj: Any, monkeypatch: pytest.MonkeyPatch, hidden: Any, weight: Any
) -> tuple[StubProcessor, StubModel]:
    """Point `obj._load` at stubs, and make frame loading independent of Pillow."""
    obj._cache_verified_recipe(obj.model_dir)
    processor, model = StubProcessor(), StubModel(hidden, weight)
    monkeypatch.setattr(type(obj), "_load", lambda _self: (processor, model))
    monkeypatch.setattr(
        "hawedit.qwen_visual.load_window_images", lambda f, p=None: ["frame"] * f.count
    )
    return processor, model


def two_frames(fps: float = 1.0, duration_ms: int = 4_162) -> WindowFrames:
    window = SceneWindow(
        media_id="m", scene_index=0, window_index=0, in_ms=0, out_ms=duration_ms, fps=fps
    )
    return WindowFrames(window=window, paths=(Path("f0.jpg"), Path("f1.jpg")))


# `duration` is `total_num_frames / fps`, the identity VideoChat3 validates and Qwen3-VL is
# measurably indifferent to — byte-identical embeddings either way. D-056.
EXPECTED_METADATA = [{"fps": 1.0, "duration": 2.0, "total_num_frames": 2}]


def test_the_embedder_passes_video_metadata_top_level(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The D-049 fix, protected. Dropping this argument was silently revertible."""
    import torch

    embedder = QwenVisualEmbedder(a_checkpoint(tmp_path, dimension=2), device="cpu")
    processor, _ = stubbed(embedder, monkeypatch, torch.zeros(1, 1, 2) + 0.5, torch.eye(2))
    embedding = embedder.embed_frames(two_frames())
    assert embedding.dimension == 2
    assert processor.calls[0]["video_metadata"] == EXPECTED_METADATA


def test_the_embedder_refuses_a_prompt_that_compresses_the_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The negative control, and the second mutation that survived: delete the assertion in
    `embed_frames` and this passes.

    The stub returns the real 24-fps fallback when no metadata arrives, so the failure here is
    the actual one — a 4.162 s window stamped 0.1 s — rather than a synthetic stand-in.
    """
    import torch

    embedder = QwenVisualEmbedder(a_checkpoint(tmp_path, dimension=2), device="cpu")
    stubbed(embedder, monkeypatch, torch.zeros(1, 1, 2) + 0.5, torch.eye(2))
    original = StubProcessor.apply_chat_template
    monkeypatch.setattr(
        StubProcessor,
        "apply_chat_template",
        lambda self, conv, **kw: original(
            self, conv, **{k: v for k, v in kw.items() if k != "video_metadata"}
        ),
    )
    with pytest.raises(TimestampsOutsideWindow, match="assumes 24 fps"):
        embedder.embed_frames(two_frames())


def test_the_reranker_score_is_the_float32_weight_difference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-051's formula, protected by arithmetic rather than by a docstring.

    `lm_head.weight` rows are `[1, 0]` for false and `[0, 1]` for true, so the direction is
    `[-1, 1]`; the hidden state is `[3, 1]`, so the score is `sigmoid(-3 + 1) = sigmoid(-2)`.
    Replacing the formula with a constant — the mutation that survived the audit — cannot
    produce this number.
    """
    import torch

    reranker = QwenVisualReranker(
        a_reranker_checkpoint(tmp_path, true_id=1, false_id=0),
        read_frames=lambda w: WindowFrames(window=w, paths=(Path("f0.jpg"),)),
        device="cpu",
    )
    stubbed(reranker, monkeypatch, torch.tensor([[[3.0, 1.0]]]), torch.eye(2))
    score = reranker.score("ڕۆژنامەوانی", two_frames())
    assert score == pytest.approx(float(torch.sigmoid(torch.tensor(-2.0))), abs=1e-6)


def test_the_reranker_asks_for_the_answer_position(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`add_generation_prompt=True` — flipping it survived the audit.

    The score is the logits of the *answer* token, so the prompt must end where the answer
    would begin. Without it the two logits read belong to whatever token the template ended
    on, and every candidate still gets a plausible number in [0, 1].
    """
    import torch

    reranker = QwenVisualReranker(
        a_reranker_checkpoint(tmp_path),
        read_frames=lambda w: WindowFrames(window=w, paths=(Path("f0.jpg"),)),
        device="cpu",
    )
    processor, model = stubbed(reranker, monkeypatch, torch.zeros(1, 1, 2), torch.zeros(9694, 2))
    reranker.score("ڕۆژنامەوانی", two_frames())
    assert processor.calls[0]["add_generation_prompt"] is True
    assert processor.calls[0]["video_metadata"] == EXPECTED_METADATA
    assert model.forward_kwargs["output_hidden_states"] is True
