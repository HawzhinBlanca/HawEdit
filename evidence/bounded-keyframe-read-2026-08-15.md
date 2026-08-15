# Bounded Stage 4 keyframe reads - 2026-08-15

## Finding

`hawedit.keyframes._read_keyframe` used `Path.read_bytes()`. The 5 MiB `JudgeFrame`
limit therefore ran only after the full ffmpeg artifact had been allocated. An empty ffmpeg
artifact also raised raw `ValueError`, outside the extractor's operational `KeyframeError`
contract.

## Red controls

Before the production change, the new tests measured:

- the file object received `read(-1)`, not a bounded read;
- an empty extraction escaped as `ValueError("judge keyframe data must be non-empty bytes")`;
- a 5 MiB + 1 extraction escaped as `ValueError("one judge keyframe exceeds ...")`.

## Implementation

- `MAX_JUDGE_FRAME_BYTES` is the single exported 5 MiB authority used by both `JudgeFrame` and
  the extractor.
- `_read_keyframe` performs exactly one `read(MAX_JUDGE_FRAME_BYTES + 1)`.
- Empty and oversized artifacts raise `KeyframeError` before `JudgeFrame` construction.
- The existing uniquely owned extraction directory remains inside the same `finally` cleanup.

## Verification

- `tests/test_keyframes.py` + `tests/test_judge.py`: 98 passed.
- Stage 4, pipeline, smoke, and VEX adjacency: 394 passed, then 357 passed.
- Focused Ruff, format, and strict mypy: green.
- The first full-suite attempt reached 2,520 passes plus the four new test cases; four release-build
  cases then refused the intentionally dirty checkout, as designed. The authoritative canonical
  clean-commit result is appended after the explicit source commit.

No external image bytes, credentials, or provider calls were used for this unit.
