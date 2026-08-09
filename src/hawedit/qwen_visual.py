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
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from hawedit.models import (
    assert_checkpoint_integrity,
    assert_fully_loaded,
    assert_transformers_config_safe,
)
from hawedit.normalize import normalize_sorani
from hawedit.registry import resolve_role
from hawedit.video_input import (
    WindowFrames,
    extract_window_frames,
    load_window_images,
    video_content,
    window_batch,
)
from hawedit.visual_index import RerankedHit, SceneWindow, VisualEmbedding, VisualHit

__all__ = [
    "EMBEDDING_MODEL_ID",
    "RERANK_MODEL_ID",
    "RERANK_SYSTEM",
    "BinaryScoreTokens",
    "EmbedderUnavailable",
    "QwenVisualEmbedder",
    "QwenVisualReranker",
    "load_processor_and_model",
    "read_pooling_prompt",
    "read_pooling_recipe",
    "read_score_tokens",
]

EMBEDDING_MODEL_ID: Final = "Qwen3-VL-Embedding-2B"
_EMBEDDING_ROLE: Final = frozenset({"visual_embedding"})

# §3 Stage 2 puts Stage 2 on a GPU; §6 gives hawapc01 two. Defaulting to `cuda:0` rather than
# falling back to CPU on purpose: a 2B VLM on CPU is not a degraded mode, it is a different
# throughput regime, and §3 Stage 1's warning about turning published figures into wall-clock
# promises applies to anything that then gets timed.
DEFAULT_DEVICE: Final = "cuda:0"
QWEN3_VL_MODEL_TYPES: Final = frozenset({"qwen3_vl", "qwen3_vl_text"})


class EmbedderUnavailable(RuntimeError):
    """A Stage 2 model could not be loaded, or this machine cannot run it."""


