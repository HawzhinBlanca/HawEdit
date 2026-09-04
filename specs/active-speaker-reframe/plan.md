# Plan: Active-Speaker Reframe (Task T2.1, re-opened pro-edit T7)

> Approved-by: Hawa (P1 Task T2.1 from `specs/pro-grade-program/tasks.md`)

## Overview

Implement Candidate Associator (a) for Task T2.1 in `src/hawedit/reframe.py`: an OpenCV Haar face tracker augmented with lower-third mouth-region pixel-motion energy calculation at >= 5 fps, correlated against exclusive diarization turns to track active speakers across multi-person dialogue without external neural weights.

## Tasks

1. **Implement `MotionSpeakerTracker` in `src/hawedit/reframe.py`**:
   - Conforms to `SpeakerSubjectTracker` protocol.
   - Computes mouth-region pixel-motion energy across sampled frames (default 5.0 fps).
   - Associates active speaker turn with moving mouth face.
   - Enforces the "on ambiguity hold, never wander" invariant.
   - Emits valid `SpeakerFocusPoint` instances.

2. **Integration in `src/hawedit/pipeline.py`**:
   - When diarization is enabled (`--diarize`) and not `--static-crop`, construct and pass `MotionSpeakerTracker()` as `speaker_tracker`.

3. **Automated Verification**:
   - Add unit tests in `tests/test_reframe.py` covering single-speaker, multi-speaker alternation, ambiguity hold, and error handling.
   - Add integration test in `tests/test_pipeline.py`.
   - Run full gate and flip ledger via `scripts/update-ledger.sh active-speaker-reframe T1 ...`.
