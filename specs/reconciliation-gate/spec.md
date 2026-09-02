# Specification — Reconciliation Gate in Delivery (`specs/reconciliation-gate`)

## Acceptance Criteria (EARS Format)

### AC-1: Duration Reconciliation
- **WHEN** a delivered MP4's measured duration differs from `clip.durations[0]` by more than ±1 frame (±40 ms at 25 fps), **THE** reconciliation gate **SHALL** raise `DeliveryRefused` specifying `"duration_mismatch"`.

### AC-2: Geometry Reconciliation
- **WHEN** a delivered MP4's measured dimensions differ from 1080×1920, **THE** reconciliation gate **SHALL** raise `DeliveryRefused` specifying `"geometry_mismatch"`.

### AC-3: Audio Dynamics Reconciliation
- **WHEN** a delivered MP4's measured integrated loudness differs from −14.0 LUFS by more than ±0.5 LUFS, or measured true peak exceeds −0.9 dBFS, **THE** reconciliation gate **SHALL** raise `DeliveryRefused` specifying `"loudness_violation"`.

### AC-4: Silence Removal Math Reconciliation
- **WHEN** the difference between the source span duration and the measured audio duration does not match `clip.silence_removed_ms` within ±1 frame, **THE** reconciliation gate **SHALL** raise `DeliveryRefused` specifying `"silence_math_mismatch"`.

### AC-5: Visual Cut and Punch-In Alignment
- **WHEN** any planned punch-in lacks a corresponding measured visual cut (`scdet`) within ±1 frame, or an unplanned visual cut occurs more than `SHOT_CUT_GUARD_MS` (1,500 ms) away from any source camera cut, **THE** reconciliation gate **SHALL** raise `DeliveryRefused` specifying `"visual_cut_mismatch"`.

### AC-6: Caption Ink Energy Verification
- **WHEN** the contract asserts `captions_burned_in == True` but the measured ink energy detected share across caption dialogue events is less than 95%, **THE** reconciliation gate **SHALL** raise `DeliveryRefused` specifying `"caption_ink_missing"`.

### AC-7: Face Tracking In-Frame Verification
- **WHEN** the contract asserts `crop_target == "face_tracked"` but the measured face-detected share across sampled speech frames is less than 90%, **THE** reconciliation gate **SHALL** raise `DeliveryRefused` specifying `"face_tracking_unsubstantiated"`.

### AC-8: Sixth Delivery Artifact Publication
- **WHEN** all reconciliation clauses pass, **THE** pipeline **SHALL** write `<clip_id>.measured.json` into the delivery bundle and publish all six artifacts atomically.
