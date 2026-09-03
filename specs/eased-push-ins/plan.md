# Plan: Eased Push-Ins (Task T2.6)

Approved-by: Autonomous Goal Execution (/goal)

## 1. Overview
Implement continuous eased push-in zooming for HawEdit's vertical framing engine (`src/hawedit/render.py`). Instead of mechanical square-wave zoom alternation, shots continuously and smoothly creep inward (1.00x -> 1.08x) using cubic smoothstep easing, resetting with crisp hard cuts on motivated pause and angle boundaries.

## 2. Implementation Steps

### Step 1: Core Mathematical Functions & Partitioning (`render.py`)
1. Define `DEFAULT_PUSH_ZOOM = 1.08` and `DEFAULT_PUSH_STEP_MS = 100`.
2. Implement `shot_spans(...)`:
   - Sort and filter candidates from `boundaries_ms` (word pauses) and `source_cuts_ms`.
   - Filter boundaries closer than `min_shot_ms` (3,000 ms).
   - Filter boundaries within `guard_ms` (1,500 ms) of source cuts.
   - Return contiguous `tuple[tuple[int, int], ...]` spanning `0` to `clip_duration_ms`.
3. Implement `eased_push_schedule(...)`:
   - Iterate over each shot span `(start_ms, end_ms)`.
   - Generate discrete time steps `t_ms` every `step_ms`.
   - Calculate normalized progress $p = (t - start) / (end - start)$.
   - Apply cubic smoothstep: $ease = 3p^2 - 2p^3$.
   - Scale factor: $1.0 + (push\_zoom - 1.0) \times ease$.
   - Return `tuple[tuple[int, float], ...]`.

### Step 2: Pipeline Integration (`pipeline.py`)
1. Add `--eased-push` argument to argument parser.
2. In `pipeline.py`, when framing dynamic shots:
   If `--eased-push` is set or in deliverable mode, calculate `eased_push_schedule` and supply it to `render_clip`.

### Step 3: Comprehensive Test Coverage (`tests/test_render.py`)
1. Test `shot_spans`:
   - Clean partition on standard pauses.
   - Respects `min_shot_ms`.
   - Omits pause within `guard_ms` of source cut.
   - Single-shot fallback on short or empty clips.
2. Test `eased_push_schedule`:
   - Starts at 1.00 and ends at `push_zoom`.
   - Monotonic growth across shot duration.
   - Instantaneous reset to 1.00 at shot transition.
   - Step spacing matches `step_ms`.
3. Test FFmpeg render:
   - Renders clip with `eased_push_schedule` without error, producing valid vertical video.

### Step 4: Verification & Gate
1. Run `verify.sh --fast` for linting and typechecking.
2. Run full `verify.sh` for all 3,439+ tests.
3. Update `specs/eased-push-ins/ledger.log` using `scripts/update-ledger.sh`.
4. Update `specs/pro-grade-program/tasks.md`.