def load_processor_and_model(
    model_dir: Path,
    device: str,
    *,
    model_id: str = EMBEDDING_MODEL_ID,
    allowed_model_types: Collection[str] = QWEN3_VL_MODEL_TYPES,
    trust_remote_code: bool = False,
    causal_lm: bool = False,
    configure: Callable[[Any], None] | None = None,
) -> tuple[Any, Any]:
    """One loader for every §7 visual checkpoint, so all of them get the same refusals.

    The CUDA check in particular: §6 puts Stage 2 on a GPU, and a silent CPU fallback would
    change what every number measured afterwards is about. Three classes with three copies of
    that check is one class away from having only two of them.

    The three keyword arguments are facts about a checkpoint, not preferences:

    * `trust_remote_code` — the checkpoint ships its own modelling code. Both Qwen entries are
      native `transformers`; `MCG-NJU/VideoChat3-4B` is not.
    * `causal_lm` — which auto class the checkpoint's `auto_map` actually names. VideoChat3's
      lists `AutoModel` and `AutoModelForCausalLM` and no `AutoModelForImageTextToText`, so the
      default here would fail to dispatch on it.
    * `configure` — mutate the config before the weights are read. VideoChat3's vision tower
      defaults to `flash_attention_2`, which resolves to `None` without flash-attn, and
      flash-attn publishes no Windows wheels.
    """
    # A config is data only until the loader interprets it. Transformers 4.57.6 can execute a
    # Hub kernel named by a private field even with trust_remote_code=False (CVE-2026-4372), so
    # validate before importing or calling any model-stack code. D-094.
    assert_transformers_config_safe(model_dir, allowed_model_types)
    assert_checkpoint_integrity(model_id, model_dir)

    # torch first and alone, then the CUDA check, then transformers. The order is the point:
    # torch ships in the `media` extra and is therefore present anywhere Stage 0 runs, while
    # transformers is in `gpu` and is absent on the CI runner. Importing them together made
    # "install the gpu extra" the only reachable error there, and hid the more specific one —
    # a GPU was asked for and this machine has none. Measured: the refusal below was untestable
    # on the runner until this was split. D-068.
    try:
        import torch
    except ImportError as exc:  # neither extra is installed
        raise EmbedderUnavailable(f"{exc}. §3 Stage 2 needs torch: see README 'Setup'.") from exc
    if device.startswith("cuda") and not torch.cuda.is_available():
        raise EmbedderUnavailable(
            f"device {device!r} was asked for and torch reports no CUDA. §6 puts Stage 2 on a "
            f"GPU; silently using the CPU would change what every measurement taken afterwards "
            f"is about."
        )
    try:
        from transformers import (
            AutoConfig,
            AutoModelForCausalLM,
            AutoModelForImageTextToText,
            AutoProcessor,
        )
    except ImportError as exc:  # the `gpu` extra is not installed
        raise EmbedderUnavailable(
            f"{exc}. §3 Stage 2 needs the GPU extra: see README 'GPU'."
        ) from exc
    # transformers ships `py.typed` while leaving `AutoProcessor.from_pretrained` untyped, so
    # this call needs an ignore where the package is installed and must NOT have one where it
    # is absent — the runner reported `unused-ignore` for exactly that reason. Binding the
    # loader through an explicitly-`Any` local says the same thing in both environments.
    load_processor: Any = AutoProcessor.from_pretrained
    processor = load_processor(str(model_dir), trust_remote_code=trust_remote_code)
    extra: dict[str, Any] = {}
    if configure is not None:
        config = AutoConfig.from_pretrained(str(model_dir), trust_remote_code=trust_remote_code)
        configure(config)
        extra["config"] = config
    auto = AutoModelForCausalLM if causal_lm else AutoModelForImageTextToText
    # `output_loading_info=True` rather than a bare load: anything absent from the checkpoint is
    # filled with a fresh random initialisation and the load succeeds anyway. Measured on
    # VideoChat3-4B, whose `lm_head.weight` arrives random at std 0.0200 against the real
    # embedding's 0.0201 — indistinguishable by statistics, visible only in this list. D-054.
    result: Any = auto.from_pretrained(
        str(model_dir),
        dtype=torch.bfloat16,
        output_loading_info=True,
        trust_remote_code=trust_remote_code,
        **extra,
    )
    loaded, info = result
    assert_fully_loaded(model_dir.name, info.get("missing_keys") or ())
    # `.to()` is wrapped by transformers and its stub takes a `PreTrainedModel` rather than a
    # device string, so strict mode rejects the documented call. Ignored on this one line rather
    # than relaxed for the module — a real type error in our own code still fails the gate.
    model = loaded.to(device).eval()
    return processor, model


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


def read_pooling_prompt(model_dir: Path, prompt_name: str | None = None) -> str:
    """One named prompt out of `config_sentence_transformers.json`.

    The embedder's is `default` and the reranker's is `query`; both are the checkpoint's own
    wording and neither is retyped here. A paraphrase would be a different instruction to a
    model trained on the original, and nothing in the output would say so.
    """
    st_file = model_dir / "config_sentence_transformers.json"
    if not st_file.exists():
        raise EmbedderUnavailable(
            f"{st_file} is missing, so this checkpoint does not state its own instruction. "
            f"Inventing one changes what the model was asked."
        )
    config = json.loads(st_file.read_text(encoding="utf-8"))
    prompts = config.get("prompts") or {}
    name = prompt_name or config.get("default_prompt_name") or "default"
    prompt = prompts.get(name)
    if not prompt:
        raise EmbedderUnavailable(
            f"{st_file} has no prompt named {name!r}; it declares {sorted(prompts)}."
        )
    return str(prompt)


def read_pooling_recipe(model_dir: Path) -> PoolingRecipe:
    """The checkpoint's declared pooling, dimension and default prompt."""
    pooling_file = model_dir / "1_Pooling" / "config.json"
    if not pooling_file.exists():
        raise EmbedderUnavailable(
            f"{pooling_file} is missing, so this checkpoint does not state how its embeddings "
            f"are pooled. Guessing is how two runs produce incomparable vectors."
        )
    pooling = json.loads(pooling_file.read_text(encoding="utf-8"))
    # One parser for that file, two policies, and the difference is deliberate. The reranker
    # raises on a missing instruction because it writes it into `<Instruct>:` — the model is
    # answering a different question without it. The embedder falls back to the literal, because
    # its chat template injects that same string as a default system message anyway, so the
    # model receives it either way and refusing would break a usable checkpoint over nothing.
    try:
        prompt = read_pooling_prompt(model_dir)
    except EmbedderUnavailable:
        prompt = "Represent the user's input."
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
        if self._loaded is None:
            self._loaded = load_processor_and_model(
                self.model_dir, self.device, model_id=self.model_id
            )
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
        content = video_content(load_window_images(frames, processor))
        batch = window_batch(
            processor, self._conversation(content), frames, add_generation_prompt=False
        )
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


