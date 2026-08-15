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
  cases then refused the intentionally dirty checkout, as designed.
- Authoritative post-commit canonical gate at source commit
  `24a5b6e65ef9501425cad508e650ed6ebd4faea4`: Ruff, strict mypy across 134 files, format,
  **2,524 collected / 2,524 passed / 0 skipped** in 345.51 seconds, fresh JUnit grading, and
  `VERIFY OK`. The gate ratcheted `scripts/test-count.floor` from 2,520 to 2,524.
- Source-bound WSL setup: accepted in 278.9 seconds with Python 3.12.0, 140 exact packages,
  Ubuntu, UID 1000, two CUDA devices, and all three Omni assets totaling 43,546,500,168 bytes.
- Live WSL VEX gate: accepted 12 findings against 12 matched dispositions in 123.5 seconds. Runtime
  source SHA-256 was `86fc8237d08e0037320e692e243d2ba74cf83ec93ba30612e3c32f97bb003fd3`;
  receipt SHA-256 was `6e0c135e8404540ba07e0ea47c89b256dc11876b2a2883b2aa32a54608b03ffb`.
  The non-overwriting external artifact is
  `C:\Users\Wareen\AppData\Local\Temp\hawedit-wsl-vex-bounded-keyframe-20260815-174154.json`,
  10,383 bytes, SHA-256
  `e068d6080537074d6cc2ff4d0d4282588f600af37184d9e9b80ca4c0f1b5567b`.

No external image bytes, credentials, or provider calls were used for this unit.
