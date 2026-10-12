# Fast Refusal EARS

| Criterion | Named Test |
| --- | --- |
| WHEN the physical source has zero bytes, THE ingester SHALL refuse before encoder discovery and SHALL NOT create stage work. | test_empty_ingest_refuses_before_decoder_discovery |
| WHEN the encoder executable cannot be launched, THE capability probe SHALL return unavailable without claiming a successful encode. | test_missing_encoder_executable_is_unavailable |
| WHEN the real encoder cannot complete the bounded probe, THE renderer SHALL preserve unavailable capability and explicit-request refusal. | test_encoder_availability_is_decided_by_a_real_encode_not_by_the_listing; test_an_unavailable_encoder_raises_instead_of_falling_back |
| WHEN valid media and available encoders are used, THE system SHALL retain measured Stage0 outputs and repeatable render evidence. | test_ingest_produces_every_stage_0_artifact; test_two_renders_of_one_edit_agree |
