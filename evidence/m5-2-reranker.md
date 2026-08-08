# The reranker, and a shortcut that was 57% of the margin it was deciding

> **Rate superseded, 2026-08-08 (D-063/D-065).** The run below is at a sampling rate
> `SceneWindow` now **refuses**: all four §7 visual checkpoints declare `fps: 2`, and above it the
> processor discards frames. The index was re-measured at 2 fps — rank-1/rank-2 rerank margin
> 0.005644 (4 fps) -> 0.015441 (3 fps) -> **0.027870** (2 fps), reranking still reversing
> retrieval. This run is no longer reproducible from the code that produced it. See
> `evidence/m5-1-declared-sampling-rate.md`.

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

`Qwen3-VL-Reranker-2B` behind `visual_index.VisualReranker`, closing M5.2's named shortfall.
§3 Stage 2: *"Retrieve top 50 → Qwen3-VL-Reranker-2B → keep top 5–10."*

## It runs, and it reorders

hawapc01 `cuda:0`, bfloat16, both Stage 2 models resident at once:

```
retrieval order: [1, 2, 0]
  rank 1: scene 1  rerank=0.448391  retrieval=0.353194
  rank 2: scene 0  rerank=0.442759  retrieval=0.333372
  rank 3: scene 2  rerank=0.400027  retrieval=0.337843
rerank order: [1, 0, 2] | changed: True
reranked 3 windows in 4.6s | peak VRAM 8.17 GiB
retrieval similarities carried through unchanged: True
```

Reranking moved scene 0 from third to second, so the model is doing something rather than
echoing retrieval — which is the one thing a reranker has to prove. No claim that the new order
is *better*: three seconds of unlabelled footage cannot say, and that is §8.2's question behind
`BLOCKED.md` #1.

Everything the model needs is read from the checkpoint, not retyped:

```
instruct: "Retrieve text relevant to the user's query."   (prompts.query)
tokens:   BinaryScoreTokens(true_id=9693, false_id=2152)  (1_LogitScore/config.json)
system:   'Judge whether the Document meets the requirements based on the Query and the
           Instruct provided. Note that the answer can only be "yes" or "no".'
```

## The shortcut, and why it was wrong

The shipped `scripts/qwen3_vl_reranker.py` builds a bias-free `Linear` whose weight is
`lm_head.weight[yes] - lm_head.weight[no]` and applies it to the last hidden state. The first
implementation here took the difference of the two **logits** instead — algebraically identical,
since `logits = lm_head(h)` and this head has no bias (verified: `lm_head has bias: False`).

Measured on one real window rather than left as an argument:

```
shipped-script formula (W_yes - W_no)·h = -0.263168
our logits difference                   = -0.250000
difference = 1.32e-02  ->  sigmoid: shipped 0.434585   ours 0.437824
```

`-0.250000` is not a coincidence — it is bfloat16 landing on an exactly representable step. The
logits are bfloat16, so differencing them quantises, and the error survives the sigmoid as
**0.0032**.

Then the number that makes it matter. With the formula corrected, the gap between rank 1 and
rank 2 is **0.448391 − 0.442759 = 0.0056**. The quantisation error is **57% of the margin it
was being used to decide.** Not a rounding difference — the same size as the decision.

Fixed by doing what the model does: index the two weight rows, cast each to float32, subtract,
dot with the float32 hidden state. Two vectors, computed once and cached — casting the whole
head first would allocate 151k × 2048 float32 for two rows' worth of arithmetic.

**The lesson generalises past this line.** "Same arithmetic on paper" is not a claim about a
number until the dtypes are in it, and every §7 checkpoint here declares `bfloat16`.

## What is tested, and what cannot be

Sixteen tests in `tests/test_qwen_visual.py` run without weights, because `models/` is
git-ignored and a CI runner has none. The reranker's `score` is injected, which lets the whole
*contract* be exercised rather than just its refusals:

- reordering by the model's score, with dense 1-based ranks
- `retrieval_similarity` carried through untouched **and** `rerank_score` equal to the injected
  number — asserting merely that the two *differ* passes by accident, and did: the first draft
  scored a window 0.8 whose retrieval similarity was also 0.8 and went red for no defect
- ties broken by time then id, so §8.2's Recall@K cannot depend on run order
- score tokens read from the checkpoint; a checkpoint that does not name them is refused,
  because hardcoding survives a tokenizer bump and ranks footage by two arbitrary tokens with
  every score still in [0, 1]
- `PySceneDetect` and the *embedder* both refused as the reranker — §7 membership is not a
  licence to fill any slot
- driven through the real `rerank_and_keep` with five synthetic windows, so all four of its
  checks (invented window, duplicate, short return, restated retrieval score) are satisfied at
  once by real output rather than by a paraphrase of the contract

**Not exercisable on this fixture:** the keep-5–10 survivor slice. §3 Stage 2's floor is five
survivors and the fixture has three scenes, so `rerank_and_keep` correctly refuses — *"the index
holds 3 windows and 5 survivors were asked for"*. The range is covered by the synthetic
five-window test above and awaits real footage, `BLOCKED.md` #1.

## Still open, carried forward

D-050's unexplained cosine 0.955 between this route and the `sentence-transformers` loader the
embedder's checkpoint declares. It bears on retrieval *quality*, not on any number's shape, and
settling it needs labelled Kurdish candidates.
