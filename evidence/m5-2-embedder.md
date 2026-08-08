# §3 Stage 2 builds a real index on real media — and one number that does not add up

> **Superseded in part, 2026-08-08 (D-060).** Every §7 visual checkpoint declares
> `do_sample_frames: true` with `fps: 2` and `min_frames: 4`, so the processor **re-samples**
> what it is handed. The windows below were extracted at 4 fps and the model received 4 of every
> 6 frames — measured off `video_grid_thw`, which nothing here was reading. The index was rebuilt
> at 3 fps, the only rate a 1400 ms scene is legal at, and every score moved: rank-1/rank-2
> margin 0.005644 -> 0.015441, one score by 0.011. See
> `evidence/m5-2-frames-reaching-the-model.md` for what in this file stands and what does not.

> **Measured on `transformers` 5.14.1.** The project now pins **4.57.6** (D-055), which every
> §7 visual checkpoint declares and which is the only version where VideoChat3 works at all.
> The library moves these numbers: on 4.57.6 the same run gives retrieval similarities
> 0.381785 / 0.373741 / 0.342425 (order unchanged) and reranker scores **0.0556 / 0.049956 /
> 0.022751** with the final order **[0, 1, 2]** rather than [1, 0, 2]. The *properties* hold on
> both — unit-norm vectors, dense ranks, retrieval scores carried through untouched, reranking
> changing the order — and the *values* do not. §8.1 says a number carries the hardware that
> produced it; this says it carries the library too.

`Qwen3-VL-Embedding-2B` behind `visual_index.VisualEmbedding`, on hawapc01's `cuda:0` in
bfloat16. Everything below is output from the run, not description of it.

## The recipe, read from the checkpoint

```
PoolingRecipe(pooling_mode='lasttoken', dimension=2048, prompt="Represent the user's input.")
```

Read from `1_Pooling/config.json` and `config_sentence_transformers.json` at construction, and
a checkpoint declaring a pooling this module does not implement is refused — `mean` would load,
run, and return 2048 finite non-zero floats that pass every check `VisualEmbedding` makes.

## An index over the fixture's three scenes

Windows planned by `plan_scene_windows` from Stage 0's own cuts at 1400/2800 ms. **At 4 fps, not
1** — D-049 measured that each 1400 ms scene yields a single frame at 1 fps, and a one-frame
video block has no temporal structure at all; `extract_window_frames` refuses it and names the
higher rate as the remedy. This is that remedy being taken.

```
kurdish-speech-3cuts:s0:w0  1400 ms @ 4.0 fps -> dim 2048, |v|=1.0000
kurdish-speech-3cuts:s1:w0  1400 ms @ 4.0 fps -> dim 2048, |v|=1.0000
kurdish-speech-3cuts:s2:w0  1362 ms @ 4.0 fps -> dim 2048, |v|=1.0000
index holds 3 windows, built in 10.4s
peak VRAM: 7.94 GiB
```

Retrieval against a Kurdish query — `ڕۆژنامەوانی کوردی قسە دەکات` — normalised inside
`embed_text` per Kurdish invariant #3, the same way `index.index_tokens` does for §2:

```
rank 1: kurdish-speech-3cuts:s1:w0  sim=0.353194
rank 2: kurdish-speech-3cuts:s2:w0  sim=0.337843
rank 3: kurdish-speech-3cuts:s0:w0  sim=0.333372
```

Ranks are dense and 1-based, which is what §8.2 counts Recall@K on. **No claim is made that this
ordering is correct** — three seconds of unlabelled footage cannot say which scene best answers a
query. What it shows is that the pipeline runs end to end and produces comparable numbers;
whether they are *good* numbers is §8.2's question and needs `BLOCKED.md` #1.

7.94 GiB peak leaves the second card entirely free, which is the layout §3 Stage 1 assumes.

## The number that does not add up

The checkpoint declares `sentence-transformers` as its loader, in its own `modules.json`. On
**identical text**, that loader and this module disagree:

```
cosine(this module, sentence-transformers) = 0.955300
```

That is not agreement, and it was worth chasing rather than rounding off. Four prompt placements,
same text, same weights, same device:

| Prompt placement | cosine vs `sentence-transformers` |
|---|---|
| system turn (the shipped script's form) | 0.955300 |
| prompt prefixed to the text, no space | 0.942398 |
| prompt prefixed to the text, with space | 0.948999 |
| **no prompt at all** | **0.955300** |

Two things fall out. First, none of them close the gap, so the cause is not prompt placement.
Second — and this explains what looked at first like a bug in this module — *system turn* and *no
prompt at all* produce the **identical** vector. The reason is in the checkpoint's own chat
template:

```jinja
{%- set default_system_message = 'Represent the user\'s input.' -%}
```

The template injects the declared prompt as a default system message on its own. So supplying it
explicitly is redundant rather than load-bearing, and the model receives the prompt on both
routes. `recipe.prompt` is still read and still checked, because the day that default changes is
the day the two must not silently diverge.

**What remains unexplained** is the residual 0.045. It is not the pooling mode (declared and
implemented), not the normalisation (both give |v| = 1.0000), and not the prompt. Recorded as open
in D-050 rather than presented as validation.

**Why it does not invalidate the index.** `embed_text` and `embed_frames` share `_pool` and one
convention, so a query and a window are always measured the same way — which is the only property
retrieval depends on. It would matter when comparing a vector from this module against one from
`sentence-transformers`, and `VisualIndex.add` already refuses to mix sources whose dimensions
disagree. It would also matter if the residual were evidence that this route places *text*
differently relative to *video* than the trained convention does, which would degrade
cross-modal retrieval quality without changing any number's shape. Settling that needs labelled
Kurdish candidates — §8.2, `BLOCKED.md` #1 — and is not settleable here.

## What is refused, and tested without weights

`models/` is git-ignored, so a CI runner has no checkpoint. The nine tests in
`tests/test_qwen_visual.py` cover the checks that decide whether a forward pass is allowed at
all, using hand-written recipe fixtures:

- a checkpoint that does not state its pooling → refused
- `pooling_mode: "mean"` → refused, naming it
- a model outside §7 → refused before any load
- `PySceneDetect` as the embedder → `WrongRole`, before the 4 GB load (audit finding #8's rule)
- missing weights → refused, naming `fetch-models.sh`
- **`cuda:0` asked for on a machine reporting no CUDA → refused, not run on the CPU.**
  `torch.cuda.is_available` is answered directly rather than branching on what this box has, so
  the test still runs on a GPU machine — deciding by hardware would delete the check exactly
  where it matters. §6 puts Stage 2 on a GPU, and a silent CPU fallback changes what every
  number measured afterwards is about, the same rule `asr.Hardware` enforces for throughput and
  `render_clip` enforces by refusing an absent encoder rather than substituting x264.
