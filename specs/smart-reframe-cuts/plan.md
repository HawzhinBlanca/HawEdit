# Plan — Smart Reframe and Cut-Aware Tracking

## Status
Approved-by: User (Review Policy)

## Goal
Eliminate dead-air panning across wide-shot tables and single-frame dropout subject switches by:
1. Adding subject persistence distance limits in `choose_face` so single-frame dropouts do not jump to distant listeners.
2. Resetting scene-local tracker state across Stage 0 shot cuts in `OpenCvFaceTracker.track`.
3. Converting sustained distant transitions in `stabilize()` into clean instantaneous cut steps rather than either sliding slowly or dropping the move.

## Proposed Changes

### Task 1: Subject Persistence in `choose_face` & `OpenCvFaceTracker` (`src/hawedit/reframe.py`)
- Add `max_distance: int | None = None` to `choose_face(faces, previous_x, min_area, max_distance)`.
- When `max_distance` is supplied and `previous_x` is set, only candidate faces within `max_distance` are eligible for continuity selection. If none exist within `max_distance`, return `None`, allowing tracker/hold mechanisms to bridge the dropout.
- In `OpenCvFaceTracker.track`, pass `max_distance = int(width * 0.35)` to `choose_face`.

### Task 2: Cut-Aware State Reset in `OpenCvFaceTracker` (`src/hawedit/reframe.py`, `src/hawedit/pipeline.py`)
- Support `shot_cuts_ms: Sequence[int] = ()` in `OpenCvFaceTracker.track`.
- Across shot cuts, clear `previous = None` and `tracker = None` so new camera angles start from fresh detection.
- In `pipeline.py:run_pipeline`, pass `shot_cuts_ms=ingested.shot_cuts_ms` to `subject_tracker.track` when supported.

### Task 3: Instant Cut Transitions for Distant Wide-Shot Moves in `stabilize` (`src/hawedit/reframe.py`)
- In `stabilize()`, when `abs(target - held) > max_pan_px` and `point.at_ms - pending[0].at_ms >= settle_ms`:
  - Execute an instantaneous cut step:
    ```python
    if start > keyframes[-1].at_ms:
        keyframes.append(FocusPoint(start, held))
    keyframes.append(FocusPoint(max(start + 1, keyframes[-1].at_ms + 1), target))
    held = target
    pending.clear()
    ```
  - This preserves wide-shot speaker switching while guaranteeing zero slow camera pans across empty space.

### Task 4: Automated Verification & Unit Tests (`tests/test_reframe.py`)
- Add `test_choose_face_rejects_distant_faces_beyond_max_distance`: asserts dropout does not jump to distant listener.
- Add `test_opencv_face_tracker_resets_across_shot_cuts`: verifies fresh angle tracking after cut.
- Add `test_stabilize_steps_instantaneously_on_sustained_distant_move`: verifies instant cut step instead of pan or stagnation.
- Run `bash scripts/verify.sh` to ensure full gate is green.
