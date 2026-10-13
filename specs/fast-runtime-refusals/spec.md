# Fast Refusal EARS

| Criterion | Named Test |
| --- | --- |
| WHEN the physical source has zero bytes, THE ingester SHALL refuse before encoder discovery and SHALL NOT create stage work. | test_empty_ingest_refuses_before_decoder_discovery |
| WHEN the encoder executable cannot be launched, THE capability probe SHALL return unavailable without claiming a successful encode. | test_missing_encoder_executable_is_unavailable |
| WHEN the real encoder cannot complete the bounded probe, THE renderer SHALL preserve unavailable capability and explicit-request refusal. | test_encoder_availability_is_decided_by_a_real_encode_not_by_the_listing; test_an_unavailable_encoder_raises_instead_of_falling_back |
| WHEN valid media and available encoders are used, THE system SHALL retain measured Stage0 outputs and repeatable render evidence. | test_ingest_produces_every_stage_0_artifact; test_two_renders_of_one_edit_agree |
| WHEN a formerly unavailable executable becomes a genuine working encoder at the same path, THE capability probe SHALL observe the new real encode rather than return a stale unavailable result. | test_encoder_recovers_when_real_executable_appears |
| WHEN a physical ISO-media ftyp header cannot fit within its source bytes, THE ingester SHALL refuse before decoder discovery or work creation. | test_truncated_iso_header_refuses_before_decoder_discovery |
| WHEN the effective ingest timeout is malformed, non-finite, nonpositive or exceeds43200s, THE runner SHALL refuse before launching its child and identify the invalid setting. | test_ingest_invalid_timeout_setting_refuses_before_real_launch; test_ingest_invalid_default_timeout_refuses_before_real_launch |
| WHEN a genuine executable launch fails, THE runner SHALL raise contextual IngestError and retain the original OS error as its cause. | test_ingest_missing_executable_has_contextual_refusal |
| WHEN extraction cannot launch its decoder, THE ingester SHALL remove private staging files and publish neither output nor provenance. | test_ingest_launch_refusal_preserves_atomic_output |
| WHEN the override is absent, empty or a valid finite positive deadline, THE runner SHALL execute the real child and retain its actual output. | test_ingest_valid_timeout_retains_actual_child_result |
