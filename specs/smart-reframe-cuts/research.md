# Research — Smart Reframe and Cut-Aware Subject Tracking

## Problem Description
In rendered vertical clips (such as Zar Podcast Episode #29 `ep29-VbX8UWwl1c4-s25-25`), two jarring artifacts occur:
1. **Dead Frame in the Middle of Wide Shots**:
   On a wide two-shot (e.g. at `t=20.5s`), two people sit on opposite sides of a podcast table (left speaker at `x=310`, right person at `x=997`). When the face tracker momentarily loses the left speaker's face, `choose_face` flips to the right face (`x=997`). `stabilize()` then initiates a 400ms camera pan (`move_ms=400`) across 687 pixels of empty space/table, filming dead air in the middle of the frame before settling on the silent listener.
2. **Slow Camera Pan / Glide Across Shot Cuts**:
   When the source video cuts from a close-up (`x=659`) to a wide shot (`x=310`) at `t=16.5s`, or from wide shot back to close-up (`x=643`) at `t=25.5s`, the camera slides over 400ms across the cut instead of cutting instantly at the cut boundary.

## Root Cause Analysis
1. `choose_face` in `reframe.py`:
   - Calculates distance weighting `(w*h) / (1 + abs(face_x - prev_x))`.
   - If `prev_x` was `310`, and for 1 frame only `x=997` is returned, `choose_face` returns `997` and permanently sets `previous = 997`.
   - Because `stabilize()` sees `held = 310` and 3 subsequent samples of `997`, after `settle_ms` (600ms) it generates a linear move `FocusPoint(start, 310)` -> `FocusPoint(start+400, 997)`.
   - In ffmpeg, `_interpolated` turns this into a continuous sliding crop that sweeps across the empty center of the wide table.
2. Shot Boundaries Ignored by `stabilize()`:
   - `stabilize()` has no awareness of shot cuts detected in Stage 0.
   - When a shot cut occurs, any reframing change between shot N and shot N+1 should be a **hard cut** (instant transition at the cut timestamp, 0ms pan), NOT a 400ms slide.
3. Distant Jumps on Wide Two-Shots:
   - On a wide shot, when two subjects are separated by more than `dead_zone_px` or `crop_w * 0.6` (e.g. 300+ px), switching between them during a single shot should never be a slow continuous pan over empty table. The tracker must prioritize subject persistence on the primary speaker during a continuous shot.

## Affected Components & Symbols
- `hawedit/reframe.py`:
  - `choose_face`: Needs subject persistence hysteresis so a 1-frame detection dropout does not instantly switch to a distant face across the room.
  - `stabilize`: Needs to support instant cuts across shot boundaries (or cut points) and eliminate linear pans over large distances within wide shots.
- `hawedit/render.py`:
  - `_interpolated`: Already handles step transitions if two keyframes share the same timestamp or 1ms step.
- `hawedit/pipeline.py`:
  - Passes Stage 0 shot cuts (or shot boundary information) into clip reframing so transitions across cuts happen on the exact cut frame.
