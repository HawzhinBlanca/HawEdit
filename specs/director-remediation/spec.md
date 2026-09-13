# Specification — Director Remediation

## Acceptance Criteria (EARS)

- **AC-1 (Zero-Skip Gate Invariant):** WHEN `pytest` executes across all test modules, THE test suite SHALL produce exactly 0 skipped tests (`skipped == 0`).
- **AC-2 (No Mock Data in Studio):** WHEN `web.py` is inspected or queried, THE studio SHALL NOT contain hardcoded `/media/ep29` endpoints or fake virality scores. Proof: `grep -c "/media/ep29" src/hawedit/web.py == 0`.
- **AC-3 (Studio Real Pipeline Execution):** WHEN a job is created in `JobManager`, THE studio SHALL invoke `run_pipeline` and stream actual stage progress rather than running `time.sleep()`.
- **AC-4 (VisualEditPlan as Render Contract):** WHEN `run_pipeline` prepares rendering, `VisualEditPlan` SHALL be generated before render execution, AND render SHALL consume the plan, AND `publish_delivery_bundle` SHALL refuse to publish if `VisualEditPlan` is missing.
- **AC-5 (Provenance Gate Enforcement):** WHEN `render_clip` is passed any non-source asset (image, audio, font), THE system SHALL verify a `.provenance.json` sidecar, AND IF absent, THE system SHALL raise a `ProvenanceViolation` error.
- **AC-6 (Critic Join Inspection):** WHEN `inspect_rendered_sequence` evaluates cut points, THE critic SHALL verify that no candidate clip boundary ends with a token in `DANGLING_CONJUNCTIONS_CKB` or starts mid-clause.
- **AC-7 (Excision by Default with Restarts):** WHEN silence planning runs, `excise_fillers` SHALL default to `True`, AND repeated n-grams within 2.0 seconds and truncated false starts SHALL be identified and excised.
- **AC-8 (Active-Speaker Face Share):** WHEN `ClipMeasurement` is calculated, THE system SHALL compute `speaking_face_share` across frames where diarization confirms active speech, AND delivery in deliverable profile SHALL enforce `speaking_face_share >= 0.98`.
- **AC-9 (Kurdish Caption RTL Order):** WHEN Kurdish subtitle events are emitted, THE displayed word tokens SHALL maintain identical relative reading order as the input words (e.g. "کاک مەسعود").
