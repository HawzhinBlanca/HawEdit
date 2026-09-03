# Spec: Face Detector Sample Rate and Tracker (Task T2.5)

## Acceptance Criteria (EARS Format)

- **AC-1 (Default Sampling Rate)**:
  WHEN `OpenCvFaceTracker` is instantiated without explicit arguments,
  THE system SHALL default `sample_fps` to 5.0 fps.

- **AC-2 (Between-Sample Tracking on Missed Detection)**:
  WHEN a frame evaluation yields no Haar cascade face detection and an active tracker is initialized,
  THE system SHALL update the tracker on the current frame and emit the tracked focus point.

- **AC-3 (Detector Priority and Tracker Re-anchoring)**:
  WHEN a frame evaluation yields a positive Haar cascade face detection,
  THE system SHALL emit the detected focus point and re-initialize the tracker with the detected box.

- **AC-4 (Tracker Loss Recovery)**:
  WHEN tracker update fails on a frame without face detection,
  THE system SHALL clear the tracker state and emit no focus point until the next positive detection.
