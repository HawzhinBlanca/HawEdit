# Plan: Face Detector Sample Rate and Tracker (Task T2.5)

Approved-by: Hawa

## Overview
Raise `OpenCvFaceTracker` sampling rate from 2.0 fps to 5.0 fps and add a between-sample tracker to bridge detection dropouts so missed Haar detections do not result in reframe drift or camera wander.

## Architecture
1. In `src/hawedit/reframe.py`:
   - Set `sample_fps: float = 5.0` as default.
   - Introduce `_create_tracker(cv2)` helper prioritizing `TrackerCSRT` -> `TrackerKCF` -> `TrackerMIL`.
   - In `track()`:
     - On positive detection: emit `FocusPoint`, initialize/re-anchor `tracker.init(frame, chosen_box)`.
     - On missed detection: if tracker is active, call `tracker.update(frame)` and emit tracked `FocusPoint`. Reset tracker if update fails.
2. In `tests/test_reframe.py`:
   - Verify default `sample_fps == 5.0`.
   - Verify tracker bridges missed detection frames.
   - Verify tracker re-anchoring when detection resumes.