# =========================================================================================
# §3 Stage 2's second half: "Retrieve top 50 → Qwen3-VL-Reranker-2B → keep top 5–10."
# =========================================================================================

RERANK_MODEL_ID: Final = "Qwen3-VL-Reranker-2B"
_RERANK_ROLE: Final = frozenset({"visual_rerank"})

# The reranker's system turn, verbatim from the `scripts/qwen3_vl_reranker.py` that ships inside
# the checkpoint. Quoted rather than paraphrased: the model was trained to answer this exact
# question, and "yes"/"no" is what the two scored token ids below are the logits of.
RERANK_SYSTEM: Final = (
    "Judge whether the Document meets the requirements based on the Query and the Instruct "
    'provided. Note that the answer can only be "yes" or "no".'
)


@dataclass(frozen=True, slots=True)
class BinaryScoreTokens:
    """The two token ids whose logits are this reranker's score.

    Read from `1_LogitScore/config.json`, never hardcoded. They are vocabulary offsets for one
    tokenizer version — a checkpoint bump that shifted them would still produce scores in
    [0, 1] that ranked footage by the logits of two arbitrary tokens.
    """

    true_id: int
    false_id: int


def read_score_tokens(model_dir: Path) -> BinaryScoreTokens:
    """The reranker's `true`/`false` token ids, from the checkpoint's own config."""
    config_file = model_dir / "1_LogitScore" / "config.json"
    if not config_file.exists():
        raise EmbedderUnavailable(
            f"{config_file} is missing, so this checkpoint does not say which tokens its score "
            f"is the logits of. Every candidate would still get a number in [0, 1]."
        )
    config = json.loads(config_file.read_text(encoding="utf-8"))
    return BinaryScoreTokens(
        true_id=int(config["true_token_id"]), false_id=int(config["false_token_id"])
    )


