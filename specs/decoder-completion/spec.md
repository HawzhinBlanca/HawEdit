# EARS

- C1: WHEN canonical decoding returns without observed natural EOS, THE backend
  SHALL refuse before alignment. Tests: test_completion_observer_refuses_non_eos_or_malformed_observation,
  test_alignable_repetition_stop_is_refused_before_alignment.
- C2: WHEN a supported decoder completes naturally, THE observer SHALL preserve
  exact model arguments and returned output. Test: test_completion_observer_preserves_natural_eos_output.
- C3: WHEN observation fails or its bindings/configuration change, THE observer
  SHALL refuse and restore temporary model/method bindings without masking the
  original cause. Tests: test_completion_observer_restores_after_exception,
  test_completion_observer_refuses_configuration_replacement,
  test_completion_observer_cleanup_does_not_mask_removed_method_refusal.
- C4: WHEN requests overlap, THE observer SHALL serialize its temporary bindings.
  Test: test_completion_observer_serializes_and_restores_concurrent_contexts.
- C5: WHEN a canonical producer encounters an existing raw transcript without
  matching admission provenance, THE store SHALL refuse before inference and
  preserve historical bytes. Tests: test_required_admission_policy_refuses_legacy_cache,
  test_pipeline_refuses_legacy_admission_before_inference.
- C6: WHEN a fresh policy-bound transcript is requested again with identical
  input/producer/source/policy, THE store SHALL verify integrity and reuse it.
  Tests: test_matching_admission_policy_reuses_verified_cache,
  test_pipeline_reuses_matching_admission_policy.
- C7: WHEN an incomplete decode occurs in production, THE worker SHALL halt
  before later segments, refinement or transcript publication. Test:
  test_incomplete_decode_stops_worker_before_later_segments.

Natural completion is necessary, not a native fidelity or publication verdict.
