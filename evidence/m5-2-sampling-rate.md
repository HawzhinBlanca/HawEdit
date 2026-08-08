# Two sampling rates in one index, and the rate was 63% of the signal

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

Found by auditing the previous iteration's own evidence rather than by a bug report. M5.2's
index was built at **4 fps** while §3 Stage 2's reference is **~1 fps**, and nothing in the code
required a media's windows to share a rate. Both halves of that turned out to matter.

## Reproduced first

```
DEFECT REPRODUCED: index accepted 1 fps and 4 fps windows together -> 2 windows
  fps present: [1.0, 4.0]
```

`VisualIndex.add` checked `media_id`, duplicate `window_id`, and dimension — *"Two dimensions
means two models, and their scores are not comparable"* — and said nothing about the rate.

## Then measured, because "not comparable" needed a number

The **same** 0–4162 ms span of the fixture, embedded three times by
`Qwen3-VL-Embedding-2B` on `cuda:0`. Same footage, same model, same weights — only the sampling
rate differs:

| Rate | Frames |
|---|---|
| 1 fps | 4 |
| 2 fps | 8 |
| 4 fps | 16 |

```
cosine between embeddings of THE SAME FOOTAGE at different rates:
  1.0 fps vs 2.0 fps: 0.882581  (distance 0.117419)
  1.0 fps vs 4.0 fps: 0.942539  (distance 0.057461)
  2.0 fps vs 4.0 fps: 0.966406  (distance 0.033594)
```

Against the reference scale already measured in `evidence/m5-2-video-timestamps.md` — three
**visually distinct** scenes of the same fixture:

| Pair | Distance |
|---|---|
| window 0 vs 1 | 0.186408 |
| window 0 vs 2 | 0.224411 |
| window 1 vs 2 | 0.219962 |

**0.117 of artefact against 0.186 of signal — the sampling rate accounts for up to 63% of the
distance between genuinely different footage.** In a mixed index a window can be ranked above a
more relevant one for no reason but having been read at a different rate, and every score still
looks ordinary. This is not noise: the rate reaches the model explicitly through
`video_metadata` (D-049), so it is the model describing what it was told are different inputs.

Note the non-monotonicity — 1 vs 2 fps (0.117) is *further* than 1 vs 4 fps (0.057). Whatever is
happening is not a smooth function of frame count, which is another reason not to treat a rate
difference as a small correction that could be tolerated or compensated for.

## Fixed where every caller already passes

`VisualIndex.add` is the single funnel — `add_all` calls it — so the guard sits beside the
dimension check it mirrors, and carries the measurement in its message:

```
m1:s1:w0 was sampled at 4.0 fps; the index holds 1.0 fps. The same footage embedded at
two rates lands up to 0.117 apart in cosine distance, against 0.186–0.224 between
different scenes — so mixing them lets the sampling rate outweigh the content.
Embed the whole media at one rate.
```

`plan_scene_windows` already takes one `fps` for a whole media, so the honest path was always
uniform. Nothing required it, which is exactly how the M5.2 evidence index came to be built at
4 fps with no record.

## The positive control

A guard that refused every rate but 1 fps would pass the test above and break D-049's remedy —
a 1400 ms scene at 1 fps is a single frame with no temporal structure, which
`extract_window_frames` refuses. So a second test builds a whole index at 4 fps and requires it
to be **accepted**. A uniform index at any rate at or above the reference is legal; a mixed one
is not.

## The consequence for §3, recorded rather than absorbed

Raising the rate for short scenes is now a decision about the *whole* media, and the 64-frame
ceiling is enforced against whatever rate is chosen, so the maximum window shrinks with it:

| Rate | Longest legal window |
|---|---|
| 1 fps | 64 s |
| 2 fps | 32 s |
| 4 fps | 16 s |

A 4 fps index therefore splits long scenes into four times as many windows as a 1 fps one —
more embeddings, more reranker calls, and a different number of candidates competing for §3's
5–10 survivor slots. Which rate a real Kurdish episode should use is not answerable from three
seconds of footage; it is §8.2's question and needs `BLOCKED.md` #1. D-052.
