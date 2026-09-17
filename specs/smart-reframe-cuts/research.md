# Research — Smart Reframe and Cut-Aware Tracking (Phase 2 Enhancement)

## 1. Problem Description & Visual Defects
In rendered vertical clips (such as Zar Podcast Episode #29 `ep29-chunk50min` / `ep29-VbX8UWwl1c4`), three distinct reframing flaws degrade visual retention:
1. **Single-Frame Dropout Flips to Distant Listener on Wide Shots**:
   - On a wide two-shot, two subjects sit across a table (e.g. host at `x=310`, guest at `x=997`).
   - When the speaking subject's face detector momentarily drops out for 1 sample (e.g. turning head or looking at notes), `choose_face` is called with `faces = [Face(x=997)]`.
   - Even with `previous_x = 310`, because there is only one candidate, `choose_face` returns `Face(x=997)`.
   - `OpenCvFaceTracker.track()` immediately sets `previous = 997` and re-initializes `tracker` on the distant face.
   - On the next frame when `x=310` is back, `previous` is now `997`, so `choose_face` permanently locks onto the distant listener (`x=997`) across the room.
2. **Slow Pan / Sliding Across Shot Cuts**:
   - `OpenCvFaceTracker.track()` maintains `previous` and `tracker` across Stage 0 shot cuts.
   - When the camera cuts from a close-up to a wide shot, the tracker drags coordinates from the previous camera setup instead of resetting scene-local identity.
3. **Reframing Stagnation on Wide-Shot Speaker Transitions (`max_pan_px` Trap)**:
   - In `stabilize()`, if a move between two distant speakers (`abs(target - held) > max_pan_px`) occurs within a continuous wide shot (no camera cut in `shot_cuts_ms`), `stabilize()` clears `pending` and continues.
   - This discards the move forever, leaving the camera permanently trapped on the old silent speaker even when the new speaker has talked for seconds.
   - The correct behavior when a sustained transition exceeds `max_pan_px` is to execute an **instant cut step** at `start` (`FocusPoint(start, held)` -> `FocusPoint(start + 1, target)`), rather than either sliding slowly over the empty table or refusing to move at all.

## 2. Root Cause Analysis in Code
- **`src/hawedit/reframe.py:choose_face`**:
  - Distance weighting is relative among available candidates: `(w * h) / (1 + abs(face_x - previous_x))`.
  - When only one distant candidate exists (`abs(cx - previous_x) > max_distance`), it still wins because there are no rivals.
  - Fix: Add optional `max_distance: int | None = None`. If `previous_x` is set and `max_distance` is specified, candidate faces further than `max_distance` are rejected, returning `None`.
- **`src/hawedit/reframe.py:OpenCvFaceTracker.track`**:
  - Does not accept or heed `shot_cuts_ms`.
  - Across a shot cut, `previous` and `tracker` must be cleared so the new shot is evaluated on fresh evidence.
  - When `choose_face` returns `None` due to a distant dropout, use the active `tracker` or hold `previous` position rather than jumping.
- **`src/hawedit/reframe.py:stabilize`**:
  - When `abs(target - held) > max_pan_px` and `point.at_ms - pending[0].at_ms >= settle_ms`:
    - Instead of discarding `pending`, step instantaneously:
      `keyframes.append(FocusPoint(start, held))`
      `keyframes.append(FocusPoint(max(start + 1, keyframes[-1].at_ms + 1), target))`
      `held = target; pending.clear()`
    - This eliminates dead-air panning across furniture while ensuring the camera promptly switches to the active speaker.

## 3. Affected Components & Invariants
- `src/hawedit/reframe.py`: `choose_face`, `OpenCvFaceTracker.track`, `stabilize`.
- `src/hawedit/pipeline.py`: pass `shot_cuts_ms` to `subject_tracker.track()` when available.
- `tests/test_reframe.py`: targeted unit tests verifying dropout immunity, cut-aware tracker clearing, and instantaneous wide-shot speaker transitions.
