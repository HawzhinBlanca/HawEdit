# Specification — speaker-boundary-fusion

Parent: `BLUEPRINT.md` §3 Stage 0 and Stage 5; true-10/10 AC-9.

## Acceptance criteria

1. **WHEN** no diarization producer is enabled, **THE system SHALL** retain the base ingest
   artifacts and report diarization as a named skipped stage rather than an empty turn set.
2. **WHEN** an enabled diarization producer returns valid exclusive turns, **THE system SHALL**
   store a deterministic media-bounded tuple and report the exact turn and speaker counts.
3. **WHEN** an enabled producer raises its declared operational error, **THE system SHALL** retain
   base ingest, serialize a bounded structured failure, and continue independent downstream work.
4. **WHEN** producer output is overlapping, out of range, negative, non-segment, or otherwise
   schema-invalid, **THE system SHALL** refuse it before boundary fusion.
5. **WHEN** the first and last selected anchors fall inside exclusive turns, **THE system SHALL**
   pass those turns' measured start and end into Stage 5 boundary fusion.
6. **WHEN** an anchor lies in a diarization gap, **THE system SHALL** omit that speaker signal
   rather than selecting a nearby or unrelated turn.
7. **WHEN** diarization did not successfully run, **THE system SHALL NOT** call the overall run
   complete even if every other stage produced an artifact.
8. **WHEN** diarization succeeds but active-speaker-to-face association has not been measured,
   **THE system SHALL** retain the `FACE_TRACKED`/`STATIC_CENTRE` labels and SHALL NOT claim
   `SPEAKER_TRACKED`.

## Test mapping

- AC 1–4: named tests in `tests/test_ingest.py` and `tests/test_pipeline.py`.
- AC 5–6: named tests in `tests/test_diarization.py` and `tests/test_pipeline.py`.
- AC 7: `tests/test_pipeline.py` completeness mutation tests.
- AC 8: existing `tests/test_reframe.py`, `tests/test_render.py`, plus a non-claim assertion in
  the pipeline integration test.

