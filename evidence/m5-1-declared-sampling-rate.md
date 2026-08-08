# The planner emitted windows the guard refuses, and the CLI forced the rate that did it

> Measured on `transformers` 4.57.6 (D-055), hawapc01 `cuda:0`, bfloat16.

Found by a 37-agent audit of what was genuinely next: 18 findings survived independent adversarial
refutation, 13 were refuted, and this was the only one ranked category (a).

## The defect

D-060 added `assert_frames_reached_model` — the guard that reads the frame count back off
`video_grid_thw` — and left `plan_scene_windows` free to emit windows it refuses. At the rate the
only entry point forced:

```
plan_scene_windows('m', duration_ms=30_000, shot_cuts_ms=(), fps=3.0)
  -> m:s0:w0  0..15000 ms  45 frames
     m:s0:w1  15000..30000 ms  45 frames
```

45 frames at 3 fps reach the model as **30**. A third of every window, on every source longer
than the 1.4 s fixture scenes, extracted by ffmpeg and thrown away. And the rate was not
optional: `pipeline.py` had `--visual-fps` at `default=3.0`, passed unconditionally, which made
its own `None -> REFERENCE_FPS` branch unreachable.

**I wrote that guard two iterations ago and did not make the planner satisfy it.** The audit's
phrasing is the fair one: a guard whose contract nothing upstream honours.

The rate is not the only way to violate it. At `REFERENCE_FPS = 1.0`, a 31-second media plans one
31-frame window — odd, and an odd count is padded by the processor **repeating the last frame**.

## The fix, in the two places the constraint actually belongs

**1. `SceneWindow` gains an upper bound on the rate.** It has always refused a rate *below* §3's
reference, because lowering the rate is how a long scene fits under the 64-frame ceiling while
describing different footage. This is the same objection from the other side: above the
checkpoints' declared `fps: 2`, frames are extracted and discarded, and the embedding is again
indistinguishable from an honest one. The bound is the checkpoints', not §3's — all four §7
visual models declare it.

**2. `extract_window_frames` trims an odd emitted count to even.** A judgment call, recorded: the
processor's padding repeats the **last** frame, so the model sees a frame that was never filmed
at the moment the window ends, biasing a temporal reading toward its own tail. Trimming costs at
most one sampling interval of tail and leaves every frame the model sees a frame that existed.
The trimmed file stays on disk — trimming is a decision about what to hand over, not a deletion.

Together these make the guard unreachable by construction, which is the point. Swept over three
legal rates x eight durations x every window the planner produces, `frames extracted == frames
read` for all 40+ windows; and the arithmetic the sweep uses is itself controlled by asserting it
still drops 44 -> 30 at 3 fps and 64 -> 32 at 4 fps.

## What it does to the numbers, measured a third time

Same query, same models, same weights. Only the frames that reach the model differ:

| | 4 fps (6 handed, **4 read**) | 3 fps (4 handed, 4 read) | 2 fps (2 handed, 2 read) |
|---|---|---|---|
| rerank s0 | 0.055600 | 0.054432 | **0.072286** |
| rerank s1 | 0.049956 | 0.038991 | **0.044416** |
| rerank s2 | 0.022751 | 0.026656 | **0.024993** |
| rank 1 → 2 margin | 0.005644 | 0.015441 | **0.027870** |
| retrieval order | — | [s1, s2, s0] | [s2, s1, s0] |
| rerank order | [s0, s1, s2] | [s0, s1, s2] | [s0, s1, s2] |
| reranking changed the order | yes | yes (full reversal) | **yes (full reversal)** |

The rank-1/rank-2 margin has widened monotonically as fewer frames were discarded — 0.0056 →
0.0154 → 0.0279, a factor of five from the first measurement to this one. §3 Stage 2's central
claim, *"the model is doing something rather than echoing retrieval"*, is stronger at every step:
at 2 fps the reranker reverses retrieval outright, promoting the window retrieval ranked last.

Path B re-read all three scenes at 2 fps: the same three descriptions (0 on black, 1 on white,
2 on blue), every SV6D time still shifted onto the media's clock, 64.2 s, and peak VRAM down from
11.99 to **9.56 GiB** because the frames being discarded were still being encoded first.

**What this does not say.** A wider margin is not a better index. At 2 fps a 1400 ms scene is
**two** frames — the minimum temporal structure `extract_window_frames` will accept — and whether
two frames of a 1.4 s scene is a good index entry is §8.2's question, not this file's.
`BLOCKED.md` #1.

## The evidence this supersedes

`evidence/m5-2-*.md` and `evidence/m5-4-path-b.md` record runs at 4 fps and 3 fps. **Both rates are
now refused at construction**, so those runs are no longer reproducible from the code that
produced them. The numbers were real and the analysis stands; the rates are not legal any more,
and the 2 fps column above is the current measurement. This is the third re-measurement of the
same index — D-055 moved it with the library pin, D-060 with the frame re-sampling, and D-065
with the rate bound. Each time the previous file was annotated rather than rewritten, and the
reason to keep doing that is on display here: the trend across all three is the finding.

## Mutation audit, against a baseline verified green first

```
CAUGHT  the declared-rate upper bound on SceneWindow
CAUGHT  the bound's value (2.0 -> 4.0 would readmit the defect)
CAUGHT  the even-count trim in extract_window_frames
CAUGHT  the composed path's rate coming from the constant

4/4 caught
```

The trim **survived** the first audit — no test caught its removal, because the sweep simulates
the processor's arithmetic rather than running ffmpeg. A real extraction closed it: 1400 ms at
2 fps emits three frames on disk and `extract_window_frames` hands over two.

## One cross-session note

`pipeline.py`'s composed visual path took its rate from a literal `3.0`; it now takes
`DECLARED_SAMPLING_FPS`, and `--visual-fps` defaults to `None` so the sentinel branch beside it is
live. That file and its test belong to a concurrent session's in-flight work. The change was
forced — its default rate is exactly the defect above — and it is one token plus an import, but
it is theirs and is flagged here rather than absorbed silently.