class QwenVisualReranker:
    """`Qwen3-VL-Reranker-2B` behind `visual_index.VisualReranker`.

    §3 Stage 2 reranks the top 50 down to 5–10, and `rerank_and_keep` enforces what a reranker
    may do: reorder and score, but never invent a window, return one twice, drop below the
    survivor count, or restate the retrieval score it was handed. This produces output that
    satisfies those checks rather than relying on them — `retrieval_similarity` is copied
    straight off the hit it came from and never recomputed.

    **The score is the model's own recipe, formed the model's own way.** `sigmoid` of
    `(lm_head.weight[yes] - lm_head.weight[no]) · h_last`, with both token ids read from
    `1_LogitScore/config.json` and the subtraction done in float32 — exactly the bias-free
    `Linear` the shipped `scripts/qwen3_vl_reranker.py` builds.

    Subtracting the two *logits* instead is the same arithmetic on paper and measurably not the
    same number: the logits are bfloat16, so their difference quantises. Measured on one real
    window, `-0.263168` the model's way against `-0.250000` from the logits — that suspiciously
    round value is bfloat16 landing on an exactly representable step — and 0.434585 against
    0.437824 after the sigmoid. A 0.0032 error is a fifth of the smallest gap between the three
    scores this reranker produced on the fixture, so it is inside the range that decides an
    order. The two weight rows are indexed and cast before subtracting, which keeps it to two
    vectors rather than materialising a 151k × 2048 float32 matrix.

    **The reranker needs pixels, and the Protocol hands it only windows.** `VisualHit` carries a
    `SceneWindow`, not frames, so `read_frames` supplies them — the same shape as
    `pipeline.run_pipeline`'s `read_scenes` for Path B. Passing a reader rather than re-extracting
    internally means the frames a window was *embedded* from are the frames it is *scored* from;
    two independent extractions of "the same" window would differ at the tail, and the reranker
    would be judging footage the index does not hold.
    """

    def __init__(
        self,
        model_dir: Path,
        read_frames: Callable[[SceneWindow], WindowFrames],
        device: str = DEFAULT_DEVICE,
        model_id: str = RERANK_MODEL_ID,
        instruct: str | None = None,
    ) -> None:
        resolve_role(model_id, _RERANK_ROLE, "the visual reranker")
        if not model_dir.is_dir():
            raise EmbedderUnavailable(
                f"no weights at {model_dir}. Run `bash scripts/fetch-models.sh {model_id}`."
            )
        self.model_dir = model_dir
        self.read_frames = read_frames
        self.device = device
        self.model_id = model_id
        self.tokens = read_score_tokens(model_dir)
        # `prompts.query` in the checkpoint's own config — its default instruction.
        self.instruct = instruct or read_pooling_prompt(model_dir, "query")
        self._loaded: tuple[Any, Any] | None = None
        self._direction: Any | None = None

    def _load(self) -> tuple[Any, Any]:
        if self._loaded is None:
            self._loaded = load_processor_and_model(
                self.model_dir, self.device, model_id=self.model_id
            )
        return self._loaded

    def score(self, query: str, frames: WindowFrames) -> float:
        """How relevant this window is to `query`, in [0, 1].

        `query` is normalised here for the same reason `embed_text` normalises: Kurdish
        invariant #3, and a query that reached the reranker unnormalised while the embedder saw
        it normalised would have the two halves of Stage 2 scoring different strings.
        """
        import torch

        processor, model = self._load()
        messages = [
            {"role": "system", "content": [{"type": "text", "text": RERANK_SYSTEM}]},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"<Instruct>: {self.instruct}"},
                    {"type": "text", "text": f"<Query>: {normalize_sorani(query)}"},
                    {"type": "text", "text": "\n<Document>:"},
                    video_content(load_window_images(frames, processor)),
                ],
            },
        ]
        # `add_generation_prompt=True` as the shipped script does: the score is the logits of the
        # *answer* token, so the prompt has to end where the answer would begin. Without it the
        # two logits read are for whatever token the template happens to end on.
        batch = window_batch(processor, messages, frames, add_generation_prompt=True)
        placed = {k: (v.to(self.device) if hasattr(v, "to") else v) for k, v in batch.items()}
        with torch.no_grad():
            hidden = model(**placed, output_hidden_states=True).hidden_states[-1][:, -1].float()
            delta = (self._score_direction() * hidden[0]).sum()
        return float(torch.sigmoid(delta))

    def _score_direction(self) -> Any:
        """`lm_head.weight[yes] - lm_head.weight[no]`, in float32, computed once.

        Two rows indexed and cast individually: casting the whole head first would be a
        151k × 2048 float32 allocation for two vectors' worth of arithmetic.
        """
        if self._direction is None:
            _, model = self._load()
            weight = model.lm_head.weight.data
            self._direction = (
                weight[self.tokens.true_id].float() - weight[self.tokens.false_id].float()
            )
        return self._direction

    def rerank(self, query: str, hits: Sequence[VisualHit]) -> tuple[RerankedHit, ...]:
        """Reorder `hits` by model relevance, carrying each retrieval score through untouched."""
        scored = [(self.score(query, self.read_frames(hit.window)), hit) for hit in hits]
        # Ties broken by time then id, exactly as `VisualIndex.retrieve` does, so two windows the
        # model scores identically cannot swap places between runs — §8.2 counts Recall@K on
        # this order, and an unstable order makes that number noise.
        scored.sort(key=lambda pair: (-pair[0], pair[1].window.in_ms, pair[1].window.window_id))
        return tuple(
            RerankedHit(
                window=hit.window,
                retrieval_similarity=hit.similarity,
                rerank_score=score,
                rank=position,
                model_id=self.model_id,
            )
            for position, (score, hit) in enumerate(scored, start=1)
        )
