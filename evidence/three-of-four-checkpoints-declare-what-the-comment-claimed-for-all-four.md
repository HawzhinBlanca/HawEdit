# Three of four checkpoints declare what the comment claimed for all four

`visual_index.py` justified `TEMPORAL_PATCH_FRAMES = 2` with a statement of measured fact:

> All four §7 visual models ship `do_sample_frames: true` with `fps: 2`, `min_frames: 4` and
> **`temporal_patch_size: 2`** in `video_preprocessor_config.json`

`video_input.py` repeats it, and D-060's table was derived from it. One third of it is false.

## The measurement

Read from the four `video_preprocessor_config.json` files on this disk:

| model | role | fps | min_frames | temporal_patch_size |
|---|---|---|---|---|
| `Qwen3-VL-Embedding-2B` | visual_embedding | 2 | 4 | 2 |
| `Qwen3-VL-Reranker-2B` | visual_rerank | 2 | 4 | 2 |
| **`MCG-NJU/VideoChat3-4B`** | visual_discovery | 2 | 4 | **1** |
| `MCG-NJU/TimeLens2-4B` | temporal_evidence | 2 | 4 | 2 |

```
distinct fps declared                : [2]        -> the comment is right
distinct min_frames declared         : [4]        -> the comment is right
distinct temporal_patch_size declared: [1, 2]     -> the comment is wrong
```

"All four" is right about the count, `fps: 2` and `min_frames: 4` hold for all four, and
`temporal_patch_size: 2` holds for **three**.

## The constant is right; its justification was not

`TEMPORAL_PATCH_FRAMES = 2` stays. It is not a shared declaration — it is the **strictest** of
them, and that distinction is the whole reason it is correct:

`extract_window_frames` extracts a window **once**, and D-140's `_FrameCache` hands those same
files to the embedder *and* the reader — `VideoChat3Reader` takes `read_frames` precisely so that
"the frames a window was *embedded* from in Stage 2 are the frames it is *read* from here". One
extraction feeding models with patches of 1 and 2 must satisfy the coarser one. Trimming to a
multiple of 2 costs VideoChat3 at most one frame it would have accepted, and saves Qwen from
padding an odd count by repeating the last frame — a frame that was never filmed, which is the
defect D-060 exists to prevent.

So nothing in the behaviour changes. What changes is that the comment now says why the number is
2, instead of asserting something about the weights that is not true of one of them.

## Pinned, so it cannot drift again

Two tests read the constants back off the checkpoints, skipped when the weights are absent (CI
installs no models, and D-095 made the floor count *passed*, so a skip is safe):

* `test_the_declared_rate_and_minimum_are_the_checkpoints_own` — `DECLARED_SAMPLING_FPS` and
  `_MIN_SAMPLED_FRAMES` are the single value every config declares.
* `test_the_temporal_patch_constant_is_the_strictest_the_checkpoints_declare` — asserts
  `TEMPORAL_PATCH_FRAMES == max(declared)`, **not** that they agree.

The second carries its own control: it also asserts the declared sizes are **not** all equal. If a
future checkpoint set made them uniform, `max` would become indistinguishable from "what they all
declare" — which is exactly the claim that was wrong here — and the test says so by name rather
than passing quietly.

## Mutation audit — 3/3 lint-clean

```
CAUGHT   the temporal patch drops to the loosest checkpoint instead of the strictest
CAUGHT   the declared rate stops matching the checkpoints
CAUGHT   the minimum sampled frames stops matching the checkpoints

file restored byte-identical: True
3/3 caught lint-clean
suite after restore: GREEN
```

Before these tests existed, all three constants could be changed to a wrong value with the whole
suite green — they were justified by a comment and checked by nothing.
