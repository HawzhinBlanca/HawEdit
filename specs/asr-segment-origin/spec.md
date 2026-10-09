# EARS

WHEN routing completes, THE producer SHALL retain original LLM/CTC/confidence,
clock and reason. test_origin_retains_pre_correction_routing_inputs.

WHEN validator alignment succeeds, THE producer SHALL record actual validator
response and selected aligned content. test_origin_records_actual_validator_selection.

WHEN no validation is needed, THE producer SHALL not instantiate the validator.
test_origin_no_route_does_not_load_validator.

WHEN diagnostic correction fails, THE producer SHALL retain original content and
actual rejection; production SHALL stop. test_origin_refused_correction_retains_draft;
test_origin_production_refusal_does_not_claim_selected_correction.

WHEN native/worker generation succeeds, THE trace SHALL survive assembly and
immutable storage. test_origin_native_and_worker_parity;
test_origin_roundtrip_and_immutable_storage.

WHEN reading legacy data, THE system SHALL preserve absent/unknown provenance
and unchanged serialization/hash. test_origin_legacy_serialization_hash_unchanged.

WHEN trace data are malformed, foreign, incomplete or inconsistent, THE reader
SHALL refuse. test_origin_invalid_record_refuses; test_origin_selected_binding_refuses.

WHEN reporting routing, THE system SHALL replay ORIGINAL inputs, never selected
correction scores or duration/word count. test_origin_policy_replay_uses_draft_inputs.
