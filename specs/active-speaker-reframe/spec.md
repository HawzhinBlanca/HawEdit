# Spec: Active-Speaker Reframe (Task T2.1, re-opened pro-edit T7)

## Acceptance Criteria (EARS Format)

- **AC-1 (Protocol Conformance & Single-Speaker Turn Focus)**:
  WHEN `MotionSpeakerTracker.track_speakers` is called on a video span with valid exclusive diarization turns and a single visible speaker,
  THE system SHALL emit strictly increasing `SpeakerFocusPoint` values where every point's timestamp falls within an active turn and carries the active speaker's label.

- **AC-2 (Mouth Pixel-Motion Energy & Multi-Speaker Turn Association)**:
  WHEN multiple faces are detected across alternating exclusive speaker turns,
  THE system SHALL compute pixel-motion energy in the lower third (mouth region) of each face box at >= 5 fps, associate the active speaker turn with the face exhibiting mouth motion, and frame that speaker's horizontal centre.

- **AC-3 (Ambiguity Hold Invariant)**:
  WHEN mouth motion energy between detected faces is ambiguous or below threshold during an active turn,
  THE system SHALL hold the speaker's last confirmed face position and SHALL NOT wander between candidates.

- **AC-4 (Pipeline & Reconciliation Gate Integration)**:
  WHEN `run_pipeline` is executed with exclusive diarization turns and `speaker_tracker=MotionSpeakerTracker()`,
  THE system SHALL reframe in `Reframe.SPEAKER_TRACKED` mode, emit `crop_target=speaker_face` in the contract, and pass Level C reconciliation Clause 7.
