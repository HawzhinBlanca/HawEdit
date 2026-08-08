"""`Qwen3-VL-Embedding-2B` behind §3 Stage 2's embedding contract.

`visual_index.py` defines what a scene-window embedding is and what an index may do with one;
this produces them from real frames on a real GPU. Nothing here decides retrieval policy — the
64-frame ceiling, the top-50 → rerank → keep-5–10 contract and the zero/NaN refusals all live
in `visual_index.py` and are enforced against whatever this returns.

**The pooling is read from the checkpoint, not guessed.** `1_Pooling/config.json` and
`config_sentence_transformers.json` state it: `lasttoken`, dimension 2048, then L2
normalisation, prompt `"Represent the user's input."`. Those files are read at construction and
a checkpoint declaring a pooling this module does not implement is refused, because a
plausible-but-different pooling produces vectors that are the right shape, the right norm, and
quietly incomparable to anything the model was trained to place near them.

**What is verified, and what is not.** Vectors come out 2048-d with |v| = 1.0000, a real index
builds over real media, and a Kurdish query retrieves against it — measured, in
`evidence/m5-2-embedder.md`. What is *not* established is agreement with
`sentence-transformers`: on identical text the two routes differ by cosine **0.955**, and the
cause is not the pooling. Four prompt placements were tried and none closed the gap, while the
chat template turns out to inject the declared prompt as a default system message on its own —
so supplying it explicitly here is redundant rather than load-bearing, and both routes give the
model the prompt. The discrepancy is recorded as open in D-050 rather than dressed up as
validation.

It does not affect retrieval *within* one index, and that is the property that matters:
`embed_text` and `embed_frames` share `_pool` and one convention, so a query and a window are
always measured the same way. What it would affect is comparing a vector from this module
against one produced by `sentence-transformers`, and `VisualIndex` already refuses to mix
sources it cannot compare.

**Why the processor and not `sentence-transformers`.** For *video* the declared loader cannot
pass frame timestamps at all, and without them a 4.16-second window reaches the model marked
0.1 seconds long. Measured, forty times compressed, silent. `video_input.py` owns that fix and
this module asserts it held — see D-049.

**Kurdish invariant #3, on the half of this module that has text.** §3 Stage 2 embeds pixels,
and the invariant is about text reaching a model as `norm` rather than raw — so it binds
`embed_text`, which produces the query vector `rerank_and_keep` takes. It is enforced the way
`index.py` enforces it for §2 queries: normalisation happens **inside** the boundary, on the way
in, rather than being asked of the caller. A query and a transcript must be normalised by the
same function or the retrieval is between two different alphabets, and a caller who forgot would
get slightly-wrong scores and no error.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from hawedit.normalize import normalize_sorani
from hawedit.registry import resolve_role
from hawedit.video_input import (
    WindowFrames,
    assert_timestamps_span_window,
    extract_window_frames,
    load_window_images,
    video_content,
    window_video_metadata,
)
from hawedit.visual_index import SceneWindow, VisualEmbedding

__all__ = [
    "EMBEDDING_MODEL_ID",
    "EmbedderUnavailable",
    "QwenVisualEmbedder",
    "read_pooling_recipe",
]

EMBEDDING_MODEL_ID: Final = "Qwen3-VL-Embedding-2B"
_EMBEDDING_ROLE: Final = frozenset({"visual_embedding"})

# §3 Stage 2 puts Stage 2 on a GPU; §6 gives hawapc01 two. Defaulting to `cuda:0` rather than
# falling back to CPU on purpose: a 2B VLM on CPU is not a degraded mode, it is a different
# throughput regime, and §3 Stage 1's warning about turning published figures into wall-clock
# promises applies to anything that then gets timed.
DEFAULT_DEVICE: Final = "cuda:0"


class EmbedderUnavailable(RuntimeError):
    """The embedding model could not be loaded, or this machine cannot run it."""


@dataclass(frozen=True, slots=True)
class PoolingRecipe:
    """How the checkpoint says its own embeddings are formed.

    Read from the files that shipped with the weights. A recipe inferred from the architecture
    would be a guess, and the failure mode of guessing here is vectors that look correct.
    """

    pooling_mode: str
    dimension: int
    prompt: str

    def assert_supported(self) -> None:
        """Refuse a checkpoint whose recipe this module does not actually implement.

        `lasttoken` is what is implemented. A future checkpoint switching to `mean` would still
        load, still return 2048 finite non-zero floats, and be silently wrong — so the
        difference is checked rather than assumed to persist.
        """
        if self.pooling_mode != "lasttoken":
            raise EmbedderUnavailable(
                f"this checkpoint pools by {self.pooling_mode!r}; this module implements "
                f"'lasttoken'. The vectors would come out the right shape and the wrong "
                f"vectors, so the mismatch is refused rather than tolerated."
            )


def read_pooling_recipe(model_dir: Path) -> PoolingRecipe:
    """The checkpoint's declared pooling, dimension and default prompt."""
    pooling_file = model_dir / "1_Pooling" / "config.json"
    st_file = model_dir / "config_sentence_transformers.json"
    if not pooling_file.exists():
        raise EmbedderUnavailable(
            f"{pooling_file} is missing, so this checkpoint does not state how its embeddings "
            f"are pooled. Guessing is how two runs produce incomparable vectors."
        )
    pooling = json.loads(pooling_file.read_text(encoding="utf-8"))
    prompt = "Represent the user's input."
    if st_file.exists():
        st_config = json.loads(st_file.read_text(encoding="utf-8"))
        prompts = st_config.get("prompts") or {}
        default_name = st_config.get("default_prompt_name") or "default"
        prompt = prompts.get(default_name, prompt)
    return PoolingRecipe(
        pooling_mode=str(pooling["pooling_mode"]),
        dimension=int(pooling["embedding_dimension"]),
        prompt=prompt,
    )


