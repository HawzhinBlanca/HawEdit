# Plan — First-Frame Gate (`specs/first-frame-gate`)

Approved-by: Hawa

> Task T2.3 from `specs/pro-grade-program/tasks.md`.
> Guarantees that the first frame of every delivered social clip contains the tracked subject at >= floor share, filtering out outward in-point expansions that cross into off-subject shots.

---

## 1. Goal
Ensure that a clip never opens on an empty frame, wrong person, or non-speaking host angle before dialogue begins, by filtering outward in-point candidates against first-frame face detection and verifying the opening frame at delivery reconciliation.

---

## 2. Architecture & Components

### 2.1 First-Frame Probing in `src/hawedit/reframe.py`
Introduce `probe_first_frame_face`:
```python
def probe_first_frame_face(
    source: Path,
    timestamp_ms: int,
    *,
    min_face_share: float = 0.10,
    expected_x: int | None = None,
    max_x_drift: int | None = None,
) -> tuple[bool, FocusPoint | None]:
```
Extracts a frame at `timestamp_ms` using OpenCV, detects frontal and profile faces, and verifies whether a face of $\ge$ `min_face_share` is present. If `expected_x` and `max_x_drift` are given, verifies the face is not an entirely different subject across the room.

### 2.2 First-Frame Gated In-Point Selection in `src/hawedit/boundary.py`
Update `fuse_boundary` with optional `first_frame_validator`:
- When candidate in-points are formed (`shot_cut`, `vad_onset`, `speaker_turn_start`, `anchor_in`), evaluate candidates in order of expansion.
- If an outward candidate fails validation (e.g. shot cut lands on host drinking), drop it and fall back to the next candidate (`vad_onset` or `anchor_in`).
- If all candidates fail validation, raise `FirstFrameLacksSubjectError` or return `candidate_failed`.

### 2.3 Integration in Pipeline (`src/hawedit/pipeline.py`)
In Stage 5/6:
- Before rendering, probe candidate in-points using `probe_first_frame_face`.
- If an outward candidate crossed a camera angle cut where the subject was not present, select the nearest candidate containing the subject.

### 2.4 Reconciliation Gate Check in `src/hawedit/delivery.py`
In `reconcile_delivery`:
- Add clause 8: Verify `first_frame_has_face` is true for face-tracked clips.
- Refuse delivery if `first_frame_has_face` is false.

---

## 3. Tasks

- [ ] T1 Implement `probe_first_frame_face` in `src/hawedit/reframe.py`
- [ ] T2 Implement first-frame gated candidate selection in `src/hawedit/boundary.py` and `pipeline.py`
- [ ] T3 Add first-frame verification clause to `reconcile_delivery` in `src/hawedit/delivery.py` and `measure.py`
- [ ] T4 Implement unit tests in `tests/test_boundary.py`, `tests/test_reframe.py`, and `tests/test_delivery.py`
- [ ] T5 Run gate, update VEX digest, and flip ledger

---

## 4. Verification Plan
- Unit test `test_a_clip_never_opens_on_a_frame_without_the_subject`.
- Unit test `test_delivery_refuses_when_first_frame_lacks_subject`.
- Full canonical gate verification via `scripts/verify.sh`.
