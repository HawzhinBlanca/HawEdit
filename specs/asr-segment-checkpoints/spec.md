# ASR Segment Checkpoint EARS

- WHEN an operation returns an admissible result, THE worker SHALL persist it
  atomically before beginning another operation. Test: test_checkpoint_survives_restart.
- WHEN an operation fails or persistence fails, THE worker SHALL halt without
  marking the operation complete. Tests: test_checkpoint_failure_is_not_cached,
  test_checkpoint_storage_failure_halts.
- WHEN a request resumes with identical source, audio, model, runtime and
  effective configuration, THE worker SHALL reuse only validated matching
  operations. Test: test_checkpoint_survives_restart.
- WHEN request/binding evidence changes or a saved record is malformed, THE
  worker SHALL refuse reuse and preserve evidence. Tests:
  test_checkpoint_refuses_changed_binding, test_checkpoint_refuses_damaged_record.
- WHEN a validator result or correction alignment is saved, THE worker SHALL
  keep it separate from the canonical draft, recompute the unchanged global
  routing decisions, and preserve first-failure halt. Test:
  test_checkpoint_keeps_draft_validator_and_alignment_separate.
- WHEN storage is unsafe or another worker owns the request, THE worker SHALL
  refuse rather than race or weaken filesystem policy. Tests:
  test_checkpoint_refuses_linked_storage, test_checkpoint_refuses_concurrent_writer.
- WHEN only checkpoints exist, THE system SHALL NOT treat them as raw transcript,
  stage completion or published media. Test: test_checkpoint_failure_is_not_cached.
