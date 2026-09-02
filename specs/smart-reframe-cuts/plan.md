# Plan — Smart Reframe and Cut-Aware Tracking

## Status
Approved-by: Hawa

## Goal
Eliminate dead-frame panning across empty tables on wide shots and replace slow 400ms sliding pans with instant cuts at shot boundaries.

## Proposed Changes

### Task 1: Shot-Cut Aware Keyframing in `reframe.py` & `pipeline.py`
1. Extend `stabilize(points, *, dead_zone_px, move_ms, settle_ms, shot_cuts_ms=())`:
   - If a reframing change crosses a shot cut boundary, the transition must be instantaneous (jump to new position at the shot cut timestamp `t_cut`, e.g. 1ms step), rather than a gradual 400ms linear interpolation that slides across the edit.
2. Update `pipeline.py` to pass Stage 0 `shot_cuts` (filtered to `[in_ms..out_ms]`) to `stabilize`.

### Task 2: Subject Persistence on Wide Two-Shots in `reframe.py`
1. Prevent camera from wandering back and forth across wide two-shots:
   - When multiple faces are present in a shot (e.g. distance > crop width or > 300px), strongly latch onto the established speaker of that shot.
   - Disallow slow pans over empty space (`distance > crop_w * 0.7`) within a single continuous shot. If a genuine speaker shift occurs, switch instantaneously on a pause/boundary, never slide slowly across empty furniture.

### Task 3: Unit Tests & Verification
1. Add tests in `tests/test_reframe.py` verifying:
   - Transitions across shot cuts produce instantaneous keyframe steps, not 400ms pans.
   - Wide two-shots maintain steady framing on the active speaker without drifting or panning across dead middle space.
2. Run `bash scripts/verify.sh` to ensure gate passes with 0 lint/type/test errors.

### Task 4: Re-render Episode #29 Reel & Verify Video Quality
1. Re-render the winning moment `ep29-VbX8UWwl1c4-s25-25`.
2. Extract frames at 16s..25s and verify that at 20s the camera stays locked on the speaking subject with zero dead frames and zero weird slides.
