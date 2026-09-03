# Spec — First-Frame Gate (`specs/first-frame-gate`)

## Acceptance Criteria (EARS Format)

- **CRIT-1**: WHEN an outward in-point candidate (e.g. shot cut up to 400ms before speech) results in an opening frame lacking the active subject or falling below minimum face share (0.10), THE system SHALL discard that candidate and test the next inward candidate (`vad_onset`, `speaker_turn_start`, or `anchor_in`).
- **CRIT-2**: WHEN all candidate in-points fail to show the subject in the opening frame, THE system SHALL raise `FirstFrameLacksSubjectError` and skip delivery with `StageSkipped(stage="boundary", reason="first_frame_lacks_subject")`.
- **CRIT-3**: WHEN independent artifact measurement (`hawedit.measure`) evaluates a delivered video, THE system SHALL extract `first_frame_face_share` at `t=0.0s`.
- **CRIT-4**: WHEN `reconcile_delivery` evaluates a clip claiming `crop_target="face_tracked"`, THE system SHALL refuse delivery (`DeliveryRefused`) if the measured opening frame contains no detected face (`first_frame_face_share is None` or `< 0.05`).
