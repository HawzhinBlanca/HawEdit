# Impact Map — Reconciliation Gate in Delivery (T1.2)

## 1. Symbol Additions & Modifications

| Symbol | Location | Change | Callers / Impact |
|---|---|---|---|
| `DeliveryRefused` | `src/hawedit/delivery.py` | NEW: Exception subclassing `DeliveryError` carrying `(reason, expected, measured)` | Called by `reconcile_delivery`; handled by `pipeline.py` delivery exception block |
| `reconcile_delivery` | `src/hawedit/delivery.py` | NEW: Function verifying 7 non-negotiable clauses against `ClipMeasurement` | Called by `src/hawedit/pipeline.py` before `bundle.publish()` |
| `_SUFFIXES` | `src/hawedit/artifact_bundle.py` | MODIFIED: Widened from 5 to 6 suffixes (`("ass", "mp4", "srt", "edl", "json", "measured.json")`) | `ArtifactBundle.publish()`, `staged_path`, `final_paths_for`, `test_artifact_bundle.py` |
| Delivery Stage | `src/hawedit/pipeline.py` | MODIFIED: Runs `measure_clip`, stages `measured.json`, and invokes `reconcile_delivery` before `publish()` | Pipeline execution; halts on mismatch without exposing bad deliverables |

## 2. Test Coverage Plan

| Test File | Target | What is verified |
|---|---|---|
| `tests/test_delivery.py` | `reconcile_delivery` | Refusal tests for all 7 clauses:<br>1. `test_delivery_refuses_duration_mismatch`<br>2. `test_delivery_refuses_geometry_mismatch`<br>3. `test_delivery_refuses_loudness_or_peak_violation`<br>4. `test_delivery_refuses_silence_math_mismatch`<br>5. `test_delivery_refuses_unplanned_cuts_or_missing_punch_ins`<br>6. `test_delivery_refuses_a_caption_claim_the_frames_do_not_show`<br>7. `test_delivery_refuses_face_tracking_claim_when_frames_lack_face` |
| `tests/test_artifact_bundle.py` | `ArtifactBundle` | 6-file atomic publication, refusal on missing `measured.json` |
| `tests/test_pipeline.py` | `run_pipeline` delivery | Delivery stage stages `measured.json` and skips if reconciliation refuses |
