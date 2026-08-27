# Plan — vertical composition

## The defect in one line

`--face-reframe` is opt-in, so the documented invocation renders a static centre crop — measured
on real footage as an empty wall with both speakers cut off at the edges.

## Approach

**Invert the flag (AC-1, AC-2).** Face tracking becomes what you get; `--static-crop` is the
opt-out. The evidence is two clips from the same episode, one unusable and one fine, differing
only in that flag. A default that produces an unpostable clip is not a default.

**Degrade visibly (AC-3).** Face tracking needs OpenCV, which is an extra. A default that hard
-fails on a missing optional dependency is worse than the problem it fixes, and one that quietly
falls back is exactly the silent case §1 forbids. So: fall back to static centre, and say so as a
named skip carrying the reason.

**Vertical framing is adaptive, and a no-op on a good source (AC-4, AC-5).** Measured across 60
samples per source: ep10 puts faces at 33% down filling 28.5% of frame height; the wide shot puts
them at 45% filling 11.6%. A blanket zoom would fix the second and ruin the first. So the crop
tightens only when the face is smaller than the target share, and the owner's own footage is
therefore untouched — the same rule D-254 applies to a candidate already in range.

**Nothing changes for a caller that measures nothing (AC-6).** `FocusPoint` gains `center_y` and
`face_height` defaulting to `None`, which is D-033's "unmeasured, not zero". 37 construction
sites keep compiling and every existing artifact renders identically.

## The numbers, and what they cost

| constant | value | why |
|---|---|---|
| `TARGET_FACE_HEIGHT_SHARE` | 0.22 | below ep10's measured 0.285, so a good source is left alone |
| `FACE_COMPOSITION_LINE` | 0.38 | where the face centre sits in the crop; ep10 measures 0.33 |
| `MAX_VERTICAL_ZOOM` | 1.5 | the cap, and it is a quality decision rather than a taste one |

**The zoom cap is the honest part.** 1920x1080 at ~850 kbps is already upscaled 1.78x to reach
1920 tall. Bringing an 11.6% face to 22% needs a further 1.9x — 3.4x total — on footage that
cannot carry it. Capped at 1.5x the face reaches 17.4% and the total upscale is 2.67x: better
framed, visibly softer. That trade is recorded rather than hidden, and a source shot this wide is
better fixed at the camera.

## Files and symbols

| file | change |
|---|---|
| `src/hawedit/reframe.py` | `FocusPoint` gains the measured box; the tracker stops discarding it; `stabilize` carries it |
| `src/hawedit/render.py` | `crop_filter` places `y`; the composition constants |
| `src/hawedit/pipeline.py` | the flag inverts; the fallback skip |
| `DECISIONS.md` | ADR: the default, the constants, and the upscale cost |

## Risks

- **Speaker tracking is still blocked** (`BLOCKED.md` #4). The default follows the dominant face,
  not the person talking, so on a two-shot it will sometimes hold on a listener. This is an
  improvement over a wall, not the thing §3 Stage 6 specifies.
- **Inverting a flag breaks an existing invocation.** `--face-reframe` must be refused with a
  message naming its replacement rather than an argparse error.
- **The zoom cap is a judgement, not a measurement.** 1.5 is chosen; the face share and centre
  positions behind it are measured. Recorded as such.
- The vertical `y` expression has never been exercised with a non-zero value, so its first real
  test is here.

Approved-by: Hawa (in chat, 2026-08-27) — "fix the framing default and headroom".
