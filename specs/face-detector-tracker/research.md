# Research: Face Detector Sample Rate and Tracker (Task T2.5)

## 1. Grounding & Context
Per `specs/pro-grade-program/tasks.md` Task T2.5:
> **T2.5** | **P1** | **Face detector: sample rate and tracker.** Raise sampling to ≥ 5 fps and add a between-sample tracker (OpenCV KCF/CSRT, already in the wheel) so a missed detection does not pan to the rug. Evaluate a DNN detector (OpenCV YuNet ships as an ONNX file, Apache-2.0) **only** via ADR + registry row + licence audit. `reframe.py:214,269-279`; §4.1 "rug on screen". A: tracker tests. B: detection recall vs 200 hand-labelled ep29 frames (D, cheap: Hawa or editor clicks faces); miss rate before/after. | ADR if a new model file

In `src/hawedit/reframe.py`, `OpenCvFaceTracker`:
- Currently samples at `sample_fps = 2.0` (every 500 ms).
- Relies solely on Haar cascade detection (`haarcascade_frontalface_default` and `haarcascade_profileface`).
- When a detection is missed (e.g. subject glances down, rapid head movement, transient profile angle), the tracker emits nothing for that step. If several consecutive samples are missed, the downstream reframe crop holds a stale position or drifts away from the subject, leading to the known "pan to the rug" regression.

## 2. Technical Investigation: OpenCV Trackers in Current Wheel
Probing the environment (`cv2` 4.12.0):
- `cv2.TrackerCSRT` / `TrackerKCF` are typically packaged in `opencv-contrib-python`.
- `cv2.TrackerMIL` is built into standard `opencv-python` and confirmed operational (`cv2.TrackerMIL.create()`).
- By querying `TrackerCSRT` -> `TrackerKCF` -> `TrackerMIL`, the system automatically selects the highest-accuracy available tracker while guaranteeing zero dependency failures on standard OpenCV wheels.

## 3. Architecture
1. **Sampling Rate**: Raise default `sample_fps` from 2.0 to 5.0 (step = 200 ms).
2. **Hybrid Detection & Tracking**:
   - Primary: Haar cascade detectors (frontal + profile + mirrored profile).
   - When a face is detected (`chosen is not None`), re-anchor the tracker with `tracker.init(frame, chosen_box)` and emit the point.
   - When detection in a frame yields no candidate (`chosen is None`) but a tracker is active, call `ok, bbox = tracker.update(frame)`. If tracking succeeds, emit the tracked focus point, maintaining continuous subject tracking through detection dropouts.
   - If tracking update fails, reset the tracker to `None` until the next positive detection.
3. **Graceful Compatibility**:
   - Check `hasattr(cv2, "TrackerMIL")` so unit test harnesses using mock cv2 objects (`_install_fake_cv2`) continue to function without error.
