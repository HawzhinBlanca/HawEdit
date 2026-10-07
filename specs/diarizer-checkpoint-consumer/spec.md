# EARS

- DC1: WHEN a noncanonical model identity is supplied, THE adapter SHALL refuse
  construction rather than use a fixed Community-1 revision for another model.
  Test: test_diarizer_refuses_noncanonical_model_identity.
- DC2: WHEN either checkpoint path contains missing/changed/extra/untrusted bytes,
  THE adapter SHALL refuse before importing or invoking the inference dependency.
  Test: test_diarizer_rejects_unverified_explicit_checkpoint_before_loading.
- DC3: WHEN a verified explicit or default checkpoint is consumed, THE adapter
  SHALL hold the publisher-coordinating reader lock from dependency import through
  load, device placement, inference and exclusive result conversion.
  Test: test_diarizer_holds_real_checkpoint_lock_through_all_consumer_stages.
- DC4: WHEN a consumer fails, THE adapter SHALL preserve its named refusal and
  release the reader lock without claiming a successful diarization.
  Test: test_diarizer_releases_checkpoint_lock_after_consumer_failure.
- DC5: WHEN a retained checkpoint changes before a later invocation, THE adapter
  SHALL reverify bytes and refuse rather than reuse prior availability evidence.
  Test: test_diarizer_reverifies_checkpoint_on_every_invocation.
- DC6: WHEN the inference extra is absent after byte validation, THE adapter SHALL
  name hawedit[diarization]; exclusive-output and attachment invariants SHALL
  remain unchanged. Tests: test_missing_pyannote_is_reported_as_a_missing_extra,
  existing test_pyannote_wire and test_ingest modules.
