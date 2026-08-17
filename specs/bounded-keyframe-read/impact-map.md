# Impact map - bounded Stage 4 keyframe reads

## Changed symbols

- `hawedit.judge.MAX_JUDGE_FRAME_BYTES`
  - read by `JudgeFrame.__post_init__`
  - read by `hawedit.keyframes._read_keyframe`
- `hawedit.keyframes._read_keyframe`
  - called only by `extract_judge_frames`

## Affected callers

- `hawedit.pipeline.run_pipeline`: keeps receiving `KeyframeError`, which it already serializes as
  a Stage 4 `StageSkipped` result.
- `hawedit.smoke`: receives the same domain error instead of an unbounded allocation or raw
  `ValueError`.
- `hawedit.gemini` and direct `JudgeFrame` users: no API change; the same byte ceiling remains.

## Verification surface

- `tests/test_keyframes.py`: bounded read, oversize/empty refusal, and owned-directory cleanup.
- `tests/test_judge.py`: shared constant and exact ceiling boundary.
- `tests/test_pipeline.py`, `tests/test_gemini.py`, `tests/test_smoke.py`: adjacency.
- Canonical repository gate and source-bound WSL VEX acceptance.
