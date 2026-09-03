# Spec — Composition Line Under Punch-Ins (`specs/punch-in-composition`)

## Acceptance Criteria (EARS Format)

- **CRIT-1**: WHEN `crop_filter` is called with dynamic `punch_ins` and a valid `face_center_y`, THE system SHALL emit a crop `y_expr` anchoring the vertical face position to `face_center_y - FACE_COMPOSITION_LINE * out_h`.
- **CRIT-2**: WHEN `crop_filter` is called with dynamic `punch_ins` and `face_center_y=None`, THE system SHALL emit a crop `y_expr` centering vertically on `(source_height // 2) - out_h / 2`.
- **CRIT-3**: WHEN the crop output size (`out_h`) changes at a punch-in keyframe, THE resulting cropped frame SHALL keep the subject's face at the 0.38 composition line within clamped frame bounds.