class QwenVisualEmbedder:
    """Turns scene windows and query text into vectors `VisualIndex` can compare.

    Loading is deferred to first use so that constructing one — which `pipeline.py` may do
    before it knows whether Stage 2 will run — costs nothing and cannot fail on a machine
    without the weights.
    """

    def __init__(
        self,
        model_dir: Path,
        device: str = DEFAULT_DEVICE,
        model_id: str = EMBEDDING_MODEL_ID,
    ) -> None:
        # §7 first: a model outside the registry, or one that is in it for a different job,
        # never gets as far as loading 4 GB of weights.
        resolve_role(model_id, _EMBEDDING_ROLE, "the visual embedding model")
        if not model_dir.is_dir():
            raise EmbedderUnavailable(
                f"no weights at {model_dir}. Run `bash scripts/fetch-models.sh "
                f"{model_id}` — §7's registry drives it, so it cannot fetch the wrong model."
            )
        self.model_dir = model_dir
        self.device = device
        self.model_id = model_id
        self.recipe = read_pooling_recipe(model_dir)
        self.recipe.assert_supported()
        self._loaded: tuple[Any, Any] | None = None

    def _load(self) -> tuple[Any, Any]:
        if self._loaded is not None:
            return self._loaded
        try:
            import torch
            from transformers import AutoModelForImageTextToText, AutoProcessor
        except ImportError as exc:  # the `gpu` extra is not installed
            raise EmbedderUnavailable(
                f"{exc}. §3 Stage 2 needs the GPU extra: see README 'GPU'."
            ) from exc
        if self.device.startswith("cuda") and not torch.cuda.is_available():
            raise EmbedderUnavailable(
                f"device {self.device!r} was asked for and torch reports no CUDA. §6 puts "
                f"Stage 2 on a GPU; silently using the CPU would change what every "
                f"measurement taken afterwards is about."
            )
        # transformers ships `py.typed` while leaving `AutoProcessor.from_pretrained` untyped.
        processor = AutoProcessor.from_pretrained(str(self.model_dir))  # type: ignore[no-untyped-call]
        # `.to()` is wrapped by transformers and its stub takes a `PreTrainedModel` rather than
        # a device string, so strict mode rejects the documented call. Ignored on this one line
        # rather than relaxed for the module — everything else here stays strict, and a real
        # type error in our own code still fails the gate.
        model = (
            AutoModelForImageTextToText.from_pretrained(str(self.model_dir), dtype=torch.bfloat16)
            .to(self.device)  # type: ignore[arg-type]
            .eval()
        )
        self._loaded = (processor, model)
        return self._loaded

    def _conversation(self, content: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {"role": "system", "content": [{"type": "text", "text": self.recipe.prompt}]},
            {"role": "user", "content": [content]},
        ]

    def _pool(self, batch: dict[str, Any]) -> tuple[float, ...]:
        """`lasttoken` then L2, which is what the checkpoint declares."""
        import torch

        _, model = self._load()
        placed = {k: (v.to(self.device) if hasattr(v, "to") else v) for k, v in batch.items()}
        with torch.no_grad():
            hidden = model(**placed, output_hidden_states=True).hidden_states[-1]
        last = hidden[:, -1, :].float()
        normalised = last / last.norm(dim=-1, keepdim=True)
        vector = tuple(float(v) for v in normalised[0].cpu())
        if len(vector) != self.recipe.dimension:
            raise EmbedderUnavailable(
                f"the model returned {len(vector)} dimensions and the checkpoint declares "
                f"{self.recipe.dimension}. Two dimensions means two models, and "
                f"`VisualIndex.add` refuses to mix them — this is the earlier place to say so."
            )
        return vector

    def embed_frames(self, frames: WindowFrames) -> VisualEmbedding:
        """One embedding for one window, from frames already on disk.

        The timestamps are checked on the **decoded prompt** before the model runs. Without
        that, a window whose frames were placed in the wrong 100 ms embeds without complaint
        and the index holds a vector about footage the model mislocated (D-049).
        """
        processor, _ = self._load()
        content = video_content(load_window_images(frames))
        batch = processor.apply_chat_template(
            self._conversation(content),
            tokenize=True,
            add_generation_prompt=False,
            return_dict=True,
            return_tensors="pt",
            video_metadata=[window_video_metadata(frames)],
        )
        assert_timestamps_span_window(processor.decode(batch["input_ids"][0]), frames)
        return VisualEmbedding(
            window=frames.window,
            vector=self._pool(dict(batch)),
            model_id=self.model_id,
        )

    def embed_window(
        self,
        video: Path,
        window: SceneWindow,
        work_dir: Path,
        ffmpeg: Path | None = None,
    ) -> VisualEmbedding:
        """Extract `window`'s frames from `video` and embed them."""
        frames = extract_window_frames(
            video, window, work_dir / window.window_id.replace(":", "_"), ffmpeg
        )
        return self.embed_frames(frames)

    def embed_text(self, query: str) -> tuple[float, ...]:
        """The query vector `visual_index.rerank_and_keep` takes, from a Sorani query.

        Kurdish invariant #3: `query` is normalised here, at the boundary, exactly as
        `index.index_tokens` does for §2. Both halves of retrieval must pass through the same
        §4.1 normalisation or they are comparing two different alphabets — and the failure is
        not an error, it is a slightly wrong score. Doing it inside means a caller cannot
        forget; `visual_index` never sees the raw string.
        """
        processor, _ = self._load()
        batch = processor.apply_chat_template(
            self._conversation({"type": "text", "text": normalize_sorani(query)}),
            tokenize=True,
            add_generation_prompt=False,
            return_dict=True,
            return_tensors="pt",
        )
        return self._pool(dict(batch))
