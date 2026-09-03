# Research — First-Frame Gate (`specs/first-frame-gate`)

> Task T2.3 from `specs/pro-grade-program/tasks.md`.
> Guarantees that every social clip opens immediately on the active subject, preventing blind outward boundary expansions from opening on off-subject or empty camera angles.

---

## 1. Problem Analysis: The "Host Drinking" Defect
In `ep29-VbX8UWwl1c4-s25-25` (the 57s canonical delivery clip), `research.md` §3.1 documented:
> "0–1 s: the opening frame is the wrong person. The hook card sits over a wide two-shot in which the crop shows the host drinking from a cup; the guest who speaks the whole clip is cut off at the right edge. The first frame a viewer sees is not the speaker."
> "Scene changes (`scene>0.3`): 10 at 0.56, 11.04, 17.08, ..."

### Root Cause in `src/hawedit/boundary.py`:
In `fuse_boundary`:
```python
in_candidates: list[tuple[int, str | None]] = [(inputs.anchor_in_ms, None)]
if inputs.vad_onset_ms is not None:
    in_candidates.append((inputs.vad_onset_ms - VAD_LEAD_IN_MS, "vad_onset"))
if inputs.speaker_turn_start_ms is not None:
    in_candidates.append((inputs.speaker_turn_start_ms, "speaker_turn_start"))
preceding_cuts = [
    cut for cut in inputs.shot_cuts_ms
    if cut <= inputs.anchor_in_ms and inputs.anchor_in_ms - cut <= SHOT_CUT_WINDOW_MS
]
if preceding_cuts:
    in_candidates.append((min(preceding_cuts), "shot_cut"))

final_in_ms, in_extended_by = min(in_candidates, key=lambda candidate: candidate[0])
```
Notice: `min(in_candidates)` blindly takes the earliest timestamp without checking what the camera is pointing at.
Because a scene cut occurred at `t = 0.56s` (560ms before the guest's close-up), an outward expansion crossed the camera cut backwards into the previous shot. The camera was pointing across the table at the host, cutting off the guest.

---

## 2. Technical Solution

### 2.1 First-Frame Candidate Evaluation
Given outward candidate in-points (ordered from earliest to latest: `shot_cut`, `vad_onset`, `speaker_turn_start`, `anchor_in`):
1. Probe the video frame at the candidate timestamp.
2. Verify that:
   - A face is detected.
   - The face height share $\ge$ floor share (`min_face_share = 0.10`).
   - The face corresponds to the speaker / subject (not an off-angle cut).
3. If the candidate frame fails, discard that expansion candidate and try the next candidate.
4. If ALL candidates fail (including `anchor_in`), refuse the clip with an explicit fail-stop reason:
   `StageSkipped(stage="boundary", reason="first_frame_lacks_subject")`.

### 2.2 Level C Reconciliation Gate Integration
In `src/hawedit/delivery.py` (`reconcile_delivery`):
Clause: Verify that the delivered clip's opening frame contains the subject face (`first_frame_has_face`).
Refuse delivery if `first_frame_has_face is False` when `crop_target == "face_tracked"`.

---

## 3. Grounding & References
- `specs/pro-grade-program/tasks.md` Task T2.3: First-frame gate.
- `src/hawedit/reframe.py`: `OpenCvSubjectTracker`, `FocusPoint`.
- `src/hawedit/boundary.py`: `fuse_boundary`, `BoundaryInputs`.
- `src/hawedit/delivery.py`: `reconcile_delivery`, `DeliveryRefused`.
