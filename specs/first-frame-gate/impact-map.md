# Impact Map — First-Frame Gate (`specs/first-frame-gate`)

## 1. Modified Files
- `src/hawedit/reframe.py`: Adds `probe_first_frame_face` helper.
- `src/hawedit/boundary.py`: Adds candidate in-point gating support in `BoundaryInputs` / `fuse_boundary`.
- `src/hawedit/measure.py`: Adds `first_frame_face_share` to `FaceTrackMeasurement`.
- `src/hawedit/delivery.py`: Adds `first_frame_has_face` reconciliation clause.
- `tests/test_boundary.py`: Unit tests for first-frame in-point candidate selection.
- `tests/test_reframe.py`: Unit tests for `probe_first_frame_face`.
- `tests/test_delivery.py`: Unit tests for first-frame reconciliation refusal.
- `security/wsl-asr-vex.json`: Updated `source_sha256`.

## 2. Invariants Preserved
- Zero silent fallbacks: an unvalidated first frame is explicitly refused, never approximated.
- Deterministic boundary math: candidates remain strict timestamps derived from VAD, shot cuts, and speech anchors.
- Backward compatibility: when no validator is supplied, `fuse_boundary` maintains default behavior.
