# D-185 recorded a route the code refuses, and the real ceiling is 8 s

D-185 (committed 330b430) closed with a claim derived from arithmetic rather than from a run:

> §3's ~32 s retrieval unit **is** reachable on this 24 GB card, at 0.25 fps: one frame per four
> seconds instead of two per second.

It is not. `SceneWindow.__post_init__` enforces a **1.0 fps floor**, and its refusal names exactly
the reasoning the claim had missed:

```
✗ window zar38champion:s0:w0 samples at 0.25 fps, below §3 Stage 2's reference 1.0 fps.
  Lowering the rate is how a long scene fits under the 64-frame ceiling without being
  segmented, and the resulting embedding is indistinguishable from an honest one.
  Split the scene instead.
```

The repo had already considered and rejected the trade D-185 proposed. `REFERENCE_FPS = 1.0`.
D-185's arithmetic was right and its conclusion was wrong, because it never asked whether the code
permitted the setting — the same failure D-182's verification caught one iteration earlier, in the
same shape: a prediction recorded where a measurement belongs.

## What is actually reachable, measured

| setting | window | outcome on `ZAR38MinTest.mp4` |
|---|---|---|
| §3 blueprint: 64 frames @ 2.0 fps | 32.0 s | not reachable — the 8-frame ceiling is `BLOCKED.md` #17 |
| 8 frames @ 2.0 fps | 4.0 s | runs; **0** of 184 complete sentences fit → no clip (D-185) |
| 8 frames @ 0.25 fps | 32.0 s | **refused** at plan time by the 1.0 fps floor |
| 8 frames @ **1.0 fps** | **8.0 s** | **crashes inside the reader** — see below |

So the real ceiling on this hardware is **8 s**, not 32 s. That is still above the median complete
sentence of 6.72 s, so the question D-185 asked remains live — but the answer is 8 s, and the route
to it is `--visual-fps 1.0`, not 0.25.

## A second, separate defect found by trying it

`--visual-fps 1.0` is a supported flag. On the real file it does not produce a refusal; it dies
with a message from inside the model:

```
✗ t:1 must be larger than temporal_factor:2
```

`SceneWindow.frame_count` is `ceil(duration_ms * fps / 1000)`, so a scene shorter than ~1.5 s
yields 1–2 frames at 1.0 fps where it yielded 3 at 2.0 fps, and the reader's temporal factor needs
more than 2. The window that failed is not named, the cause is not stated, and the run dies after
Stage 0 and a full re-embed rather than at plan time.

That is this repo's own "fail visible, not silent" standard unmet: a supported setting produces a
library traceback instead of a refusal naming the window and the reason. **Not fixed in this
increment** — the minimum frame count is a property of each §7 reader and must be read from the
checkpoints rather than guessed, and `_MIN_SAMPLED_FRAMES = 4` already exists nearby for a
*different* quantity (what the processor takes after re-sampling). Recorded as `BLOCKED.md` #22
with the measurement.

## What changed here

D-185 and `BLOCKED.md` #17 corrected to state the 1.0 fps floor, the 8 s real ceiling, and that the
0.25 fps route does not exist. No code changed; the correction is to the record, which is where the
error was.
