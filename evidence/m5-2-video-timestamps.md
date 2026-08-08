# A 4.16-second window reached the model marked 0.1 seconds long

> **Measured on `transformers` 5.14.1.** The project now pins **4.57.6** (D-055), which every
> §7 visual checkpoint declares and which is the only version where VideoChat3 works at all.
> The library moves these numbers: on 4.57.6 the same run gives retrieval similarities
> 0.381785 / 0.373741 / 0.342425 (order unchanged) and reranker scores **0.0556 / 0.049956 /
> 0.022751** with the final order **[0, 1, 2]** rather than [1, 0, 2]. The *properties* hold on
> both — unit-norm vectors, dense ranks, retrieval scores carried through untouched, reranking
> changing the order — and the *values* do not. §8.1 says a number carries the hardware that
> produced it; this says it carries the library too.

`evidence/gpu-stack.md` recorded that `sentence-transformers` warns *"no video metadata was
provided ... Defaulting to `fps=24`"*, and D-048 turned that warning into an architecture
decision. **A warning is not a measurement.** This is the measurement, and it found something
worse than the warning suggested.

## What the model is actually told

A Qwen3-VL processor writes timestamp tokens into the prompt — `<0.5 seconds>` — which is how
each temporal group of frames is placed in time. Read back out of the decoded prompt, for the
fixture's full 4162 ms window sampled at §3 Stage 2's reference 1 fps:

| Input | Timestamps the model receives |
|---|---|
| no metadata | **`(0.0, 0.1)`** |
| `fps` inside the video content dict | `(0.0, 0.1)` |
| `video_metadata` inside the video content dict | `(0.0, 0.1)` |
| **`video_metadata=` top-level to `apply_chat_template`** | **`(0.5, 2.5)`** |

`(0.5, 2.5)` is right: four frames become two temporal groups (Qwen3-VL pairs frames), and each
stamp is its group's midpoint — 0.5 covers t=0,1 and 2.5 covers t=2,3.

`(0.0, 0.1)` is a **4.162-second window presented as 0.1 seconds** — forty times compressed.

## Why nothing catches it

Every layer accepts the wrong answer without a word:

- The `fps` key in the content dict is accepted and **ignored**. `input_ids` come out
  byte-identical for `fps=1`, `fps=24`, `fps=2` and no fps at all — same shape `(1, 475)`, same
  `video_grid_thw` `[[2, 22, 40]]`, `(base == other).all()` is `True` in every pair.
- `video_metadata` in the content dict is equally inert.
- `sentence-transformers` — the loader this checkpoint *declares*, in its own `modules.json` and
  `config_sentence_transformers.json` — **cannot** pass it: `ValueError: Multimodal dict input
  contains unrecognized modality keys: ['video_metadata']`.
- The output is a well-formed, correctly-normalised 2048-d vector either way.

So D-048's conclusion (use the `transformers` processor, not `sentence-transformers`) is
confirmed — but its stated reason was the fps warning, and the real reason is that the declared
loader has no channel for the timestamps at all.

## Does it change the embedding? Yes, and here is the scale

Same frames, same model, `cuda:0`, bfloat16, lasttoken-pooled and L2-normalised:

```
dim 2048 | cosine(correct-time, wrong-time) = 0.990391      → distance 0.009609
peak VRAM: 4.23 GiB
```

Not identical, so the defect is not cosmetic. Whether 0.0096 matters depends on how far apart
real windows sit, so that was measured too — the fixture's three scenes, planned by
`plan_scene_windows` from Stage 0's own cuts at 1400/2800 ms:

| Pair | Distance (1 − cos, correct timestamps) |
|---|---|
| window 0 vs 1 | 0.186408 |
| window 0 vs 2 | 0.224411 |
| window 1 vs 2 | 0.219962 |

So the timestamp defect moves a window about **5% of the distance between three visually
distinct cuts**. Stated carefully: on this footage it would not reorder retrieval. The footage
is three unrelated shots, which is close to the easiest case there is — the product's actual
input is a single-speaker Kurdish podcast, where consecutive windows differ by far less than
0.19 and 0.0096 is proportionally much larger. The honest claim is that the defect is real and
measurable, that its size relative to the signal is unmeasured on representative material, and
that `BLOCKED.md` #1 is why.

The per-window defect measured **0.000000** on each of the three 1400 ms windows — because each
yields a single frame, one temporal group, and one group is stamped `0.0` either way. Which
turned out to be a second defect.

## Second defect, found in the code written for the first

`plan_scene_windows` on the real fixture:

```
kurdish-speech-3cuts:s0:w0  1400 ms  planned 2 frames  ffmpeg emitted 1
kurdish-speech-3cuts:s1:w0  1400 ms  planned 2 frames  ffmpeg emitted 1
kurdish-speech-3cuts:s2:w0  1362 ms  planned 2 frames  ffmpeg emitted 1
```

ffmpeg's `fps` filter samples at interval **centres**, so over 1.4 s at 1 fps it emits one frame
at 0.5 s and the next centre, 1.5 s, is past the end. Over 4.162 s it emits four — 0.5, 1.5,
2.5, 3.5 — where `SceneWindow.frame_count`'s `ceil` predicts five. The plan runs one high
whenever the duration is not a whole number of frames.

The first tolerance written here allowed "one frame short", which is exactly the systematic
offset — and therefore also allowed **1 of 2**. A one-frame video block has no temporal
structure at all, and §7 excludes CLIP because *"frame-averaging loses temporal structure"*;
this reaches the same place from the other side, with nothing left to lose. Its embedding is
indistinguishable from an honest window's.

`extract_window_frames` now refuses it, and names the remedy: `SceneWindow` permits any rate at
or above the reference and enforces the 64-frame ceiling against whatever rate is chosen, so a
1400 ms scene is embeddable at 4 fps. Verified both ways — the 1 fps window raises, the same
window at 4 fps returns ≥ 2 real frames.

## The guard, and its negative control

`assert_timestamps_span_window` reads the decoded prompt and refuses stamps that do not reach
half the window. The threshold is set against the failure it exists to catch: the broken default
reaches 0.1 s of 4.162, which is **2.4%**. Anything under half is not tail rounding.

Run against the real model, both directions:

```
guard accepts correct: (0.5, 2.5)
guard rejects broken:  ... spans 4.162 s but the prompt's last timestamp is 0.100 s
                       — 2.4% of the window ...
```

`tests/test_video_input.py` pins both, using those exact numbers rather than invented ones, so
a guard that stopped distinguishing them would go red. The tests are pure — the processor needs
4 GB of weights, so the end-to-end run above is the evidence and the gate checks the logic.
