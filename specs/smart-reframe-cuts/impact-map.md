# Impact Map — Smart Reframe and Cut-Aware Tracking

## Modified Symbols
| Symbol | File | Callers Affected | Test Coverage Required |
|---|---|---|---|
| `choose_face` | `src/hawedit/reframe.py` | `OpenCvFaceTracker.track`, `tests/test_reframe.py` | Verify single-frame dropouts do not abandon established subject on wide shots |
| `stabilize` | `src/hawedit/reframe.py` | `pipeline.py`, `tests/test_reframe.py`, `tests/test_pipeline.py` | Verify shot-cut awareness and instant transitions across shot cuts, zero sliding over dead middle space |
| `_crop_filter` / `reframe` | `src/hawedit/pipeline.py` | `Stage 6 render` | Pass shot cut boundaries to reframing pipeline |

## Invariants to Preserve
1. Strict Fail-Stop: No silent fallbacks.
2. Exact timestamps: Keyframe timestamps must remain strictly increasing.
3. Test suite green: All existing tests in `tests/test_reframe.py`, `tests/test_render.py`, and `tests/test_pipeline.py` must pass.
