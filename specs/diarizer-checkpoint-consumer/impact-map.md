# Caller Impact

- PyannoteDiarizer.__post_init__: dataclass construction via create_diarizer and
  direct adapter tests; enforce the already-named canonical model identity.
- PyannoteDiarizer.diarize: direct adapter/wire tests and dynamic Diarizer calls
  through ingest.attach_diarization -> pipeline.run_pipeline. Preserve named
  unavailable/invalid-output exceptions and exact exclusive conversion rules.
- create_diarizer: pipeline._build_and_run (CLI/durable/studio shared builder),
  test_pyannote_wire._wire. Signature/defaults unchanged.
- verified_checkpoint_access: existing models/ASR/visual consumers unchanged;
  adapter becomes an additional consumer, not a new verifier implementation.
- Test wiring: _wire and missing-extra test must supply actual temporary manifest
  and files rather than an empty directory. All original assertions retained.

Actual seven-pair Serena map and reference excerpts retained externally. Full
test_pyannote_checkpoint, test_pyannote_adapter, test_pyannote_wire, test_ingest,
test_pipeline and test_models modules plus exact canonical gate cover callers.
