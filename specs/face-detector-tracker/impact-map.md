# Impact Map: Face Detector Sample Rate and Tracker (Task T2.5)

## Modified Files
- `src/hawedit/reframe.py`:
  - `OpenCvFaceTracker`: default `sample_fps` changed from 2.0 to 5.0.
  - `OpenCvFaceTracker`: added `enable_tracker: bool = True` option.
  - `OpenCvFaceTracker.track`: added OpenCV tracker factory and between-sample tracking loop logic.
- `tests/test_reframe.py`:
  - Added unit tests for default 5.0 fps sampling rate, tracker bridging across detection dropouts, and tracker re-anchoring.

## Invariants & Safety
- Haar detection remains the ground-truth anchor; tracker only bridges between samples or transient detection dropouts.
- When no face is detected in the video from the start, no focus points are invented.
- Stand-in/fake cv2 harnesses (`_FakeDetector`, `_FakeCapture`) remain fully functional.
