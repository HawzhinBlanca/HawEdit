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
    read_pooling_recipe,
)
from hawedit.registry import WrongRole


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
