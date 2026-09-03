# Impact Map: Eased Push-Ins (Task T2.6)

## 1. Target Symbols & Callers

### New Symbols in `src/hawedit/render.py`
- `DEFAULT_PUSH_ZOOM: Final = 1.08`: Default creep zoom factor for speech shots.
- `DEFAULT_PUSH_STEP_MS: Final = 100`: Keyframe step interval for `sendcmd` (10 fps).
- `shot_spans(boundaries_ms, clip_duration_ms, source_cuts_ms=(), min_shot_ms=MIN_SHOT_MS, guard_ms=SHOT_CUT_GUARD_MS) -> tuple[tuple[int, int], ...]`:
  Partitions clip duration into contiguous shot intervals using word pauses and source cuts.
- `eased_push_schedule(shot_spans, push_zoom=DEFAULT_PUSH_ZOOM, step_ms=DEFAULT_PUSH_STEP_MS, base_zoom=1.0) -> tuple[tuple[int, float], ...]`:
  Generates smoothstep keyframes across each shot span.

### Modified Symbols in `src/hawedit/render.py`
- `__all__`: Export `DEFAULT_PUSH_ZOOM`, `DEFAULT_PUSH_STEP_MS`, `shot_spans`, `eased_push_schedule`.

### Modified Symbols in `src/hawedit/pipeline.py`
- CLI argument `--eased-push`: Optional flag (or enabled in deliverable mode) allowing selection between legacy mechanical punch-in schedule and eased push-in schedule.

### Modified Test Modules
- `tests/test_render.py`:
  - Add unit tests for `shot_spans` (partitioning, guard bands, min shot length).
  - Add unit tests for `eased_push_schedule` (smoothstep progression, monotonicity, step spacing, boundary resets).
  - Add render integration test verifying FFmpeg renders an eased push-in video successfully.

## 2. Risk Assessment
- **Breaking Changes:** None. Existing `punch_in_schedule` remains intact and unaffected.
- **FFmpeg Compatibility:** Confirmed on FFmpeg 8.1.1. `sendcmd` handles hundreds of keyframe commands seamlessly.
- **Performance Impact:** Zero runtime overhead during inference; negligible string formatting time in filter graph assembly.
