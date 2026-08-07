# M5.1 — §3 Stage 2 scene windows, measured on real media

`src/hawedit/visual_index.py` · `tests/test_visual_index.py` (51 tests) ·
`tests/test_pipeline.py::test_stage_2s_window_plan_was_built_from_this_runs_own_shot_cuts`

## What §3 asks for

> **Visual:** `Qwen3-VL-Embedding-2B`, one embedding per scene. Reference settings run ~1 fps
> with a maximum of 64 frames, so segment before embedding. Retrieve top 50 →
> `Qwen3-VL-Reranker-2B` → keep top 5–10.

Both models are unreachable here (`BLOCKED.md` #2 GPU, #6 weights). The *segmentation* is
arithmetic over Stage 0's shot cuts and needs neither, so it runs.

## The run

```
$ python -m hawedit.pipeline tests/fixtures/kurdish-speech-3cuts.mp4 --json
media   kurdish-speech-3cuts
stage 0 4162 ms · 2 shot cut(s) · 2 speech region(s) · diarization: not run
stage 2 3 scene window(s) · 6 frame(s) at 1.0 fps · embedding still blocked
```

| window | span (ms) | frames @ 1.0 fps |
|---|---|---|
| `kurdish-speech-3cuts:s0:w0` | 0 → 1400 | 2 |
| `kurdish-speech-3cuts:s1:w0` | 1400 → 2800 | 2 |
| `kurdish-speech-3cuts:s2:w0` | 2800 → 4162 | 2 |

The cuts are the ones PySceneDetect found **on this video** in the same run — 1400 ms and
2800 ms, the two joins in a fixture built from three 1.4 s segments. The plan tiles
`0 → 4162` with no gap and no overlap, which the run asserts against `assert_window_coverage`
rather than by eye.

## The measurement that matters

The 64-frame ceiling and the ~1 fps rate are one setting, not two, and a scene can satisfy
either alone while breaking the pair:

```
180 s at 0.35 fps -> 63 frames; ceiling is 64; under ceiling: True
180 s at 1.0  fps -> 180 frames
```

So a three-minute scene sampled at a third of the reference rate passes a frame-count check
and returns a vector of the right dimension and the right norm. Nothing downstream can see
that it described different footage than the published retrieval numbers were measured on.
`SceneWindow` therefore refuses `fps < 1.0` outright, and `plan_scene_windows` splits long
scenes instead — `test_a_long_window_cannot_buy_itself_room_by_lowering_the_frame_rate` is
the regression, and the 63 above is why it is not tautological.

## What this does *not* show

The fixture is 4.16 s, so every scene here is one window and **the splitting path is exercised
by tests and arithmetic, not by real footage**. Splitting on a real long episode is unverified
until there is one to run — the same gap `BLOCKED.md` #1 names for everything else that wants
real Kurdish material. Retrieval and reranking are likewise contract-only: the cosine search is
real and tested, the embeddings that would fill it are not (`BLOCKED.md` #2, #6).
