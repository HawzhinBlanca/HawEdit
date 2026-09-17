# Impact Map — Smart Reframe and Cut-Aware Tracking

## Modified Symbols
| Symbol | File | Callers Affected | Test Coverage Required |
|---|---|---|---|
| `choose_face` | `src/hawedit/reframe.py` | `OpenCvFaceTracker.track`, `probe_first_frame_face`, `tests/test_reframe.py` | Verify `max_distance` preserves subject persistence during single-frame dropouts |
| `OpenCvFaceTracker.track` | `src/hawedit/reframe.py` | `pipeline.py`, `tests/test_reframe.py` | Verify `shot_cuts_ms` parameter resets tracking across camera cuts |
| `stabilize` | `src/hawedit/reframe.py` | `_steady_camera` in `pipeline.py`, `tests/test_reframe.py` | Verify sustained moves exceeding `max_pan_px` execute instant cut steps rather than dropping out or sliding |
| `_steady_camera` / `run_pipeline` | `src/hawedit/pipeline.py` | Stage 6 render reframing | Pass `shot_cuts_ms` to `subject_tracker.track` |

## Invariants to Preserve
1. **Strict Fail-Stop**: No silent fallbacks or unhandled exceptions.
2. **Strictly Increasing Timestamps**: Keyframe timestamps in `stabilize` must remain strictly monotonic.
3. **No Added Dependencies**: Use only OpenCV / Python stdlib.
4. **Zero Test Regressions**: All 3,736 existing tests must remain green.
